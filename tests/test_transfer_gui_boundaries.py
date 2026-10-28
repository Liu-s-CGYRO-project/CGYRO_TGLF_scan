"""Transfer display builds controls without reading unrelated plot payloads."""
import ast
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import Mock, patch

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / 'CGYRO_TGLF_scan/LIB'), str(REPO / 'CGYRO_TGLF_scan/Transfer_tool/LIB')]
import OMFITlib_transfer_plot_ui as plots


class Unreadable:
    def __getitem__(self, key):
        raise AssertionError('parsed an unselected payload')
    def __contains__(self, key):
        raise AssertionError('parsed an unselected payload')
    def keys(self):
        raise AssertionError('parsed an unselected payload')


class DisplayUI:
    def __init__(self):
        self.buttons, self.entries = [], []
    def TitleGUI(self, *args, **kwargs):
        pass
    def Label(self, *args, **kwargs):
        return object()
    def ComboBox(self, *args, **kwargs):
        pass
    def Entry(self, *args, **kwargs):
        self.entries.append(kwargs)
    def FilePicker(self, *args, **kwargs):
        pass
    def same_row(self):
        return nullcontext()
    def Button(self, label, action, **kwargs):
        self.buttons.append((label, action, kwargs))


class TransferGuiBoundaryTests(unittest.TestCase):
    def test_open_and_switch_plot_tabs_do_not_parse_any_payload(self):
        scripts = {name + '.py': SimpleNamespace(plot=Mock()) for name in plots.CATALOG}
        root = {'SETTINGS': {}, 'INPUTS': {'input.gacode': Unreadable()},
                'Transfer_file': {'input.gacode': Unreadable()},
                'OUTPUTS': {'Profiles_gen': {'input.tglf_1': Unreadable(), 'input.tglf_2': Unreadable()},
                            'TGYRO': Unreadable()}, 'PLOTS': scripts}
        ui = DisplayUI()
        class Pages:
            def __init__(self, ui, captions, state, key, render):
                self.render = render
                render('profiles')
        with patch.object(plots, 'TabPages', Pages), \
                patch.object(plots, 'section_group', side_effect=lambda *args: nullcontext()), \
                patch.object(plots, 'finish_gui_layout'), \
                patch.object(plots, 'data_issues', side_effect=AssertionError('eager validation')):
            view = plots.TransferPlotsUI(root, ui)
            view.render()
            self.assertEqual(len(ui.buttons), 4)
            view.pages.render('estimates')
            view.pages.render('transport')
            self.assertEqual(len(ui.buttons), len(plots.CATALOG))
            self.assertTrue(all(not row['updateGUI'] for row in ui.entries))
            self.assertTrue(all(not row[2]['updateGUI'] for row in ui.buttons))
            ui.buttons[0][1]()
        scripts['profile.py'].plot.assert_called_once_with()
        self.assertTrue(all(script.plot.call_count == 0 for name, script in scripts.items() if name != 'profile.py'))

    def test_selected_parameter_table_still_validates_before_reading(self):
        view = plots.TransferPlotsUI({'SETTINGS': {}, 'INPUTS': {}, 'Transfer_file': {}, 'OUTPUTS': {}}, DisplayUI())
        with patch.object(plots, 'data_issues', return_value=['Selected input is incomplete']) as check, \
                patch.object(plots, 'parameter_rows') as rows:
            with self.assertRaisesRegex(ValueError, 'Selected input is incomplete'):
                view.show_parameters(None)
        check.assert_called_once_with(view.root, 'printinfo')
        rows.assert_not_called()

    def test_all_standalone_transfer_entries_own_local_refresh_boundaries(self):
        for filename in ('transfer.py', 'convert.py', 'plots.py'):
            tree = ast.parse((REPO / 'CGYRO_TGLF_scan/Transfer_tool/GUIS' / filename).read_text(encoding='utf-8'))
            calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                     and isinstance(node.func, ast.Name) and node.func.id == 'deferred_section']
            self.assertEqual(len(calls), 1, filename)
            self.assertEqual({arg.arg: ast.literal_eval(arg.value) for arg in calls[0].keywords},
                             {'local': True, 'container': True, 'action': True}, filename)

    def test_input_keystroke_updates_only_selected_row(self):
        tree = ast.parse((REPO / 'CGYRO_TGLF_scan/LIB/OMFITlib_workbench_transfer_ui.py').read_text(encoding='utf-8'))
        changed = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == 'changed')
        table = Mock()
        table.get_children.side_effect = AssertionError('keystroke traversed all input parameters')
        state = dict(selected='N_RADIAL', selected_item='row200', loading=False,
                     parameters={'N_RADIAL': 32}, edits={})
        namespace = dict(state=state, table=table, parameter_text=SimpleNamespace(get=lambda: '48'),
                         save_button=Mock(), status=Mock())
        exec(compile(ast.Module(body=[changed], type_ignores=[]), '<input-edit-callback>', 'exec'), namespace)
        namespace['changed']()
        table.set.assert_called_once_with('row200', 'value', '48')
        table.item.assert_called_once_with('row200', tags=('changed',))
        self.assertEqual(state['edits'], {'N_RADIAL': '48'})


if __name__ == '__main__':
    unittest.main()
