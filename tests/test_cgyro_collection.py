"""Collection metadata/protocol regressions; no scheduler, GUI or solver calls."""
import ast
import copy
from contextlib import ExitStack
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import test_cgyro_storage as fixtures
import OMFITlib_cgyro_run_state as state
import OMFITlib_cgyro_retry as retry

queue = fixtures.queue_api


def collection_functions():
    # Native script entry statements require OMFIT. Its helpers are deliberately
    # pure or injected so these tests execute the real implementations alone.
    path = fixtures.REPO / 'CGYRO_TGLF_scan/CGYRO_scan/SCRIPTS/downsync.py'
    body = [node for node in ast.parse(path.read_text(encoding='utf-8')).body
            if isinstance(node, ast.FunctionDef)]
    namespace = dict(os=os, re=re, shell_quote=state.quote, output_text=state.text_output,
                     OUTPUT_PROBE_MAX_BYTES=16 * 1024, point_scheduler_states=retry.point_scheduler_states)
    exec(compile(ast.Module(body=body, type_ignores=[]), str(path), 'exec'), namespace)
    return namespace


class CompressedSchedulerTests(unittest.TestCase):
    def points(self, count):
        return ['p{:06d}'.format(index + 1) for index in range(count)]

    def report(self, rows, job='123', points=None, indices=None, queue_rows=''):
        output = 'CGYRO_QUEUE_OK\nCGYRO_ACCOUNT_OK\n' + queue_rows
        output += ''.join('CGYRO_STATE|' + row + '\n' for row in rows)
        return state.parse_probe(output, job, self.points(135) if points is None else points, indices)

    def test_reported_first_array_keeps_completed_and_cancelled_points_distinct(self):
        cancelled = {45, 51, 60, 65, 66, 67, 75, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90}
        rows = ['123_{}|{}|0:0'.format(index, 'CANCELLED by 1000' if index in cancelled else 'COMPLETED')
                for index in range(91)] + ['123_[91-134%40]|CANCELLED by 1000|0:0']
        result = self.report(rows)
        self.assertTrue(result['terminal'])
        self.assertEqual(result['outcome'], 'cancelled')
        self.assertEqual(list(result['point_states'].values()).count('COMPLETED'), 71)
        self.assertEqual(list(result['point_states'].values()).count('CANCELLED'), 64)
        self.assertIn('123_[91-134%40]', result['scheduler_status'])

    def test_four_reported_pending_arrays_cancelled_as_one_group(self):
        for job in ('124', '125', '126', '127'):
            with self.subTest(job=job):
                result = self.report([job + '_[0-134%40]|CANCELLED by 1000|0:0'], job)
                self.assertTrue(result['terminal'])
                self.assertEqual(set(result['point_states'].values()), {'CANCELLED'})
                self.assertEqual(len(result['point_states']), 135)

    def test_retry_subset_uses_original_task_indices_for_groups_lists_and_steps(self):
        result = self.report(['123_[1,5-9:2%40]|COMPLETED|0:0'],
                             points=['first', 'second', 'third'], indices=[1, 5, 9])
        self.assertTrue(result['terminal'])
        self.assertEqual(result['point_states'], dict(first='COMPLETED', second='COMPLETED', third='COMPLETED'))

    def test_large_group_matches_only_requested_indices(self):
        result = self.report(['123_[0-999999999%40]|CANCELLED by 1000|0:0'],
                             points=['one', 'two'], indices=[0, 999999999])
        self.assertTrue(result['terminal'])
        self.assertEqual(len(result['point_states']), 2)

    def test_missing_task_prevents_terminal_confirmation(self):
        result = self.report(['123_[0-133%40]|CANCELLED by 1000|0:0'])
        self.assertFalse(result['terminal'])
        self.assertEqual(result['outcome'], 'unknown')
        self.assertEqual(result['point_states']['p000135'], '')

    def test_live_requeued_task_overrides_finished_accounting(self):
        result = self.report(['123_[0-134%40]|CANCELLED by 1000|0:0'],
                             queue_rows='CGYRO_QUEUE|123_2|RUNNING\n')
        self.assertTrue(result['active'])
        self.assertFalse(result['terminal'])

    def test_other_job_and_steps_cannot_complete_missing_tasks(self):
        result = self.report(['124_[0-134%40]|CANCELLED|0:0', '123_0.batch|COMPLETED|0:0'])
        self.assertFalse(result['terminal'])
        self.assertEqual(set(result['point_states'].values()), {''})

    def test_malformed_or_conflicting_groups_remain_unconfirmed(self):
        for selector in ('[134-0%40]', '[0-134:0%40]', '[0-134,]', '[bad]'):
            with self.subTest(selector=selector):
                result = self.report(['123|COMPLETED|0:0', '123_' + selector + '|CANCELLED|0:0'])
                self.assertFalse(result['terminal'])
        result = self.report(['123_[0-134%40]|CANCELLED|0:0', '123_0|COMPLETED|0:0'])
        self.assertFalse(result['terminal'])

    def test_queue_or_account_failure_still_prevents_terminal_confirmation(self):
        output = 'CGYRO_QUEUE_OK\nCGYRO_ACCOUNT_OK\nCGYRO_STATE|123_[0-134%40]|CANCELLED|0:0\n'
        for marker in ('CGYRO_QUEUE_OK', 'CGYRO_ACCOUNT_OK'):
            with self.subTest(marker=marker):
                result = state.parse_probe(output.replace(marker, marker + '_ERROR'), '123', self.points(135))
                self.assertFalse(result['terminal'])

    def test_unconfirmed_query_explains_queue_accounting_and_missing_task_failures(self):
        complete = 'CGYRO_QUEUE_OK\nCGYRO_ACCOUNT_OK\nCGYRO_STATE|123_[0-134]|CANCELLED|0:0\n'
        self.assertIn('squeue 查询失败', state.parse_probe(complete.replace('CGYRO_QUEUE_OK',
            'CGYRO_QUEUE_ERROR'), '123', self.points(135))['reason'])
        self.assertIn('sacct 查询失败', state.parse_probe(complete.replace('CGYRO_ACCOUNT_OK',
            'CGYRO_ACCOUNT_MISSING'), '123', self.points(135))['reason'])
        self.assertIn('没有返回作业 123', self.report([])['reason'])
        self.assertIn('缺少 1 / 135', self.report(['123_[0-133]|CANCELLED|0:0'])['reason'])
        self.assertIn('p000135', self.report(['123_[0-133]|CANCELLED|0:0'])['reason'])
        self.assertEqual(self.report(['123_[0-134]|CANCELLED|0:0'])['reason'], '')

    def test_actual_shell_probe_requests_uncompressed_accounting(self):
        script = '''squeue() { return 0; }
sacct() {
  case " $* " in *" --array "*) printf '123_0|COMPLETED|0:0\\n123_1|CANCELLED by 1000|0:0\\n';;
    *) printf 'array expansion was not requested\\n' >&2; return 7;; esac
}
''' + state.slurm_probe('123')
        done = subprocess.run(['bash', '-c', script], capture_output=True, text=True, timeout=15)
        self.assertEqual(done.returncode, 0, done.stderr)
        result = state.parse_probe(done.stdout, '123', self.points(2))
        self.assertTrue(result['terminal'])
        self.assertEqual(result['point_states'], dict(p000001='COMPLETED', p000002='CANCELLED'))

    def shell_report(self, body, points=135, queue_rows=''):
        with tempfile.TemporaryDirectory() as directory:
            calls = Path(directory) / 'calls'
            script = ('squeue() { printf %s ' + state.quote(queue_rows) + '; }\n'
                      'sacct() { printf "%s\\n" "$*" >> ' + state.quote(str(calls)) + '\n'
                      + body + '\n}\n' + state.slurm_probe('123'))
            done = subprocess.run(['bash', '-c', script], capture_output=True, text=True, timeout=15)
            arguments = calls.read_text().splitlines()
        self.assertEqual(done.returncode, 0, done.stderr)
        return done, arguments, state.parse_probe(done.stdout, '123', self.points(points))

    def test_old_sacct_rejects_array_option_then_confirms_all_grouped_tasks(self):
        for error in ("sacct: unrecognized option '--array'", "sacct: unrecognized option `--array'"):
            body = ('case " $* " in *" --array "*) printf "%s\\n" ' + state.quote(error)
                    + ' >&2; return 1;; esac\n'
                    "printf '123_[0-134%%40]|CANCELLED by 1000|0:0\\n'")
            with self.subTest(error=error):
                done, arguments, result = self.shell_report(body)
                self.assertEqual(len(arguments), 2)
                self.assertIn('--array', arguments[0])
                self.assertNotIn('--array', arguments[1])
                self.assertIn('-j 123', arguments[1])
                self.assertIn('--format=JobID%128,State%64,ExitCode', arguments[1])
                self.assertTrue(result['terminal'])
                self.assertEqual(result['outcome'], 'cancelled')
                self.assertEqual(len(result['point_states']), 135)
                self.assertEqual(set(result['point_states'].values()), {'CANCELLED'})
                self.assertEqual(done.stderr, '')

    def test_accounting_connection_owner_and_other_option_errors_do_not_retry(self):
        for error in ('sacct: database connection failed', 'sacct: access denied',
                      "sacct: unrecognized option '-X'", 'sacct: --array requires an argument'):
            with self.subTest(error=error):
                done, arguments, result = self.shell_report('printf "%s\\n" ' + state.quote(error) + ' >&2; return 1')
                self.assertEqual(len(arguments), 1)
                self.assertFalse(result['terminal'])
                self.assertFalse(result['accounting_verified'])
                self.assertIn('CGYRO_ACCOUNT_ERROR', done.stdout)
                self.assertIn(error, done.stderr)

    def test_old_sacct_failed_fallback_still_reports_accounting_error(self):
        body = '''case " $* " in *" --array "*) printf "%s\\n" "sacct: unrecognized option '--array'" >&2; return 1;; esac
printf 'sacct: database connection failed\\n' >&2; return 1'''
        done, arguments, result = self.shell_report(body)
        self.assertEqual(len(arguments), 2)
        self.assertFalse(result['terminal'])
        self.assertFalse(result['accounting_verified'])
        self.assertIn('database connection failed', done.stderr)

    def test_supported_empty_accounting_is_unknown_without_retry(self):
        done, arguments, result = self.shell_report('return 0')
        self.assertEqual(len(arguments), 1)
        self.assertTrue(result['accounting_verified'])
        self.assertFalse(result['terminal'])
        self.assertEqual(result['outcome'], 'unknown')

    def test_legacy_option_fallback_does_not_bypass_missing_or_active_task_checks(self):
        for coverage, queue_rows in ((133, ''), (134, '123_2|RUNNING\n')):
            body = ('''case " $* " in *" --array "*) printf "%s\\n" "sacct: unrecognized option '--array'" >&2; return 1;; esac
printf '%s\\n' ''' + state.quote('123_[0-' + str(coverage) + '%40]|CANCELLED|0:0'))
            with self.subTest(coverage=coverage, queue_rows=queue_rows):
                done, arguments, result = self.shell_report(body, queue_rows=queue_rows)
                self.assertEqual(len(arguments), 2)
                self.assertTrue(result['accounting_verified'])
                self.assertFalse(result['terminal'])


