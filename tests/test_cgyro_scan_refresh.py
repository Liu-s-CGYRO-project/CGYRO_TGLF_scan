"""Preparing a scan must not render the hidden result/archive page."""
import ast
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import Mock, patch

REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO.parents[2] / 'OMFIT-source-ASIPP_unstable/omfit'
sys.path.insert(0, str(REPO / 'CGYRO_TGLF_scan/LIB'))
from collections import OrderedDict
from OMFITlib_gui_deferred import TabPages, deferred_section
from OMFITlib_gui_layout import finish_gui_layout


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
        namespace = dict(tk=SimpleNamespace(Misc=Frame, TclError=RuntimeError), OrderedDict=OrderedDict,
            ttk=SimpleNamespace(Notebook=Notebook), MODULES={'cgyro': ('CGYRO_scan',)},
            read=lambda root, path: root[path[0]], ResultBrowser=self.browser, queue_records=self.queue,
            TabPages=TabPages, sync_cgyro_choices=lambda *args: [])
        exec(compile(ast.Module(body=constants + [cls], type_ignores=[]), str(source), 'exec'), namespace)
        self.page = namespace['CgyroPage']()
        self.notebook = Notebook()
        self.page.root, self.page.settings, self.page.cgyro_rows = {'CGYRO_scan': {}}, {}, []
        self.page.ui = SimpleNamespace(Tab=Mock(), UpdateGUI=Mock(),
                                      _aux={'parentGUI': Frame(self.notebook)})
        self.page.actions = SimpleNamespace(continue_cgyro=Mock(), factory=dict)
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
        self.assertEqual(self.page.settings['cgyro_main_tab'], 'results')

    def test_user_switch_never_requests_owner_refresh_and_ignores_other_notebook(self):
        host = self.native_host()
        notebook = self.page.cgyro_main_notebook
        section = self.page.cgyro_results_section
        section.show = Mock(wraps=section.show)
        notebook.select(2)
        host.root.update()
        self.assertEqual(self.page.settings['cgyro_main_tab'], 'results')
        section.show.assert_called_once_with()
        event = SimpleNamespace(widget=notebook)
        self.page.cgyro_main_tab_changed(event)  # Rebuild/programmatic duplicate event.
        self.assertEqual(section.show.call_count, 2)  # The section handles idempotency.
        self.page.cgyro_main_tab_changed(SimpleNamespace(widget=Notebook()))
        self.assertEqual(section.show.call_count, 2)
        notebook.select(0)
        host.root.update()
        notebook.select(1)
        host.root.update()
        self.assertEqual(host.updates, [])
        self.browser.return_value.render.assert_called_once_with(title=False)

    def test_invalid_saved_tab_falls_back_to_input_without_loading_results(self):
        self.page.settings['cgyro_main_tab'] = 'removed-page'
        self.page.render_cgyro()
        self.assertEqual(self.page.settings['cgyro_main_tab'], 'input')
        self.assertEqual(self.page.settings['cgyro_main_tab'], 'input')
        self.browser.assert_not_called()

    def native_host(self, selected='input'):
        # Reuse the real native GUI/control harness, not just a Notebook stub.
        # Its original GUI.update destroys controls and emits tree events, so
        # the tests below detect the visible whole-window redraw regression.
        import tkinter as tk
        from tkinter import ttk
        import test_gui_refresh_native as native
        import OMFITlib_gui_fonts as fonts
        # Geometry/selection tests use an installed font, never a downloader.
        font = patch.object(fonts, 'font_family', return_value='DejaVu Sans')
        font.start()
        self.addCleanup(font.stop)
        with patch.object(native, 'SOURCE', SOURCE):
            host = native.NativeTkRefreshTests()
            self.addCleanup(host.doCleanups)
            host.setUp()
        self.addCleanup(host.tearDown)
        self.addCleanup(host.drain)
        native.native_definitions(SOURCE / 'omfit_classes/OMFITx.py',
            {'Tab', 'Label', '_Label', '_absLocation'}, host.api.__dict__)
        host.owner.pythonFile.identity, host.other.pythonFile.identity = 'owner', 'other'
        host.api.OMFIT = {'owner': host.tree, 'other': dict(number=-1)}
        host.api.relativeLocations = lambda file: {'key': file.identity}
        host.api.absLocation = lambda location, context, **kwargs: (
            "OMFIT[" + repr(context['key']) + "]" + location[len('root'):])
        self.page.render_cgyro.__globals__.update(tk=tk, ttk=ttk)
        self.page.settings['cgyro_main_tab'] = selected
        self.page.label.side_effect = lambda text: self.page.ui.Label(text, align='left')
        self.page.compound.side_effect = lambda *args, **kwargs: host.controls.update(
            input=self.page.ui.Entry("root['number']", 'Input', updateGUI=False))
        self.page.render_cgyro_parameters.side_effect = lambda *args: self.page.label('Parameters')
        self.browser.return_value.render.side_effect = lambda **kwargs: host.controls.update(
            result=self.page.ui.Entry("root['number']", 'Result', updateGUI=False))
        def build(ui):
            self.page.ui = ui
            intro = ui.Label('CGYRO scan')
            self.page.render_cgyro()
            finish_gui_layout(intro, ui, fit_tabs=True)
        host.render(build)
        # The entire process-global context now belongs to another window.
        host.api._aux.update(parentGUI=host.other.parentGUI, topGUI=host.other.top,
                             notebook=None, configure_size=[], tab_list={})
        host.tree_events = []
        host.root.bind('<<update_treeGUI>>', lambda event: host.tree_events.append(event), add='+')
        return host

    def test_native_switch_keeps_widgets_and_does_not_emit_tree_refresh(self):
        host = self.native_host()
        notebook = self.page.cgyro_main_notebook
        entry = host.controls['input']
        entry.delete(0, 'end')
        entry.insert(0, '42')  # Uncommitted text must not vanish on tab switch.
        self.browser.assert_not_called()
        for index in (1, 0, 1, 2, 0, 2, 1, 0):
            notebook.select(index)
            host.root.update()
        host.drain()
        self.browser.return_value.render.assert_called_once_with(title=False)
        self.assertEqual(host.updates, [])
        self.assertEqual(host.tree_events, [])
        self.assertTrue(entry.winfo_exists())
        self.assertEqual(entry.get(), '42')
        self.assertEqual(self.page.settings['cgyro_main_tab'], 'input')

    def test_native_initial_results_selection_builds_once(self):
        host = self.native_host('results')
        host.drain()
        self.browser.return_value.render.assert_called_once_with(title=False)
        self.assertTrue(self.page.cgyro_results_section.built)
        self.assertEqual(self.page.cgyro_main_notebook.index('current'), 2)
        self.assertEqual(host.updates, [])

    def test_result_action_refreshes_result_tab_and_invalidates_other_tabs_lazily(self):
        host = self.native_host()
        notebook = self.page.cgyro_main_notebook
        self.page.cgyro_main_pages.select('parameters')
        host.root.update()
        self.browser.return_value.render.side_effect = lambda **kwargs: host.controls.update(
            sync=self.page.ui.Button('Synthetic status synchronization', lambda: None, updateGUI=True))
        self.page.cgyro_main_pages.select('results')
        host.root.update()
        self.assertEqual(self.page.compound.call_count, 1)
        self.assertEqual(self.page.render_cgyro_parameters.call_count, 1)
        old = host.controls['sync']
        host.invoke(old.invoke)
        host.drain()
        self.assertFalse(old.winfo_exists())
        self.assertIs(self.page.cgyro_main_notebook, notebook)
        self.browser.return_value.render.assert_called_with(title=False)
        self.assertEqual(self.browser.return_value.render.call_count, 2)
        self.assertEqual(self.page.compound.call_count, 1)
        self.assertEqual(self.page.render_cgyro_parameters.call_count, 1)
        self.assertEqual(host.updates, [])
        # A data-changing action marks hidden previews stale without parsing
        # them immediately; the next visit rebuilds them once.
        self.page.cgyro_main_pages.select('parameters')
        host.root.update()
        self.assertEqual(self.page.render_cgyro_parameters.call_count, 2)

    def test_deferred_controls_use_captured_module_and_restore_other_gui(self):
        host = self.native_host()
        previous = dict(host.api._aux)
        original_file = host.owner.pythonFile
        host.owner.pythonFile = host.other.pythonFile  # CompoundGUI has since returned.
        self.page.cgyro_main_notebook.select(2)
        host.root.update()
        self.assertEqual(host.api._aux, previous)
        self.assertIs(host.owner.pythonFile, host.other.pythonFile)
        entry = host.controls['result']
        entry.delete(0, 'end')
        entry.insert(0, '25')
        # Deliver the unchanged Return binding as a widget-targeted virtual
        # event: WSL and parallel Tk tests need not steal OS keyboard focus.
        entry.bind('<<TestCommit>>', entry.bind('<Return>'))
        entry.event_generate('<<TestCommit>>')
        host.root.update()
        self.assertEqual(host.tree['number'], 25)
        self.assertEqual(host.api.OMFIT['other']['number'], -1)
        host.owner.pythonFile = original_file

    def test_failed_panel_is_removed_and_context_restored_before_retry(self):
        host = self.native_host()
        section = self.page.cgyro_results_section
        previous = dict(host.api._aux)
        original = self.browser.return_value.render.side_effect
        def fail(**kwargs):
            original(**kwargs)
            raise ValueError('Cannot enumerate selected result metadata')
        self.browser.return_value.render.side_effect = fail
        self.page.settings['cgyro_main_tab'] = 'results'
        with self.assertRaisesRegex(ValueError, 'selected result metadata'):
            section.show()
        self.assertFalse(section.built)
        self.assertFalse(section.running)
        self.assertEqual(section.parent.winfo_children(), [])
        self.assertEqual(host.api._aux, previous)
        self.browser.return_value.render.side_effect = original
        section.show()
        self.assertTrue(section.built)
        self.assertEqual(len(section.parent.winfo_children()), 1)
        self.assertEqual(host.updates, [])

    def test_save_lock_delays_only_visible_section_and_close_cancels_timer(self):
        host = self.native_host()
        section = self.page.cgyro_results_section
        host.api.OMFITaux['GUI'].lockSave = True
        self.page.cgyro_main_notebook.select(2)
        host.root.update()
        self.assertIsNotNone(section.pending)
        self.browser.assert_not_called()
        self.page.cgyro_main_notebook.select(0)
        host.api.OMFITaux['GUI'].lockSave = False
        host.drain(130)
        self.browser.assert_not_called()
        host.api.OMFITaux['GUI'].lockSave = True
        self.page.cgyro_main_notebook.select(2)
        host.root.update()
        host.owner.top.destroy()
        self.assertIsNone(section.pending)
        host.drain(130)
        section.show()  # Stale callbacks cannot recreate a closed window.
        self.browser.assert_not_called()

    def test_save_lock_resumes_visible_panel_without_refresh(self):
        host = self.native_host()
        host.api.OMFITaux['GUI'].lockSave = True
        self.page.cgyro_main_notebook.select(2)
        host.root.update()
        host.api.OMFITaux['GUI'].lockSave = False
        host.drain(130)
        self.browser.return_value.render.assert_called_once_with(title=False)
        self.assertEqual(host.updates, [])
        self.assertEqual(host.tree_events, [])

    def test_rebuild_invalidates_section_and_does_not_reuse_dead_widgets(self):
        host = self.native_host('results')
        old_section = self.page.cgyro_results_section
        self.page.settings['cgyro_main_tab'] = 'input'
        host.owner.update()
        host.root.update()
        old_section.show()
        self.browser.return_value.render.assert_called_once_with(title=False)
        self.page.cgyro_main_notebook.select(2)
        host.root.update()
        self.assertEqual(self.browser.return_value.render.call_count, 2)
        self.assertIsNot(self.page.cgyro_results_section, old_section)


if __name__ == '__main__':
    unittest.main()
