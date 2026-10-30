"""Real Tk lifecycle tests: scoped unbind and responsive, cancellable backoff."""
from pathlib import Path
import sys
import tkinter as tk
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'CGYRO_TGLF_scan/LIB'))
from OMFITlib_tk_callbacks import RetryWait, unbind_callback


class TkCallbacksTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.close)
        self.widget = tk.Toplevel(self.root)
        self.widget.update()
        self.errors = []
        self.root.report_callback_exception = lambda *args: self.errors.append(args)

    def close(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def handlers(self):
        self.calls = []
        return [self.widget.bind('<<Probe>>', lambda e, i=i: self.calls.append(i), add='+') for i in range(3)]

    def test_whitespace_binding_removes_only_target_and_is_idempotent(self):
        first, second, third = self.handlers()
        self.widget.bind('<<Probe>>', '\n'.join('  ' + s for s in self.widget.bind('<<Probe>>').splitlines()))
        with patch.object(self.widget, 'unbind', side_effect=AssertionError('legacy global unbind')):
            self.assertTrue(unbind_callback(self.widget, '<<Probe>>', second))
            self.assertFalse(unbind_callback(self.widget, '<<Probe>>', second))
        self.widget.event_generate('<<Probe>>')
        self.assertEqual(self.calls, [0, 2])
        self.assertFalse(self.widget.tk.call('info', 'commands', second))
        self.assertTrue(self.widget.tk.call('info', 'commands', first))
        self.assertTrue(self.widget.tk.call('info', 'commands', third))
        self.assertEqual(self.errors, [])

    def test_unknown_tcl_wrapper_keeps_live_command_and_other_callbacks(self):
        _, second, _ = self.handlers()
        script = self.widget.bind('<<Probe>>')
        lines = script.splitlines()
        self.widget.bind('<<Probe>>', '\n'.join('if {1} {' + line + '}' if second in line else line for line in lines))
        self.assertFalse(unbind_callback(self.widget, '<<Probe>>', second))
        self.widget.event_generate('<<Probe>>')
        self.assertEqual(self.calls, [0, 1, 2])
        self.assertEqual(self.errors, [])

    def test_residual_reference_prevents_deleting_shared_command(self):
        _, second, _ = self.handlers()
        script = self.widget.bind('<<Probe>>')
        self.widget.bind('<<Probe>>', script + '\n# keep ' + second)
        self.assertFalse(unbind_callback(self.widget, '<<Probe>>', second))
        self.assertEqual(self.widget.bind('<<Probe>>'), script + '\n# keep ' + second)

    def test_missing_and_destroyed_binding_are_safe(self):
        first, _, _ = self.handlers()
        before = self.widget.bind('<<Probe>>')
        self.assertFalse(unbind_callback(self.widget, '<<Probe>>', 'missing'))
        self.assertEqual(before, self.widget.bind('<<Probe>>'))
        self.widget.destroy()
        self.assertFalse(unbind_callback(self.widget, '<<Probe>>', first))

    def waiter(self):
        return RetryWait(SimpleNamespace(OMFITaux={'rootGUI': self.root}), 'test retry')

    def test_wait_dispatches_events_reuses_dialog_and_restores_grab(self):
        self.widget.grab_set()
        calls = []
        self.root.after(5, lambda: calls.append('timer'))
        with self.waiter() as retry, patch('OMFITlib_tk_callbacks.time.sleep', side_effect=AssertionError('Tk slept')):
            retry.wait(.03, 'one')
            self.assertEqual(calls, ['timer'])
            dialog = retry.dialog
            self.assertIs(self.root.grab_current(), self.widget)
            retry.wait(.01, 'two')
            self.assertIs(retry.dialog, dialog)
        self.assertFalse(dialog.winfo_exists())
        self.assertEqual(self.root.tk.call('after', 'info'), '')
        self.assertEqual(self.errors, [])

    def test_cancel_interrupts_long_backoff_and_cleans_timer(self):
        with self.waiter() as retry:
            self.root.after(5, retry.cancel)
            with self.assertRaises(KeyboardInterrupt):
                retry.wait(60, 'cancel')
        self.assertEqual(self.root.tk.call('after', 'info'), '')
        self.assertEqual(self.errors, [])

    def test_destroying_wait_dialog_interrupts_without_dangling_timer(self):
        with self.waiter() as retry:
            self.root.after(5, lambda: retry.dialog.destroy())
            with self.assertRaises(KeyboardInterrupt):
                retry.wait(60, 'destroy')
        self.assertEqual(self.root.tk.call('after', 'info'), '')
        self.assertEqual(self.errors, [])

    def test_destroying_parent_releases_nested_wait(self):
        with self.waiter() as retry:
            self.root.after(5, self.root.destroy)
            with self.assertRaises(KeyboardInterrupt):
                retry.wait(60, 'destroy parent')
        self.assertEqual(self.errors, [])

    def test_headless_wait_uses_timed_backoff_without_tk(self):
        with RetryWait(SimpleNamespace(), 'headless') as retry, patch('OMFITlib_tk_callbacks.time.sleep') as sleep:
            retry.wait(2, 'headless')
            sleep.assert_called_once_with(2)
            self.assertIsNone(retry.dialog)

    def test_cancel_before_first_wait_is_safe_and_does_not_sleep_or_open_dialog(self):
        for retry in (self.waiter(), RetryWait(SimpleNamespace(), 'headless')):
            with retry, patch('OMFITlib_tk_callbacks.time.sleep') as sleep:
                retry.cancel()
                retry.cancel()
                with self.assertRaises(KeyboardInterrupt):
                    retry.wait(60, 'already cancelled')
                sleep.assert_not_called()
                self.assertIsNone(retry.dialog)


if __name__ == '__main__':
    unittest.main()
