"""Startup stays interactive while optional discovery is slow or unavailable.

Real Tk widgets and the real worker event transport run here. Downloads, live
OMFIT objects and GitHub are replaced only at their external boundaries.
"""
from contextlib import ExitStack
from pathlib import Path
import sys
import tempfile
import threading
import time
import tkinter as tk
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import warnings

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'LIB'))
import OMFITlib_gui_fonts as fonts
from OMFITlib_template_ui import TemplateManager
from OMFITlib_template_github import GitHub, GitHubNetworkError
from OMFITlib_template_service import Cancelled, list_library
from OMFITlib_template_archive import TemplateError


class ManagerStartupTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.root = tk.Tk()
        self.root.withdraw()
        self.errors = []
        self.root.report_callback_exception = lambda *error: self.errors.append(error)
        self.scope = ExitStack()
        self.addCleanup(self.scope.close)
        self.gates = []
        self.app = None
        self.addCleanup(self.cleanup)
        self.scope.enter_context(patch.object(fonts, 'ensure_fonts', side_effect=AssertionError('startup downloaded a font')))
        self.scope.enter_context(patch.object(fonts, 'cached_fonts', side_effect=AssertionError('Tk verified the font cache')))
        self.scope.enter_context(patch('OMFITlib_template_ui.cached_fonts', return_value=None))
        self.scope.enter_context(patch('OMFITlib_template_ui.messagebox.showerror',
                                      side_effect=lambda *args, **kw: self.errors.append(args)))

    def cleanup(self):
        if self.app is not None and self.app.alive:
            self.app.close()
        for gate in self.gates:
            gate.set()
        try:
            self.root.destroy()
        except tk.TclError:
            pass
        self.assertFalse(self.errors)

    def create(self, session=None):
        self.app = TemplateManager(self.root, preferences=self.directory / 'settings.json',
                                   library=self.directory / 'library', session=session)
        self.root.after_cancel(self.app._refresh_after)
        self.app._refresh_after = None
        return self.app

    def pump_until(self, predicate):
        deadline = time.monotonic() + 5
        while not predicate() and time.monotonic() < deadline:
            self.root.update()
            time.sleep(.01)
        self.assertTrue(predicate(), 'background test operation did not finish')

    def slow_client(self):
        started, release = threading.Event(), threading.Event()
        self.gates.append(release)
        client = Mock()
        def connect():
            self.assertIsNot(threading.current_thread(), threading.main_thread())
            started.set()
            release.wait(5)
            return dict(repository='team/old', login='old-user', private=False,
                        default_branch='main', empty=False)
        client.connect.side_effect = connect
        client.list_releases.return_value = ([], [])
        factory = self.scope.enter_context(patch('OMFITlib_template_ui.GitHub', return_value=client))
        return client, factory, started, release

    def test_cold_start_does_not_download_fonts_or_disable_controls_and_starts_once(self):
        client, factory, started, release = self.slow_client()
        version_started = threading.Event()
        def check(client):
            self.assertIsNot(threading.current_thread(), threading.main_thread())
            version_started.set()
            return dict(available=False, latest='', packages={})
        self.scope.enter_context(patch('OMFITlib_template_manager_ui.GitHub'))
        self.scope.enter_context(patch('OMFITlib_template_manager_ui.check_manager_update', side_effect=check))
        app = self.create()
        self.assertEqual(len(app.tabs.tabs()), 4)
        app._startup()
        app._startup()
        self.assertTrue(started.wait(2))
        self.assertTrue(version_started.wait(2))
        self.assertFalse(app.busy)
        self.assertFalse(app.proxy_settings_button.instate(['disabled']))
        app.tabs.select(3)
        app.search.set('still editable')
        self.assertEqual(app.tabs.index(app.tabs.select()), 3)
        factory.assert_called_once()
        self.assertEqual(factory.call_args.kwargs['discovery_timeout'], 20)
        # Closing discovery does not wait for a socket timeout, and its late
        # completion cannot access widgets that have already been destroyed.
        app.close()
        self.assertFalse(app.alive)
        self.assertTrue(factory.call_args.kwargs['cancel'].is_set())
        release.set()

    def test_repository_and_proxy_edits_discard_late_startup_results(self):
        app = self.create()
        for variable, value in ((app.repository, 'team/new'), (app.proxy_mode, '不使用代理')):
            with self.subTest(variable=str(variable)):
                client, factory, started, release = self.slow_client()
                with patch.object(app, '_loaded') as loaded:
                    app._connect(automatic=True)
                    self.assertTrue(started.wait(2))
                    variable.set(value)
                    self.assertTrue(factory.call_args.kwargs['cancel'].is_set())
                    release.set()
                    self.pump_until(lambda: client.list_releases.called)
                    app._poll()
                    loaded.assert_not_called()
                    self.assertEqual(app.github_login, '')

    def test_explicit_action_owns_selection_after_startup_request(self):
        client, factory, started, release = self.slow_client()
        app = self.create()
        app._connect(automatic=True)
        self.assertTrue(started.wait(2))
        results = []
        app._run('explicit operation', lambda: 'new selection', results.append)
        self.assertTrue(factory.call_args.kwargs['cancel'].is_set())
        release.set()
        self.pump_until(lambda: not app.busy)
        self.assertEqual(results, ['new selection'])
        self.assertEqual(app.github_login, '')

    def test_slow_local_startup_can_be_closed_without_waiting(self):
        app = self.create()
        # Set the initial source without triggering an explicit foreground read.
        app.busy = True
        app.view_source.set('本地模板库')
        app.busy = False
        started, release = threading.Event(), threading.Event()
        self.gates.append(release)
        def load(directory, cancel=None):
            self.assertIsNot(threading.current_thread(), threading.main_thread())
            started.set()
            release.wait(5)
            self.assertTrue(cancel.is_set())
            return [], []
        with patch('OMFITlib_template_ui.list_library', side_effect=load):
            app.refresh(automatic=True)
            self.assertTrue(started.wait(2))
            self.assertFalse(app.busy)
            app.close()
            self.assertFalse(app.alive)
            release.set()

    def test_automatic_update_only_reads_version_metadata(self):
        session = SimpleNamespace(project_path=lambda: '', can_undo_live=lambda: False,
                                  manager_sources=Mock(side_effect=AssertionError('automatic live OMFIT access')))
        app = self.create(session=session)
        report = dict(available=True, latest='99.0.0', incremental={'asset_id': 1}, packages={})
        with patch('OMFITlib_template_manager_ui.GitHub'), \
                patch('OMFITlib_template_manager_ui.check_manager_update', return_value=report), \
                patch('OMFITlib_template_manager_ui.plan_incremental') as plan:
            app._check_manager_update(automatic=True)
            self.pump_until(lambda: app.manager_update_result is not None)
            plan.assert_not_called()
        session.manager_sources.assert_not_called()
        self.assertFalse(app.busy)

    def test_explicit_local_scan_observes_close_cancellation(self):
        app = self.create()
        app.busy = True
        app.view_source.set('本地模板库')
        app.busy = False
        started = threading.Event()
        seen = []
        def load(directory, cancel=None):
            seen.append(cancel)
            started.set()
            if cancel.wait(5):
                raise Cancelled('cancelled library scan')
            raise AssertionError('close did not cancel the directory scan')
        with patch('OMFITlib_template_ui.list_library', side_effect=load):
            app.refresh()
            self.assertTrue(started.wait(2))
            self.assertTrue(app.busy)
            self.assertEqual(seen, [app.cancel])
            app.close()
            self.assertTrue(seen[0].is_set())
            self.pump_until(lambda: not app.alive)

    def test_verified_font_is_applied_in_main_thread_without_rebuilding_pages(self):
        app = self.create()
        tabs = tuple(app.tabs.tabs())
        seen = []
        with patch('OMFITlib_template_ui.font_family', side_effect=lambda *a, **kw: seen.append(threading.current_thread())), \
                patch('OMFITlib_template_ui.configure_window_fonts') as configure:
            app._startup_fonts({fonts.FONT_FILENAME: '/verified/cache'})
            self.assertEqual(seen, [threading.main_thread()])
            configure.assert_called_once_with(self.root, refresh=True)
            self.assertFalse(self.root._project_cjk_defer_load)
            self.assertEqual(tuple(app.tabs.tabs()), tabs)
        self.root._project_cjk_defer_load = True

    def test_disappeared_verified_font_never_hashes_or_downloads_on_main_thread(self):
        app = self.create()
        with patch.object(fonts, '_register', side_effect=OSError('cache was removed')) as register, \
                warnings.catch_warnings():
            warnings.simplefilter('ignore', RuntimeWarning)
            app._startup_fonts({fonts.FONT_FILENAME: '/removed/font'})
            register.assert_called_once_with('/removed/font', retry=True)
            self.assertFalse(fonts.font_status(self.root)['active'])
            self.assertEqual(len(app.tabs.tabs()), 4)


class DiscoveryBudgetTest(unittest.TestCase):
    def test_optional_discovery_does_not_retry_and_uses_remaining_budget(self):
        with patch('OMFITlib_template_github.monotonic', side_effect=[100, 105, 121]):
            client = GitHub('team/project', token='', discovery_timeout=20)
            client.opener = Mock()
            client.opener.open.side_effect = TimeoutError('slow route')
            with self.assertRaises(GitHubNetworkError):
                client._json(client.base)
            self.assertEqual(client.opener.open.call_count, 1)
            self.assertEqual(client.opener.open.call_args.kwargs['timeout'], 15)
            with self.assertRaisesRegex(TemplateError, '自动发现已超时'):
                client._json(client.base)
            self.assertEqual(client.opener.open.call_count, 1)

    def test_local_library_cancel_stops_before_opening_another_package(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'anything.omfittpl.zip'
            path.write_bytes(b'not opened')
            cancel = threading.Event()
            cancel.set()
            with patch('OMFITlib_template_service.Template', side_effect=AssertionError('opened cancelled package')):
                with self.assertRaises(Cancelled):
                    list_library(folder, cancel=cancel)


if __name__ == '__main__':
    unittest.main()
