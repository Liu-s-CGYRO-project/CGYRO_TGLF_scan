"""KY_ONLY selects spectra, with configuration filters only when needed."""
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'CGYRO_TGLF_scan/LIB'))
from OMFITlib_cgyro_scan_view import axis_values, comparison_case_view, coordinate_label, multiaxis_scans
from OMFITlib_compare_cases import CaseSelection
from OMFITlib_compare_state import dict_path
from test_compare_case_selection import FakeUI


def ky_case(grids=(32,), kys=(-.2, .2, 1., 3., 23.), scaled=True, result_factory=None):
    info = dict(scan_dimensions=0, scan_axes=[dict(name='NU_EE', fixed=True, values=[.00471])],
                scale_time_with_ky=scaled)
    tasks, linear = {}, {}
    for group, grid in enumerate(grids):
        for number, ky in enumerate(kys, 1):
            point = 'job{}:p{:06d}'.format(group, number)
            step = .01 / ky if scaled and ky > 1 else .01
            path = ['KY_ONLY', '.00471', 'lin', str(ky)]
            parameters = dict(NU_EE=.00471, KY=ky, N_THETA=grid, N_ENERGY=32, N_XI=48, DELTA_T=step)
            tasks[point] = dict(values={'NU_EE': .00471, 'KY': ky},
                                input_parameters=parameters, result_info=dict(info),
                                coordinate_path=path, result_path=path + [str(group)])
            payload = result_factory(ky, grid) if result_factory else {'__RESULT_REF__': point}
            linear.setdefault(str(ky), {})[str(group)] = payload
    return {'KY_ONLY': {'.00471': {'lin': linear}}, '__SCANS__': {'KY_ONLY': dict(info=info, tasks=tasks)}}


def all_curves(case, config=None):
    view, selected, metadata, errors = comparison_case_view(case, {'KY_ONLY': [.00471]}, config)
    curves = [(view[key][value]['lin'], coordinate_label(metadata[key], value))
              for key, values in selected.items() for value in values if value in view[key]]
    return curves, errors


