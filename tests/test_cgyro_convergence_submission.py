"""One immutable convergence array with distinct physical point inputs."""
import ast
import copy
import hashlib
import itertools
import json
import os
from pathlib import Path
import re
import tempfile
import unittest
import zipfile

import numpy as np
import test_cgyro_storage
import test_project
import OMFITlib_cgyro_convergence as convergence
from OMFITlib_cgyro_archive import canonical_case_key
from OMFITlib_cgyro_parameters import FIELDS, apply_parameters, constant_parameters, initialize_parameters, parameter_value, validate_zeff
from OMFITlib_cgyro_read import num2str_xj
from OMFITlib_cgyro_scan_values import AXIS_KEYS, ky_values, scan_axes
from OMFITlib_cgyro_launch import launch_spec, slurm_guard, slurm_process_limits
from OMFITlib_cgyro_recovery_manifest import _point_index, _verify_coordinates

SCRIPT = test_project.REPO / 'CGYRO_TGLF_scan/CGYRO_scan/SCRIPTS/subscan_lin.py'


def native_scope():
    tree = ast.parse(SCRIPT.read_text(encoding='utf-8'))
    definitions = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
    scope = dict(np=np, itertools=itertools, copy=copy, re=re, num2str_xj=num2str_xj,
        AXIS_KEYS=AXIS_KEYS, resolved_scan_axes=scan_axes, ky_values=ky_values,
        initialize_parameters=initialize_parameters, apply_parameters=apply_parameters,
        configured_constants=constant_parameters, canonical_case_key=canonical_case_key,
        CALCULATION_FIELDS=FIELDS, parameter_value=parameter_value, OMFITtree=dict,
        os=os, slurm_guard=slurm_guard, slurm_process_limits=slurm_process_limits)
    exec(compile(ast.Module(body=definitions, type_ignores=[]), str(SCRIPT), 'exec'), scope)
    return tree, scope


def plan_fixture(cases=((1, .33, 'T'),)):
    physics = dict(scan_mode='convergence', kyarr=[i / 10 for i in range(1, 8)],
                   fixed_parameters={}, scale_time_with_ky=False)
    source = test_project.cgyro()
    source.update(N_ENERGY=32, N_XI=48, N_RADIAL=32, N_THETA=32, E_MAX=8,
                  MAX_TIME=1200, DELTA_T=.01, PRINT_STEP=100, ERROR_TOL=1e-4)
    convergence.initialize(physics, source)
    root, plan = dict(BATCH_INPUTS={}), []
    for nr, rho, ion in cases:
        base = source.duplicate()
        base.update(RMIN=rho, MASS_1={'H': 1., 'D': 2., 'T': 3.}[ion])
        for job in convergence.jobs(physics, base, 1, str(nr)):
            value = base.duplicate()
            apply_parameters(value, job['physics'], 1)
            key = job['batch_key']
            root['BATCH_INPUTS'].setdefault(key, {})[ion] = value
            group = copy.deepcopy(job['convergence_group'])
            group['submit_coordinates'] = [[number, ky] for number in job['physics']['1d']['Range']
                                           for ky in ky_values(physics)]
            group['reused_scope'] = dict(coordinates=[], unknown=[], issues=[])
            plan.append(dict(batch_key=key, ion_case=ion, nr=nr, rho=rho, runid='Jet_convergence',
                case_id='nr={}__rho={}__ion={}'.format(nr, rho, ion), convergence_group=group,
                scan_controls={name: copy.deepcopy(job['physics'][name]) for name in
                               ('1d', 'fixed_parameters', 'constant_parameter') if name in job['physics']}))
    return root, plan, physics


