"""Launch, queue and output-contract regressions without a remote solver."""
import ast
import copy
from contextlib import ExitStack
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'CGYRO_TGLF_scan/LIB'))
import test_cgyro_storage  # Explicit native file adapters required by queue imports.
import test_tglf_multi as tglf_fixture
import OMFITlib_cgyro_launch as launch
import OMFITlib_cgyro_queue as queue
import OMFITlib_cgyro_run_state as state
import OMFITlib_cgyro_retry as retry
import OMFITlib_tglf_multi_run as tglf
from omfit_mapping import OMFITMapping, treeify


def subscan_tree():
    path = REPO / 'CGYRO_TGLF_scan/CGYRO_scan/SCRIPTS/subscan_lin.py'
    return path, ast.parse(path.read_text(encoding='utf-8'))


class LaunchContractTests(unittest.TestCase):
    def test_adjacent_shell_operators_cannot_receive_solver_resource_arguments(self):
        for command in ('cgyro -e .; echo finished', 'cgyro -e .&&echo finished',
                        'cgyro -e .|cat', 'cgyro -e .& echo finished',
                        'cgyro -e .||true', 'cgyro -e . ; echo finished'):
            with self.subTest(command=command), self.assertRaisesRegex(ValueError, 'inline shell'):
                launch.launch_spec(dict(scheduler='slurm', nodes=1, ntasks_per_node=32,
                                        cpus_per_task=1, executable=command))

    def test_quoted_escaped_paths_and_redirections_remain_one_invocation(self):
        for argument in ('"input; data|a&b"', "'a;b'", r'input\;name', r'input\&name'):
            with self.subTest(argument=argument):
                command = 'cgyro -e ' + argument + ' -n 4 2>&1 # note; is not code'
                rendered = launch.command_template(command)
                self.assertIn('-e ' + argument, rendered)
                self.assertIn('2>&1', rendered)
                self.assertIn('-n {mpi}', rendered)
        self.assertIn('&> run_log', launch.command_template('cgyro -e . &> run_log'))

    def test_standalone_hybrid_layout_is_preserved_until_resources_are_explicit(self):
        spec = launch.launch_spec(dict(scheduler='local', executable='cgyro -e . -n 8 -nomp 4'),
                                  dict(num_cores=32, cpus_per_task=1))
        self.assertEqual((spec['mpi_ranks'], spec['threads'], spec['total_cpus']), (8, 4, 32))
        override = launch.launch_spec(dict(scheduler='local', cpus_per_task=2,
                                          executable='cgyro -e . -n 8 -nomp 4'))
        self.assertEqual((override['mpi_ranks'], override['threads']), (8, 2))

    def test_native_local_script_uses_resolved_threads_for_arguments_and_environment(self):
        path, tree = subscan_tree()
        definitions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in
                       ('cfg_get', 'cfg_str', 'required_cfg', 'required_cfg_int', 'config_error', 'script_fragment')]
        selected, active = [], False
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'environment'
                                                    for target in node.targets):
                active = True
            if active:
                selected.append(node)
                if isinstance(node, ast.With):
                    break
        config = dict(scheduler='local', environment='true', executable='cgyro -e . -n 8 -nomp 4')
        with tempfile.TemporaryDirectory() as directory:
            namespace = dict(os=os, server_setup=config, setup={}, manifest={}, local_submit=True,
                             execution=launch.launch_spec(config), submit_workdir=directory,
                             dir_list=['p000001'], slurm_guard=launch.slurm_guard,
                             slurm_process_limits=launch.slurm_process_limits)
            exec(compile(ast.Module(body=definitions + selected, type_ignores=[]), str(path), 'exec'), namespace)
            script = (Path(directory) / 'scan.pbs').read_text()
        self.assertIn('export OMP_NUM_THREADS=4\n', script)
        self.assertIn('export OMP_THREAD_LIMIT=4\n', script)
        self.assertEqual(launch.command_layout(script)['threads'], 4)
        self.assertEqual(namespace['manifest']['cpus_per_task'], 4)


class UncollectedRunTests(unittest.TestCase):
    def test_failed_cancelled_allocations_protect_batch_until_collection(self):
        for factory in (dict, OMFITMapping):
            for phase in ('failed', 'cancelled'):
                with self.subTest(factory=factory, phase=phase):
                    manifest = dict(run_token='old', job_id='123', status=phase, collection_status='pending')
                    root = treeify(dict(RUN_HISTORY={'old': {'manifest': manifest}},
                                        RUN_BATCH={'tokens': ['old']}), factory)
                    self.assertEqual(queue.pending_runs(root), [manifest])
                    root['RUN_HISTORY']['old']['manifest']['collection_status'] = 'partial'
                    self.assertEqual(queue.pending_runs(root), [])

    def test_definite_rejection_without_job_does_not_require_collection(self):
        manifest = dict(run_token='old', job_id='', status='failed', submission_uncertain=False)
        root = dict(RUN_HISTORY={'old': {'manifest': manifest}}, RUN_BATCH={'tokens': ['old']})
        self.assertEqual(queue.pending_runs(root), [])
        manifest['submission_uncertain'] = True
        self.assertEqual(queue.pending_runs(root), [manifest])

    def test_native_submission_guard_rejects_uncollected_failed_single_job(self):
        path, tree = subscan_tree()
        guard = next(node for node in tree.body if isinstance(node, ast.If)
                     and isinstance(node.test, ast.BoolOp)
                     and isinstance(node.test.values[0], ast.Call)
                     and getattr(node.test.values[0].func, 'id', '') == 'uncollected_job')
        namespace = dict(previous_manifest=dict(status='failed', job_id='123'), root={}, batch_id='',
                         uncollected_job=state.uncollected_job, advancing_batch=lambda *args: False)
        with self.assertRaisesRegex(ValueError, 'has not been collected'):
            exec(compile(ast.Module(body=[guard], type_ignores=[]), str(path), 'exec'), namespace)
        namespace['advancing_batch'] = lambda *args: True
        exec(compile(ast.Module(body=[guard], type_ignores=[]), str(path), 'exec'), namespace)


