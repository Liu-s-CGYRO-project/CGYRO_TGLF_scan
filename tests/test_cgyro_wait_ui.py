"""Real Tk native-shaped wait panels: compact display, exact identity, cleanup."""
import ast
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import tkinter as tk
from tkinter import ttk
from tkinter.font import Font
import unittest
from unittest.mock import patch

from OMFITlib_cgyro_wait_ui import NativeWaitView
from OMFITlib_cgyro_run_state import linked_local_action

SOURCE = Path(__file__).resolve().parents[4] / 'OMFIT-source-ASIPP_unstable/omfit'


class NativeWaitViewTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.update_idletasks()
        self.addCleanup(self.close_root)
        self.errors = []
        self.root.report_callback_exception = lambda *error: self.errors.append(error)
        self.ui = SimpleNamespace(_aux={'rootGUI': self.root})
        self.markers = ('exact_job=10061984', 'exact_token=selected')
        self.command = '\n'.join(self.markers) + '\n' + 'a very long polling script\n' * 150

    def close_root(self):
        self.root.update_idletasks()
        self.root.destroy()

    def test_native_omfit_embedded_panel_keeps_progress_and_exact_job_stop_controls(self):
        source = SOURCE / 'omfit_classes/OMFITx.py'
        tree = ast.parse(source.read_text(encoding='utf-8'))
        native = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == '_system_unix')
        # Execute the unchanged native GUI construction block, including its
        # nested button row and update_idletasks/Map ordering.
        blocks = [node for node in ast.walk(native) if isinstance(node, ast.If) and node.body
                  and isinstance(node.body[0], ast.Try)
                  and any(isinstance(child, ast.Name) and child.id == 'fixedWidthDetailsText'
                          for child in ast.walk(node))]
        self.assertEqual(len(blocks), 1, 'Native wait panel contract changed')
        workflow = tk.Toplevel(self.root)
        workflow.geometry('800x180')  # Height left by an earlier workflow step.
        actions = []
        font_module = ModuleType('utils_widgets')
        font_module.OMFITfont = lambda **kw: 'TkFixedFont'
        namespace = dict(tk=tk, ttk=ttk, OMFITaux={'rootGUI': self.root, 'pythonRunWindows': [workflow]},
                         fixedWidthDetails=self.command, tkDetails=tk.StringVar(self.root, self.command),
                         tkMessage=tk.StringVar(self.root, 'Running remotely:'), progressFunction=lambda _: 0,
                         onKill=lambda: actions.append('native-kill'), onAbort=lambda: actions.append('native-abort'),
                         extraButtons={})
        with patch.dict(sys.modules, {'utils_widgets': font_module}), \
                linked_local_action(self.ui, 'selected', self.markers, lambda: actions.append('selected-job-only')), \
                NativeWaitView(self.ui, '10061984', self.markers) as view:
            exec(compile(ast.Module(body=blocks, type_ignores=[]), str(source), 'exec'), namespace)
            self.root.update()
            text, bar, buttons = namespace['fixedWidthDetailsText'], namespace['p'], namespace['frm'].winfo_children()
            self.assertEqual(int(text['height']), 3)
            self.assertEqual(str(bar['mode']), 'indeterminate')
            for widget in [bar] + buttons:
                self.assertTrue(widget.winfo_ismapped())
                self.assertLessEqual(widget.winfo_rooty() + widget.winfo_height(),
                                     workflow.winfo_rooty() + workflow.winfo_height())
            view.progress('CGYRO_WAIT|10061984|2|1|0\n')
            self.assertIn('排队 2，运行 1', text.get('1.0', '1.end'))
            buttons[0].invoke()
            self.assertEqual(actions, ['selected-job-only', 'native-kill'])
            buttons[-1].invoke()
            self.assertEqual(actions[-1], 'native-abort')
        self.assertFalse(self.root._cgyro_wait_views)
        self.assertFalse(self.root._cgyro_stop_handlers)
        self.assertFalse(self.errors)

    def panel(self, command=None):
        top = tk.Toplevel(self.root)
        frame = tk.Frame(top)
        frame.pack(fill='both', expand=True)
        tk.Label(frame, text='Running remotely:').pack()
        text = tk.Text(frame, height=10, width=80)
        text.pack()
        text.insert('1.0', self.command if command is None else command)
        text.configure(state='disabled')
        bar = ttk.Progressbar(frame, mode='determinate')
        bar.pack(fill='x')
        self.stops = []
        button = ttk.Button(frame, text='Kill local', command=lambda: self.stops.append('native-stop'))
        button.pack()
        self.root.update()
        return top, text, bar, button

    def test_progress_and_stop_visible_and_command_remains_available_to_exact_job_binding(self):
        with NativeWaitView(self.ui, '10061984', self.markers) as view:
            top, text, bar, button = self.panel()
            self.assertEqual(int(text.cget('height')), 3)
            self.assertEqual(str(bar.cget('mode')), 'indeterminate')
            self.assertTrue(text.tk.getboolean(text.tag_cget('cgyro_wait_command', 'elide')))
            self.assertTrue(all(marker in text.get('1.0', 'end') for marker in self.markers))
            self.assertGreater(bar.winfo_height(), 0)
            self.assertLessEqual(button.winfo_rooty() + button.winfo_height(), top.winfo_rooty() + top.winfo_height())
            view.progress('CGYRO_WAIT|10061984|3|1|0\n')
            self.assertIn('排队 3，运行 1', text.get('1.0', '1.end'))
            self.assertEqual(text.get('3.0', 'end-1c'), self.command)
            text.edit_modified(False)
            view.progress('CGYRO_WAIT|10061984|3|1|0\n')
            view.progress('CGYRO_WAIT|10061984|3|1|0\n[heartbeat] still queued\n')
            self.assertFalse(text.edit_modified(), 'Unchanged state must not redraw the Text on every native poll')
            button.invoke()
            self.assertEqual(self.stops, ['native-stop'])
        self.assertEqual(text.get('1.0', 'end-1c'), self.command)
        self.assertEqual(int(text.cget('height')), 10)
        self.assertFalse(self.root._cgyro_wait_views)
        self.assertFalse(self.errors)

    def test_other_jobs_and_malformed_output_do_not_change_this_panel(self):
        with NativeWaitView(self.ui, '10061984', self.markers) as view:
            _, text, _, _ = self.panel()
            _, other, other_bar, _ = self.panel('exact_job=999\nexact_token=other')
            initial = text.get('1.0', '1.end')
            view.progress('CGYRO_WAIT|999|1|2|0\nCGYRO_WAIT|10061984|x|2|0\n')
            self.assertEqual(text.get('1.0', '1.end'), initial)
            self.assertEqual(int(other.cget('height')), 10)
            self.assertEqual(str(other_bar.cget('mode')), 'determinate')
            view.progress('CGYRO_WAIT_LEFT|10061984\n')
            self.assertIn('已离开队列，等待收集校验', text.get('1.0', '1.end'))
            self.assertNotIn('成功', text.get('1.0', '1.end'))
        self.assertFalse(self.errors)

    def test_compacting_panel_keeps_its_selected_cjk_font_during_and_after_wait(self):
        _, text, _, _ = self.panel()
        font = Font(self.root, name='SelectedCjkFont', family='Noto Sans CJK SC', size=13)
        text.configure(font=font)
        before = str(text.cget('font'))
        with NativeWaitView(self.ui, '10061984', self.markers) as view:
            view.attach(text)
            view.progress('CGYRO_WAIT|10061984|0|1|0\n')
            self.assertEqual(str(text.cget('font')), before)
            self.assertEqual(int(text.cget('height')), 3)
        self.assertEqual(str(text.cget('font')), before)
        self.assertEqual(int(text.cget('height')), 10)

    def test_native_destruction_and_failed_connection_always_remove_scoped_handler(self):
        with self.assertRaisesRegex(OSError, 'connection'):
            with NativeWaitView(self.ui, '10061984', self.markers) as view:
                top, _, _, _ = self.panel()
                top.destroy()
                view.progress('CGYRO_WAIT|10061984|0|1|0\n')
                raise OSError('connection lost')
        self.assertFalse(self.root._cgyro_wait_views)
        _, text, _, _ = self.panel()
        self.assertEqual(int(text.cget('height')), 10)
        self.assertFalse(self.errors)

    def test_headless_wait_retains_native_callback_contract(self):
        view = NativeWaitView(SimpleNamespace(), '10061984', self.markers)
        view.root = None
        with view:
            self.assertEqual(view.progress('CGYRO_WAIT|10061984|0|1|0'), 0)


if __name__ == '__main__':
    unittest.main()