class OutputProbeTests(unittest.TestCase):
    def setUp(self):
        self.functions = collection_functions()
        self.points = ['p000001', 'p000002']

    def parse(self, text, points=None):
        return self.functions['parse_output_probe'](text, self.points if points is None else points)

    def test_zero_bytes_is_a_present_size_and_missing_directory_can_be_skipped(self):
        result = self.parse('CGYRO_BYTES|p000001|0\nCGYRO_POINT|p000001|\n'
                            'CGYRO_POINT|p000002|out.cgyro.grids out.cgyro.time frequency no_exit_record\n')
        self.assertEqual(result['sizes'], {'p000001': 0})
        self.assertEqual(result['complete'], {'p000001'})
        self.assertEqual(result['failed'], {'p000002'})

    def test_solver_failure_keeps_readable_samples_and_pipe_in_diagnostic(self):
        result = self.parse('environment warning\nCGYRO_BYTES|p000001|40\nCGYRO_POINT|p000001|solver_error\n'
                            'CGYRO_ERROR|p000001|ERROR: limit | detail\n', ['p000001'])
        self.assertEqual(result['missing'], {})
        self.assertEqual(result['solver_errors']['p000001'], ['ERROR: limit | detail'])
        self.assertEqual(result['failed'], {'p000001'})

    def test_rejects_missing_duplicate_invalid_and_foreign_size_rows(self):
        base = 'CGYRO_POINT|p000001|\nCGYRO_BYTES|p000001|100\n'
        for text in (base + 'CGYRO_POINT|p000002|\n',
                     base + 'CGYRO_BYTES|p000001|0\n',
                     base.replace('|100', '|-1'), base.replace('|100', '|١'),
                     base + 'CGYRO_BYTES|foreign|0\n'):
            with self.subTest(text=text), self.assertRaises(RuntimeError):
                self.parse(text, ['p000001'] if 'p000002' not in text else self.points)

    def test_rejects_duplicate_foreign_missing_and_empty_point_sets(self):
        for text, points in (
            ('CGYRO_POINT|p000001|\nCGYRO_POINT|p000001|\n', ['p000001']),
            ('CGYRO_ERROR|foreign|bad\n', ['p000001']),
            ('CGYRO_BYTES|p000001|1\n', ['p000001']),
            ('', []), ('', ['p000001', 'p000001']),
        ):
            with self.subTest(text=text, points=points), self.assertRaises((ValueError, RuntimeError)):
                self.parse(text, points)

    def test_probe_validates_every_point_before_committing_sizes(self):
        manifest = dict(workDir='/runs/frozen', point_output_bytes={'prior': 17})
        output = 'CGYRO_BYTES|p000001|20\nCGYRO_POINT|p000001|\nCGYRO_POINT|p000002|\n'
        with self.assertRaisesRegex(RuntimeError, 'omitted a readable point size'):
            self.functions['probe_run_outputs'](manifest, self.points, lambda command: (0, output, ''), '123')
        self.assertEqual(manifest['point_output_bytes'], {})
        self.assertNotIn('complete_output_points', manifest)
        self.assertNotIn('solver_errors', manifest)

    def test_probe_preserves_previous_attempt_failure_states(self):
        manifest = dict(workDir='/runs/frozen', attempts=[dict(scheduler_sync=dict(point_states={'p000001': 'OUT_OF_MEMORY'}))],
                        scheduler_sync=dict(point_states={'p000002': 'COMPLETED'}))
        output = ''.join('CGYRO_BYTES|{}|20\nCGYRO_POINT|{}|\n'.format(p, p) for p in self.points)
        failed = self.functions['probe_run_outputs'](manifest, self.points, lambda command: (0, output, ''), '123', {})
        self.assertEqual(failed, ['p000001'])
        self.assertEqual(manifest['complete_output_points'], self.points)

    def test_empty_scan_rejected_before_remote_call(self):
        def forbidden(command):
            raise AssertionError('empty scan executed remotely')
        with self.assertRaises(ValueError):
            self.functions['probe_run_outputs']({}, [], forbidden, '123')

    def test_probe_commands_bound_utf8_quoted_size_and_use_frozen_point_paths(self):
        points = ['p{:06d}'.format(i) for i in range(1, 180)]
        manifest = dict(workDir="/runs/原始/'directory", point_workdirs={points[-1]: '/runs/retried'})
        batches = list(self.functions['output_probe_commands'](manifest, points))
        self.assertGreater(len(batches), 1)
        self.assertEqual([point for batch, _ in batches for point in batch], points)
        for _, command in batches:
            self.assertLessEqual(len(('/bin/bash -c ' + state.quote(command)).encode('utf-8')), 16 * 1024)
        self.assertIn('/runs/retried/' + points[-1], batches[-1][1])

    def test_actual_probe_requires_normal_linear_termination_even_with_zero_exit(self):
        points = ['p000001', 'p000002', 'p000003', 'p000004']
        manifest = dict(workDir='/cgyro_probe_fixture', case_tag='linear')
        source = '''set -eu
probe_dir=$(mktemp -d)
trap 'rm -r -- "$probe_dir"' EXIT
cd "$probe_dir"
for point in p000001 p000002 p000003 p000004; do
  mkdir "$point"
  for file in out.cgyro.grids out.cgyro.time out.cgyro.freq; do printf '1\\n' > "$point/$file"; done
  printf '0\\n' > "$point/cgyro.exit"
done
printf 'Still initializing\\n' > p000001/out.cgyro.info
printf 'Linear converged\\n' > p000002/out.cgyro.info
printf 'Linear terminated at max time\\n' > p000003/out.cgyro.info
printf 'Linear converged\\nERROR: Integration error exceeded limit\\n' > p000004/out.cgyro.info
'''
        source += '\n'.join(command.replace('/cgyro_probe_fixture/', './')
                            for _, command in self.functions['output_probe_commands'](manifest, points))
        command = ['wsl.exe', '-d', 'Ubuntu', '--', '/bin/bash', '-s'] if os.name == 'nt' else ['/bin/bash', '-s']
        completed = subprocess.run(command, input=source.encode(), stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, timeout=20)
        self.assertEqual(completed.returncode, 0, completed.stderr.decode(errors='replace'))
        result = self.parse(completed.stdout.decode(), points)
        self.assertEqual(result['complete'], {'p000002', 'p000003'})
        self.assertEqual(result['failed'], {'p000001', 'p000004'})
        self.assertEqual(result['missing'], {})  # Keep readable partial data.