class KyOnlyTest(unittest.TestCase):
    def test_one_configuration_needs_no_numeric_selection_and_retains_signed_ky(self):
        case = ky_case()
        self.assertEqual(axis_values(multiaxis_scans(case)['KY_ONLY']), {})
        curves, errors = all_curves(case, {'KY_ONLY': dict(axis='DELTA_T', values={'DELTA_T': []})})
        self.assertFalse(errors)
        self.assertEqual(len(curves), 1)
        points, label = curves[0]
        self.assertEqual(label, 'KY_ONLY')
        self.assertEqual({float(ky) for ky in points}, {-.2, .2, 1., 3., 23.})
        for ky, payload in points.items():
            self.assertIs(payload, case['KY_ONLY']['.00471']['lin'][ky]['0'])

    def test_only_different_grid_is_a_filter_and_never_joins_other_grid(self):
        case = ky_case((24, 32))
        self.assertEqual(axis_values(multiaxis_scans(case)['KY_ONLY']), {'N_THETA': [24., 32.]})
        curves, errors = all_curves(case)
        self.assertFalse(errors)
        self.assertEqual({label for _, label in curves}, {'KY_ONLY · N_THETA=24', 'KY_ONLY · N_THETA=32'})
        curves, errors = all_curves(case, {'KY_ONLY': dict(ky_only=True, values={'N_THETA': [32]})})
        self.assertFalse(errors)
        self.assertEqual(len(curves), 1)
        for ky, payload in curves[0][0].items():
            self.assertIs(payload, case['KY_ONLY']['.00471']['lin'][ky]['1'])

    def test_real_time_step_difference_is_not_discarded(self):
        case = ky_case((32, 32), scaled=False)
        for point, row in case['__SCANS__']['KY_ONLY']['tasks'].items():
            if point.startswith('job1:'):
                row['input_parameters']['DELTA_T'] = .02
        self.assertEqual(axis_values(multiaxis_scans(case)['KY_ONLY']), {'DELTA_T': [.01, .02]})
        curves, errors = all_curves(case)
        self.assertFalse(errors)
        self.assertEqual(len(curves), 2)
        self.assertTrue(all(len(points) == 5 for points, _ in curves))

    def test_legacy_unscaled_requested_step_is_not_scaled_again(self):
        case = ky_case()
        for row in case['__SCANS__']['KY_ONLY']['tasks'].values():
            row.pop('input_parameters')
            row['values']['DELTA_T'] = .01
        self.assertEqual(axis_values(multiaxis_scans(case)['KY_ONLY']), {})
        self.assertEqual(len(all_curves(case)[0]), 1)

    def test_common_grid_filter_also_applies_to_a_single_configuration_case(self):
        curves, _ = all_curves(ky_case((24,)), {'KY_ONLY': dict(ky_only=True, values={'N_THETA': [32]})})
        self.assertEqual(curves, [])

    def test_empty_grid_selection_is_respected(self):
        curves, _ = all_curves(ky_case((24, 32)), {'KY_ONLY': dict(ky_only=True, values={'N_THETA': []})})
        self.assertEqual(curves, [])

    def test_shared_ui_filter_keeps_constant_configuration_in_other_case(self):
        settings = dict(selected_paras={'KY_ONLY': [.00471]})
        root = {'settings': settings}
        run = {'rho1': ky_case((24,)), 'rho2': ky_case((32, 48))}
        app = CaseSelection(root, FakeUI(root))
        app._multi_axis_entries(settings, lambda *keys: dict_path("root['settings']", *keys),
                                run, list(run), 'KY_ONLY', settings['selected_paras'])
        config = settings['cgyro_multi']
        self.assertEqual(list(config['KY_ONLY']['values']), ['N_THETA'])
        self.assertEqual(list(config['KY_ONLY']['values']['N_THETA']), [24., 32., 48.])
        self.assertEqual(len(all_curves(run['rho1'], config)[0]), 1)
        self.assertEqual(len(all_curves(run['rho2'], config)[0]), 2)

    def test_ui_removes_placeholder_and_stale_derived_filters_locally(self):
        for grids, labels in (((32,), []), ((24, 32), ['N_THETA'])):
            with self.subTest(grids=grids):
                settings = dict(selected_paras={'KY_ONLY': [.00471]},
                                cgyro_multi={'KY_ONLY': dict(axis='DELTA_T', values={'DELTA_T': []})})
                root = {'settings': settings}
                ui = FakeUI(root)
                app = CaseSelection(root, ui)
                self.assertTrue(app._multi_axis_entries(settings, lambda *keys: dict_path("root['settings']", *keys),
                    {'T': ky_case(grids)}, ['T'], 'KY_ONLY', settings['selected_paras']))
                self.assertEqual([args[1] for _, kind, args, _ in ui.events if kind == 'Entry'], labels)
                self.assertFalse(any(kind in ('ComboBox', 'CompoundGUI') for _, kind, _, _ in ui.events))
                self.assertEqual(settings['selected_paras']['KY_ONLY'], [0.])
                self.assertEqual(list(settings['cgyro_multi']['KY_ONLY']['values']), labels)

    def test_index_roundtrip_unchanged_and_unselected_payload_never_read(self):
        class Untouched(dict):
            def keys(self):
                raise AssertionError('unselected result was opened')
            def items(self):
                raise AssertionError('unselected metadata was traversed')
        case = ky_case((24, 32))
        before = copy.deepcopy(case)
        reopened = json.loads(json.dumps(case))
        reopened['Other'] = Untouched()
        reopened['__SCANS__']['Other'] = dict(info={}, tasks=Untouched())
        curves, errors = all_curves(reopened, {'KY_ONLY': dict(ky_only=True, values={'N_THETA': [32]})})
        self.assertFalse(errors)
        self.assertEqual(len(curves), 1)
        self.assertEqual(case, before)


if __name__ == '__main__':
    unittest.main()
