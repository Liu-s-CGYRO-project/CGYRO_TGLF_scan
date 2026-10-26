"""Preparing a scan must not render the hidden result/archive page."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO.parents[2] / 'OMFIT-source-ASIPP_unstable/omfit'


class Notebook:
    def __init__(self):
        self.selected, self.callback = '0', None

    def select(self, index=None):
        if index is not None:
            self.selected = str(index)
        return self.selected

    def index(self, selected):
        return int(selected)

    def bind(self, event, callback, **kwargs):
        self.callback = callback


class Frame:
    def __init__(self, notebook):
        self.master = notebook


class ScanRefreshTests(unittest.TestCase):
    def setUp(self):
        source = REPO / 'CGYRO_TGLF_scan/LIB/OMFITlib_workbench_cgyro_ui.py'
        tree = ast.parse(source.read_text(encoding='utf-8-sig'))
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'CgyroPage')
        cls.body = [node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name in (
            'render_cgyro', 'render_cgyro_results', 'cgyro_main_tab_changed')]
        constants = [node for node in tree.body if isinstance(node, ast.Assign)
                     and any(isinstance(target, ast.Name) and target.id == 'CGYRO_MAIN_TABS' for target in node.targets)]
        self.browser, self.queue = Mock(), Mock(return_value=[])
        namespace = dict(tk=SimpleNamespace(Misc=Frame, TclError=RuntimeError),
            ttk=SimpleNamespace(Notebook=Notebook), MODULES={'cgyro': ('CGYRO_scan',)},
            read=lambda root, path: root[path[0]], ResultBrowser=self.browser, queue_records=self.queue)
        exec(compile(ast.Module(body=constants + [cls], type_ignores=[]), str(source), 'exec'), namespace)
        self.page = namespace['CgyroPage']()
        self.notebook = Notebook()
        self.page.root, self.page.settings, self.page.cgyro_rows = {'CGYRO_scan': {}}, {}, []
        self.page.ui = SimpleNamespace(Tab=Mock(), UpdateGUI=Mock(),
                                      _aux={'parentGUI': Frame(self.notebook)})
        self.page.actions = SimpleNamespace(continue_cgyro=Mock())
        for name in ('compound', 'show_message', 'render_cgyro_parameters', 'render_cgyro_recovery',
                     'render_cgyro_cleanup', 'nav', 'label'):
            setattr(self.page, name, Mock())

    def test_repeated_input_and_parameter_edits_do_not_visit_result_records(self):
        for selected in ('input', 'parameters'):
            self.page.settings['cgyro_main_tab'] = selected
            for _ in range(5):
                self.page.render_cgyro()
        self.queue.assert_not_called()
        self.browser.assert_not_called()

    def test_explicit_result_tab_renders_and_restores_selection(self):
        self.page.settings['cgyro_main_tab'] = 'results'
        self.page.render_cgyro()
        self.queue.assert_called_once_with(self.page.root['CGYRO_scan'])
        self.browser.return_value.render.assert_called_once_with(title=False)
        self.assertEqual(self.notebook.select(), '2')

    def test_user_switch_requests_only_one_refresh_and_ignores_other_notebook(self):
        self.page.render_cgyro()
        self.assertIsNotNone(self.notebook.callback)
        self.notebook.select(2)
        event = SimpleNamespace(widget=self.notebook)
        self.notebook.callback(event)
        self.assertEqual(self.page.settings['cgyro_main_tab'], 'results')
        self.page.ui.UpdateGUI.assert_called_once_with()
        self.notebook.callback(event)  # Rebuild/programmatic duplicate event.
        self.notebook.callback(SimpleNamespace(widget=Notebook()))
        self.page.ui.UpdateGUI.assert_called_once_with()
        self.page.render_cgyro()
        self.browser.return_value.render.assert_called_once_with(title=False)

    def test_invalid_saved_tab_falls_back_to_input_without_loading_results(self):
        self.page.settings['cgyro_main_tab'] = 'removed-page'
        self.page.render_cgyro()
        self.assertEqual(self.page.settings['cgyro_main_tab'], 'input')
        self.assertEqual(self.notebook.select(), '0')
        self.browser.assert_not_called()

    def test_native_tab_events_keep_input_refreshes_separate_from_results(self):
        # Use the actual native Tab body and real Tk events. Mock-only tab
        # selection misses queued <<NotebookTabChanged>> events during rebuild.
        import tkinter as tk
        from tkinter import ttk
        try:
            root = tk.Tk()
        except tk.TclError as error:
            self.skipTest('A Tk display is required: ' + str(error))
        root.withdraw()
        self.addCleanup(root.destroy)
        errors = []
        root.report_callback_exception = lambda kind, error, trace: errors.append(error)
        source = SOURCE / 'omfit_classes/OMFITx.py'
        definition = next(node for node in ast.parse(source.read_text(encoding='utf-8')).body
                          if isinstance(node, ast.FunctionDef) and node.name == 'Tab')
        definition.decorator_list = []
        parent = ttk.Frame(root)
        auxiliary = dict(parentGUI=parent, notebook=None, tab_name='', tab_list={'': parent},
                         open_tabs={}, compoundGUIid='', topGUI=root)
        namespace = dict(tk=tk, ttk=ttk, _aux=auxiliary,
                         _GUIs={str(root): SimpleNamespace(notebooks={})})
        exec(compile(ast.Module(body=[definition], type_ignores=[]), str(source), 'exec'), namespace)
        self.page.render_cgyro.__globals__.update(tk=tk, ttk=ttk)
        self.page.ui = SimpleNamespace(Tab=namespace['Tab'], _aux=auxiliary, UpdateGUI=Mock())
        self.page.render_cgyro()
        root.update()
        notebook = auxiliary['notebook']
        self.assertIs(self.page.cgyro_main_notebook, notebook)
        self.browser.assert_not_called()
        self.page.ui.UpdateGUI.assert_not_called()
        notebook.select(2)
        root.update()
        self.page.ui.UpdateGUI.assert_called_once_with()
        self.page.render_cgyro()
        root.update()
        self.browser.return_value.render.assert_called_once_with(title=False)
        self.page.ui.UpdateGUI.assert_called_once_with()  # No rebuild loop.
        notebook.select(0)
        root.update()
        self.page.render_cgyro()
        root.update()
        self.browser.return_value.render.assert_called_once_with(title=False)
        self.assertEqual(self.page.settings['cgyro_main_tab'], 'input')
        self.assertFalse(errors)


if __name__ == '__main__':
    unittest.main()