class NativeCollectionEntryTests(unittest.TestCase):
    def collect(self, output, reader_calls, scheduler_output=None, stopped=False):
        points = ['p000001', 'p000002']
        manifest = dict(run_token='token', points=points, workDir='/runs/frozen', local_workDir='/tmp/test',
                        server='recorded-server', tunnel='recorded-tunnel', scheduler='slurm',
                        case_tag='linear', job_id='123', stop_requested=stopped,
                        point_table={p: {'values': {'KY': 0.0}} for p in points})
        root = dict(RUN_MANIFEST=manifest, SETTINGS=dict(SETUP=dict(icgyro=1), REMOTE_SETUP={}))
        stored = {}
        class UI:
            def remote_execute(self, server, command, directory, tunnel, **kwargs):
                if (server, directory, tunnel) != ('recorded-server', '/runs/frozen', 'recorded-tunnel'):
                    raise AssertionError('collection used a different endpoint')
                kwargs['std_out'].append(scheduler_output if scheduler_output is not None and 'cgyro_queue_rows()' in command else output)
                return 0
        def reader(location, **kwargs):
            reader_calls.append(location)
            return {'n_time': 1, 't': [0.0]}
        path = fixtures.REPO / 'CGYRO_TGLF_scan/CGYRO_scan/SCRIPTS/downsync.py'
        with ExitStack() as stack:
            stack.enter_context(patch.object(queue, 'save_current'))
            stack.enter_context(patch.object(fixtures.db_api, 'run_cases', return_value=stored))
            stack.enter_context(patch.object(fixtures.storage, 'store_result', side_effect=lambda node, candidate, factory, **kwargs: candidate))
            stack.enter_context(patch.object(fixtures.scratch, 'ensure_capacity', return_value={}))
            if scheduler_output is None:
                stack.enter_context(patch.object(state, 'refresh_run_state', return_value=dict(
                    active=False, terminal=True, outcome='completed', queue_verified=True)))
            exec(compile(path.read_text(encoding='utf-8'), str(path), 'exec'), dict(
                root=root, OMFITtree=dict, OMFITx=UI(), OMFITcgyro=reader))
        return manifest, stored

    def test_stopped_array_collects_readable_points_with_real_grouped_state_parser(self):
        output = ''.join('CGYRO_BYTES|{}|20\nCGYRO_POINT|{}|\n'.format(p, p) for p in ('p000001', 'p000002'))
        scheduler = ('CGYRO_QUEUE_OK\nCGYRO_ACCOUNT_OK\nCGYRO_STATE|123_0|COMPLETED|0:0\n'
                     'CGYRO_STATE|123_[1-1%40]|CANCELLED by 1000|0:0\n')
        calls = []
        manifest, stored = self.collect(output, calls, scheduler_output=scheduler, stopped=True)
        self.assertEqual(manifest['scheduler_sync']['outcome'], 'cancelled')
        self.assertEqual(manifest['loaded_points'], ['p000001'])
        self.assertEqual(manifest['partial_points'], ['p000002'])
        self.assertEqual(set(stored), {'p000001', 'p000002'})
        self.assertEqual(len(calls), 2)

    def test_stopped_pending_array_with_no_outputs_skips_without_reading_results(self):
        output = ''.join('CGYRO_POINT|{}|out.cgyro.grids out.cgyro.time frequency no_exit_record\n'.format(p)
                         for p in ('p000001', 'p000002'))
        scheduler = 'CGYRO_QUEUE_OK\nCGYRO_ACCOUNT_OK\nCGYRO_STATE|123_[0-1%40]|CANCELLED by 1000|0:0\n'
        calls = []
        manifest, stored = self.collect(output, calls, scheduler_output=scheduler, stopped=True)
        self.assertEqual(manifest['collection_status'], 'ready')
        self.assertEqual(manifest['status'], 'cancelled')
        self.assertEqual(manifest['skipped_points'], ['p000001', 'p000002'])
        self.assertEqual(calls, [])
        self.assertEqual(stored, {})
        path = fixtures.REPO / 'CGYRO_TGLF_scan/CGYRO_scan/SCRIPTS/CGYROScan.py'
        publish = next(node for node in ast.parse(path.read_text(encoding='utf-8')).body
                       if isinstance(node, ast.FunctionDef) and node.name == 'publish_loaded_run')
        namespace = dict(OMFITtree=dict, compact_storage=lambda *args, **kwargs: None,
                         remember_collection=lambda *args: None, print=lambda *args: None)
        exec(compile(ast.Module(body=[publish], type_ignores=[]), str(path), 'exec'), namespace)
        manifest['dimensions'] = 1
        previous = object()
        root = dict(RUN_MANIFEST=manifest, RUN_DB={'previous': previous})
        namespace['publish_loaded_run'](root)
        self.assertEqual(manifest['collection_status'], 'empty')
        self.assertFalse(manifest['submission_complete'])
        self.assertFalse(manifest['scan_complete'])
        self.assertIs(root['RUN_DB']['previous'], previous)

    def test_stopped_array_with_live_task_does_not_read_any_result(self):
        scheduler = ('CGYRO_QUEUE_OK\nCGYRO_ACCOUNT_OK\nCGYRO_QUEUE|123_1|RUNNING\n'
                     'CGYRO_STATE|123_[0-1%40]|CANCELLED by 1000|0:0\n')
        calls = []
        with self.assertRaisesRegex(RuntimeError, 'still queued/running'):
            self.collect('', calls, scheduler_output=scheduler, stopped=True)
        self.assertEqual(calls, [])

    def test_native_entry_collects_zero_time_samples_from_saved_endpoint(self):
        output = ''.join('CGYRO_BYTES|{}|20\nCGYRO_POINT|{}|\n'.format(p, p)
                         for p in ('p000001', 'p000002'))
        calls = []
        manifest, stored = self.collect(output, calls)
        self.assertEqual(manifest['status'], 'loaded')
        self.assertEqual(manifest['collection_status'], 'ready')
        self.assertEqual(manifest['loaded_points'], list(stored))
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0], ['/runs/frozen/p000001', 'recorded-server', 'recorded-tunnel'])

    def test_missing_later_size_stops_native_entry_before_first_reader(self):
        calls = []
        with self.assertRaisesRegex(RuntimeError, 'omitted a readable point size'):
            self.collect('CGYRO_BYTES|p000001|20\nCGYRO_POINT|p000001|\nCGYRO_POINT|p000002|\n', calls)
        self.assertEqual(calls, [])


