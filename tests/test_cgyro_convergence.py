"""One-variable plans use ordinary CGYRO jobs, immutable inputs and RUN_DB."""
import copy
import ast
import hashlib
import itertools
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import test_cgyro_storage  # Isolated native file adapters.
import test_project as project_tests
import OMFITlib_cgyro_convergence as convergence
import OMFITlib_cgyro_plan as plans
from OMFITlib_project_ui import ProjectUI
import OMFITlib_cgyro_archive as archive
from OMFITlib_cgyro_parameters import apply_parameters
from OMFITlib_cgyro_read import num2str_xj
from OMFITlib_compare_convergence import convergence_case_view
from OMFITlib_cgyro_scan_values import AXIS_KEYS, ky_values, scan_axes
import numpy as np


class UnreadResults(dict):
    def __getitem__(self, key):
        raise AssertionError('Result read during convergence planning')
    def __iter__(self):
        raise AssertionError('Result traversal during convergence planning')
    keys = values = items = __iter__


def fixture():
    source = project_tests.cgyro()
    source.update(N_ENERGY=32, N_XI=48, N_RADIAL=32, N_THETA=32, E_MAX=8,
                  ERROR_TOL=1e-4, FREQ_TOL=1e-3, MAX_TIME=1200, KY=.1, rho=.33)
    physics = dict(scan_mode='convergence', kyarr=[i / 10 for i in range(1, 8)],
                   fixed_parameters={}, scale_time_with_ky=False)
    convergence.initialize(physics, source)
    # Retain the original user-specified 77-point plan independently of GUI defaults.
    physics['convergence']['groups']['N_ENERGY']['values'] = [32, 48, 64]
    return source, physics


def indexed_group(module, runid, caseid, source, controls, values=None, group=None):
    """Persist only the existing index contract; owners explode if inspected."""
    parameter = controls['1d']['Para']
    values = controls['1d']['Range'] if values is None else values
    case, tasks = {}, {}
    for value in values:
        for ky in ky_values(controls):
            requested = {key: number for key, number in source.items() if str(key).isupper()}
            requested.update({parameter: value, 'KY': ky, 'NONLINEAR_FLAG': 0})
            if controls.get('scale_time_with_ky', False) and ky > 1:
                for name in ('DELTA_T', 'MAX_TIME'):
                    requested[name] /= ky
            owner = hashlib.sha256(json.dumps(requested, sort_keys=True).encode()).hexdigest()
            module['RUN_DB'].setdefault('__STORE__', {})[owner] = UnreadResults()
            path = [parameter, str(value), 'lin', str(ky)]
            case.setdefault(parameter, {}).setdefault(str(value), {}).setdefault('lin', {})[str(ky)] = {
                '__RESULT_REF__': owner}
            point = 'p{:06d}'.format(len(tasks) + 1)
            tasks[point] = dict(result_path=path, values={parameter: value, 'KY': ky},
                input_parameter_source='input.cgyro.gen', input_requested_parameters=requested,
                input_parameters={key: number for key, number in requested.items()
                                  if key not in archive.RUN_CONTROL_PARAMETERS},
                result_summary=dict(version=1, result_id=owner, solver_status='max_time',
                                    final_time=1200., sample_count=120001))
    info = dict(runid=runid, case_id=caseid, source_nr=1, rho=.33, ion_case='BASE',
                dimensions=1, scan_dimensions=1, scan_axes=[dict(name=parameter, values=list(values), linked=[])])
    if group is not None:
        info['convergence_group'] = group
    archive.store_scan(case, case, info, tasks)
    destination = module['RUN_DB'].setdefault(runid, {}).setdefault(caseid, {})
    destination.update(archive.combine_cases([destination, case]))
    return destination['__SCANS__'][archive.scan_key(info)]['tasks']


