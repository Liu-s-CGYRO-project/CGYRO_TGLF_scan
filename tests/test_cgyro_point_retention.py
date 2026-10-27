"""Mixed old/new ky snapshots must retire only proven superseded points."""
import copy
from pathlib import Path
import unittest
import test_cgyro_retention as rt
from test_cgyro_retention import storage, db_api, fixtures, retire_superseded


class PointRetentionTests(unittest.TestCase):
    setUp, tearDown = rt.RetentionTests.setUp, rt.RetentionTests.tearDown
    result, snapshot = rt.RetentionTests.result, rt.RetentionTests.snapshot
    publish, plan, pair = rt.RetentionTests.publish, rt.RetentionTests.plan, rt.RetentionTests.pair

    def partial_pair(self):
        root, old, old_cases, new, new_cases = self.pair()
        raw = storage.resolve_result(root, new_cases['p000002'])
        (Path(raw.filename) / 'out.cgyro.time').write_text('19 0 0\n')
        return root, old, old_cases, new, new_cases

    def test_partial_coverage_removes_only_the_covered_ky_and_keeps_frozen_manifest(self):
        root, old, old_cases, new, new_cases = self.partial_pair()
        original = copy.deepcopy(old)
        report = retire_superseded(root, storage.resolve_result, storage.reference_id, prune=storage.prune_storage)
        self.assertEqual(set(report['partial']['old']['points']), {'p000001'})
        record = db_api.run_records(root)['old']
        self.assertEqual(set(record['cases']), {'p000002'})
        self.assertEqual(record['manifest'], original)
        self.assertNotIn('payload_retired', record)
        self.assertNotIn(storage.reference_id(old_cases['p000001']), storage.result_pool(root))
        self.assertIsNotNone(storage.resolve_result(root, old_cases['p000002']))
        view, cases = fixtures.continuation.saved_run(root, 'old')
        self.assertEqual(view['points'], ['p000002'])
        self.assertEqual(set(view['point_table']), {'p000002'})
        self.assertEqual(set(cases), {'p000002'})

    def test_later_coverage_retires_remaining_snapshot_and_combines_evidence(self):
        root, old, old_cases, new, new_cases = self.partial_pair()
        retire_superseded(root, storage.resolve_result, storage.reference_id, prune=storage.prune_storage)
        raw = storage.resolve_result(root, new_cases['p000002'])
        (Path(raw.filename) / 'out.cgyro.time').write_text('30 0 0\n')
        report = retire_superseded(root, storage.resolve_result, storage.reference_id, prune=storage.prune_storage)
        self.assertEqual(set(report['retire']['old']['points']), {'p000001', 'p000002'})
        self.assertNotIn('retired_points', db_api.run_records(root)['old'])
        with self.assertRaisesRegex(ValueError, 'superseded'):
            fixtures.continuation.saved_run(root, 'old')

    def test_abort_after_partial_removal_restores_both_ky_and_inputs(self):
        root, old, old_cases, new, new_cases = self.partial_pair()
        record = db_api.run_records(root)['old']
        inputs = record['inputs']
        def abort(module):
            storage.prune_storage(module)
            raise KeyboardInterrupt('abort')
        with self.assertRaises(KeyboardInterrupt):
            retire_superseded(root, storage.resolve_result, storage.reference_id, prune=abort)
        self.assertIs(record['cases'], old_cases)
        self.assertIs(record['inputs'], inputs)
        self.assertNotIn('retired_points', record)
        for ref in old_cases.values():
            self.assertIsNotNone(storage.resolve_result(root, ref))

    def test_shorter_converged_linear_output_can_replace_failed_iteration(self):
        root, old, old_cases, new, new_cases = self.partial_pair()
        for ref, message, limit in ((old_cases['p000002'], 'Linear terminated at max time', 20),
                                     (new_cases['p000002'], 'Linear converged', 30)):
            directory = Path(storage.resolve_result(root, ref).filename)
            (directory / 'out.cgyro.info').write_text('INFO: (CGYRO) ' + message + '\n')
            (directory / 'input.cgyro').write_text('KY=0.2\nNONLINEAR_FLAG=0\nMAX_TIME=' + str(limit) + '\n')
        plan = self.plan(root)
        self.assertIn('old', plan['retire'])
        self.assertEqual(plan['retire']['old']['points']['p000002']['reason'], 'converged_linear_replacement')
        # Existing converged results and physically different calculations are
        # not made disposable merely because another run says COMPLETED.
        old_directory = Path(storage.resolve_result(root, old_cases['p000002']).filename)
        (old_directory / 'out.cgyro.info').write_text('Linear converged\n')
        self.assertNotIn('old', self.plan(root)['retire'])
        (old_directory / 'out.cgyro.info').write_text('Linear terminated at max time\n')
        (old_directory / 'input.cgyro').write_text('KY=0.2\nNONLINEAR_FLAG=1\nMAX_TIME=20\n')
        self.assertNotIn('old', self.plan(root)['retire'])

    def test_uncollected_child_does_not_pin_replaced_parent_files(self):
        root, old, old_cases, new, new_cases = self.partial_pair()
        db_api.run_records(root)['child'] = dict(manifest=dict(run_token='child', status='submitted',
            continuation=dict(source_token='old')))
        plan = self.plan(root)
        self.assertIn('old', plan['partial'])
        self.assertEqual(set(plan['partial']['old']['points']), {'p000001'})

    def test_old_callback_cannot_recreate_retired_point_payloads(self):
        root, old, old_cases, new, new_cases = self.partial_pair()
        retire_superseded(root, storage.resolve_result, storage.reference_id, prune=storage.prune_storage)
        root['RUN_MANIFEST'] = copy.deepcopy(old)
        fixtures.queue_api.save_current(root)
        self.assertEqual(set(db_api.run_records(root)['old']['cases']), {'p000002'})
        with self.assertRaisesRegex(ValueError, 'remaining points'):
            fixtures.queue_api.require_retained_run(root, 'old')

    def test_old_snapshot_does_not_duplicate_public_coordinates_in_result_picker(self):
        root, old, old_cases, new, new_cases = self.partial_pair()
        old.update(workDir='/old', loaded_points=[], partial_points=list(old_cases))
        retire_superseded(root, storage.resolve_result, storage.reference_id, prune=storage.prune_storage)
        entries = fixtures.index_api.result_records(root)
        self.assertEqual(len(entries), 1)
        entry = next(iter(entries.values()))
        self.assertEqual(set(entry['tasks']), {'p000001', 'p000002'})
        binding = fixtures.index_api.select_result(root, entry, 'p000002')
        self.assertEqual(binding['result_id'], storage.reference_id(new_cases['p000002']))


if __name__ == '__main__':
    unittest.main()
