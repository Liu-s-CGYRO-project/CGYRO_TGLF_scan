"""Convergence plots join only proven RUN_DB point references, without readers."""
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'CGYRO_TGLF_scan/LIB'))
from OMFITlib_compare_convergence import convergence_case_view, convergence_groups


BASE = {'N_ENERGY': 32, 'N_XI': 48, 'N_RADIAL': 32, 'N_THETA': 32, 'E_MAX': 8}
PHYSICS = dict(BASE, BETAE_UNIT=.0001, ERROR_TOL=1e-4, FREQ_TOL=1e-3,
               DELTA_T=.01, DELTA_T_METHOD=1, MASS_2=2, MAX_TIME=1200)


def add_scan(case, branch, axis, values, requested, *, baseline=None, fixed=None,
             role='direction', kys=(.5,), physics=None, token=None):
    """All branches intentionally reuse p000001 and need full coordinates."""
    token = token or branch
    context = dict(parameter=axis, baseline=dict(baseline or BASE),
                   fixed=dict(fixed or {}), requested=list(requested), role=role)
    info = dict(runid='Jet_convergence', case_id='nr=1__rho=0.33__ion=T',
                source_nr=1, rho=.33, ion_case='T', run_token=token,
                scan_axes=[dict(name=axis)], parameters=[branch],
                fixed_parameters=dict(fixed or {}), convergence_group=context)
    tasks = {}
    rows = case.setdefault(branch, {})
    for value in values:
        for ky in kys:
            parameters = dict(physics or PHYSICS, **dict(fixed or {}), **{axis: value, 'KY': ky})
            path = [branch, str(value), 'lin', str(ky)]
            # This is an inert owner reference; touching its optional browser
            # expression or loading the actual result is not needed here.
            digest = format(sum(len(scan['tasks']) for scan in case.get('__SCANS__', {}).values()) + len(tasks) + 1, '064x')
            ref = {'__RESULT_REF__': digest}
            rows.setdefault(str(value), {}).setdefault('lin', {})[str(ky)] = ref
            tasks['p%06d' % (len(tasks) + 1)] = dict(result_path=path,
                coordinate_path=[axis, str(value), 'lin', str(ky)],
                values={axis: value, 'KY': ky}, run_token=token,
                result_info=copy.deepcopy(info), input_parameters=parameters,
                input_parameter_source='input.cgyro.gen')
    case.setdefault('__SCANS__', {})[branch] = {'info': info, 'tasks': tasks}
    return tasks


def fixture():
    case = {}
    add_scan(case, 'Base case', 'N_ENERGY', [32], [32], role='baseline', kys=(-.5, .5))
    add_scan(case, 'N_ENERGY', 'N_ENERGY', [48, 64], [32, 48, 64], kys=(-.5, .5))
    add_scan(case, 'N_XI', 'N_XI', [32, 64], [48, 32, 64], kys=(-.5, .5))
    add_scan(case, 'E_MAX', 'E_MAX', [10, 12], [8, 10, 12], fixed={'N_ENERGY': 64}, kys=(-.5, .5))
    return case


def token_for(case, axis):
    return next(key for key, group in convergence_groups(case).items() if group['axis'] == axis)


def scaled_fixture():
    case = {}
    add_scan(case, 'Base case', 'N_ENERGY', [32], [32], role='baseline', kys=(.5, 2.))
    add_scan(case, 'N_XI', 'N_XI', [32], [48, 32], kys=(.5, 2.))
    for entry in case['__SCANS__'].values():
        entry['info'].update(scale_time_with_ky=True, fixed_parameters={'DELTA_T': .01})
        for row in entry['tasks'].values():
            row['result_info'].update(scale_time_with_ky=True, fixed_parameters={'DELTA_T': .01})
            step = .01 / max(1, row['input_parameters']['KY'])
            row['effective_time'] = {'DELTA_T': step}
            row['input_parameters']['DELTA_T'] = step
    return case