class ConvergenceTests(unittest.TestCase):
    def test_range_defaults_follow_the_current_grid_and_keep_integer_candidates(self):
        for name, center, expected in (
                ('N_ENERGY', 16, [12, 16, 20]), ('N_ENERGY', 32, [24, 32, 40]),
                ('N_XI', 48, [32, 48, 64]),
                ('N_RADIAL', 24, [18, 24, 36]), ('N_THETA', 32, [24, 32, 48]),
                ('N_RADIAL', 26, [20, 26, 40]), ('E_MAX', 10, [10, 12.5, 15])):
            with self.subTest(parameter=name, center=center):
                values = convergence.default_values(name, center)
                self.assertEqual(values, expected)
                if name != 'E_MAX':
                    self.assertTrue(all(type(value) is int for value in values))

    def test_energy_defaults_bracket_small_centers_without_zero_or_duplicates(self):
        for center in (1, 2, 3, 4, 5, 16, 48, 64):
            with self.subTest(center=center):
                values = convergence.default_values('N_ENERGY', center)
                self.assertIn(center, values)
                self.assertGreater(values[-1], center)
                if center > 1:
                    self.assertLess(values[0], center)
                self.assertTrue(all(type(value) is int and value > 0 for value in values))
                self.assertEqual(values, sorted(set(values)))

    def test_new_defaults_keep_the_conditional_energy_limit_baseline(self):
        source, physics = fixture()
        del physics['convergence']
        convergence.initialize(physics, source)
        self.assertEqual(physics['convergence']['groups']['N_ENERGY']['values'], [24, 32, 40])
        jobs = convergence.jobs(physics, source, 1, '1')
        energy_limit = next(job for job in jobs if job['convergence_group']['parameter'] == 'E_MAX')
        self.assertEqual(energy_limit['physics']['1d']['Range'], [8, 10, 12])
        self.assertEqual(energy_limit['physics']['fixed_parameters']['N_ENERGY']['value'], 64)
        self.assertEqual(sum(len(job['physics']['1d']['Range']) for job in jobs), 12)

    def test_baseline_edit_regenerates_only_its_direction_without_reading_input_or_results(self):
        source, physics = fixture()
        config = physics['convergence']
        previous = copy.deepcopy(config['groups'])
        config['baseline']['N_ENERGY'] = 16
        self.assertTrue(convergence.sync_values(physics, 'N_ENERGY', UnreadResults({'forbidden': 1})))
        self.assertEqual(config['groups']['N_ENERGY']['values'], [12, 16, 20])
        for name in convergence.DIRECTIONS:
            expected = previous[name]
            if name == 'N_ENERGY':
                expected['values'] = [12, 16, 20]
            self.assertEqual(config['groups'][name], expected)

    def test_manual_range_survives_baseline_changes_and_auto_can_be_restored(self):
        source, physics = fixture()
        config = physics['convergence']
        group = config['groups']['N_ENERGY']
        group.update(auto_values=False, values=[12, 24, 60], fixed={'E_MAX': 10})
        config['baseline']['N_ENERGY'] = 48
        self.assertFalse(convergence.sync_values(physics, 'N_ENERGY', source))
        self.assertEqual(group['values'], [12, 24, 60])
        reopened = json.loads(json.dumps(physics))
        convergence.initialize(reopened, source)
        self.assertFalse(reopened['convergence']['groups']['N_ENERGY']['auto_values'])
        self.assertEqual(reopened['convergence']['groups']['N_ENERGY']['values'], [12, 24, 60])
        group['auto_values'] = True
        self.assertTrue(convergence.sync_values(physics, 'N_ENERGY', source))
        self.assertEqual(group['values'], [36, 48, 60])
        self.assertEqual(group['fixed'], {'E_MAX': 10})

    def test_invalid_baseline_does_not_replace_any_direction_values(self):
        source, physics = fixture()
        previous = copy.deepcopy(physics['convergence']['groups'])
        for value in (0, -2, 32.5, float('nan')):
            with self.subTest(value=value):
                physics['convergence']['baseline']['N_ENERGY'] = value
                with self.assertRaises(ValueError):
                    convergence.sync_values(physics, 'N_ENERGY', source)
                self.assertEqual(physics['convergence']['groups'], previous)

    def test_previous_five_directions_are_eleven_configs_and_77_points(self):
        source, physics = fixture()
        groups = convergence.groups(physics, source)
        self.assertEqual(sum(len(group['values']) for group in groups), 11)
        self.assertEqual(sum(len(group['values']) for group in groups) * 7, 77)
        self.assertEqual(groups[-1]['values'], [10, 12])
        self.assertEqual(groups[-1]['fixed'], {'N_ENERGY': 64})
        self.assertEqual(groups[-1]['shared'], [dict(value=8, group='N_ENERGY')])

    def test_only_one_variable_changes_and_each_group_baseline_is_included(self):
        source, physics = fixture()
        baseline = physics['convergence']['baseline']
        for group in convergence.groups(physics, source):
            self.assertIn(baseline.get(group['parameter'], source[group['parameter']]), group['requested'])
            fixed = group['physics']['fixed_parameters']
            for name, value in baseline.items():
                self.assertEqual(fixed[name]['value'], group['fixed'].get(name, value))
            self.assertEqual(group['physics']['1d'], dict(Para=group['parameter'], Range=group['values']))

    def test_precision_direction_is_optional(self):
        source, physics = fixture()
        physics['convergence']['groups']['ERROR_TOL']['enabled'] = True
        groups = convergence.groups(physics, source)
        self.assertEqual(sum(len(group['values']) for group in groups), 12)
        self.assertEqual(groups[-1]['values'], [1e-5])

    def test_identical_parameter_values_are_deduplicated(self):
        source, physics = fixture()
        physics['convergence']['groups']['N_ENERGY']['values'] = [32, 48, 32, 64, 48]
        self.assertEqual(convergence.groups(physics, source)[0]['values'], [32, 48, 64])

    def test_storage_names_and_baseline_job_do_not_duplicate_configurations(self):
        source, physics = fixture()
        jobs = convergence.jobs(physics, source, 1, '1')
        self.assertEqual(convergence.archive_runid('Jet'), 'Jet_convergence')
        self.assertEqual(convergence.archive_runid('Jet_convergence'), 'Jet_convergence')
        configurations = []
        for job in jobs:
            controls = job['physics']
            fixed = {name: item['value'] for name, item in controls['fixed_parameters'].items()
                     if item.get('enabled', False)}
            for value in controls['1d']['Range']:
                configurations.append(tuple(sorted(dict(fixed, **{controls['1d']['Para']: value}).items())))
        self.assertEqual(len(configurations), len(set(configurations)))
        self.assertEqual(jobs[0]['physics']['1d']['Range'], [32])
        self.assertEqual(jobs[1]['physics']['1d']['Range'], [48, 64])
        self.assertEqual(jobs[-1]['physics']['1d']['Range'], [10, 12])

    def test_formatted_extra_fixed_center_is_owned_once_by_base_case(self):
        source, physics = fixture()
        physics['convergence']['groups']['N_THETA']['fixed'] = {'E_MAX': 8.0000000001}
        before = copy.deepcopy(physics)
        jobs = convergence.jobs(physics, source, 1, '1')
        self.assertEqual(sum(len(job['physics']['1d']['Range']) for job in jobs), 11)
        theta = next(job for job in jobs if job['convergence_group']['storage_branch'] == 'N_THETA')
        self.assertEqual(theta['physics']['1d']['Range'], [24, 48])
        self.assertIn(dict(value=32, group='Base case'), theta['convergence_group']['shared'])
        self.assertEqual(physics, before)

    def test_float_axis_center_drift_does_not_schedule_a_duplicate(self):
        source, physics = fixture()
        group = physics['convergence']['groups']['ERROR_TOL']
        group.update(enabled=True, values=[1e-4 + 1e-14, 1e-5])
        jobs = convergence.jobs(physics, source, 1, '1')
        precision = next(job for job in jobs if job['convergence_group']['parameter'] == 'ERROR_TOL')
        self.assertEqual(precision['physics']['1d']['Range'], [1e-5])
        self.assertIn(dict(value=1e-4, group='Base case'), precision['convergence_group']['shared'])

    def test_distinct_extra_fixed_physics_is_not_absorbed_into_base(self):
        source, physics = fixture()
        physics['convergence']['groups']['N_THETA']['fixed'] = {'E_MAX': 8.0001}
        jobs = convergence.jobs(physics, source, 1, '1')
        theta = next(job for job in jobs if job['convergence_group']['storage_branch'] == 'N_THETA')
        self.assertIn(32, theta['physics']['1d']['Range'])
        self.assertNotIn(dict(value=32, group='Base case'), theta['convergence_group']['shared'])

    def test_invalid_grid_and_conflicting_extra_are_rejected(self):
        for name, value in [('N_ENERGY', 1.5), ('N_XI', 0), ('E_MAX', float('nan'))]:
            with self.subTest(name=name):
                source, physics = fixture()
                physics['convergence']['baseline'][name] = value
                with self.assertRaises(ValueError):
                    convergence.groups(physics, source)
        source, physics = fixture()
        physics['convergence']['groups']['N_ENERGY']['fixed'] = {'N_ENERGY': 64}
        with self.assertRaisesRegex(ValueError, '同时扫描并固定'):
            convergence.groups(physics, source)

    def test_source_and_ordinary_axes_survive_plan_and_settings_roundtrip(self):
        source, physics = fixture()
        physics['2d'] = dict(Para_x='Q', Range_x=[1, 2])
        before_source, before_physics = copy.deepcopy(source), copy.deepcopy(physics)
        jobs = convergence.jobs(json.loads(json.dumps(physics)), source, 2, 'scheme:1')
        self.assertEqual(len(jobs), 6)
        self.assertTrue(all(job['dimensions'] == 1 for job in jobs))
        self.assertEqual(source, before_source)
        self.assertEqual(physics, before_physics)
        self.assertEqual(jobs[0]['batch_key'], 'scheme:1:convergence:Base case')
        self.assertEqual(jobs[0]['convergence_group']['role'], 'baseline')
        self.assertEqual(sum(len(job['physics']['1d']['Range']) for job in jobs), 11)

    def test_native_point_generation_is_unique_and_keeps_every_full_grid_coordinate(self):
        path = project_tests.REPO / 'CGYRO_TGLF_scan/CGYRO_scan/SCRIPTS/subscan_lin.py'
        definitions = [node for node in ast.parse(path.read_text(encoding='utf-8')).body
                       if isinstance(node, ast.FunctionDef) and node.name in
                       ('json_scalar', 'configured_axes', 'scan_points')]
        scope = dict(np=np, itertools=itertools, re=convergence.re, num2str_xj=num2str_xj,
                     AXIS_KEYS=AXIS_KEYS, resolved_scan_axes=scan_axes, ky_values=ky_values)
        exec(compile(ast.Module(body=definitions, type_ignores=[]), str(path), 'exec'), scope)
        source, physics = fixture()
        unique = set()
        for group in convergence.groups(physics, source):
            value = copy.deepcopy(source)
            apply_parameters(value, group['physics'], 1)
            points, axes = scope['scan_points'](group['physics'], 1, 5, value)
            for point, overrides, metadata in points:
                current = dict(value, **overrides)
                key = tuple(current[name] for name in list(convergence.BASELINE) + ['KY'])
                self.assertNotIn(key, unique)
                unique.add(key)
            selected = [list((points[0][1][group['parameter']], points[0][1]['KY'])),
                        list((points[-1][1][group['parameter']], points[-1][1]['KY']))]
            subset, _ = scope['scan_points'](group['physics'], 1, 5, value, selected=selected)
            self.assertEqual(len(subset), 2)
            self.assertEqual([item[0] for item in subset], ['p000001', 'p000002'])
            with self.assertRaisesRegex(ValueError, 'disagree'):
                scope['scan_points'](group['physics'], 1, 5, value, selected=[[9999, .1]])
        self.assertEqual(len(unique), 77)


