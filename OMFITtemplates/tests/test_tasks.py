"""Task lifecycle regressions without a display, network, or live project."""
from pathlib import Path
import queue
import shutil
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import weakref

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'LIB'))
from OMFITlib_template_tasks import BackgroundTasks
from OMFITlib_template_ui import TemplateManager
from OMFITlib_template_manager_ui import ManagerUpdateUI
from OMFITlib_template_session import OMFITSession
from OMFITlib_template_live import Prepared


def outcome(tasks, blocked=()):
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        try:
            return tasks.next_event(blocked)
        except queue.Empty:
            time.sleep(.001)
    raise AssertionError('Worker did not deliver an outcome')


def headless_ui():
    app = object.__new__(TemplateManager)
    app.alive, app.close_requested, app.busy = True, False, True
    app.tasks = BackgroundTasks()
    app.window = SimpleNamespace(after=Mock(return_value='next-poll'))
    app.status = SimpleNamespace(set=Mock())
    app._finish_progress = Mock()
    app._show_progress = Mock()
    app._set_busy = lambda value: setattr(app, 'busy', value)
    app._error = Mock()
    app._log = Mock()
    return app


class TaskLifecycleTest(unittest.TestCase):
    def staged_result(self):
        # Exercise the real cleanup method without a network/template fixture.
        result = object.__new__(Prepared)
        result.path = Path(tempfile.mkdtemp(prefix='omfit-task-test-'))
        result._cleanup = weakref.finalize(result, shutil.rmtree, str(result.path), True)
        self.addCleanup(result.discard)
        return result

    def test_worker_abort_delivers_completion_instead_of_leaving_busy(self):
        app = headless_ui()
        abort = KeyboardInterrupt('worker aborted')
        def work():
            raise abort
        app.tasks.start('foreground', work)
        event = outcome(app.tasks)
        self.assertIs(event.error, abort)
        accepted, cancelled = app.tasks.accept(event)
        self.assertTrue(accepted)
        app._task_event(event, cancelled)
        self.assertFalse(app.busy)
        self.assertIn('KeyboardInterrupt', str(app._error.call_args.args[0]))

    def test_cancel_after_completion_suppresses_follow_on_action(self):
        app = headless_ui()
        success = Mock()
        cancel = app.tasks.start('foreground', lambda: 'downloaded', success)
        event = outcome(app.tasks)
        cancel.set()
        accepted, cancelled = app.tasks.accept(event)
        self.assertTrue(accepted and cancelled)
        app._task_event(event, cancelled)
        success.assert_not_called()
        self.assertFalse(app.busy)

    def test_cancelled_unclaimed_preparation_is_disposed(self):
        app = headless_ui()
        prepared = self.staged_result()
        callback = Mock()
        cancel = app.tasks.start('foreground', lambda: prepared, callback, dispose=Prepared.discard)
        event = outcome(app.tasks)
        cancel.set()
        accepted, cancelled = app.tasks.accept(event)
        app._task_event(event, cancelled)
        self.assertFalse(prepared.path.exists())
        callback.assert_not_called()

    def test_stale_preparation_is_disposed(self):
        tasks = BackgroundTasks()
        prepared = self.staged_result()
        tasks.start('preview', lambda: prepared, dispose=Prepared.discard)
        stale = outcome(tasks)
        tasks.invalidate('preview')
        self.assertEqual(tasks.accept(stale), (False, False))
        self.assertFalse(prepared.path.exists())

    def test_close_disposes_queued_preparation(self):
        tasks = BackgroundTasks()
        prepared = self.staged_result()
        tasks.start('preview', lambda: prepared, dispose=Prepared.discard)
        event = outcome(tasks)
        tasks._completed.append(event)
        tasks.close()
        self.assertFalse(prepared.path.exists())

    def test_cleanup_failure_cannot_skip_other_results_during_close(self):
        tasks = BackgroundTasks()
        prepared = self.staged_result()
        for channel, result, dispose in (
                ('first', 'broken', Mock(side_effect=KeyboardInterrupt('cleanup interrupted'))),
                ('second', prepared, Prepared.discard)):
            tasks.start(channel, lambda value=result: value, dispose=dispose)
            event = outcome(tasks, blocked=('first',) if channel == 'second' else ())
            tasks._completed.append(event)
        tasks.close()
        self.assertFalse(prepared.path.exists())
        self.assertEqual(tasks.take_disposal_errors(), ('KeyboardInterrupt: cleanup interrupted',))
        self.assertEqual(tasks.take_disposal_errors(), ())

    def test_cleanup_failure_does_not_change_new_task_ownership(self):
        tasks = BackgroundTasks()
        tasks.start('preview', lambda: 'old', dispose=Mock(side_effect=OSError('locked')))
        stale = outcome(tasks)
        tasks.start('preview', lambda: 'new')
        self.assertEqual(tasks.accept(stale), (False, False))
        current = outcome(tasks)
        self.assertEqual(current.result, 'new')
        self.assertEqual(tasks.accept(current), (True, False))
        self.assertEqual(tasks.take_disposal_errors(), ('OSError: locked',))

    def test_late_preparation_after_close_is_disposed(self):
        tasks = BackgroundTasks()
        prepared = self.staged_result()
        release, disposed = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        def work():
            release.wait(2)
            return prepared
        def dispose(result):
            result.discard()
            disposed.set()
        tasks.start('preview', work, dispose=dispose)
        tasks.close()
        release.set()
        self.assertTrue(disposed.wait(2))
        self.assertFalse(prepared.path.exists())

    def test_delivered_preparation_survives_controller_close(self):
        app = headless_ui()
        prepared = self.staged_result()
        session_owned = []
        app.tasks.start('foreground', lambda: prepared, session_owned.append, dispose=Prepared.discard)
        event = outcome(app.tasks)
        accepted, cancelled = app.tasks.accept(event)
        app._task_event(event, cancelled)
        app.tasks.close()
        self.assertIs(session_owned[0], prepared)
        self.assertTrue(prepared.path.exists())

    def test_cancel_after_commit_still_delivers_receipt(self):
        app = headless_ui()
        callback = Mock()
        cancel = app.tasks.start('foreground', lambda: 'https://example.test/releases/v1', callback,
                                 receipt='Published: ')
        event = outcome(app.tasks)
        cancel.set()
        accepted, cancelled = app.tasks.accept(event)
        app._task_event(event, cancelled)
        callback.assert_called_once_with(event.result)
        app.status.set.assert_called_with('Published: ' + event.result)
        app._log.assert_called_with('Published: ' + event.result)

    def test_close_after_commit_logs_receipt_without_follow_on_action(self):
        app = headless_ui()
        app.close_requested = True
        app.close = Mock()
        callback = Mock()
        app.tasks.start('foreground', lambda: '/installed/v1', callback, receipt='Installed: ')
        event = outcome(app.tasks)
        accepted, cancelled = app.tasks.accept(event)
        app._task_event(event, cancelled)
        app._log.assert_called_once_with('Installed: /installed/v1')
        callback.assert_not_called()
        app.close.assert_called_once()

    def test_cancel_after_package_build_preserves_path_without_upload(self):
        app = headless_ui()
        app.cancel = threading.Event()
        app.cancel.set()
        app._prepare_upload = Mock()
        app._published = Mock()
        app._package_built('/templates/v1.zip')
        self.assertEqual(app.package_path, '/templates/v1.zip')
        app._prepare_upload.assert_not_called()
        app._published.assert_not_called()

    def test_cancel_after_install_reports_path_without_version_switch(self):
        app = headless_ui()
        app.cancel = threading.Event()
        app.cancel.set()
        app._save_preferences = Mock()
        app._manager_installed('/installed/v1')
        app._save_preferences.assert_not_called()
        self.assertIn('/installed/v1', app.status.set.call_args.args[0])

    def test_replaced_channel_ignores_already_queued_old_outcome(self):
        tasks = BackgroundTasks()
        tasks.start('manager-check', lambda: 'old')
        stale = outcome(tasks)
        tasks.start('manager-check', lambda: 'new')
        self.assertEqual(tasks.accept(stale), (False, False))
        current = outcome(tasks)
        self.assertEqual(current.result, 'new')
        self.assertEqual(tasks.accept(current), (True, False))

    def test_cancellation_does_not_hide_a_real_worker_failure(self):
        app = headless_ui()
        failure = OSError('rollback failed')
        def work():
            raise failure
        cancel = app.tasks.start('foreground', work)
        event = outcome(app.tasks)
        cancel.set()
        accepted, cancelled = app.tasks.accept(event)
        app._task_event(event, cancelled)
        app._error.assert_called_once_with(failure)
        self.assertFalse(app.busy)

    def test_close_waits_for_completion_then_closes_without_success_callback(self):
        app = headless_ui()
        app.close_requested = True
        app.close = Mock()
        success = Mock()
        app.tasks.start('foreground', lambda: None, success)
        event = outcome(app.tasks)
        accepted, cancelled = app.tasks.accept(event)
        app._task_event(event, cancelled)
        app.close.assert_called_once_with()
        success.assert_not_called()
        self.assertFalse(app.busy)

    def test_blocked_login_does_not_block_foreground_completion(self):
        tasks = BackgroundTasks()
        tasks.start('login-check', lambda: 'user')
        login = outcome(tasks)
        # Return an existing event to the transport to control queue ordering.
        tasks._completed.append(login)
        tasks.start('foreground', lambda: 'done')
        event = outcome(tasks, blocked=('login-check',))
        self.assertEqual(event.channel, 'foreground')
        self.assertEqual(tasks.next_event().channel, 'login-check')

    def test_progress_is_coalesced_and_discarded_after_completion(self):
        tasks = BackgroundTasks()
        ready, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        def work():
            for number in range(10000):
                tasks.progress('copy', number, 10000)
            ready.set()
            release.wait(2)
        tasks.start('foreground', work)
        self.assertTrue(ready.wait(2))
        event = tasks.next_event()
        self.assertEqual((event.kind, event.done), ('progress', 9999))
        with self.assertRaises(queue.Empty):
            tasks.next_event()
        release.set()
        tasks.accept(outcome(tasks))
        with self.assertRaises(queue.Empty):
            tasks.next_event()

    def test_close_cancels_and_drops_late_worker(self):
        tasks = BackgroundTasks()
        release, finished = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        def work():
            release.wait(2)
            finished.set()
            return 'late'
        cancel = tasks.start('foreground', work)
        tasks.close()
        self.assertTrue(cancel.is_set())
        release.set()
        self.assertTrue(finished.wait(2))
        with self.assertRaises(queue.Empty):
            tasks.next_event()
        with self.assertRaises(RuntimeError):
            tasks.start('foreground', lambda: None)

    def test_failure_callback_cannot_disable_future_polling(self):
        app = headless_ui()
        def work():
            raise ValueError('download failed')
        app.tasks.start('foreground', work, failure=Mock(side_effect=RuntimeError('callback failed')))
        event = outcome(app.tasks)
        app.tasks._completed.append(event)
        app._poll()
        self.assertFalse(app.busy)
        app.window.after.assert_called_once_with(100, app._poll)
        self.assertEqual(str(app._error.call_args.args[0]), 'callback failed')

    def test_native_abort_in_callback_reschedules_before_propagating(self):
        app = headless_ui()
        app.tasks.start('foreground', lambda: None, Mock(side_effect=KeyboardInterrupt()))
        event = outcome(app.tasks)
        app.tasks._completed.append(event)
        with self.assertRaises(KeyboardInterrupt):
            app._poll()
        self.assertFalse(app.busy)
        app.window.after.assert_called_once_with(100, app._poll)

    def test_callback_queue_empty_is_reported_as_failure(self):
        app = headless_ui()
        error = queue.Empty('callback queue empty')
        app.tasks.start('foreground', lambda: None, Mock(side_effect=error))
        event = outcome(app.tasks)
        app.tasks._completed.append(event)
        app._poll()
        app._error.assert_called_once_with(error)
        app.window.after.assert_called_once_with(100, app._poll)

    def test_thread_start_failure_restores_idle(self):
        app = headless_ui()
        app.busy = False
        with patch('OMFITlib_template_tasks.threading.Thread.start', side_effect=RuntimeError('no threads')):
            with self.assertRaisesRegex(RuntimeError, 'no threads'):
                app._run('start', lambda: None, Mock())
        self.assertFalse(app.busy)

    def test_preference_failure_keeps_close_retryable_and_tasks_alive(self):
        for failure in (OSError('preferences temporary file locked'), KeyboardInterrupt()):
            with self.subTest(failure=type(failure).__name__):
                app = headless_ui()
                app.busy = False
                app.close_requested = True
                app._manager_auto_cancel = threading.Event()
                app._stop_login_check = Mock()
                app._save_preferences = Mock(side_effect=failure)
                app.window.destroy = Mock()
                with self.assertRaises(type(failure)) as raised:
                    app.close()
                self.assertIs(raised.exception, failure)
                self.assertTrue(app.alive)
                self.assertFalse(app.close_requested)
                app.window.destroy.assert_not_called()
                app.tasks.start('foreground', lambda: 'retry')
                event = outcome(app.tasks)
                self.assertEqual(app.tasks.accept(event), (True, False))

    def test_manager_switch_abort_restores_old_module_and_cancels_reopen(self):
        parent = SimpleNamespace(after=Mock(return_value='reopen'), after_cancel=Mock())
        app = SimpleNamespace(cancel=threading.Event(), _save_preferences=Mock(),
            window=SimpleNamespace(master=parent), session=Mock(), close=Mock(side_effect=KeyboardInterrupt()))
        with self.assertRaises(KeyboardInterrupt):
            ManagerUpdateUI._manager_installed(app, '/new')
        parent.after_cancel.assert_called_once_with('reopen')
        app.session.restore_manager.assert_called_once_with(app.session.replace_manager.return_value)

    def test_manager_reopen_abort_restores_old_module(self):
        parent = SimpleNamespace(after=Mock(return_value='reopen'), after_cancel=Mock())
        app = SimpleNamespace(cancel=threading.Event(), _save_preferences=Mock(),
            window=SimpleNamespace(master=parent), session=Mock(), close=Mock())
        app.session.reopen_manager.side_effect = KeyboardInterrupt()
        ManagerUpdateUI._manager_installed(app, '/new')
        callback = parent.after.call_args.args[1]
        with self.assertRaises(KeyboardInterrupt):
            callback()
        app.session.restore_manager.assert_called_once_with(app.session.replace_manager.return_value)

    def test_rollback_attempts_restore_even_if_callback_cancellation_fails(self):
        parent = SimpleNamespace(after=Mock(return_value='reopen'), after_cancel=Mock(side_effect=OSError('destroyed')))
        abort = KeyboardInterrupt()
        app = SimpleNamespace(cancel=threading.Event(), _save_preferences=Mock(),
            window=SimpleNamespace(master=parent), session=Mock(), close=Mock(side_effect=abort))
        with self.assertRaises(KeyboardInterrupt) as raised:
            ManagerUpdateUI._manager_installed(app, '/new')
        self.assertIs(raised.exception, abort)
        app.session.restore_manager.assert_called_once()
        self.assertEqual(abort.template_rollback_errors[0]['step'], 'manager reopen callback')

    def test_manager_module_assignment_abort_restores_partial_assignment(self):
        class Module(dict):
            def __init__(self, *args, **kwargs):
                super().__init__(SETTINGS={'MODULE': {'ID': 'OMFITtemplates'}}, GUIS={'main': object()})
        class NativeTree(dict):
            interrupt = True
            def __setitem__(self, key, value):
                super().__setitem__(key, value)
                if self.interrupt:
                    self.interrupt = False
                    raise KeyboardInterrupt()
        previous = Module()
        tree = NativeTree(OMFITtemplates=previous)
        with self.assertRaises(KeyboardInterrupt):
            OMFITSession(tree).replace_manager('/new')
        self.assertIs(tree['OMFITtemplates'], previous)

    def test_install_without_selected_manager_result_is_noop(self):
        ManagerUpdateUI._install_manager_update(SimpleNamespace(busy=False, manager_update_result=None))


if __name__ == '__main__':
    unittest.main()