class ConvergenceSubmissionTests(unittest.TestCase):
    def test_77_points_share_one_array_and_keep_conditional_baseline(self):
        tree, scope = native_scope()
        root, plan, physics = plan_fixture()
        points, sources = scope['convergence_points'](root, plan, physics, 5)
        self.assertEqual([point for point, _, _ in points], ['p{:06d}'.format(i) for i in range(1, 78)])
        unique = set()
        for point, overrides, row in points:
            values = dict(sources[point], **overrides)
            key = tuple(values[name] for name in (*convergence.BASELINE, 'KY'))
            self.assertNotIn(key, unique)
            unique.add(key)
            info = row['result_info']
            if info['convergence_group']['storage_branch'] == 'E_MAX':
                self.assertEqual(values['N_ENERGY'], 64)
                self.assertIn(values['E_MAX'], (10, 12))
            self.assertNotIn('submit_coordinates', info['convergence_group'])
        self.assertEqual(points[0][2]['result_info']['convergence_group']['storage_branch'], 'Base case')
        selected, active = [], False
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'environment'
                                                    for target in node.targets):
                active = True
            if active:
                selected.append(node)
                if isinstance(node, ast.With):
                    break
        config = dict(scheduler='slurm', environment='true', executable='cgyro -e .',
                      nodes=1, ntasks_per_node=32, cpus_per_task=2, queue='normal', w='16:00:00', array_parallel=8)
        with tempfile.TemporaryDirectory() as directory:
            scope.update(server_setup=config, setup={}, manifest={}, local_submit=False,
                         execution=launch_spec(config), submit_workdir=directory,
                         dir_list=[point for point, _, _ in points])
            exec(compile(ast.Module(body=selected, type_ignores=[]), str(SCRIPT), 'exec'), scope)
            script = (Path(directory) / 'scan.pbs').read_text()
        self.assertEqual(script.count('#SBATCH --array='), 1)
        self.assertIn('#SBATCH --array=0-76%8\n', script)
        self.assertIn('#SBATCH --ntasks=32\n', script)
        self.assertIn('#SBATCH --cpus-per-task=2\n', script)

    def test_different_radii_or_isotopes_require_separate_arrays(self):
        _, scope = native_scope()
        for cases in (((1, .33, 'H'), (1, .33, 'T')), ((1, .33, 'T'), (2, .5, 'T'))):
            with self.subTest(cases=cases):
                root, plan, physics = plan_fixture(cases)
                with self.assertRaisesRegex(ValueError, 'one radius/isotope case'):
                    scope['convergence_points'](root, plan, physics, 5)
                for case in cases:
                    root, plan, physics = plan_fixture((case,))
                    points, sources = scope['convergence_points'](root, plan, physics, 5)
                    self.assertEqual(len(points), 77)
                    self.assertEqual(points[0][0], 'p000001')
                    for point, _, row in points:
                        info = row['result_info']
                        self.assertEqual(sources[point]['RMIN'], info['rho'])
                        self.assertEqual(sources[point]['MASS_1'], {'H': 1., 'D': 2., 'T': 3.}[info['ion_case']])

    def test_reused_coordinates_are_not_staged_and_pending_ids_remain_contiguous(self):
        _, scope = native_scope()
        root, plan, physics = plan_fixture()
        chosen = [plan[1], plan[-1]]
        chosen[0]['convergence_group']['submit_coordinates'] = [[48, .2]]
        chosen[1]['convergence_group']['submit_coordinates'] = [[12, .7]]
        points, sources = scope['convergence_points'](root, chosen, physics, 5)
        self.assertEqual([point for point, _, _ in points], ['p000001', 'p000002'])
        self.assertEqual([overrides for _, overrides, _ in points],
                         [dict(N_ENERGY=48, KY=.2), dict(E_MAX=12, KY=.7)])
        self.assertEqual(sources['p000002']['N_ENERGY'], 64)

    def test_plan_and_inputs_are_not_mutated_and_context_survives_json(self):
        _, scope = native_scope()
        root, plan, physics = plan_fixture()
        before = copy.deepcopy((root, plan, physics))
        points, _ = scope['convergence_points'](root, plan, physics, 5)
        self.assertEqual((root, plan, physics), before)
        stored = json.loads(json.dumps({point: row for point, _, row in points}))
        self.assertEqual(stored[points[-1][0]], points[-1][2])
        self.assertEqual(stored['p000001']['result_info']['runid'], 'Jet_convergence')

    def test_empty_or_duplicated_plan_is_rejected_before_submission(self):
        _, scope = native_scope()
        root, plan, physics = plan_fixture()
        with self.assertRaisesRegex(ValueError, 'No pending'):
            scope['convergence_points'](root, [], physics, 5)
        with self.assertRaisesRegex(ValueError, 'Duplicate convergence'):
            scope['convergence_points'](root, [plan[0], plan[0]], physics, 5)

    def test_real_staging_loop_freezes_each_direction_input_not_first_direction(self):
        tree, scope = native_scope()
        root, plan, physics = plan_fixture()
        selected = [plan[1], plan[-1]]
        selected[0]['convergence_group']['submit_coordinates'] = [[48, .2]]
        selected[1]['convergence_group']['submit_coordinates'] = [[12, .7]]
        points, sources = scope['convergence_points'](root, selected, physics, 5)
        class Input(test_project.CgyroInput):
            filename = ''
            def deploy(self, path):
                Path(path).write_text(''.join('{}={}\n'.format(k, v) for k, v in sorted(self.items())), encoding='utf-8')
        sources = {key: Input(value) for key, value in sources.items()}
        loop = next(node for node in tree.body if isinstance(node, ast.For)
                    and isinstance(node.target, ast.Tuple) and isinstance(node.target.elts[0], ast.Name)
                    and node.target.elts[0].id == 'point_number')
        with tempfile.TemporaryDirectory() as directory:
            scope.update(points=points, convergence_inputs=sources, base_input=sources['p000001'],
                submit_workdir=directory, physics=physics, case_id='first', fixed_parameters={}, constant_parameters={},
                continuation=None, restart_mode=0, input_names=['input.cgyro'], inputs_node={}, inputs=[], dir_list=[],
                input_checksums={}, point_table={}, prepared_cases={}, OMFITpath=str, run_token='0'*32,
                zipfile=zipfile, hashlib=hashlib, validate_zeff=validate_zeff,
                ensure_capacity=lambda *args: None, clean_stage=lambda *args, **kw: None)
            exec(compile(ast.Module(body=[loop], type_ignores=[]), str(SCRIPT), 'exec'), scope)
            frozen = json.loads(json.dumps(dict(convergence_batch=True, points=scope['dir_list'],
                                               point_table=scope['point_table'])))
            self.assertEqual(_point_index(frozen), ['p000001', 'p000002'])
            texts = []
            for point in scope['dir_list']:
                with zipfile.ZipFile(Path(directory) / (point+'.zip')) as archive:
                    _verify_coordinates(archive, frozen['point_table'][point])
                    raw = archive.read('input.cgyro')
                self.assertEqual(hashlib.sha256(raw).hexdigest(), scope['input_checksums'][point]['input.cgyro'])
                texts.append(raw.decode('utf-8').replace('\r\n', '\n'))
        self.assertIn('MASS_1=3.0\n', texts[0])
        self.assertIn('N_ENERGY=48\n', texts[0])
        self.assertIn('MASS_1=3.0\n', texts[1])
        self.assertIn('N_ENERGY=64\n', texts[1])
        self.assertIn('E_MAX=12\n', texts[1])
        self.assertEqual(scope['point_table']['p000002']['result_info']['rho'], .33)


if __name__ == '__main__':
    unittest.main()
