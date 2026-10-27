"""Collection metadata/protocol regressions; no scheduler, GUI or solver calls."""
import ast
import copy
from contextlib import ExitStack
import os
from pathlib import Path
import re
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


class NativeCollectionEntryTests(unittest.TestCase):
    def collect(self, output, reader_calls):
        points = ['p000001', 'p000002']
        manifest = dict(run_token='token', points=points, workDir='/runs/frozen', local_workDir='/tmp/test',
                        server='recorded-server', tunnel='recorded-tunnel', scheduler='slurm',
                        case_tag='linear', job_id='123', point_table={p: {'values': {'KY': 0.0}} for p in points})
        root = dict(RUN_MANIFEST=manifest, SETTINGS=dict(SETUP=dict(icgyro=1), REMOTE_SETUP={}))
        stored = {}
        class UI:
            def remote_execute(self, server, command, directory, tunnel, **kwargs):
                if (server, directory, tunnel) != ('recorded-server', '/runs/frozen', 'recorded-tunnel'):
                    raise AssertionError('collection used a different endpoint')
                kwargs['std_out'].append(output)
                return 0
        def reader(location, **kwargs):
            reader_calls.append(location)
            return {'n_time': 1, 't': [0.0]}
        path = fixtures.REPO / 'CGYRO_TGLF_scan/CGYRO_scan/SCRIPTS/downsync.py'
        with ExitStack() as stack:
            stack.enter_context(patch.object(queue, 'save_current'))
            stack.enter_context(patch.object(fixtures.db_api, 'run_cases', return_value=stored))
            stack.enter_context(patch.object(fixtures.storage, 'store_result', side_effect=lambda node, candidate, factory: candidate))
            stack.enter_context(patch.object(fixtures.scratch, 'ensure_capacity', return_value={}))
            stack.enter_context(patch.object(state, 'refresh_run_state', return_value=dict(
                active=False, terminal=True, outcome='completed', queue_verified=True)))
            exec(compile(path.read_text(encoding='utf-8'), str(path), 'exec'), dict(
                root=root, OMFITtree=dict, OMFITx=UI(), OMFITcgyro=reader))
        return manifest, stored

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