class ConvergenceReferenceTests(unittest.TestCase):
    def test_metadata_groups_are_directions_not_cartesian_axes(self):
        case = fixture()
        class NoPayload(dict):
            def __getitem__(self, key):
                if key != '__SCANS__':
                    raise AssertionError('payload accessed while building options')
                return super().__getitem__(key)
        groups = convergence_groups(NoPayload(case))
        self.assertEqual({group['axis'] for group in groups.values()}, {'N_ENERGY', 'N_XI', 'E_MAX'})
        self.assertEqual(groups[token_for(case, 'N_XI')]['coordinate_names'], ['N_XI'])
        self.assertEqual(groups[token_for(case, 'N_XI')]['values'], [48, 32, 64])
        self.assertIn('N_ENERGY=64', groups[token_for(case, 'E_MAX')]['label'])

    def test_baseline_shared_by_complete_physics_and_signed_ky(self):
        case = fixture()
        view, selected, metadata, diagnostics = convergence_case_view(case, {token_for(case, 'N_XI'): [32, 64]})
        self.assertEqual(selected, {token_for(case, 'N_XI'): [48, 32, 64]})
        self.assertEqual(diagnostics, [])
        self.assertEqual(metadata[token_for(case, 'N_XI')]['baseline_value'], 48)
        for ky in (-.5, .5):
            self.assertIs(view[token_for(case, 'N_XI')][48]['lin'][ky], case['Base case']['32']['lin'][str(ky)])
        self.assertNotEqual(view[token_for(case, 'N_XI')][48]['lin'][-.5], view[token_for(case, 'N_XI')][48]['lin'][.5])

    def test_energy_limit_uses_ne64_baseline_not_global_center(self):
        case = fixture()
        view, _, _, diagnostics = convergence_case_view(case, {token_for(case, 'E_MAX'): [10, 12]})
        self.assertEqual(diagnostics, [])
        self.assertIs(view[token_for(case, 'E_MAX')][8]['lin'][.5], case['N_ENERGY']['64']['lin']['0.5'])
        self.assertIsNot(view[token_for(case, 'E_MAX')][8]['lin'][.5], case['Base case']['32']['lin']['0.5'])

    def test_runtime_duration_does_not_change_physical_baseline_identity(self):
        case = fixture()
        for row in case['__SCANS__']['Base case']['tasks'].values():
            row['input_parameters'].update(MAX_TIME=600, PRINT_STEP=200, FIELD_PRINT_FLAG=0)
        view, _, _, diagnostics = convergence_case_view(case, {token_for(case, 'N_XI'): [32]})
        self.assertEqual(diagnostics, [])
        self.assertEqual(len(view[token_for(case, 'N_XI')][48]['lin']), 2)

    def test_ky_scaled_effective_step_keeps_one_group_and_matches_baseline(self):
        case = scaled_fixture()
        groups = convergence_groups(case)
        self.assertEqual(len(groups), 1)
        token = next(iter(groups))
        view, _, _, diagnostics = convergence_case_view(case, {token: [32]})
        self.assertEqual(diagnostics, [])
        self.assertEqual(set(view[token][48]['lin']), {.5, 2.})
        self.assertEqual(set(view[token][32]['lin']), {.5, 2.})
        self.assertIs(view[token][48]['lin'][2.], case['Base case']['32']['lin']['2.0'])

    def test_ky_scaling_does_not_allow_generated_step_to_disagree_with_effective_step(self):
        case = scaled_fixture()
        for row in case['__SCANS__']['Base case']['tasks'].values():
            if row['input_parameters']['KY'] == 2.:
                row['input_parameters']['DELTA_T'] = .006
        token = token_for(case, 'N_XI')
        view, _, _, diagnostics = convergence_case_view(case, {token: [32]})
        self.assertEqual(set(view[token][48]['lin']), {.5})
        self.assertEqual(set(view[token][32]['lin']), {.5, 2.})
        self.assertTrue(any('基准' in text and 'KY=2.0' in text for text in diagnostics))

    def test_tolerance_direction_uses_its_original_requested_center(self):
        case = fixture()
        add_scan(case, 'ERROR_TOL', 'ERROR_TOL', [1e-5], [1e-4, 1e-5], kys=(-.5, .5))
        view, choices, _, diagnostics = convergence_case_view(case, {token_for(case, 'ERROR_TOL'): [1e-5]})
        self.assertEqual(diagnostics, [])
        self.assertEqual(choices[token_for(case, 'ERROR_TOL')], [1e-4, 1e-5])
        self.assertIs(view[token_for(case, 'ERROR_TOL')][1e-4]['lin'][.5], case['Base case']['32']['lin']['0.5'])

    def test_regular_untagged_scan_remains_regular(self):
        case = fixture()
        for entry in case['__SCANS__'].values():
            entry['info'].pop('convergence_group')
            for row in entry['tasks'].values():
                row['result_info'].pop('convergence_group')
        self.assertEqual(convergence_groups(case), {})

    def test_different_frozen_physics_never_join_or_cartesian_expand(self):
        case = fixture()
        add_scan(case, 'N_XI_other', 'N_XI', [32, 64], [48, 32, 64],
                 physics=dict(PHYSICS, BETAE_UNIT=.002))
        groups = convergence_groups(case)
        xi = [group for group in groups.values() if group['axis'] == 'N_XI']
        self.assertEqual(len(xi), 2)
        self.assertTrue(all(group['coordinate_names'] == ['N_XI'] for group in xi))
        self.assertEqual({group['label'] for group in xi},
                         {'俯仰角分辨率（BETAE_UNIT=0.0001）', '俯仰角分辨率（BETAE_UNIT=0.002）'})
        view, _, _, diagnostics = convergence_case_view(case)
        other = next(group['token'] for group in xi if group['_rows'][0][2]['BETAE_UNIT'] == .002)
        self.assertFalse(view[other][48]['lin'])
        self.assertTrue(any('BETAE_UNIT=0.002' in text and '基准' in text for text in diagnostics))

    def test_family_token_remains_stable_when_other_physics_or_ky_arrive(self):
        case = fixture()
        original = token_for(case, 'N_XI')
        add_scan(case, 'N_XI_other', 'N_XI', [32], [48, 32], physics=dict(PHYSICS, BETAE_UNIT=.002))
        add_scan(case, 'N_XI_more', 'N_XI', [24, 32], [48, 24, 32], kys=(.6,))
        groups = convergence_groups(case)
        self.assertIn(original, groups)
        self.assertEqual(groups[original]['axis'], 'N_XI')
        self.assertIn(24, groups[original]['values'])

    def test_wrong_radius_or_ion_cannot_supply_baseline(self):
        for change in ({'rho': .34, 'case_id': 'nr=1__rho=0.34__ion=T'},
                       {'ion_case': 'D', 'case_id': 'nr=1__rho=0.33__ion=D'}):
            with self.subTest(change=change):
                case = fixture()
                for row in case['__SCANS__']['Base case']['tasks'].values():
                    row['result_info'].update(change)
                view, _, _, diagnostics = convergence_case_view(case, {token_for(case, 'N_XI'): [32]})
                self.assertFalse(view[token_for(case, 'N_XI')][48]['lin'])
                self.assertTrue(diagnostics)
                self.assertEqual(len(view[token_for(case, 'N_XI')][32]['lin']), 2)

    def test_duplicate_owner_alias_is_accepted_but_conflicting_owner_is_not(self):
        case = fixture()
        tasks = add_scan(case, 'alias', 'N_ENERGY', [32], [32], role='baseline', kys=(-.5, .5))
        for ky in (-.5, .5):
            case['alias']['32']['lin'][str(ky)] = dict(case['Base case']['32']['lin'][str(ky)])
        view, _, _, diagnostics = convergence_case_view(case, {token_for(case, 'N_XI'): [32]})
        self.assertEqual(diagnostics, [])
        self.assertEqual(len(view[token_for(case, 'N_XI')][48]['lin']), 2)
        case['alias']['32']['lin']['0.5'] = {'__RESULT_REF__': 'f' * 64}
        view, _, _, diagnostics = convergence_case_view(case, {token_for(case, 'N_XI'): [32]})
        self.assertNotIn(.5, view[token_for(case, 'N_XI')][48]['lin'])
        self.assertIn(-.5, view[token_for(case, 'N_XI')][48]['lin'])
        self.assertTrue(any('不同结果引用' in text for text in diagnostics))

    def test_unselected_direction_payload_is_not_touched(self):
        case = fixture()
        class Forbidden(dict):
            def __getitem__(self, key):
                raise AssertionError('unselected payload read')
        case['E_MAX'] = Forbidden()
        case['N_ENERGY'] = Forbidden()
        view, _, _, diagnostics = convergence_case_view(case, {token_for(case, 'N_XI'): [32]})
        self.assertEqual(diagnostics, [])
        self.assertEqual(set(view), {token_for(case, 'N_XI')})
        self.assertEqual(convergence_case_view(case, {})[0], {})

    def test_missing_baseline_file_reference_does_not_drop_valid_curves(self):
        case = fixture()
        del case['Base case']['32']['lin']['0.5']
        view, _, _, diagnostics = convergence_case_view(case, {token_for(case, 'N_XI'): [32]})
        self.assertNotIn(.5, view[token_for(case, 'N_XI')][48]['lin'])
        self.assertEqual(len(view[token_for(case, 'N_XI')][32]['lin']), 2)
        self.assertTrue(any('基准' in text and 'KY=0.5' in text for text in diagnostics))

    def test_partial_direction_keeps_available_baseline_at_missing_ky(self):
        case = fixture()
        tasks = case['__SCANS__']['N_XI']['tasks']
        for point in list(tasks):
            if tasks[point]['input_parameters']['KY'] == -.5:
                tasks.pop(point)
        view, _, _, diagnostics = convergence_case_view(case, {token_for(case, 'N_XI'): [32]})
        self.assertEqual(set(view[token_for(case, 'N_XI')][48]['lin']), {-.5, .5})
        self.assertEqual(set(view[token_for(case, 'N_XI')][32]['lin']), {.5})
        self.assertTrue(any('扫描 N_XI=32.0 / KY=-0.5' in text for text in diagnostics))

    def test_missing_generated_input_summary_does_not_guess_baseline(self):
        case = fixture()
        for row in case['__SCANS__']['Base case']['tasks'].values():
            row.pop('input_parameters')
        view, _, _, diagnostics = convergence_case_view(case, {token_for(case, 'N_XI'): [32]})
        self.assertFalse(view[token_for(case, 'N_XI')][48]['lin'])
        self.assertTrue(diagnostics)

    def test_inconsistent_generated_input_cannot_supply_coordinate(self):
        case = fixture()
        for row in case['__SCANS__']['Base case']['tasks'].values():
            row['input_parameters']['N_ENERGY'] = 64
        view, _, _, diagnostics = convergence_case_view(case, {token_for(case, 'N_XI'): [32]})
        self.assertFalse(view[token_for(case, 'N_XI')][48]['lin'])
        self.assertTrue(diagnostics)

    def test_legacy_header_does_not_retag_old_untagged_retained_point(self):
        case = fixture()
        row = next(iter(case['__SCANS__']['N_XI']['tasks'].values()))
        row['result_info'].pop('convergence_group')
        row['run_token'] = 'older-ordinary-run'
        self.assertEqual(len(convergence_groups(case)[token_for(case, 'N_XI')]['_rows']), 3)

    def test_json_save_reopen_preserves_groups_and_joined_references(self):
        original = fixture()
        reopened = json.loads(json.dumps(original))
        first = convergence_case_view(original)
        second = convergence_case_view(reopened)
        self.assertEqual(first, second)


if __name__ == '__main__':
    unittest.main()
