"""Selected spectra use indexed coordinates, never inferred storage levels."""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'CGYRO_TGLF_scan/LIB'))
from OMFITlib_cgyro_scan_view import axis_values, comparison_case_view, multiaxis_scans
from OMFITlib_compare_cases import CaseSelection
from OMFITlib_compare_state import dict_path, _cgyro_axis_errors
from test_compare_case_selection import FakeUI


def scan_case(grids=(24, 32), kys=(-3., .2, 3., 23.), linked=False):
    axes = [dict(name='N_THETA', values=list(grids))]
    if linked:
        axes[0]['linked'] = [dict(name='N_RADIAL', values=[value * 2 for value in grids])]
    info = dict(scan_dimensions=1, scan_axes=axes, scale_time_with_ky=True)
    tasks, branch = {}, {}
    for group, grid in enumerate(grids):
        for number, ky in enumerate(kys, 1):
            point = 'job{}:p{:06d}'.format(group, number)
            path = ['N_THETA', str(grid), 'lin', str(ky)]
            values = dict(N_THETA=grid, KY=ky)
            if linked:
                values['N_RADIAL'] = grid * 2
            tasks[point] = dict(values=values, result_info=copy.deepcopy(info),
                input_parameters=dict(values, DELTA_T=.01 / ky if ky > 1 else .01),
                coordinate_path=path, result_path=path + [point])
            branch.setdefault(str(grid), {}).setdefault('lin', {}).setdefault(str(ky), {})[point] = {'ref': point}
    return {'N_THETA': branch, '__SCANS__': {'N_THETA': dict(info=info, tasks=tasks)}}