class ConvergenceProjectTests(unittest.TestCase):
    def setUp(self):
        self.host = project_tests.ProjectTest()
        self.host.setUp()
        self.host.send()
        self.host.configure()
        for name in ('root', 'actions', 'cg', 'transfer'):
            setattr(self, name, getattr(self.host, name))
        source, physics = fixture()
        self.transfer['Transfer_file']['input.cgyro'].update(source)
        self.cg['SETTINGS']['PHYSICS'].update(physics)
        self.cg['RUN_DB']['untouched'] = UnreadResults()

    def test_batch_prepares_six_groups_for_one_array_without_result_reads(self):
        plan = self.actions.run_cgyro(prepare=True)
        summary = plans.cgyro_plan_summary(self.root)
        self.assertEqual(len(plan), 6)
        self.assertEqual(summary['total_points'], 77)
        self.assertEqual((summary['jobs'], summary['group_count'], summary['array_points']), (1, 6, 77))
        self.assertEqual([row['convergence_group']['storage_branch'] for row in plan], ['Base case'] + list(convergence.DIRECTIONS)[:-1])
        self.assertTrue(all(row['runid'] == 'test_convergence' for row in plan))
        self.cg['SCRIPTS']['runCGYRO.py'].run.assert_not_called()

    def test_submission_installs_first_group_and_passes_whole_plan_once_then_restores_editor(self):
        self.actions.run_cgyro(prepare=True)  # Initialize the ordinary parameter catalogue first.
        physics = self.cg['SETTINGS']['PHYSICS']
        setup = self.cg['SETTINGS']['SETUP']
        original_controls = copy.deepcopy({key: physics.get(key) for key in ('1d', '2d', 'fixed_parameters')})
        original_dimension = setup['idimrun']
        original_input = self.cg['INPUTS']['input.cgyro']
        def submit(**kwargs):
            self.assertEqual(setup['idimrun'], 1)
            self.assertEqual(physics['1d']['Para'], 'N_ENERGY')
            self.assertNotIn('convergence_group', kwargs)
            plan = kwargs['convergence_plan']
            self.assertEqual([item['convergence_group']['storage_branch'] for item in plan],
                             ['Base case'] + list(convergence.DIRECTIONS)[:-1])
            self.assertEqual(sum(len(item['convergence_group']['submit_coordinates']) for item in plan), 77)
            for item in plan:
                source = self.cg['BATCH_INPUTS'][item['batch_key']][item['ion_case']]
                if item['convergence_group']['parameter'] == 'E_MAX':
                    self.assertEqual(source['N_ENERGY'], 64)
            self.cg['RUN_MANIFEST'] = dict(status='published')
        self.cg['SCRIPTS']['runCGYRO.py'].run.side_effect = submit
        self.assertEqual(len(self.actions.run_cgyro()), 1)
        self.cg['SCRIPTS']['runCGYRO.py'].run.assert_called_once()
        self.assertEqual(setup['idimrun'], original_dimension)
        self.assertIs(self.cg['INPUTS']['input.cgyro'], original_input)
        self.assertEqual({key: physics.get(key) for key in original_controls}, original_controls)

    def test_two_radii_and_two_ions_submit_and_collect_four_case_arrays(self):
        source = self.transfer['Transfer_file']['input.cgyro']
        profiles = {name: source.duplicate() for name in ('input.cgyro_1', 'input.cgyro_2')}
        profiles['input.cgyro_2']['rho'] = .5
        self.transfer['SETTINGS']['PHYSICS'].setdefault('generation', {}).update(minimum=.33, maximum=.5)
        self.transfer.setdefault('OUTPUTS', {}).update(Profiles_gen=profiles,
            Particle_processing=dict(main_count=1, options=plans.particle_options(
                self.transfer['SETTINGS']['PHYSICS'].get('generation', {}))))
        self.actions.settings.update(cgyro_source_mode='generated',
            cgyro_ion_cases=dict(BASE=True, H=False, D=False, T=True))
        config = self.cg['SETTINGS']['REMOTE_SETUP']['localhost']
        config.update(scheduler='slurm', array_parallel=3, nodes=2, ntasks_per_node=16, cpus_per_task=2)
        original_config = copy.deepcopy(config)
        preview = self.actions.preview_cgyro_convergence()
        self.assertEqual((preview['jobs'], preview['group_count'], preview['array_points']), (4, 24, 308))
        submitted, collected = [], []
        def submit(**kwargs):
            plan = kwargs['convergence_plan']
            identity = (plan[0]['nr'], plan[0]['ion_case'])
            self.assertEqual({(item['nr'], item['ion_case']) for item in plan}, {identity})
            self.assertNotIn(identity, submitted)
            self.assertEqual(len(plan), 6)
            self.assertEqual(sum(len(item['convergence_group']['submit_coordinates']) for item in plan), 77)
            self.assertEqual(len(self.cg['RUN_BATCH']['case_ids']), 4)
            self.assertFalse(kwargs['wait_for_completion'])
            self.assertEqual(kwargs['check_temp_start'], not submitted)
            submitted.append(identity)
            token = 'combined-' + str(len(submitted))
            manifest = dict(status='submitted', run_token=token, case_id=plan[0]['case_id'],
                            job_id=str(1000 + len(submitted)), batch_id=kwargs['batch_id'])
            self.cg['RUN_MANIFEST'] = manifest
            self.cg.setdefault('RUN_HISTORY', {})[token] = dict(manifest=copy.deepcopy(manifest))
            self.cg['RUN_BATCH']['tokens'].append(token)
        def collect(**kwargs):
            self.assertEqual(len(submitted), 4)
            token = self.cg['RUN_MANIFEST']['run_token']
            self.assertNotIn(token, collected)
            collected.append(token)
            self.cg['RUN_MANIFEST']['status'] = 'published'
        def activate(node, token):
            node['RUN_MANIFEST'] = copy.deepcopy(node['RUN_HISTORY'][token]['manifest'])
        def save(node, factory):
            manifest = node['RUN_MANIFEST']
            node['RUN_HISTORY'][manifest['run_token']]['manifest'] = copy.deepcopy(manifest)
        self.cg['SCRIPTS']['runCGYRO.py'].run.side_effect = submit
        self.cg['SCRIPTS']['CGYROScan.py'].run.side_effect = collect
        with patch.object(project_tests.project, 'runtime_issues', return_value=[]), \
                patch('OMFITlib_cgyro_workflow.activate_run', side_effect=activate), \
                patch('OMFITlib_cgyro_workflow.save_current', side_effect=save):
            self.assertEqual(len(self.actions.run_cgyro()), 4)
        self.assertEqual(set(submitted), {(1, 'BASE'), (1, 'T'), (2, 'BASE'), (2, 'T')})
        self.assertEqual(self.cg['SCRIPTS']['runCGYRO.py'].run.call_count, 4)
        self.assertEqual(self.cg['SCRIPTS']['CGYROScan.py'].run.call_count, 4)
        self.assertEqual(self.cg['SCRIPTS']['wait_current_run.py'].run.call_count, 4)
        self.assertEqual(len(collected), 4)
        self.assertEqual(config, original_config)

    def test_combined_submission_excludes_every_reused_point(self):
        original = self.index_plan()[0]
        tasks = self.cg['RUN_DB']['test_convergence'][original['case_id']]['__SCANS__']['Base case']['tasks']
        next(iter(tasks.values()))['result_summary']['final_time'] = 600.
        preview = self.actions.preview_cgyro_convergence()
        self.assertEqual((preview['jobs'], preview['array_points'], preview['pending_groups']), (1, 1, 1))
        def submit(**kwargs):
            self.assertEqual(len(kwargs['convergence_plan']), 1)
            self.assertEqual(kwargs['convergence_plan'][0]['convergence_group']['submit_coordinates'], [[32, .1]])
            self.cg['RUN_MANIFEST'] = dict(status='published')
        self.cg['SCRIPTS']['runCGYRO.py'].run.side_effect = submit
        self.actions.run_cgyro()
        self.cg['SCRIPTS']['runCGYRO.py'].run.assert_called_once()

    def test_ordinary_scan_still_submits_each_ion_separately(self):
        self.cg['SETTINGS']['PHYSICS']['scan_mode'] = 'regular'
        self.actions.settings['cgyro_ion_cases'] = dict(BASE=True, H=False, D=False, T=True)
        def submit(**kwargs):
            self.assertNotIn('convergence_plan', kwargs)
            self.cg['RUN_MANIFEST'] = dict(status='published')
        self.cg['SCRIPTS']['runCGYRO.py'].run.side_effect = submit
        self.assertEqual(len(self.actions.run_cgyro()), 2)
        self.assertEqual(self.cg['SCRIPTS']['runCGYRO.py'].run.call_count, 2)

    def test_combined_submission_failure_restores_input_and_controls(self):
        self.actions.run_cgyro(prepare=True)
        original_input = self.cg['INPUTS']['input.cgyro']
        setup, physics = self.cg['SETTINGS']['SETUP'], self.cg['SETTINGS']['PHYSICS']
        before_setup, before_physics = copy.deepcopy(setup), copy.deepcopy(physics)
        before_runid = self.cg['SETTINGS']['EXPERIMENT']['runid']
        self.cg['SCRIPTS']['runCGYRO.py'].run.side_effect = RuntimeError('combined submission failed')
        with self.assertRaisesRegex(RuntimeError, 'combined submission failed'):
            self.actions.run_cgyro()
        self.cg['SCRIPTS']['runCGYRO.py'].run.assert_called_once()
        self.assertIs(self.cg['INPUTS']['input.cgyro'], original_input)
        self.assertEqual(setup, before_setup)
        self.assertEqual(physics, before_physics)
        self.assertEqual(self.cg['SETTINGS']['EXPERIMENT']['runid'], before_runid)

    def test_existing_content_selector_switches_modes_without_resetting_ranges(self):
        physics = self.cg['SETTINGS']['PHYSICS']
        old_range = copy.deepcopy(physics['1d'])
        baseline = copy.deepcopy(physics['convergence'])
        self.actions.settings['cgyro_scan_content'] = 2
        self.actions.select_cgyro_scan_content()
        self.assertFalse(convergence.active(physics))
        self.assertEqual(self.cg['SETTINGS']['SETUP']['idimrun'], 2)
        self.actions.settings['cgyro_scan_content'] = 'convergence'
        self.actions.select_cgyro_scan_content()
        self.assertTrue(convergence.active(physics))
        self.assertEqual(physics['1d'], old_range)
        self.assertEqual(physics['convergence'], baseline)

    def test_convergence_controls_only_refresh_their_local_section(self):
        ui = project_tests.UI(self.root)
        view = ProjectUI(self.actions, ui)
        rows = plans.sync_cgyro_choices(self.root, self.actions.settings)
        view.render_cgyro_scan_settings(self.cg, rows)
        field_options = [kw for kind, args, kw in ui.events if kind == 'Entry' and "['convergence']" in args[0]]
        self.assertTrue(field_options)
        self.assertTrue(all(kw.get('updateGUI') is False and kw.get('refresh_tree') is False for kw in field_options))
        result = view.preview_cgyro_convergence()
        self.assertEqual(result['total_points'], 77)

    def index_plan(self):
        plan = self.actions.run_cgyro(prepare=True)
        for item in plan:
            source = self.cg['BATCH_INPUTS'][item['batch_key']][item['ion_case']]
            controls = dict(self.cg['SETTINGS']['PHYSICS'], **item['scan_controls'])
            indexed_group(self.cg, item['runid'], item['case_id'], source, controls, group=item['convergence_group'])
        return plan

    def test_all_matching_results_reuse_only_summaries_without_starting_a_job(self):
        self.index_plan()
        self.cg['RUN_HISTORY'] = UnreadResults()
        old_batch = self.cg['RUN_BATCH'] = dict(untouched=True)
        preview = self.actions.preview_cgyro_convergence()
        self.assertEqual((preview['total_points'], preview['reused_points'], preview['jobs']), (77, 77, 0))
        self.assertEqual(self.actions.run_cgyro(), [])
        self.assertIs(self.cg['RUN_BATCH'], old_batch)
        self.cg['SCRIPTS']['runCGYRO.py'].run.assert_not_called()

    def test_reuse_is_per_point_and_preserves_the_full_requested_precision(self):
        original = self.index_plan()[0]
        tasks = self.cg['RUN_DB']['test_convergence'][original['case_id']]['__SCANS__']['Base case']['tasks']
        row = next(iter(tasks.values()))
        row['result_summary']['final_time'] = 600.
        preview = self.actions.preview_cgyro_convergence()
        self.assertEqual((preview['submit_points'], preview['reused_points'], preview['jobs']), (1, 76, 1))
        plan = self.actions.run_cgyro(prepare=True)
        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0]['convergence_group']['submit_coordinates'], [[32, .1]])
        # Explicit preparation installs a fresh point index without changing
        # file owners; edit the current metadata rather than its old object.
        tasks = self.cg['RUN_DB']['test_convergence'][original['case_id']]['__SCANS__']['Base case']['tasks']
        row = next(item for item in tasks.values() if item['values']['KY'] == .1)
        row['result_summary']['solver_status'] = 'converged'
        self.assertEqual(self.actions.preview_cgyro_convergence()['submit_points'], 0)
        physics = self.cg['SETTINGS']['PHYSICS']
        physics['fixed_parameters']['ERROR_TOL'] = dict(enabled=True, value=1e-5)
        self.assertEqual(self.actions.preview_cgyro_convergence()['reused_points'], 0)

    def test_unknown_stale_incomplete_and_different_output_rows_do_not_reuse(self):
        original = self.index_plan()[0]
        tasks = self.cg['RUN_DB']['test_convergence'][original['case_id']]['__SCANS__']['Base case']['tasks']
        rows = list(tasks.values())
        rows[0].pop('input_requested_parameters')
        rows[1]['result_summary']['result_id'] = 'a' * 64
        rows[2]['result_summary']['solver_status'] = 'failed'
        rows[3]['input_requested_parameters']['HIPREC_FLAG'] = 0
        rows[4]['result_summary']['final_time'] = None
        rows[5]['result_summary']['final_time'] = float('nan')
        rows[6]['values']['KY'] = .6
        result = self.actions.preview_cgyro_convergence()
        self.assertEqual((result['submit_points'], result['reused_points']), (7, 70))

    def test_saved_index_reopens_with_same_reuse_decision_and_disabling_reuse_is_explicit(self):
        self.index_plan()
        saved = json.loads(json.dumps(self.cg['RUN_DB']))
        self.cg['RUN_DB'] = saved
        self.assertEqual(self.actions.preview_cgyro_convergence()['reused_points'], 77)
        self.cg['SETTINGS']['PHYSICS']['convergence']['reuse_results'] = False
        self.assertEqual(self.actions.preview_cgyro_convergence()['submit_points'], 77)

    def energy_only(self):
        physics = self.cg['SETTINGS']['PHYSICS']
        for name, group in physics['convergence']['groups'].items():
            group['enabled'] = name == 'N_ENERGY'
        original = self.index_plan()[0]
        case = self.cg['RUN_DB']['test_convergence'][original['case_id']]
        return physics, original, case

    def test_changed_center_all_reused_adopts_current_base_and_direction_without_owner_copy(self):
        import OMFITlib_compare_convergence as comparison
        physics, original, case = self.energy_only()
        old_48 = case['N_ENERGY']['48']['lin']['0.1']['__RESULT_REF__']
        old_32 = case['Base case']['32']['lin']['0.1']['__RESULT_REF__']
        owners = dict(self.cg['RUN_DB']['__STORE__'])
        unrelated = case['untouched_results'] = UnreadResults()
        physics['convergence']['baseline']['N_ENERGY'] = 48
        old_info = case['__SCANS__']['Base case']['info']
        preview = self.actions.preview_cgyro_convergence()
        self.assertEqual((preview['reused_points'], preview['jobs']), (21, 0))
        self.assertIs(case['__SCANS__']['Base case']['info'], old_info)
        self.assertEqual(old_info['convergence_group']['baseline']['N_ENERGY'], 32)
        self.assertEqual(self.actions.run_cgyro(), [])
        self.cg['SCRIPTS']['runCGYRO.py'].run.assert_not_called()
        self.assertEqual(case['Base case']['48']['lin']['0.1']['__RESULT_REF__'], old_48)
        self.assertEqual(case['N_ENERGY']['32']['lin']['0.1']['__RESULT_REF__'], old_32)
        self.assertEqual(case['__SCANS__']['Base case']['info']['convergence_group']['baseline']['N_ENERGY'], 48)
        self.assertTrue(case['__SCANS__']['N_ENERGY']['info']['scan_complete'])
        contexts = [row['result_info']['convergence_group'] for row in case['__SCANS__']['N_ENERGY']['tasks'].values()]
        self.assertTrue(all(item['baseline']['N_ENERGY'] == 48 for item in contexts))
        self.assertEqual([group['baseline_value'] for group in comparison.convergence_groups(case).values()], [48.])
        self.assertIs(case['untouched_results'], unrelated)
        self.assertEqual(set(self.cg['RUN_DB']['__STORE__']), set(owners))
        self.assertTrue(all(self.cg['RUN_DB']['__STORE__'][key] is owner for key, owner in owners.items()))

    def test_changed_center_adopted_refs_and_plot_context_survive_save_reopen(self):
        import OMFITlib_compare_convergence as comparison
        physics, original, case = self.energy_only()
        physics['convergence']['baseline']['N_ENERGY'] = 48
        self.assertEqual(self.actions.run_cgyro(prepare=True), [])
        owners = set(self.cg['RUN_DB']['__STORE__'])
        self.cg['RUN_DB'] = json.loads(json.dumps(self.cg['RUN_DB']))
        reopened = self.cg['RUN_DB']['test_convergence'][original['case_id']]
        groups = comparison.convergence_groups(reopened)
        self.assertEqual(len(groups), 1)
        group = next(iter(groups.values()))
        self.assertEqual(group['baseline_value'], 48)
        view, _, _, diagnostics = comparison.convergence_case_view(reopened)
        self.assertEqual(diagnostics, [])
        for value in (32, 48, 64):
            self.assertEqual(len(view[group['token']][value]['lin']), 7)
            self.assertTrue(all(node['__RESULT_REF__'] in owners for node in view[group['token']][value]['lin'].values()))
        self.assertEqual(self.actions.preview_cgyro_convergence()['submit_points'], 0)

    def test_reused_destination_scope_uses_new_scan_not_source_branch(self):
        physics, original, case = self.energy_only()
        physics['convergence']['baseline']['N_ENERGY'] = 48
        physics['convergence']['groups']['N_ENERGY']['values'].append(96)
        plan = self.actions.run_cgyro(prepare=True)
        self.assertEqual(len(plan), 1)
        group = plan[0]['convergence_group']
        self.assertEqual(group['storage_branch'], 'N_ENERGY')
        self.assertEqual({row['scan'] for row in group['reused_scope']['coordinates']}, {'N_ENERGY'})
        self.assertEqual(group['reused_points'], 14)
        self.assertEqual(group['submit_coordinates'], [[96, i / 10] for i in range(1, 8)])
        self.assertEqual(case['__SCANS__']['N_ENERGY']['info']['convergence_group']['baseline']['N_ENERGY'], 48)
        self.assertFalse(case['__SCANS__']['N_ENERGY']['info']['scan_complete'])
        self.assertEqual(case['__SCANS__']['N_ENERGY']['info']['collection_status'], 'partial')

    def test_adoption_commit_abort_restores_touched_branches_and_indexes(self):
        physics, original, case = self.energy_only()
        class InterruptCommit(dict):
            armed = True
            def __setitem__(self, key, value):
                if key == '__TASKS__' and self.armed:
                    self.armed = False
                    raise KeyboardInterrupt('fixture commit abort')
                super().__setitem__(key, value)
        protected = InterruptCommit(case)
        self.cg['RUN_DB']['test_convergence'][original['case_id']] = protected
        previous = dict(protected)
        physics['convergence']['baseline']['N_ENERGY'] = 48
        with self.assertRaisesRegex(KeyboardInterrupt, 'fixture commit abort'):
            self.actions.run_cgyro(prepare=True)
        self.assertEqual(set(protected), set(previous))
        self.assertTrue(all(protected[key] is value for key, value in previous.items()))

    def test_changed_center_adoption_handles_grouped_radius_and_preserves_other_ions(self):
        physics, original, case = self.energy_only()
        run = self.cg['RUN_DB']['test_convergence']
        archive.install_case(run, original['case_id'], case)
        del run[original['case_id']]
        path = archive.case_destination(self.cg, 'test_convergence', original['case_id'])
        radial = run[path[1]]
        unrelated = radial['T'] = UnreadResults()
        physics['convergence']['baseline']['N_ENERGY'] = 48
        self.assertEqual(self.actions.run_cgyro(prepare=True), [])
        updated = archive.catalog_runs(self.cg, 'test_convergence', original['case_id'])['test_convergence'][original['case_id']]
        self.assertIn('48', updated['Base case'])
        self.assertEqual(updated['__SCANS__']['N_ENERGY']['info']['convergence_group']['baseline']['N_ENERGY'], 48)
        self.assertIs(radial['T'], unrelated)

    def test_conflicting_exact_coordinate_owners_do_not_reuse_arbitrary_version(self):
        _, original, case = self.energy_only()
        source = copy.deepcopy(self.cg['BATCH_INPUTS'][original['batch_key']][original['ion_case']])
        source['N_ENERGY'] = 48
        controls = dict(self.cg['SETTINGS']['PHYSICS'], kyarr=[.1], **{'1d': dict(Para='N_THETA', Range=[32])})
        rows = indexed_group(self.cg, original['runid'], original['case_id'], source, controls)
        case = self.cg['RUN_DB'][original['runid']][original['case_id']]
        row = next(iter(rows.values()))
        owner = 'b' * 64
        self.cg['RUN_DB']['__STORE__'][owner] = UnreadResults()
        row['result_summary']['result_id'] = owner
        case['N_THETA']['32']['lin']['0.1'] = {'__RESULT_REF__': owner}
        preview = self.actions.preview_cgyro_convergence()
        self.assertEqual((preview['reused_points'], preview['submit_points']), (20, 1))

    def test_changed_center_adopts_in_place_for_legacy_short_case_key(self):
        physics, original, case = self.energy_only()
        run = self.cg['RUN_DB']['test_convergence']
        run['nr=1'] = run.pop(original['case_id'])
        physics['convergence']['baseline']['N_ENERGY'] = 48
        self.assertEqual(self.actions.run_cgyro(prepare=True), [])
        self.assertEqual(set(run), {'nr=1'})
        self.assertIn('48', run['nr=1']['Base case'])
        self.assertEqual(case['__SCANS__']['N_ENERGY']['info']['convergence_group']['baseline']['N_ENERGY'], 48)

    def test_row_identity_cannot_borrow_result_from_another_run_radius_or_ion(self):
        _, _, case = self.energy_only()
        row = next(iter(case['__SCANS__']['Base case']['tasks'].values()))
        row['result_info'].update(runid='unrelated_run', case_id='nr=2__rho=0.7__ion=T',
                                  source_nr=2, rho=.7, ion_case='T')
        preview = self.actions.preview_cgyro_convergence()
        self.assertEqual((preview['reused_points'], preview['submit_points']), (20, 1))

    def test_missing_or_inconsistent_generated_cache_only_rejects_affected_point(self):
        _, _, case = self.energy_only()
        row = next(iter(case['__SCANS__']['Base case']['tasks'].values()))
        verified = copy.deepcopy(row['input_parameters'])
        changed = [None, dict(verified, KY=-.1), dict(verified, N_ENERGY=48),
                   {name: value for name, value in verified.items() if name != 'N_XI'}]
        for cached in changed:
            with self.subTest(cache=cached):
                row['input_parameters'] = cached
                preview = self.actions.preview_cgyro_convergence()
                self.assertEqual((preview['reused_points'], preview['submit_points']), (20, 1))
        row['input_parameters'] = dict(verified, KY=.1 * (1 + 1e-10))
        self.assertEqual(self.actions.preview_cgyro_convergence()['reused_points'], 21)

    def test_scaled_time_uses_collected_effective_values_for_reuse(self):
        physics = self.cg['SETTINGS']['PHYSICS']
        physics.update(scale_time_with_ky=True, kyarr=[2.])
        physics['fixed_parameters']['DELTA_T'] = dict(enabled=True, value=.01)
        _, _, case = self.energy_only()
        for _, _, rows in archive.case_scans(case):
            for row in rows.values():
                requested = row['input_requested_parameters']
                row['result_info']['fixed_parameters'] = {'DELTA_T': requested['DELTA_T'] * 2}
                row['effective_time'] = {name: requested[name] for name in ('DELTA_T', 'MAX_TIME')}
        self.assertEqual(self.actions.preview_cgyro_convergence()['reused_points'], 3)
        row['effective_time']['DELTA_T'] *= 2
        preview = self.actions.preview_cgyro_convergence()
        self.assertEqual((preview['reused_points'], preview['submit_points']), (2, 1))


