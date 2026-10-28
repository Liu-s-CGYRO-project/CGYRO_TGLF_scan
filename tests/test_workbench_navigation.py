"""Workbench view changes stay local in a real native OMFIT Tk host."""
from collections import Counter
import copy
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_gui_refresh_native as native
from OMFITlib_gui_deferred import TabPages, deferred_section
from OMFITlib_gui_layout import finish_gui_layout
from OMFITlib_workbench_catalog import PAGES
import OMFITlib_gui_fonts as fonts
from OMFITlib_gui_api import gui_view

REPO = Path(__file__).resolve().parents[1]
SOURCE = native.SOURCE


class WorkbenchNavigationTests(unittest.TestCase):
    def setUp(self):
        source = patch.object(native, 'SOURCE', SOURCE)
        source.start()
        self.addCleanup(source.stop)
        font = patch.object(fonts, 'font_family', lambda *args, **kwargs: 'DejaVu Sans')
        font.start()
        self.addCleanup(font.stop)
        self.host = native.NativeTkRefreshTests()
        self.addCleanup(self.host.doCleanups)
        self.host.setUp()
        self.addCleanup(self.host.tearDown)
        self.addCleanup(self.host.drain)
        native.native_definitions(SOURCE / 'omfit_classes/OMFITx.py',
            {'Tab', 'Label', '_Label', 'same_row'}, self.host.api.__dict__)
        self.host.api.TitleGUI = lambda title: self.host.owner.top.title(title)
        namespace = dict(tk=native.tk, ttk=native.ttk, PAGES=PAGES,
                         gui_view=gui_view,
                         deferred_section=deferred_section, finish_gui_layout=finish_gui_layout,
                         render_page=self.render_page, ERROR_NOTICE_SUFFIX='error')
        for name in ('CgyroPage', 'RuntimePage', 'TransferPage', 'ScanControls'):
            namespace[name] = type(name, (), {})
        native.native_definitions(REPO / 'CGYRO_TGLF_scan/LIB/OMFITlib_project_ui.py',
                                 {'ProjectUI'}, namespace)
        self.ProjectUI = namespace['ProjectUI']
        self.counts, self.script_runs, self.tree_events = Counter(), 0, []
        self.state = dict(page='overview', message='')
        self.host.root.bind('<<update_treeGUI>>', lambda event: self.tree_events.append(event), add='+')

    def render_page(self, view, key):
        self.counts[key] += 1
        if key == 'cgyro':
            def tab(page):
                self.counts['cgyro_' + page] += 1
                view.label(page)
            self.tabs = TabPages(view.ui, dict(input='Input', results='Results'),
                                 self.state, 'cgyro_tab', tab)
        else:
            self.body_label = view.label(str(self.host.tree['number']))
            view.nav('Go CGYRO', 'cgyro')
            view.guarded('Change value', lambda: self.host.tree.__setitem__('number', 77), [])

    def build(self):
        def render(api):
            self.script_runs += 1
            actions = SimpleNamespace(root=self.host.tree, settings=self.state,
                open_page=lambda page: self.state.__setitem__('page', page),
                check=lambda: self.state.__setitem__('message', 'Configuration status'))
            self.view = self.ProjectUI(actions, api)
            self.view.render()
        self.host.render(render)
        self.tree_events.clear()

    def choose(self, page):
        self.view.page_picker.current(list(PAGES.values()).index(page))
        self.host.invoke(lambda: self.view.page_picker.event_generate('<<ComboboxSelected>>'))
        self.host.drain()

    def test_page_selection_and_reset_preserve_header_without_tree_or_script_refresh(self):
        self.build()
        picker, intro, content = self.view.page_picker, self.view.page_intro, self.view.page_content
        initial_scripts = self.script_runs
        for page in ('run', 'templates', 'cgyro', 'overview', 'run'):
            self.choose(page)
        self.assertEqual(self.counts, dict(overview=2, run=2, templates=1, cgyro=1, cgyro_input=1))
        self.assertEqual(self.script_runs, initial_scripts)
        self.assertEqual(self.host.updates, [])
        self.assertEqual(self.tree_events, [])
        self.assertIs(self.view.page_picker, picker)
        self.assertIs(self.view.page_intro, intro)
        self.assertIs(self.view.page_content, content)
        self.assertIn('计算资源', str(intro.cget('text')))
        before = dict(self.counts)
        self.choose('run')
        self.assertEqual(self.counts, before)
        self.host.button(picker.master, '重置').invoke()
        self.host.drain()
        self.assertEqual(self.state['page'], 'overview')
        self.assertEqual(picker.current(), 0)
        self.assertEqual(self.tree_events, [])

    def test_navigation_button_is_local_and_keeps_unvisited_results_unbuilt(self):
        self.build()
        self.host.button(self.view.page_content.frame, 'Go CGYRO').invoke()
        self.host.drain()
        self.assertEqual(self.state['page'], 'cgyro')
        self.assertEqual(self.counts, dict(overview=1, cgyro=1, cgyro_input=1))
        self.assertEqual(self.host.updates, [])
        self.assertEqual(self.tree_events, [])
        self.assertEqual(self.view.page_picker.current(), list(PAGES.values()).index('cgyro'))

    def test_open_template_manager_does_not_rebuild_launching_page(self):
        opened = []
        def template_page(view):
            view.open_templates = lambda: opened.append(True)
            view.render_templates()
        with patch.object(self.ProjectUI, 'render_selected_page', template_page):
            self.build()
            body = self.view.page_content.frame
            self.host.button(body, '打开 OMFIT 模板管理器').invoke()
            self.host.drain()
            self.assertEqual(opened, [True])
            self.assertIs(self.view.page_content.frame, body)
            self.assertEqual(self.script_runs, 1)
            self.assertEqual(self.host.updates, [])
            self.assertEqual(self.tree_events, [])

    def test_help_and_result_browser_open_without_main_tree_repaint(self):
        opened = []
        self.host.tree['GUIS'] = {'CGYRO_results': SimpleNamespace(run=lambda: opened.append(('GUIS', 'CGYRO_results')))}
        self.ProjectUI.task.__globals__['read'] = lambda root, path: root['GUIS']['CGYRO_results']
        self.ProjectUI.note.__globals__['show_help'] = lambda parent, text: opened.append(text)
        def page(view):
            view.actions.call = lambda *args, **kwargs: self.fail('Opening a view must not execute a data action')
            view.note('Details', 'Help text')
            view.task('Open results', ('GUIS', 'CGYRO_results'))
        with patch.object(self.ProjectUI, 'render_selected_page', page):
            self.build()
            body = self.view.page_content.frame
            for label in ('查看说明', 'Open results'):
                self.host.button(body, label).invoke()
                self.host.drain()
            self.assertEqual(opened, ['Help text', ('GUIS', 'CGYRO_results')])
            self.assertIs(self.view.page_content.frame, body)
            self.assertEqual(self.tree_events, [])
            self.assertEqual(self.script_runs, 1)

    def test_native_keyboard_selection_and_rapid_changes_build_only_latest_page(self):
        self.build()
        picker = self.view.page_picker
        # Tk's keyboard/popdown selection procedure queues ComboboxSelected;
        # unlike OS focus synthesis it is deterministic under parallel Xvfb.
        picker.tk.call('ttk::combobox::SelectEntry', str(picker), list(PAGES.values()).index('run'))
        self.host.drain()
        self.assertEqual(self.state['page'], 'run')
        self.assertEqual(self.counts, dict(overview=1, run=1))
        for page in ('templates', 'cgyro', 'transfer'):
            self.view.select_page(page)
        self.host.drain()
        self.assertEqual(self.counts, dict(overview=1, run=1, transfer=1))
        self.assertEqual(self.host.updates, [])
        self.assertEqual(self.tree_events, [])

    def test_explicit_refresh_rebuilds_current_page_without_imports_or_tree(self):
        self.build()
        self.choose('run')
        picker, content = self.view.page_picker, self.view.page_content
        self.host.tree['number'] = 91
        self.host.button(self.host.owner.top, '刷新').invoke()
        self.host.drain()
        self.assertEqual(self.host.updates, [])
        self.assertEqual(self.tree_events, [])
        self.assertEqual(self.script_runs, 1)
        self.assertIs(self.view.page_picker, picker)
        self.assertIs(self.view.page_content, content)
        self.assertEqual(self.state['page'], 'run')
        self.assertEqual(self.view.page_picker.current(), list(PAGES.values()).index('run'))
        self.assertEqual(str(self.body_label.cget('text')), '91')

    def test_reopened_gui_restores_saved_page(self):
        self.build()
        self.choose('run')
        self.state = copy.deepcopy(self.state)
        self.host.owner.update()
        self.host.drain()
        self.assertEqual(self.view.page_picker.current(), list(PAGES.values()).index('run'))
        self.assertEqual(self.state['page'], 'run')

    def test_save_blocks_local_build_and_close_cancels_queued_navigation(self):
        self.build()
        content = self.view.page_content
        self.host.api.OMFITaux['GUI'].lockSave = True
        self.choose('run')
        self.assertEqual(self.counts, dict(overview=1))
        self.assertIsNotNone(content.refresh.pending)
        self.host.owner.top.destroy()
        self.assertIsNone(content.refresh.pending)
        self.host.drain(130)

    def test_business_action_and_explicit_callback_refresh_only_current_page(self):
        self.build()
        intro, picker = self.view.page_intro, self.view.page_picker
        self.host.button(self.view.page_content.frame, 'Change value').invoke()
        self.host.drain()
        self.assertEqual(self.host.tree['number'], 77)
        self.assertEqual(str(self.body_label.cget('text')), '77')
        self.assertEqual(self.counts, dict(overview=2))
        self.assertEqual(self.host.updates, [])
        self.assertIs(self.view.page_intro, intro)
        self.assertIs(self.view.page_picker, picker)
        self.host.tree['number'] = 82
        self.view.ui.UpdateGUI()  # A task manager or async action completed.
        self.host.drain()
        self.assertEqual(str(self.body_label.cget('text')), '82')
        self.assertEqual(self.host.updates, [])
        self.host.button(self.host.owner.top, '检查配置').invoke()
        self.host.drain()
        self.assertEqual(self.counts, dict(overview=4))
        self.assertEqual(self.host.updates, [])
        self.assertTrue(any(isinstance(widget, native.ttk.Label) and
            str(widget.cget('text')) == 'Configuration status'
            for widget in self.host.descendants(self.view.page_content.frame)))


if __name__ == '__main__':
    unittest.main()
