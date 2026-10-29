"""One-variable plans use ordinary CGYRO jobs, immutable inputs and RUN_DB."""
import copy
import ast
import hashlib
import itertools
import json
from pathlib import Path
import unittest

import test_cgyro_storage  # Isolated native file adapters.
import test_project as project_tests
import OMFITlib_cgyro_convergence as convergence
import OMFITlib_cgyro_plan as plans
from OMFITlib_project_ui import ProjectUI
import OMFITlib_cgyro_archive as archive
from OMFITlib_cgyro_parameters import apply_parameters
from OMFITlib_cgyro_read import num2str_xj
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
    return source, physics


def indexed_group(module, runid, caseid, source, controls, values=None):
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
    archive.store_scan(case, case, info, tasks)
    destination = module['RUN_DB'].setdefault(runid, {}).setdefault(caseid, {})
    destination.update(archive.combine_cases([destination, case]))
    return destination['__SCANS__'][parameter]['tasks']


class ConvergenceTests(unittest.TestCase):
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
        self.assertEqual(len(jobs), 5)
        self.assertTrue(all(job['dimensions'] == 1 for job in jobs))
        self.assertEqual(source, before_source)
        self.assertEqual(physics, before_physics)
        self.assertEqual(jobs[0]['batch_key'], 'scheme:1:convergence:N_ENERGY')

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

    def test_batch_prepares_five_native_jobs_without_result_reads(self):
        plan = self.actions.run_cgyro(prepare=True)
        summary = plans.cgyro_plan_summary(self.root)
        self.assertEqual(len(plan), 5)
        self.assertEqual(summary['total_points'], 77)
        self.assertEqual(summary['jobs'], 5)
        self.assertEqual([row['convergence_group']['parameter'] for row in plan], list(convergence.DIRECTIONS)[:-1])
        self.assertTrue(all(row['runid'] == 'test' for row in plan))
        self.cg['SCRIPTS']['runCGYRO.py'].run.assert_not_called()

    def test_submission_installs_each_group_then_restores_ordinary_scan_and_editor(self):
        self.actions.run_cgyro(prepare=True)  # Initialize the ordinary parameter catalogue first.
        physics = self.cg['SETTINGS']['PHYSICS']
        setup = self.cg['SETTINGS']['SETUP']
        original_controls = copy.deepcopy({key: physics.get(key) for key in ('1d', '2d', 'fixed_parameters')})
        original_dimension = setup['idimrun']
        original_input = self.cg['INPUTS']['input.cgyro']
        calls = []
        def submit(**kwargs):
            self.assertEqual(setup['idimrun'], 1)
            name = physics['1d']['Para']
            calls.append(name)
            if name == 'E_MAX':
                self.assertEqual(self.cg['INPUTS']['input.cgyro']['N_ENERGY'], 64)
            self.assertEqual(kwargs['convergence_group']['parameter'], name)
            self.cg['RUN_MANIFEST'] = dict(status='published')
        self.cg['SCRIPTS']['runCGYRO.py'].run.side_effect = submit
        self.actions.run_cgyro()
        self.assertEqual(calls, list(convergence.DIRECTIONS)[:-1])
        self.assertEqual(setup['idimrun'], original_dimension)
        self.assertIs(self.cg['INPUTS']['input.cgyro'], original_input)
        self.assertEqual({key: physics.get(key) for key in original_controls}, original_controls)

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
            indexed_group(self.cg, item['runid'], item['case_id'], source, controls)
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
        tasks = self.cg['RUN_DB']['test'][original['case_id']]['__SCANS__']['N_ENERGY']['tasks']
        row = next(iter(tasks.values()))
        row['result_summary']['final_time'] = 600.
        preview = self.actions.preview_cgyro_convergence()
        self.assertEqual((preview['submit_points'], preview['reused_points'], preview['jobs']), (1, 76, 1))
        plan = self.actions.run_cgyro(prepare=True)
        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0]['convergence_group']['submit_coordinates'], [[32, .1]])
        row['result_summary']['solver_status'] = 'converged'
        self.assertEqual(self.actions.preview_cgyro_convergence()['submit_points'], 0)
        physics = self.cg['SETTINGS']['PHYSICS']
        physics['fixed_parameters']['ERROR_TOL'] = dict(enabled=True, value=1e-5)
        self.assertEqual(self.actions.preview_cgyro_convergence()['reused_points'], 0)

    def test_unknown_stale_incomplete_and_different_output_rows_do_not_reuse(self):
        original = self.index_plan()[0]
        tasks = self.cg['RUN_DB']['test'][original['case_id']]['__SCANS__']['N_ENERGY']['tasks']
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


if __name__ == '__main__':
    unittest.main()
