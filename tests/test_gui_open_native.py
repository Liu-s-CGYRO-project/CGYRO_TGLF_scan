"""Opening/lifetime regressions using native OMFIT GUI, labels and help rows.

File readers/session state are adapters. No solver, network or result parsing
belongs to window construction. Linux/Tk must also run these tests: native
font metrics expose requested-width feedback that Windows alone can miss.
"""
from collections import Counter
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

import test_gui_tab_pages as tabs
import test_gui_refresh_native as native
import test_project as fixture
from OMFITlib_gui_api import adapt, begin_view_open
from OMFITlib_gui_controls import PARAMETER_PAGE_SIZE
from OMFITlib_gui_layout import finish_gui_layout
from OMFITlib_project import ProjectActions, PAGES
from OMFITlib_project_ui import ProjectUI

SOURCE = native.SOURCE


class NoResults(dict):
    def __getitem__(self, key):
        raise AssertionError('Opening or editing a page read result data')

    def __iter__(self):
        raise AssertionError('Opening or editing a page traversed results')

    keys = values = items = __iter__


class NativeOpenTests(unittest.TestCase):
    def setUp(self):
        source = patch.object(tabs, 'SOURCE', SOURCE)
        source.start()
        self.addCleanup(source.stop)
        self.case = tabs.NativeTabsTests()
        self.addCleanup(self.case.doCleanups)
        self.case.setUp()
        self.host = self.case.host
        native.native_definitions(SOURCE / 'omfit_classes/OMFITx.py',
            {'Separator', 'TitleGUI', '_helpButton', '_urlButton', 'FilePicker'}, self.host.api.__dict__)
        self.host.api.helpTip = SimpleNamespace(showtip=lambda *args, **kw: None)
        self.host.api.openInBrowser = lambda *args: None
        self.host.api._clearGUIPreferences = lambda *args, **kwargs: None
        font = ModuleType('utils_widgets')
        font.OMFITfont = lambda *args: 'TkDefaultFont'

        class ChildGUI:
            def __init__(self, name):
                self.name = name

            def __run__(self, workbench=None, **kwargs):
                if self.name == 'CGYRO_controls':
                    return workbench.render_cgyro_scan_tabs()
                if self.name == 'TGLF_controls':
                    return workbench.render_scan_tabs()
                # Separately exercised by native entry/refresh boundary suites.

        python_host = ModuleType('omfit_classes.omfit_python')
        python_host.OMFITpythonGUI = ChildGUI
        modules = patch.dict(sys.modules, {'omfit_classes.omfit_python': python_host, 'utils_widgets': font})
        modules.start()
        self.addCleanup(modules.stop)
        root = fixture.fixture()
        root['GUIS'].update((name, ChildGUI(name)) for name in root['GUIS'])
        root['Transfer_tool']['GUIS'].update((name, ChildGUI(name)) for name in root['Transfer_tool']['GUIS'])
        root['SETTINGS'].setdefault('WORKBENCH', {}).update(
            page='cgyro', cgyro_main_tab='parameters', cgyro_parameter_group='all',
            cgyro_source_mode='generated', cgyro_ion_cases=dict(BASE=True, H=False, D=False, T=False))
        source = fixture.cgyro()
        source.update(N_ENERGY=32, N_XI=48, HIPREC_FLAG=1)
        root['Transfer_tool']['OUTPUTS']['Profiles_gen'] = {
            'input.cgyro_' + str(i): source.copy() for i in range(1, 4)}
        root['TGLF_scan']['TGLF']['FILES']['input.tglf'] = fixture.tglf()
        root['CGYRO_scan']['RUN_DB'] = NoResults()
        root['TGLF_scan']['RUN_DB'] = NoResults()
        self.host.tree.clear()
        self.host.tree.update(root)
        self.actions = ProjectActions(self.host.tree)
        self.views = []

    def open(self):
        def build(api):
            begin_view_open(api)
            view = ProjectUI(self.actions, adapt(api))
            view.render()
            self.views.append(view)
        script = self.host.raw_view(build)
        script()
        self.host.root.update()
        self.host.drain(120)
        view = self.views[-1]
        self.assertTrue(view.page_picker.winfo_viewable())
        self.assertEqual(self.host.errors, [])
        self.host.updates.clear()
        return view

    def test_project_label_wrap_has_one_owner_and_native_api_keeps_its_hook(self):
        def build(ui):
            pending = self.host.api._aux['configure_size']
            native_label = self.host.api.Label('Other native label')
            hooks = list(pending)
            label = ui.Label('A long project parameter caption ' * 3, wraplength=600)
            self.assertIs(label.master.master, native_label.master.master)
            self.assertEqual(pending, hooks)
            self.assertTrue(any(widget is native_label.master for widget, action in pending))
            finish_gui_layout(label, ui)
            self.label = label
        self.host.render(build)
        self.host.drain(120)
        # The local viewport still wraps project labels after native sizing.
        self.assertGreater(self.label.winfo_pixels(self.label.cget('wraplength')), 0)
        self.assertFalse(self.label.master.bind('<Configure>'))

    def test_saved_cgyro_parameter_page_opens_and_search_clear_is_local(self):
        view = self.open()
        table = view.cgyro_parameter_list
        header, notebook = view.page_picker, view.cgyro_main_pages.notebook
        original_names = table.visible_names()
        self.assertEqual(len(original_names), PARAMETER_PAGE_SIZE)
        for value in ('HIPREC_FLAG', '', 'not_a_parameter', ''):
            table.query.set(value)
            table.flush()
            self.host.drain(80)
            self.assertIs(view.page_picker, header)
            self.assertIs(view.cgyro_main_pages.notebook, notebook)
        self.assertEqual(table.visible_names(), original_names)
        self.assertTrue(table.section.frame.winfo_viewable())
        table.following.invoke()
        self.host.drain(80)
        self.assertNotEqual(table.visible_names(), original_names)
        view.cgyro_main_pages.select('input')
        self.settle_layout(view)
        view.cgyro_main_pages.select('parameters')
        self.settle_layout(view)
        self.assertTrue(table.section.frame.winfo_viewable())
        self.assertEqual(self.host.updates, [])

    def test_tglf_open_resize_close_reopen_discards_geometry_callbacks(self):
        from OMFITlib_tglf_workbench import initialize
        settings, _ = initialize(self.host.tree)
        settings.update(page='parameters', source='current', mode='single', parameter_group='all')
        self.actions.settings['page'] = 'tglf'
        counts = Counter()
        original = native.ttk.Label.configure

        def measured(label, cnf=None, **kwargs):
            if 'wraplength' in kwargs:
                counts[label] += 1
                if counts[label] > 100:
                    return  # Fail below instead of hanging a broken Tk test.
            return original(label, cnf, **kwargs)

        with patch.object(native.ttk.Label, 'configure', measured), patch.object(native.ttk.Label, 'config', measured):
            for _ in range(2):
                view = self.open()
                window = view.page_picker.winfo_toplevel()
                for geometry in ('660x700', '1050x800', '720x740'):
                    window.geometry(geometry)
                    self.host.root.update()
                    self.host.drain(120)
                layout = view.page_intro.master.master._cgyro_gui_layout
                layout._queue_scroll()
                pending = layout.scroll_pending
                self.assertIsNotNone(pending)
                window.destroy()
                self.assertNotIn(pending, self.host.root.tk.call('after', 'info'))
                self.host.drain(30)
        self.assertLess(max(counts.values()), 100, 'Label wrapping did not settle')

    def test_all_workbench_page_bodies_switch_without_reopening_window(self):
        # Overview counts index keys; the parameter-only tests above forbid
        # even traversing that index. There are no payload readers here.
        self.host.tree['CGYRO_scan']['RUN_DB'] = {}
        self.host.tree['TGLF_scan']['RUN_DB'] = {}
        self.actions.settings['page'] = 'overview'
        view = self.open()
        header = view.page_picker
        for page in PAGES.values():
            with self.subTest(page=page):
                view.select_page(page)
                self.host.drain(150)
                self.assertIs(view.page_picker, header)
                self.assertTrue(header.winfo_viewable())
                self.assertEqual(self.host.errors, [])
        self.assertEqual(self.host.updates, [])

    def test_nested_tabs_fit_selected_body_after_local_switches(self):
        self.actions.settings.update(cgyro_ion_mode='custom',
            cgyro_ion_cases=dict(BASE=False, H=False, D=False, T=True))
        view = self.open()
        header = view.page_picker
        header.winfo_toplevel().geometry('760x1100')
        for selected in ('input', 'parameters', 'input', 'parameters', 'input'):
            # Follow the native Notebook tab-click event, including first use
            # of an unbuilt tab, instead of calling the eager TabPages helper.
            book = view.cgyro_main_pages.notebook
            book.select(view.cgyro_main_pages.keys.index(selected))
            self.host.drain(150)
            if selected == 'input':
                for nested in ('settings', 'run', 'input'):
                    view.cgyro_scan_pages.select(nested)
                    self.host.root.update()
                    self.host.drain(150)
                    self.assert_selected_panes_fit(view)
            self.host.root.update()
            self.host.drain(150)
            self.assert_selected_panes_fit(view)
        # Interleave native tab events with pending geometry work. Only the
        # final selection should determine the visible height.
        for index in range(12):
            self.host.root.after(index * 4, book.select, 1 - index % 2)
        self.host.drain(60)
        self.settle_layout(view)
        self.assertEqual(book.index('current'), 0)
        self.assert_selected_panes_fit(view)
        self.assertIs(view.page_picker, header)
        self.assertEqual(self.host.updates, [])

    def assert_selected_panes_fit(self, view):
        content = view.page_intro.master.master
        layout = content._cgyro_gui_layout
        for book in layout.notebooks:
            if not book.winfo_viewable():
                continue
            pane = book.nametowidget(book.select())
            self.assertGreaterEqual(pane.winfo_height() + 2, pane.winfo_reqheight(),
                (view.settings.get('cgyro_main_tab'), view.settings.get('cgyro_scan_page'),
                 str(book), book.cget('height'), pane.winfo_height(), pane.winfo_reqheight()))
        self.assertGreaterEqual(content.winfo_height(), layout._content_height())

    def settle_layout(self, view):
        layout = view.page_intro.master.master._cgyro_gui_layout
        previous = None
        for _ in range(80):
            self.host.drain(25)
            sizes = (layout.content.winfo_height(), layout._content_height(),
                     tuple((book.winfo_height(), book.winfo_reqheight()) for book in layout.notebooks))
            if layout.scroll_pending is None and sizes == previous:
                return
            previous = sizes
        self.fail('Local geometry did not settle: ' + repr(previous))

    def test_late_tab_geometry_grows_and_shrinks_without_refresh_or_result_reads(self):
        view = self.open()
        view.cgyro_main_pages.select('input')
        section = view.cgyro_scan_pages.sections['input']
        message = native.ttk.Label(section.frame, text='Status')
        message.pack()
        self.settle_layout(view)
        layout = view.page_intro.master.master._cgyro_gui_layout
        canvas = layout.content.master
        header, body = view.page_picker, section.frame
        initial = layout.content.winfo_height()
        # Late native geometry/font/message changes may alter the requested
        # height while a fixed-height Notebook emits no Configure event.
        message.configure(text='Updated status\n' * 40)
        self.settle_layout(view)
        self.assert_selected_panes_fit(view)
        self.assertGreater(layout.content.winfo_height(), initial + 400)
        canvas.yview_moveto(1)
        self.host.root.update_idletasks()
        self.assertLessEqual(message.winfo_rooty() + message.winfo_height(),
                             canvas.winfo_rooty() + canvas.winfo_height())
        message.configure(text='Status')
        self.settle_layout(view)
        self.assert_selected_panes_fit(view)
        self.assertEqual(layout.content.winfo_height(), initial)
        # A cached taller parameter page must not keep the short input tall.
        for selected in ('parameters', 'input'):
            view.cgyro_main_pages.select(selected)
            self.settle_layout(view)
            self.assert_selected_panes_fit(view)
        self.assertEqual(layout.content.winfo_height(), initial)
        self.assertIs(section.frame, body)
        self.assertIs(view.page_picker, header)
        self.assertEqual(self.host.updates, [])


if __name__ == '__main__':
    unittest.main()