class QueueMetadataTests(unittest.TestCase):
    def root(self):
        manifests = {token: dict(run_token=token, batch_id='batch', case_id=token, status='submitted',
                                 job_id=number, submission_uncertain=False, points=['p000001'])
                     for token, number in [('first', '1'), ('second', '2')]}
        return dict(SETTINGS={}, RUN_MANIFEST=copy.deepcopy(manifests['second']),
                    RUN_HISTORY={token: dict(manifest=copy.deepcopy(m)) for token, m in manifests.items()},
                    RUN_BATCH=dict(tokens=list(manifests), case_ids=list(manifests), batch_id='batch'),
                    RUN_DB={'__STORAGE__': {'version': fixtures.db_api.STORAGE_SCHEMA_VERSION},
                            '__RUNS__': {token: dict(manifest=copy.deepcopy(m)) for token, m in manifests.items()}})

    def test_refresh_updates_noncurrent_frozen_metadata_and_preserves_payload_identity(self):
        root = self.root()
        owner = object()
        root['RUN_DB']['__RUNS__']['first']['cases'] = {'point': owner}
        def refreshed(view, ui):
            view['RUN_MANIFEST'].update(status='failed', scheduler_sync=dict(outcome='failed', terminal=True, active=False))
        with patch.object(queue, 'save_current'), patch.object(queue, 'refresh_run_state', refreshed):
            queue.refresh_queue(root, object())
        for token in ('first', 'second'):
            self.assertEqual(root['RUN_HISTORY'][token]['manifest'], root['RUN_DB']['__RUNS__'][token]['manifest'])
            self.assertEqual(root['RUN_DB']['__RUNS__'][token]['manifest']['status'], 'failed')
        self.assertEqual(root['RUN_MANIFEST'], root['RUN_HISTORY']['second']['manifest'])
        self.assertIs(root['RUN_DB']['__RUNS__']['first']['cases']['point'], owner)

    def test_recovery_removes_old_uncertain_parent_from_both_saved_views(self):
        root = self.root()
        root['RUN_HISTORY']['first']['manifest'].update(submission_uncertain=True, submission_parent={'old': 1})
        root['RUN_DB']['__RUNS__']['first']['manifest'] = copy.deepcopy(root['RUN_HISTORY']['first']['manifest'])
        def recovered(view, ui, factory):
            view['RUN_MANIFEST'].update(submission_uncertain=False, job_id='99')
            view['RUN_MANIFEST'].pop('submission_parent')
        with patch.object(queue, 'save_current'), patch.object(queue, 'refresh_run_state', lambda view, ui: None):
            queue.refresh_queue(root, object(), recover=recovered)
        frozen = root['RUN_DB']['__RUNS__']['first']['manifest']
        self.assertEqual(frozen['job_id'], '99')
        self.assertFalse(frozen['submission_uncertain'])
        self.assertNotIn('submission_parent', frozen)

    def test_grouped_cancel_sync_commits_all_five_jobs_without_reading_payloads(self):
        manifests, points = {}, ['p{:06d}'.format(index + 1) for index in range(135)]
        for index, job in enumerate(('11', '12', '13', '14', '15')):
            token = '{:032x}'.format(index + 1)
            manifests[token] = dict(run_token=token, batch_id='batch', case_id='case-' + job,
                status='cancel_requested', job_id=job, scheduler='slurm', points=points,
                server='user@cluster', workDir='/runs/' + token, stop_requested=True,
                cancellation=dict(accepted=True, wake_sent=True))
        tokens = list(manifests)
        root = dict(SETTINGS={'REMOTE_SETUP': {}}, RUN_MANIFEST=copy.deepcopy(manifests[tokens[-1]]),
            RUN_HISTORY={token: dict(manifest=copy.deepcopy(manifest)) for token, manifest in manifests.items()},
            RUN_BATCH=dict(tokens=tokens, case_ids=[m['case_id'] for m in manifests.values()],
                           batch_id='batch', stop_requested=True),
            RUN_DB={'__STORAGE__': {'version': fixtures.db_api.STORAGE_SCHEMA_VERSION},
                    '__RUNS__': {token: dict(manifest=copy.deepcopy(m)) for token, m in manifests.items()}})
        queried = []
        class UI:
            def remote_execute(self, server, command, directory, tunnel, **kwargs):
                if 'scancel ' in command or 'sbatch ' in command:
                    raise AssertionError('Status synchronization changed a job')
                job = re.search(r'job_id=([0-9]+)', command).group(1)
                queried.append(job)
                cancelled = {45, 51, 60, 65, 66, 67, 75, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90}
                rows = ([job + '_{}|{}|0:0'.format(i, 'CANCELLED' if i in cancelled else 'COMPLETED')
                         for i in range(91)] + [job + '_[91-134%40]|CANCELLED by 1000|0:0'] if job == '11'
                        else [job + '_[0-134%40]|CANCELLED by 1000|0:0'])
                fake_scheduler = '''squeue() { return 0; }
sacct() {
  case " $* " in *" --array "*) printf "%s\\n" "sacct: unrecognized option '--array'" >&2; return 1;; esac
  printf '%s\\n' ROWS
}
'''.replace('ROWS', ' '.join(state.quote(row) for row in rows))
                done = subprocess.run(['bash', '-c', fake_scheduler + shlex.split(command)[2]],
                                      capture_output=True, text=True, timeout=15)
                kwargs['std_out'].append(done.stdout)
                kwargs['std_err'].append(done.stderr)
                return done.returncode
        with patch.object(queue, 'compact_storage', side_effect=AssertionError('Result files inspected')), \
                patch.object(queue, 'freeze_run_inputs', side_effect=AssertionError('Inputs copied')):
            summary = queue.refresh_queue(root, UI())
        self.assertIn('已结束 5，活动 0，未确认 0', summary)
        self.assertIn('作业 11：Slurm 已取消', summary)
        self.assertIn('完整 0 / 5', queue.queue_summary(root))
        self.assertEqual(queried, ['11', '12', '13', '14', '15'])
        for token in tokens:
            for manifest in (root['RUN_HISTORY'][token]['manifest'], root['RUN_DB']['__RUNS__'][token]['manifest']):
                self.assertEqual(manifest['status'], 'cancelled')
                self.assertTrue(manifest['scheduler_sync']['terminal'])
                states = list(manifest['scheduler_sync']['point_states'].values())
                self.assertEqual(states.count('COMPLETED'), 71 if manifest['job_id'] == '11' else 0)
                self.assertEqual(states.count('CANCELLED'), 64 if manifest['job_id'] == '11' else 135)
        self.assertEqual(root['RUN_MANIFEST']['status'], 'cancelled')
        with patch.object(queue, 'ensure_layout'):
            queue.activate_run(root, tokens[0])
        self.assertEqual(root['RUN_MANIFEST']['job_id'], '11')
        self.assertTrue(root['RUN_MANIFEST']['scheduler_sync']['terminal'])

    def test_sync_never_compacts_freezes_or_migrates_results_and_uses_live_metadata(self):
        root = self.root()
        root['Cases'] = {'opaque_legacy_payload': object()}
        root['RUN_MANIFEST']['active_points'] = ['p000001']
        before_cases = root['Cases']
        queried = []
        def refreshed(view, ui):
            queried.append(copy.deepcopy(view['RUN_MANIFEST']))
            self.assertEqual(set(view), {'RUN_MANIFEST', 'SETTINGS'})
        with patch.object(queue, 'compact_storage', side_effect=AssertionError('result files read')), \
                patch.object(queue, 'freeze_run_inputs', side_effect=AssertionError('input ZIP copied')), \
                patch.object(fixtures.db_api, 'ensure_layout', side_effect=AssertionError('legacy tree migrated')), \
                patch.object(queue, 'refresh_run_state', refreshed):
            queue.refresh_queue(root, object())
        self.assertEqual(len(queried), 2)
        self.assertEqual(queried[-1]['active_points'], ['p000001'])
        self.assertIs(root['Cases'], before_cases)

    def test_sync_after_cancel_queries_only_once_per_job(self):
        root = self.root()
        root['RUN_BATCH']['stop_requested'] = True
        for manifest in [root['RUN_MANIFEST']] + [entry['manifest'] for entry in root['RUN_HISTORY'].values()]:
            manifest['scheduler'] = 'slurm'
        def stopped(view, ui, job, token):
            view['RUN_MANIFEST']['status'] = 'cancelled'
            return dict(outcome='cancelled', active=False, terminal=True)
        with patch.object(queue, 'stop_run', side_effect=stopped) as stop, \
                patch.object(queue, 'refresh_run_state', side_effect=AssertionError('duplicate query')):
            queue.refresh_queue(root, object())
        self.assertEqual(stop.call_count, 2)
        self.assertEqual(root['RUN_MANIFEST']['status'], 'cancelled')

    def test_focused_sync_does_not_touch_unrelated_current_run(self):
        root = self.root()
        root['RUN_BATCH']['focus_token'] = 'first'
        original = copy.deepcopy(root['RUN_MANIFEST'])
        with patch.object(queue, 'refresh_run_state') as query, \
                patch.object(queue, 'save_current', side_effect=AssertionError('unrelated result saved')):
            queue.refresh_queue(root, object())
        self.assertEqual(query.call_count, 1)
        self.assertEqual(query.call_args.args[0]['RUN_MANIFEST']['run_token'], 'first')
        self.assertEqual(root['RUN_MANIFEST'], original)

    def test_reentrant_job_replacement_is_not_overwritten_by_late_query(self):
        root = self.root()
        root['RUN_BATCH']['focus_token'] = 'second'
        def query(view, ui):
            root['RUN_MANIFEST']['job_id'] = 'new-job'
            view['RUN_MANIFEST']['status'] = 'failed'
        with patch.object(queue, 'refresh_run_state', query), \
                self.assertRaisesRegex(RuntimeError, 'changed during synchronization'):
            queue.refresh_queue(root, object())
        self.assertEqual(root['RUN_MANIFEST']['job_id'], 'new-job')
        self.assertEqual(root['RUN_HISTORY']['second']['manifest']['status'], 'submitted')

    def test_single_run_script_uses_metadata_view_for_recovery_and_stop(self):
        root = self.root()
        root.pop('RUN_BATCH')
        root['RUN_MANIFEST'].update(submission_uncertain=True, submission_stop_requested=True)
        def recover(view, ui, factory):
            self.assertEqual(set(view), {'RUN_MANIFEST', 'SETTINGS'})
            view['RUN_MANIFEST'].update(submission_uncertain=False, job_id='99')
        result = dict(outcome='cancelled', active=False, terminal=True)
        def stop(view, ui, job, token):
            view['RUN_MANIFEST'].update(status='cancelled', scheduler_sync=result)
            return result
        path = fixtures.REPO / 'CGYRO_TGLF_scan/CGYRO_scan/SCRIPTS/refresh_run_status.py'
        with patch.object(retry, 'recover_submission', recover), patch.object(queue, 'stop_run', side_effect=stop) as stopped, \
                patch.object(queue, 'refresh_run_state', side_effect=AssertionError('duplicate query')), \
                patch.object(queue, 'save_current', side_effect=AssertionError('payload save')):
            exec(compile(path.read_text(encoding='utf-8'), str(path), 'exec'), dict(root=root, OMFITx=object(), OMFITtree=dict))
        self.assertEqual(stopped.call_count, 1)
        self.assertEqual(root['RUN_MANIFEST']['job_id'], '99')
        self.assertTrue(root['RUN_MANIFEST']['auto_collect_requested'])
        self.assertEqual(root['RUN_MANIFEST'], root['RUN_DB']['__RUNS__']['second']['manifest'])

    def test_query_error_keeps_payloads_and_records_failure_without_retry(self):
        root = self.root()
        root['RUN_BATCH']['focus_token'] = 'second'
        with patch.object(queue, 'refresh_run_state', side_effect=RuntimeError('network unavailable')) as query, \
                self.assertRaisesRegex(RuntimeError, 'network unavailable'):
            queue.refresh_queue(root, object())
        self.assertEqual(query.call_count, 1)
        self.assertEqual(root['RUN_MANIFEST']['status'], 'submitted')
        self.assertEqual(root['RUN_MANIFEST']['sync_error'], 'network unavailable')
        self.assertEqual(root['RUN_MANIFEST'], root['RUN_HISTORY']['second']['manifest'])

    def test_successful_process_with_failed_squeue_is_not_silently_reported_as_synced(self):
        root = self.root()
        root['SETTINGS'] = {'REMOTE_SETUP': {}}
        for token, entry in root['RUN_HISTORY'].items():
            entry['manifest'].update(scheduler='slurm', status='cancel_requested', stop_requested=True,
                                     server='user@cluster', workDir='/runs/' + token)
        root['RUN_MANIFEST'] = copy.deepcopy(root['RUN_HISTORY']['second']['manifest'])
        seen = []
        class UI:
            def remote_execute(self, server, command, directory, tunnel, **kwargs):
                job = '1' if directory.endswith('first') else '2'
                seen.append(job)
                kwargs['std_out'].append('CGYRO_QUEUE_ERROR\nCGYRO_ACCOUNT_OK\n'
                    'CGYRO_STATE|' + job + '_0|CANCELLED by 1000|0:0\n')
                kwargs['std_err'].append('squeue: query failed')
                return 0
        with patch.object(queue, 'compact_storage', side_effect=AssertionError('result files read')), \
                patch.object(queue, 'freeze_run_inputs', side_effect=AssertionError('inputs copied')), \
                self.assertRaisesRegex(RuntimeError, 'squeue 查询失败'):
            queue.refresh_queue(root, UI())
        self.assertEqual(seen, ['1', '2'])
        for token, entry in root['RUN_HISTORY'].items():
            record = entry['manifest']
            self.assertEqual(record['status'], 'cancel_requested')
            self.assertFalse(record['scheduler_sync']['terminal'])
            self.assertIn('CGYRO_QUEUE_ERROR', record['scheduler_sync']['raw'])
            self.assertIn('squeue 查询失败', record['sync_error'])
            self.assertIn('squeue: query failed', record['sync_error'])
            self.assertEqual(record, root['RUN_DB']['__RUNS__'][token]['manifest'])
        summary = queue.queue_sync_summary(root)
        self.assertIn('已结束 0，活动 0，未确认 2', summary)
        self.assertIn('作业 1：未确认终态', summary)
        self.assertNotIn('已同步', summary)

    def test_abort_after_recovering_receipt_keeps_job_identity_in_all_views(self):
        root = self.root()
        root['RUN_BATCH']['focus_token'] = 'second'
        root['RUN_MANIFEST']['submission_uncertain'] = True
        def recover(view, ui, factory):
            view['RUN_MANIFEST'].update(job_id='99', submission_uncertain=False)
            raise KeyboardInterrupt('Abort after receipt')
        with self.assertRaisesRegex(KeyboardInterrupt, 'Abort after receipt'):
            queue.refresh_queue(root, object(), recover=recover)
        self.assertEqual(root['RUN_MANIFEST']['job_id'], '99')
        self.assertFalse(root['RUN_MANIFEST']['submission_uncertain'])
        self.assertEqual(root['RUN_MANIFEST'], root['RUN_HISTORY']['second']['manifest'])
        self.assertEqual(root['RUN_MANIFEST'], root['RUN_DB']['__RUNS__']['second']['manifest'])

    def test_abort_during_metadata_commit_rolls_back_all_views(self):
        root = self.root()
        original = copy.deepcopy(root)
        class AbortAfterAssignment(dict):
            armed = True
            def __setitem__(self, key, value):
                super().__setitem__(key, value)
                if self.armed and key == 'manifest':
                    self.armed = False
                    raise KeyboardInterrupt('abort after record assignment')
        root['RUN_DB']['__RUNS__']['second'] = AbortAfterAssignment(root['RUN_DB']['__RUNS__']['second'])
        changed = dict(root['RUN_MANIFEST'], status='failed')
        with self.assertRaises(KeyboardInterrupt):
            queue._commit_synced_manifest(root, 'second', changed, dict)
        self.assertEqual(root, original)

    def test_wrong_identity_rejected_without_any_metadata_change(self):
        root = self.root()
        original = copy.deepcopy(root)
        with self.assertRaisesRegex(ValueError, 'another run'):
            queue._commit_synced_manifest(root, 'first', root['RUN_MANIFEST'], dict)
        self.assertEqual(root, original)


    def test_secondary_rollback_failure_does_not_hide_abort_or_skip_record_restore(self):
        root = self.root()
        original = copy.deepcopy(root)
        interrupted = KeyboardInterrupt('original abort')
        class BrokenHistoryRollback(dict):
            assignments = 0
            def __setitem__(self, key, value):
                self.assignments += 1
                if self.assignments == 2:
                    raise RuntimeError('history restore refused')
                super().__setitem__(key, value)
        class AbortRecord(dict):
            armed = True
            def __setitem__(self, key, value):
                super().__setitem__(key, value)
                if self.armed:
                    self.armed = False
                    raise interrupted
        root['RUN_HISTORY']['second'] = BrokenHistoryRollback(root['RUN_HISTORY']['second'])
        root['RUN_DB']['__RUNS__']['second'] = AbortRecord(root['RUN_DB']['__RUNS__']['second'])
        with self.assertRaises(KeyboardInterrupt) as caught:
            queue._commit_synced_manifest(root, 'second', dict(root['RUN_MANIFEST'], status='failed'), dict)
        self.assertIs(caught.exception, interrupted)
        self.assertEqual(caught.exception.cgyro_rollback_errors, ['history: history restore refused'])
        self.assertEqual(root['RUN_DB']['__RUNS__']['second'], original['RUN_DB']['__RUNS__']['second'])
        self.assertEqual(root['RUN_MANIFEST'], original['RUN_MANIFEST'])
        self.assertNotEqual(root['RUN_HISTORY']['second'], original['RUN_HISTORY']['second'])

    def test_abort_inside_current_update_restores_all_previous_keys(self):
        root = self.root()
        original = copy.deepcopy(root)
        class AbortPartialUpdate(dict):
            armed = True
            def update(self, values):
                if self.armed:
                    self.armed = False
                    key = next(iter(values))
                    self[key] = values[key]
                    raise KeyboardInterrupt('partial update')
                super().update(values)
        root['RUN_MANIFEST'] = AbortPartialUpdate(root['RUN_MANIFEST'])
        with self.assertRaises(KeyboardInterrupt):
            queue._commit_synced_manifest(root, 'second', dict(root['RUN_MANIFEST'], status='failed'), dict)
        self.assertEqual(root, original)