class ScanViewTest(unittest.TestCase):
    def test_scaled_time_is_not_an_extra_axis_and_indexed_1d_reaches_exact_leaf(self):
        case = scan_case()
        before = copy.deepcopy(case)
        with patch('builtins.open', side_effect=AssertionError('plot selection read a file')):
            self.assertEqual(axis_values(multiaxis_scans(case)['N_THETA']), {'N_THETA': [24., 32.]})
            view, selected, metadata, errors = comparison_case_view(case, {'N_THETA': [32]})
        self.assertFalse(errors)
        self.assertEqual(len(selected), 1)
        token = next(iter(selected))
        self.assertEqual(set(view[token]), {32.})
        self.assertEqual({float(ky) for ky in view[token][32.]['lin']}, {-3., .2, 3., 23.})
        for ky, leaf in view[token][32.]['lin'].items():
            self.assertIs(leaf, next(iter(case['N_THETA']['32']['lin'][ky].values())))
        self.assertEqual(metadata[token]['coordinate_names'], ['N_THETA'])
        self.assertEqual(before, case)

    def test_linked_axis_stays_a_label_but_conflicting_linkage_stays_separate(self):
        case = scan_case(linked=True)
        self.assertEqual(list(axis_values(multiaxis_scans(case)['N_THETA'])), ['N_THETA'])
        view, selected, metadata, errors = comparison_case_view(case, {'N_THETA': [24, 32]})
        self.assertFalse(errors)
        self.assertEqual(len(selected), 1)
        self.assertEqual(next(iter(metadata.values()))['coordinates'][32.]['N_RADIAL'], 64.)
        tasks = case['__SCANS__']['N_THETA']['tasks']
        row = copy.deepcopy(next(iter(tasks.values())))
        row['values']['N_RADIAL'] = row['input_parameters']['N_RADIAL'] = 80
        row['result_path'][-1] = 'other'
        tasks['other'] = row
        case['N_THETA']['24']['lin']['-3.0']['other'] = {'ref': 'other'}
        self.assertEqual(list(axis_values(multiaxis_scans(case)['N_THETA'])), ['N_THETA', 'N_RADIAL'])

    def test_close_but_distinct_parameters_are_not_collapsed(self):
        case = scan_case(grids=(1.23456100001, 1.23456100002), kys=(.2,))
        scan = multiaxis_scans(case)['N_THETA']
        self.assertEqual(len(axis_values(scan)['N_THETA']), 2)
        view, selected, _, errors = comparison_case_view(case, {'N_THETA': [1.23456100002]})
        self.assertFalse(errors)
        self.assertEqual(set(view[next(iter(selected))]), {1.23456100002})

    def test_scaled_step_axis_uses_requested_value_even_when_high_ky_is_first(self):
        step = .0001
        info = dict(scan_axes=[dict(name='DELTA_T', values=[step])], scale_time_with_ky=True)
        tasks, branch = {}, {}
        for ky in (13., .2, 3.):
            path = ['DELTA_T', str(step), 'lin', str(ky)]
            tasks[str(ky)] = dict(values={'DELTA_T': step, 'KY': ky},
                input_parameters={'DELTA_T': step / ky if ky > 1 else step},
                coordinate_path=path, result_path=path)
            branch.setdefault(str(step), {}).setdefault('lin', {})[str(ky)] = {'ref': ky}
        case = {'DELTA_T': branch, '__SCANS__': {'DELTA_T': dict(info=info, tasks=tasks)}}
        self.assertEqual(axis_values(multiaxis_scans(case)['DELTA_T']), {'DELTA_T': [step]})
        view, chosen, _, errors = comparison_case_view(case, {'DELTA_T': [step]})
        self.assertFalse(errors)
        self.assertEqual(len(view[next(iter(chosen))][step]['lin']), 3)

    def test_bad_point_is_diagnosed_without_blocking_other_points(self):
        case = scan_case()
        tasks = case['__SCANS__']['N_THETA']['tasks']
        tasks['job0:p000001']['values']['KY'] = 'broken'
        view, selected, _, errors = comparison_case_view(case, {'N_THETA': [32]})
        self.assertEqual(len(view[next(iter(selected))][32.]['lin']), 4)
        self.assertTrue(any('job0:p000001' in error for error in errors))

    def test_equivalent_ky_spellings_cannot_silently_duplicate_one_coordinate(self):
        case = scan_case(grids=(32,), kys=(.1,))
        tasks = case['__SCANS__']['N_THETA']['tasks']
        row = copy.deepcopy(next(iter(tasks.values())))
        row['coordinate_path'][-1] = row['result_path'][-2] = '0.10'
        tasks['second'] = row
        with self.assertRaisesRegex(ValueError, 'Duplicate ky'):
            comparison_case_view(case, {'N_THETA': [32]})

    def test_ui_prunes_invisible_filters_and_does_not_add_a_single_axis_dropdown(self):
        settings = dict(selected_paras={'N_THETA': [24, 32]},
            cgyro_multi={'N_THETA': dict(axis='DELTA_T', values={'DELTA_T': [], 'N_THETA': [32]})})
        root = {'settings': settings}
        ui = FakeUI(root)
        app = CaseSelection(root, ui)
        app._multi_axis_entries(settings, lambda *keys: dict_path("root['settings']", *keys),
            {'T': scan_case()}, ['T'], 'N_THETA', settings['selected_paras'])
        self.assertEqual(list(settings['cgyro_multi']['N_THETA']['values']), ['N_THETA'])
        self.assertEqual(settings['cgyro_multi']['N_THETA']['axis'], 'N_THETA')
        self.assertFalse(_cgyro_axis_errors(settings))
        self.assertFalse(any(kind == 'ComboBox' for _, kind, _, _ in ui.events))

    def test_shared_config_filter_includes_case_where_it_is_constant(self):
        first, second = scan_case(), scan_case()
        for row in first['__SCANS__']['N_THETA']['tasks'].values():
            row['input_parameters']['MASS_1'] = 1.
        for index, row in enumerate(second['__SCANS__']['N_THETA']['tasks'].values()):
            row['input_parameters']['MASS_1'] = 2. if index < 4 else 3.
        settings = dict(selected_paras={'N_THETA': [24, 32]})
        root = {'settings': settings}
        app = CaseSelection(root, FakeUI(root))
        app._multi_axis_entries(settings, lambda *keys: dict_path("root['settings']", *keys),
            {'a': first, 'b': second}, ['a', 'b'], 'N_THETA', settings['selected_paras'])
        cfg = settings['cgyro_multi']
        self.assertEqual(list(cfg['N_THETA']['values']['MASS_1']), [1., 2., 3.])
        cfg['N_THETA']['values']['MASS_1'] = [2.]
        self.assertFalse(comparison_case_view(first, settings['selected_paras'], cfg)[1])
        self.assertEqual(len(comparison_case_view(second, settings['selected_paras'], cfg)[1]), 1)


if __name__ == '__main__':
    unittest.main()