class ConvergenceArchiveTests(unittest.TestCase):
    def setUp(self):
        self.host = test_cgyro_storage.StorageCases()
        self.host.setUp()
        self.addCleanup(self.host.doCleanups)
        self.addCleanup(self.host.tearDown)
        self.root = {}
        self.publish = self.host.publisher()
        self.caseid = 'nr=1__rho=0.33__ion=T'

    def attempt(self, token, parameter, value, kys, loaded=None, group=None):
        tasks, results = {}, {}
        for index, ky in enumerate(kys, 1):
            point = 'p{:06d}'.format(index)
            tasks[point] = dict(values={parameter: value, 'KY': ky},
                               result_path=[parameter, str(value), 'lin', str(ky)])
            result = self.host.result(token + point, parameters=tasks[point]['values'])
            Path(result.filename, 'out.cgyro.time').write_text('0\n60\n')
            results[point] = result
        manifest = dict(run_token=token, case_tag='case', case_id=self.caseid, nr=1, rho=.33, mass='T',
            runid='Jet', server='fixture', workDir='/runs/' + token, job_id='job-' + token,
            dimensions=1, scan_dimensions=1, scan_axes=[dict(name=parameter, values=[value], linked=[])],
            status='loaded', collection_status='ready', points=list(tasks),
            loaded_points=list(tasks) if loaded is None else loaded, point_table=tasks)
        if group is not None:
            manifest['convergence_group'] = group
        self.root['RUN_MANIFEST'], self.root['Cases'] = manifest, {'case': results}
        return manifest

    def test_partial_group_preserves_other_axes_and_existing_baseline(self):
        self.attempt('baseline', 'N_ENERGY', 32, [.1, .2])
        self.publish(self.root)
        self.attempt('other', 'N_THETA', 32, [.1])
        self.publish(self.root)
        case = archive.catalog_runs(self.root)['Jet'][self.caseid]
        old = copy.deepcopy(case['N_ENERGY']['32'])
        other = copy.deepcopy(case['N_THETA'])
        info, tasks = case['__SCANS__']['N_ENERGY']['info'], case['__SCANS__']['N_ENERGY']['tasks']
        scope = test_cgyro_storage.index_api.scan_scope(dict(info, tasks=tasks))
        group = dict(parameter='N_ENERGY', baseline={'N_ENERGY': 32}, requested=[32, 48], shared=[], fixed={},
                     reused_scope=scope, reused_points=2, submit_coordinates=[[48, .1], [48, .2]])
        manifest = self.attempt('new', 'N_ENERGY', 48, [.1, .2], loaded=['p000001'], group=group)
        self.publish(self.root)
        case = archive.catalog_runs(self.root)['Jet'][self.caseid]
        self.assertEqual(case['N_ENERGY']['32'], old)
        self.assertEqual(case['N_THETA'], other)
        self.assertIn('0.1', case['N_ENERGY']['48']['lin'])
        self.assertFalse(manifest['submission_complete'])
        self.assertFalse(manifest['scan_complete'])
        self.assertEqual(case['__SCANS__']['N_ENERGY']['info']['convergence_group']['parameter'], 'N_ENERGY')

    def test_removed_reused_point_does_not_block_archive_or_claim_whole_scan_complete(self):
        self.attempt('baseline', 'N_ENERGY', 32, [.1])
        self.publish(self.root)
        case = archive.catalog_runs(self.root)['Jet'][self.caseid]
        scope = test_cgyro_storage.index_api.scan_scope(dict(case['__INFO__'], tasks=case['__TASKS__']))
        self.root['RUN_DB'].pop('Jet')
        group = dict(parameter='N_ENERGY', baseline={'N_ENERGY': 32}, requested=[32, 48], shared=[], fixed={},
                     reused_scope=scope, reused_points=1, submit_coordinates=[[48, .1]])
        manifest = self.attempt('new', 'N_ENERGY', 48, [.1], group=group)
        self.publish(self.root)
        self.assertTrue(manifest['submission_complete'])
        self.assertFalse(manifest['scan_complete'])
        self.assertIn('48', archive.catalog_runs(self.root)['Jet'][self.caseid]['N_ENERGY'])

    def test_new_hierarchy_resolves_base_and_direction_by_index_after_reopen(self):
        self.caseid += '__constant=BETAE_UNIT=0.0001'
        group = dict(parameter='N_ENERGY', baseline={'N_ENERGY': 32}, requested=[32],
                     shared=[], fixed={}, role='baseline', storage_branch='Base case')
        manifest = self.attempt('base', 'N_ENERGY', 32, [.1, -.1], group=group)
        manifest.update(runid='Jet_convergence', constant_parameters={'BETAE_UNIT': .0001})
        self.publish(self.root)
        group = dict(group, role='direction', storage_branch='N_ENERGY', requested=[32, 48])
        manifest = self.attempt('energy', 'N_ENERGY', 48, [.1], group=group)
        manifest.update(runid='Jet_convergence', constant_parameters={'BETAE_UNIT': .0001})
        self.publish(self.root)
        radius = 'nr=1_rho=0.33_BETAE_UNIT=0.0001'
        run = self.root['RUN_DB']['Jet_convergence']
        case = run[radius]['T']
        self.assertEqual(set(case) - {'__INFO__', '__TASKS__', '__SCANS__'}, {'Base case', 'N_ENERGY'})
        self.assertEqual(set(case['N_ENERGY']), {'48'})
        self.assertEqual(len(case['__SCANS__']['Base case']['tasks']), 2)
        # Only the lightweight public index is serialized; owners are unchanged.
        self.root['RUN_DB']['Jet_convergence'] = json.loads(json.dumps(run))
        self.root['RUN_HISTORY'] = {}
        selection = 'scan:' + json.dumps(['Jet_convergence', self.caseid, 'Base case'], separators=(',', ':'))
        entry = test_cgyro_storage.index_api.find_record(self.root, selection)
        binding = test_cgyro_storage.index_api.select_result(self.root, entry, 'p000001')
        self.assertEqual(binding['location'][:4], ['Jet_convergence', radius, 'T', 'Base case'])
        self.assertEqual(binding['info']['convergence_group']['role'], 'baseline')
        self.assertEqual(binding['identity']['values']['KY'], .1)
        result = test_cgyro_storage.index_api.selected_result(self.root, binding)
        self.assertTrue(Path(result.filename, 'input.cgyro').is_file())
        with patch.object(test_cgyro_storage.continuation, 'resume_source', return_value={'mode': 'checkpoint'}):
            plan = test_cgyro_storage.continuation.continuation_plan(
                self.root, selection, ['p000001'], 600, selections={'p000001': binding})
        self.assertEqual(plan['source_runid'], 'Jet_convergence')
        self.assertEqual(archive.scan_key(plan['info']), 'Base case')

    def test_collected_generated_inputs_drive_real_convergence_baseline_join(self):
        group = dict(parameter='N_ENERGY', baseline=dict(convergence.BASELINE),
                     requested=[32, 48], shared=[], fixed={}, role='baseline', storage_branch='Base case')
        for token, value, role in [('base', 32, 'baseline'), ('energy', 48, 'direction')]:
            group.update(role=role, storage_branch='Base case' if role == 'baseline' else 'N_ENERGY')
            manifest = self.attempt(token, 'N_ENERGY', value, [.1, -.1], group=copy.deepcopy(group))
            manifest['runid'] = 'Jet_convergence'
            for point, result in self.root['Cases']['case'].items():
                parameters = dict(convergence.BASELINE, ERROR_TOL=1e-4, FREQ_TOL=1e-3,
                                  DELTA_T=.01, **manifest['point_table'][point]['values'])
                Path(result.filename, 'input.cgyro').write_text(''.join(
                    '{}={}\n'.format(name, number) for name, number in parameters.items()))
                Path(result.filename, 'input.cgyro.gen').write_text(''.join(
                    '{} {}\n'.format(number, name) for name, number in parameters.items()))
            self.publish(self.root)
        case = archive.catalog_runs(self.root)['Jet_convergence'][self.caseid]
        view, selected, metadata, diagnostics = convergence_case_view(case)
        self.assertEqual(diagnostics, [])
        self.assertEqual(len(selected), 1)
        key = next(iter(selected))
        self.assertEqual(metadata[key]['axis'], 'N_ENERGY')
        self.assertEqual(selected[key], [32, 48])
        for ky in (.1, -.1):
            self.assertEqual(view[key][32]['lin'][ky], case['Base case']['32']['lin'][str(ky)])
            self.assertEqual(view[key][48]['lin'][ky], case['N_ENERGY']['48']['lin'][str(ky)])


if __name__ == '__main__':
    unittest.main()
