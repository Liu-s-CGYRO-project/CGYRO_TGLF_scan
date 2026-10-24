"""Retention policy regressions using real temporary files, no cluster calls."""
import copy
import json
from pathlib import Path
import unittest

import test_cgyro_storage as fixtures
from OMFITlib_cgyro_retention import retention_plan, retire_superseded

storage, archive_api, db_api = fixtures.storage, fixtures.archive_api, fixtures.db_api


class RetentionTests(unittest.TestCase):
    setUp, tearDown = fixtures.StorageCases.setUp, fixtures.StorageCases.tearDown
    result = fixtures.StorageCases.result

    def snapshot(self, module, token, times=(10, 20), kys=(.1, .2), axis='N_THETA'):
        cases, table = {}, {}
        for number, (time, ky) in enumerate(zip(times, kys), 1):
            point = 'p{:06d}'.format(number)
            raw = self.result(token + point, token.encode())
            (Path(raw.filename) / 'out.cgyro.time').write_text(str(time) + ' 0 0\n')
            cases[point] = storage.store_result(module, raw)
            table[point] = dict(task_id=point, run_token=token, values={axis: 16, 'KY': ky},
                                result_path=[axis, '16.00000', 'lin', str(ky)])
        manifest = dict(run_token=token, runid='Jet', case_id='nr=1__rho=0.33__ion=T',
                        nr=1, rho=.33, mass='T', status='failed', collection_status='partial',
                        points=list(table), point_table=table, scan_axes=[dict(name=axis, values=[16])])
        db_api.run_records(module, dict)[token] = dict(manifest=manifest, cases=cases, inputs={})
        return manifest, cases

    def publish(self, module, manifest, cases, status='loaded'):
        info = copy.deepcopy(manifest)
        info.update(source_nr=1, ion_case='T', scan_dimensions=1)
        tasks, payload = copy.deepcopy(manifest['point_table']), {}
        for point, row in tasks.items():
            row.update(status=status, resume_pending=status != 'loaded')
            node = payload
            for key in row['result_path'][:-1]:
                node = node.setdefault(key, {})
            node[row['result_path'][-1]] = cases[point]
        case = {}
        archive_api.store_scan(case, payload, info, tasks)
        run = module['RUN_DB'].setdefault('Jet', {})
        archive_api.install_case(run, info['case_id'], case)

    def plan(self, root):
        return retention_plan(root, storage.resolve_result, storage.reference_id)

    def pair(self):
        root = {}
        old, old_cases = self.snapshot(root, 'old')
        new, new_cases = self.snapshot(root, 'new', times=(30, 40))
        new.update(status='published', collection_status='complete')
        root['RUN_MANIFEST'] = new
        self.publish(root, new, new_cases)
        return root, old, old_cases, new, new_cases

    def subset_continuation(self, suffix=''):
        root = {}
        first, first_cases = self.snapshot(root, 'first' + suffix, times=(30, 40))
        first.update(nr=1, mass='T', workDir='/first', status='published',
                     collection_status='complete', loaded_points=list(first_cases), partial_points=[])
        self.publish(root, first, first_cases)
        first_case = archive_api.catalog_runs(root)['Jet'][first['case_id']]
        # Published runs retain metadata, not duplicate result/input owners.
        record = db_api.run_records(root)[first['run_token']]
        record.pop('cases')
        record.pop('inputs')
        child, child_cases = self.snapshot(root, 'child' + suffix, times=(20,), kys=(.1,))
        child.update(nr=1, mass='T', workDir='/child', loaded_points=[], partial_points=list(child_cases),
                     continuation=dict(source_token=first['run_token'], source_points=list(first_cases)))
        self.publish(root, child, child_cases, status='partial')
        child_case = archive_api.catalog_runs(root)['Jet'][child['case_id']]
        merged = archive_api.combine_cases([first_case, child_case])
        archive_api.install_case(root['RUN_DB']['Jet'], child['case_id'], merged)
        root['RUN_MANIFEST'] = child
        return root, merged, first_cases, child_cases

    def test_partial_subset_resolves_surviving_published_ancestor_by_coordinate(self):
        root, merged, first_cases, child_cases = self.subset_continuation()
        # Catalog IDs can be reassigned on a merge. The frozen p000002 must
        # resolve from owner+coordinate, not a currently matching row ID.
        tasks = merged['__TASKS__']
        tasks['p000099'] = tasks.pop('p000002')
        tasks['p000099'].update(task_id='p000099', source_point_id='p000002')
        with self.assertRaises(ValueError):
            fixtures.continuation.archived_case(root, 'first')  # stale dialog
        context = fixtures.continuation.stopped_context(root, 'child')
        self.assertEqual(set(context['results']), {'p000001', 'p000002'})
        self.assertEqual(context['unfinished'], {'p000001'})
        self.assertIs(context['results']['p000001'], storage.resolve_result(root, child_cases['p000001']))
        self.assertIs(context['results']['p000002'], storage.resolve_result(root, first_cases['p000002']))

    def test_ancestor_fallback_rejects_foreign_owner_or_changed_signed_ky(self):
        for changed in ('owner', 'signed_ky'):
            with self.subTest(changed=changed):
                # Distinct temporary fixture directories for each scenario.
                root, merged, first_cases, child_cases = self.subset_continuation(suffix=changed)
                row = merged['__TASKS__']['p000002']
                if changed == 'owner':
                    row['run_token'] = 'foreign'
                else:
                    row['result_path'][-1] = '-0.2'
                with self.assertRaisesRegex(ValueError, 'ancestry was replaced or is incomplete'):
                    fixtures.continuation.stopped_context(root, root['RUN_MANIFEST']['run_token'])

    def test_replaced_failed_snapshot_retires_payload_but_keeps_manifest(self):
        root, old, old_cases, new, new_cases = self.pair()
        source_files = [storage.resolve_result(root, ref).filename for ref in old_cases.values()]
        report = retire_superseded(root, storage.resolve_result, storage.reference_id)
        self.assertEqual(set(report['retire']), {'old'})
        saved = db_api.run_records(root)['old']
        self.assertEqual(saved['manifest'], old)
        self.assertNotIn('cases', saved)
        self.assertNotIn('inputs', saved)
        self.assertEqual(storage.prune_storage(root), 2)
        self.assertTrue(all(Path(path).is_dir() for path in source_files))
        for ref in new_cases.values():
            self.assertIsNotNone(storage.resolve_result(root, ref))

    def test_compaction_reports_final_pool_after_retirement(self):
        root, old, old_cases, new, new_cases = self.pair()
        report = storage.consolidate_storage(root)
        pool = storage.result_pool(root)
        self.assertEqual(set(report['retired_runs']), {'old'})
        self.assertEqual(report['physical_results'], 2)
        self.assertEqual(report['physical_bytes'] + report['file_dedup_bytes'], sum(
            storage.storage_state(root)['bytes'][key] for key in pool if key != '__FILES__'))
        self.assertGreater(report['released_result_bytes'], 0)

    def test_different_scan_or_signed_ky_does_not_count_as_coverage(self):
        for axis, kys in [('N_ENERGY', (.1, .2)), ('N_THETA', (-.1, .2))]:
            with self.subTest(axis=axis, kys=kys):
                root = {}
                self.snapshot(root, 'old' + axis + str(kys))
                new, cases = self.snapshot(root, 'new' + axis + str(kys), times=(30, 40), axis=axis, kys=kys)
                self.publish(root, new, cases)
                self.assertEqual(self.plan(root)['retire'], {})

    def test_partial_or_shorter_replacement_keeps_entire_old_snapshot(self):
        root, old, old_cases, new, new_cases = self.pair()
        self.publish(root, new, new_cases, status='partial')
        self.assertNotIn('old', self.plan(root)['retire'])
        self.publish(root, new, new_cases)
        raw = storage.resolve_result(root, new_cases['p000002'])
        (Path(raw.filename) / 'out.cgyro.time').write_text('19 0 0\n')
        self.assertNotIn('old', self.plan(root)['retire'])

    def test_unadvanced_publication_keeps_scan_header_source_after_other_scan(self):
        root = {}
        first, first_cases = self.snapshot(root, 'first', times=(30, 40))
        first.update(status='published', collection_status='complete')
        self.publish(root, first, first_cases)
        retry, retry_cases = self.snapshot(root, 'retry', times=(10, 20))
        self.publish(root, retry, retry_cases, status='partial')
        # Real publication merges the retry into the existing scan, preserving
        # completed point rows even though the scan header advances to retry.
        run = root['RUN_DB']['Jet']
        retry_case = archive_api.catalog_runs(root)['Jet'][retry['case_id']]
        self.publish(root, first, first_cases)
        first_case = archive_api.catalog_runs(root)['Jet'][first['case_id']]
        merged = archive_api.combine_cases([first_case, retry_case])
        archive_api.install_case(run, retry['case_id'], merged)
        _, info, tasks = archive_api.case_scans(merged)[0]
        self.assertEqual(info['run_token'], 'retry')
        self.assertEqual({row['run_token'] for row in tasks.values()}, {'first'})
        other, other_cases = self.snapshot(root, 'other', axis='N_ENERGY')
        root['RUN_MANIFEST'] = other
        # Preserve the same logical case's other scans as the publisher does.
        self.publish(root, other, other_cases)
        other_case = archive_api.catalog_runs(root)['Jet'][other['case_id']]
        archive_api.install_case(run, retry['case_id'], archive_api.combine_cases([merged, other_case]))
        plan = self.plan(root)
        self.assertNotIn('retry', plan['retire'])
        self.assertEqual(plan['retained']['retry'], 'current public scan anchor')
        report = retire_superseded(root, storage.resolve_result, storage.reference_id,
                                   prune=storage.prune_storage)
        self.assertNotIn('retry', report['retire'])
        self.assertIs(db_api.run_records(root)['retry']['cases'], retry_cases)

    def test_valid_checkpoint_cannot_be_replaced_by_no_or_unknown_checkpoint(self):
        root, old, old_cases, new, new_cases = self.pair()
        key = storage.reference_id(old_cases['p000001'])
        storage.storage_state(root)['checkpoints'][key] = json.dumps(dict(resume_ready=True))
        self.assertNotIn('old', self.plan(root)['retire'])
        new_key = storage.reference_id(new_cases['p000001'])
        storage.storage_state(root)['checkpoints'][new_key] = json.dumps(dict(resume_ready=True))
        self.assertIn('old', self.plan(root)['retire'])

    def test_uncollected_and_partial_child_protect_ancestors(self):
        root, old, old_cases, new, new_cases = self.pair()
        for status, collection in [('running', 'pending'), ('cancelled', 'partial')]:
            child = dict(run_token='child', status=status, collection_status=collection,
                         continuation=dict(source_token='old'))
            db_api.run_records(root)['child'] = dict(manifest=child)
            self.assertNotIn('old', self.plan(root)['retire'])
        child.update(status='published', collection_status='complete')
        self.assertIn('old', self.plan(root)['retire'])

    def test_uncollected_old_run_and_current_run_are_never_retired(self):
        root, old, old_cases, new, new_cases = self.pair()
        old.update(collection_status='incomplete')
        self.assertNotIn('old', self.plan(root)['retire'])
        old.update(collection_status='partial')
        root['RUN_MANIFEST'] = old
        self.assertNotIn('old', self.plan(root)['retire'])

    def test_active_unknown_or_inconsistent_state_keeps_collected_snapshot(self):
        root, old, old_cases, new, new_cases = self.pair()
        updates = [dict(status=status, scheduler_sync={}) for status in
                   ('prepared', 'uploading', 'submitting', 'submitted', 'running',
                    'cancel_requested', 'future_unknown_state', '')]
        updates += [dict(status='failed', scheduler_sync=sync) for sync in
                    (dict(active=True, terminal=False, outcome='active'),
                     dict(active=False, terminal=False, outcome='unknown'),
                     dict(active=False, terminal=True, outcome='unrecognized'))]
        updates += [dict(status='published', scheduler_sync={})]
        for fields in updates:
            with self.subTest(fields=fields):
                old.update(fields)
                plan = self.plan(root)
                self.assertNotIn('old', plan['retire'])
                self.assertIn('run state', plan['retained']['old'])
        old.update(status='failed', scheduler_sync=dict(active=False, terminal=True, outcome='failed'))
        self.assertIn('old', self.plan(root)['retire'])

    def test_inconsistent_published_child_still_protects_source_chain(self):
        root, old, old_cases, new, new_cases = self.pair()
        child = dict(run_token='child', status='published', collection_status='complete',
                     continuation=dict(source_token='old'),
                     scheduler_sync=dict(active=True, terminal=False, outcome='active'))
        db_api.run_records(root)['child'] = dict(manifest=child)
        self.assertNotIn('old', self.plan(root)['retire'])
        child['scheduler_sync'] = dict(active=False, terminal=True, outcome='completed')
        self.assertIn('old', self.plan(root)['retire'])

    def test_other_branch_reference_keeps_shared_physical_owner(self):
        root, old, old_cases, new, new_cases = self.pair()
        root['RUN_DB']['__UNCLASSIFIED__'] = dict(unknown=old_cases['p000001'])
        retire_superseded(root, storage.resolve_result, storage.reference_id)
        self.assertEqual(storage.prune_storage(root), 1)
        self.assertIsNotNone(storage.resolve_result(root, old_cases['p000001']))

    def test_bad_public_owner_aborts_plan_without_mutating_snapshots(self):
        root, old, old_cases, new, new_cases = self.pair()
        key = storage.reference_id(new_cases['p000002'])
        del storage.result_pool(root)[key]
        plan = self.plan(root)
        self.assertNotIn('old', plan['retire'])
        self.assertIn('Missing physical', plan['retained']['old'])
        self.assertEqual(db_api.run_records(root)['old']['cases'], old_cases)

    def test_unknown_frozen_input_content_retains_whole_snapshot(self):
        root, old, old_cases, new, new_cases = self.pair()
        record = db_api.run_records(root)['old']
        for inputs in ({'unclassified.bin': old_cases['p000001']},
                       {'p000001': {'zip': {}, 'extra': old_cases['p000001']}}):
            with self.subTest(keys=list(inputs)):
                record['inputs'] = inputs
                report = retire_superseded(root, storage.resolve_result, storage.reference_id,
                                           prune=storage.prune_storage)
                self.assertNotIn('old', report['retire'])
                self.assertIn('Unclassified', report['retained']['old'])
                self.assertIs(record['inputs'], inputs)
                self.assertEqual(record['cases'], old_cases)

    def test_abort_after_prune_returns_restores_owners_and_retired_links(self):
        root, old, old_cases, new, new_cases = self.pair()
        records, pool = db_api.run_records(root), storage.result_pool(root)
        original_cases, original_inputs = records['old']['cases'], records['old']['inputs']
        original_owners = dict(pool)
        original_state = copy.deepcopy(dict(storage.storage_state(root)))
        def prune_then_abort(module):
            self.assertEqual(storage.prune_storage(module), 2)
            self.assertNotIn(storage.reference_id(old_cases['p000001']), pool)
            raise KeyboardInterrupt('after successful pruning')
        with self.assertRaises(KeyboardInterrupt):
            retire_superseded(root, storage.resolve_result, storage.reference_id, prune=prune_then_abort)
        self.assertIs(records['old']['cases'], original_cases)
        self.assertIs(records['old']['inputs'], original_inputs)
        self.assertNotIn('payload_retired', records['old'])
        self.assertEqual(dict(storage.storage_state(root)), original_state)
        for key, owner in original_owners.items():
            self.assertIs(pool[key], owner)
        for ref in old_cases.values():
            self.assertIsNotNone(storage.resolve_result(root, ref))

    def test_prune_rollback_attempts_other_owners_after_one_restore_fails(self):
        root, old, old_cases, new, new_cases = self.pair()
        retire_superseded(root, storage.resolve_result, storage.reference_id)
        removed = [storage.reference_id(ref) for ref in old_cases.values()]
        original_abort = KeyboardInterrupt('after deleting both owners')
        class InterruptedPool(dict):
            def __delitem__(self, key):
                super().__delitem__(key)
                if key == removed[-1]:
                    raise original_abort
            def __setitem__(self, key, value):
                if key == removed[0]:
                    raise RuntimeError('first owner restore rejected')
                super().__setitem__(key, value)
        original_pool = storage.result_pool(root)
        root['RUN_DB'][db_api.POOL] = pool = InterruptedPool(original_pool)
        previous_state = copy.deepcopy(dict(storage.storage_state(root)))
        with self.assertRaises(KeyboardInterrupt) as caught:
            storage.prune_storage(root)
        self.assertIs(caught.exception, original_abort)
        self.assertNotIn(removed[0], pool)  # Report the rejected restore honestly.
        self.assertIs(pool[removed[1]], original_pool[removed[1]])
        self.assertEqual(dict(storage.storage_state(root)), previous_state)
        self.assertIn('first owner restore rejected', original_abort.cgyro_rollback_errors[0])

    def test_retirement_rollback_restores_links_after_one_owner_restore_fails(self):
        root, old, old_cases, new, new_cases = self.pair()
        blocked = storage.reference_id(old_cases['p000001'])
        class InterruptedPool(dict):
            fail = False
            def __setitem__(self, key, value):
                if self.fail and key == blocked:
                    raise RuntimeError('owner restore rejected')
                super().__setitem__(key, value)
        original_pool = storage.result_pool(root)
        root['RUN_DB'][db_api.POOL] = pool = InterruptedPool(original_pool)
        records = db_api.run_records(root)
        original_inputs = records['old']['inputs']
        original_abort = KeyboardInterrupt('after pruning')
        original_abort.cgyro_rollback_errors = ['inner rollback diagnostic']
        def prune_then_abort(module):
            storage.prune_storage(module)
            pool.fail = True
            raise original_abort
        with self.assertRaises(KeyboardInterrupt) as caught:
            retire_superseded(root, storage.resolve_result, storage.reference_id, prune=prune_then_abort)
        self.assertIs(caught.exception, original_abort)
        self.assertIs(records['old']['cases'], old_cases)
        self.assertIs(records['old']['inputs'], original_inputs)
        self.assertNotIn('payload_retired', records['old'])
        second = storage.reference_id(old_cases['p000002'])
        self.assertIs(pool[second], original_pool[second])
        self.assertEqual(original_abort.cgyro_rollback_errors[0], 'inner rollback diagnostic')
        self.assertIn('owner restore rejected', original_abort.cgyro_rollback_errors[1])

    def test_retirement_rollback_restores_other_fields_after_link_restore_fails(self):
        root, old, old_cases, new, new_cases = self.pair()
        class InterruptedRecord(dict):
            fail = False
            def __setitem__(self, key, value):
                if self.fail and key == 'cases':
                    raise RuntimeError('cases restore rejected')
                super().__setitem__(key, value)
        records = db_api.run_records(root)
        records['old'] = record = InterruptedRecord(records['old'])
        original_inputs = record['inputs']
        original_abort = KeyboardInterrupt('after unlinking')
        def abort(module):
            record.fail = True
            raise original_abort
        with self.assertRaises(KeyboardInterrupt) as caught:
            retire_superseded(root, storage.resolve_result, storage.reference_id, prune=abort)
        self.assertIs(caught.exception, original_abort)
        self.assertIs(record['inputs'], original_inputs)
        self.assertNotIn('payload_retired', record)
        self.assertNotIn('cases', record)
        self.assertIn('cases restore rejected', original_abort.cgyro_rollback_errors[0])

    def test_circular_candidate_ancestry_is_retained_with_its_descendants(self):
        root, old, old_cases, new, new_cases = self.pair()
        peer, _ = self.snapshot(root, 'peer', times=(11, 21))
        descendant, _ = self.snapshot(root, 'descendant', times=(12, 22))
        old['continuation'] = dict(source_token='peer')
        peer['continuation'] = dict(source_token='old')
        descendant['continuation'] = dict(source_token='old')
        # All three have complete public coverage. A candidate-only cycle must
        # still block cleanup, independently of which record was inserted first.
        for reverse in (False, True):
            records = db_api.run_records(root)
            root['RUN_DB'][db_api.RUNS] = dict(reversed(list(records.items()))) if reverse else dict(records)
            plan = self.plan(root)
            self.assertFalse({'old', 'peer', 'descendant'} & set(plan['retire']))
            for token in ('old', 'peer', 'descendant'):
                self.assertIn('cyclic', plan['retained'][token])


if __name__ == '__main__':
    unittest.main()