class StateContractTests(unittest.TestCase):
    def test_one_unreadable_point_does_not_block_verified_neighbors(self):
        from types import SimpleNamespace
        manifest = dict(run_token='x', collection_status='pending')
        calls = []
        def download():
            calls.append(True)
            manifest.update(load_errors={'bad': 'truncated download'}, loaded_points=['good'],
                            partial_points=[], collection_status='ready')
            raise RuntimeError('download failed for bad')
        root = dict(RUN_MANIFEST=manifest, SCRIPTS={'downsync.py': SimpleNamespace(run=download)})
        with patch.object(retry, 'require_retained_run'), patch.object(retry, 'save_current'), \
                patch.object(retry, 'collected_points', return_value={'good'}), patch.object(retry.RetryWait, 'wait'), \
                patch.object(retry, 'submit_retry', side_effect=AssertionError('unexpected solver submission')):
            retry.collect_current(root, object(), dict, None, None)
        self.assertEqual(len(calls), 3)
        self.assertEqual(manifest['collection_status'], 'ready')
        self.assertEqual(manifest['loaded_points'], ['good'])
        self.assertEqual(manifest['load_errors'], {'bad': 'truncated download'})

    def test_publication_retry_never_downloads_already_verified_points(self):
        from types import SimpleNamespace
        manifest = dict(run_token='x', collection_status='ready', loaded_points=['good'], partial_points=[])
        def forbidden():
            raise AssertionError('duplicate download')
        root = dict(RUN_MANIFEST=manifest, SCRIPTS={'downsync.py': SimpleNamespace(run=forbidden)})
        with patch.object(retry, 'require_retained_run'), patch.object(retry, 'save_current'), \
                patch.object(retry, 'collected_points', return_value={'good'}):
            retry.collect_current(root, object(), dict, None, None)

    def test_collection_completion_and_retirement_have_distinct_requirements(self):
        complete = dict(status='loaded', collection_status='complete')
        self.assertFalse(state.collection_finished(complete))
        self.assertTrue(state.collection_recorded(complete))
        self.assertTrue(state.run_settled(complete))
        for phase in ('uploading', 'submitting', 'submission_unconfirmed', 'submitted', 'unknown'):
            self.assertFalse(state.run_settled(dict(complete, status=phase)))
        self.assertFalse(state.run_settled(dict(complete, scheduler_sync=dict(active=True, terminal=True, outcome='completed'))))
        self.assertFalse(state.run_settled(dict(complete, scheduler_sync=dict(active=False, terminal=False, outcome='unknown'))))

    def test_unknown_point_status_requires_an_explicit_legacy_opt_in(self):
        self.assertFalse(state.point_complete({}))
        self.assertTrue(state.point_complete({}, legacy_default=True))
        self.assertFalse(state.point_complete(dict(status='loaded', resume_pending=True)))
        self.assertTrue(state.point_complete(dict(status='loaded', final_time=0)))

    def test_wait_script_uses_one_poll_constant_for_sleep_and_heartbeat_accounting(self):
        with patch.object(state, 'QUEUE_POLL_SECONDS', 7), patch.object(state, 'WAIT_HEARTBEAT_SECONDS', 70):
            command = state.slurm_wait('12', 'a' * 32)
            self.assertIn('"$tick" -lt 7', command)
            self.assertIn('hb=$((hb+7))', command)
            self.assertIn('"$hb" -ge 70', command)
            self.assertNotIn('POLL_SECONDS', command)
            self.assertIn('sleep 7', state.pbs_wait('12.server'))


if __name__ == '__main__':
    unittest.main()