class TglfOutputContractTests(unittest.TestCase):
    def test_empty_mismatched_nonfinite_or_nondimensional_spectra_are_rejected(self):
        variants = [dict(ky=np.array(.1)), dict(ky=np.array([[.1, .3, .6]])),
                    dict(gamma=np.empty((0, 3)), freq=np.empty((0, 3))),
                    dict(freq=np.zeros((1, 3))), dict(gamma=np.full((2, 3), np.nan))]
        for fields in variants:
            with self.subTest(fields=list(fields)):
                result = tglf_fixture.result()
                result['eigenvalue_spectrum'].update(fields)
                with self.assertRaises(ValueError):
                    tglf.validate_result(result)

    def test_truncated_flux_rows_cannot_be_marked_complete(self):
        for rows in ([], [('elec',)], [('elec', 1.)], [('elec', 1., np.inf)]):
            with self.subTest(rows=rows):
                result = tglf_fixture.result()
                result['gbflux']['data'] = rows
                with self.assertRaises(ValueError):
                    tglf.validate_result(result)
        result = tglf_fixture.result()
        result['eigenvalue_spectrum']['gamma'][:] = 0.0
        result['gbflux']['data'] = [('elec', 0., 0.)]
        tglf.validate_result(result)  # Physical zero is data, not missing output.

    def test_bad_output_remains_retryable_and_corrected_attempt_completes(self):
        fixture = tglf_fixture.TestMultiInput()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        malformed = tglf_fixture.result()
        malformed['gbflux']['data'] = [('elec',)]
        fixture.runner.tglf = lambda path: malformed
        self.assertEqual(fixture.run_cases()['failed'], 1)
        point = next(iter(fixture.latest()['points'].values()))
        prior = point['attempts'][point['selected_attempt']]
        self.assertEqual((point['status'], prior['status']), ('failed', 'failed'))
        self.assertNotIn('result', prior)
        fixture.runner.tglf = lambda path: tglf_fixture.result()
        self.assertEqual(fixture.run_cases('run')['failed'], 0)
        self.assertEqual(point['status'], 'complete')
        self.assertEqual(prior['status'], 'failed')
        self.assertEqual(len(point['attempts']), 2)


class CollectionRollbackTests(unittest.TestCase):
    def test_secondary_failure_keeps_abort_and_attempts_other_restoration(self):
        for failing_stage in ('cases restore', 'save metadata', 'manifest clear'):
            with self.subTest(stage=failing_stage), ExitStack() as scope:
                abort = KeyboardInterrupt('original abort')
                abort.cgyro_rollback_errors = ['earlier rollback issue']
                class Manifest(dict):
                    def clear(self):
                        if failing_stage == 'manifest clear':
                            raise RuntimeError('clear refused')
                        super().clear()
                manifest = Manifest(run_token='old', status='failed', collection_status='partial',
                                    loaded_points=['p000001'])
                def download():
                    manifest.update(dict(status='loading', loaded_points=[]))
                    raise abort
                reader = Mock(side_effect=download)
                root = dict(RUN_MANIFEST=manifest, SCRIPTS={'downsync.py': Mock(run=reader)})
                scope.enter_context(patch.object(retry, 'require_retained_run'))
                save = scope.enter_context(patch.object(retry, 'save_current', side_effect=(
                    [None, RuntimeError('save refused')] if failing_stage == 'save metadata' else None)))
                scope.enter_context(patch.object(retry, 'run_cases', return_value={'point': [1]}))
                scope.enter_context(patch.object(retry, 'copy_result_tree', side_effect=lambda value, factory: copy.deepcopy(value)))
                restore = scope.enter_context(patch.object(retry, 'set_run_cases', side_effect=(
                    RuntimeError('case restore refused') if failing_stage == 'cases restore' else None)))
                with self.assertRaises(KeyboardInterrupt) as caught:
                    retry.collect_current(root, object(), dict, None, None)
                self.assertIs(caught.exception, abort)
                self.assertEqual(manifest['status'], 'failed')
                self.assertEqual(manifest['loaded_points'], ['p000001'])
                self.assertEqual(manifest['collection_error'], 'original abort')
                self.assertEqual(save.call_count, 2)
                restore.assert_called_once()
                self.assertEqual(abort.cgyro_rollback_errors[0], 'earlier rollback issue')
                self.assertTrue(abort.cgyro_rollback_errors[-1].startswith(failing_stage + ':'))
                reader.assert_called_once()

    def test_failed_rollback_prevents_automatic_read_retry(self):
        error = RuntimeError('connection reset')
        reader = Mock(side_effect=error)
        root = dict(RUN_MANIFEST=dict(run_token='old', status='failed', collection_status='partial'),
                    SCRIPTS={'downsync.py': Mock(run=reader)})
        with patch.object(retry, 'require_retained_run'), patch.object(retry, 'save_current'), \
             patch.object(retry, 'run_cases', return_value={}), patch.object(retry, 'copy_result_tree', return_value={}), \
             patch.object(retry, 'set_run_cases', side_effect=RuntimeError('restore refused')), \
             patch.object(retry.time, 'sleep', side_effect=AssertionError('retry after failed rollback')):
            with self.assertRaises(RuntimeError) as caught:
                retry.collect_current(root, object(), dict, None, None)
        self.assertIs(caught.exception, error)
        reader.assert_called_once()


if __name__ == '__main__':
    unittest.main()
