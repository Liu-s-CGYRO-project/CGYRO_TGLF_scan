"""Unchanged native OMFIT controls respect each Transfer tool's boundary."""
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import test_gui_refresh_native as native
import test_gui_tab_pages as tabs_fixture
from test_transfer_gui_boundaries import Unreadable
import OMFITlib_transfer_plot_ui as plots

SOURCE = native.SOURCE
REPO = Path(__file__).resolve().parents[1]


class TransferNativeBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.start_patch(patch.object(tabs_fixture, 'SOURCE', SOURCE))
        fixture = tabs_fixture.NativeTabsTests()
        self.addCleanup(fixture.doCleanups)
        fixture.setUp()
        self.host = fixture.host
        native.native_definitions(SOURCE / 'omfit_classes/OMFITx.py', {'Separator'}, self.host.api.__dict__)
        self.host.api.TitleGUI = lambda title: self.host.owner.top.title(title)
        self.host.api.FilePicker = lambda path, label, **kw: self.host.api.Label(label)
        self.host.tree.update(SETTINGS={'PHYSICS': {}, 'SETUP': {}}, INPUTS={},
                              OUTPUTS={}, Transfer_file={}, TEMPLATES={})
        self.tree_events = []
        self.host.root.bind('<<update_treeGUI>>', lambda event: self.tree_events.append('tree'), add='+')

    def start_patch(self, patcher):
        result = patcher.start()
        self.addCleanup(patcher.stop)
        return result

    def build(self, filename):
        script = REPO / 'CGYRO_TGLF_scan/Transfer_tool/GUIS' / filename
        def render(ui):
            self.header = ui.Label('Unrelated project header')
            self.action = ui.Button('Unrelated action', lambda: None)
            namespace = dict(OMFITx=self.host.api, root=self.host.tree, scratch={}, OMFITtree=dict,
                             OMFITnc=Mock(), OMFITgacode=Mock(), OMFITinputgacode=Mock(),
                             OMFITpFile=Mock(), OMFITgeqdsk=Mock(), show_run_button=False,
                             defaultVars=lambda **kw: None)
            exec(compile(script.read_text(encoding='utf-8'), str(script), 'exec'), namespace)
            self.namespace = namespace
        self.host.render(render)
        self.tree_events.clear()

    def combo(self, label):
        return next(widget for widget in self.host.descendants(self.host.owner.top)
                    if isinstance(widget, native.ttk.Combobox) and label in widget.cget('values'))

    def choose(self, combo, value):
        combo.set(value)
        self.host.invoke(lambda: combo.event_generate('<<ComboboxSelected>>'))
        self.host.drain(40)

    def assert_external_intact(self, header, action):
        self.assertIs(self.header, header)
        self.assertIs(self.action, action)
        self.assertTrue(header.winfo_exists())
        self.assertTrue(action.winfo_exists())
        self.assertEqual(self.host.updates, [])
        self.assertEqual(self.tree_events, [])

    def test_profile_source_change_rebuilds_only_transfer_tool(self):
        self.build('transfer.py')
        header, action = self.header, self.action
        combo = self.combo('剖面文件（p-file）')
        self.choose(combo, '剖面文件（p-file）')
        self.assertEqual(self.host.tree['SETTINGS']['PHYSICS']['start_from'], 'pfile')
        self.assertFalse(combo.winfo_exists())
        self.assert_external_intact(header, action)

    def test_conversion_direction_change_rebuilds_only_converter(self):
        # The production dependency is used only for one legacy bool migration.
        self.start_patch(patch.dict('sys.modules', {'omfit_classes.utils_base': SimpleNamespace(evalExpr=lambda value: value)}))
        self.build('convert.py')
        header, action = self.header, self.action
        combo = self.combo('CGYRO → TGLF')
        self.choose(combo, 'CGYRO → TGLF')
        self.assertEqual(self.host.tree['SETTINGS']['PHYSICS']['conversion_mode'], 'cgyro_to_tglf')
        self.assertFalse(combo.winfo_exists())
        self.assert_external_intact(header, action)

    def test_plot_tabs_and_radius_edit_keep_widgets_and_unselected_data_unread(self):
        self.host.tree['INPUTS']['input.gacode'] = Unreadable()
        self.host.tree['Transfer_file']['input.gacode'] = Unreadable()
        self.host.tree['OUTPUTS']['Profiles_gen'] = {'input.tglf_1': Unreadable(), 'input.tglf_2': Unreadable()}
        self.host.tree['PLOTS'] = {name + '.py': SimpleNamespace(plot=Mock()) for name in plots.CATALOG}
        validation = self.start_patch(patch.object(plots, 'data_issues', side_effect=AssertionError('display parsed payload')))
        self.build('plots.py')
        header, action = self.header, self.action
        view = self.namespace['plots']
        self.assertFalse(view.pages.sections['estimates'].built)
        self.assertFalse(view.pages.sections['transport'].built)
        for page in ('estimates', 'transport', 'profiles'):
            view.pages.select(page)
            self.host.drain(10)
        field = next(widget for widget in self.host.descendants(self.host.owner.top)
                     if isinstance(widget, native.ttk.Entry) and not isinstance(widget, native.ttk.Combobox))
        field.delete(0, 'end')
        field.insert(0, '.2')
        self.host.submit_entry(field)
        self.host.drain(20)
        self.assertTrue(field.winfo_exists())
        self.host.button(self.host.owner.top, '绘制剖面与梯度').invoke()
        self.host.drain(20)
        self.host.tree['PLOTS']['profile.py'].plot.assert_called_once_with()
        validation.assert_not_called()
        self.assert_external_intact(header, action)


if __name__ == '__main__':
    unittest.main()
