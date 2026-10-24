"""Task boundaries, merged signed-ky coordinates and abort-safe owner retention."""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'CGYRO_TGLF_scan/LIB'))
import test_cgyro_storage as fixture
from omfit_mapping import OMFITMapping, treeify
import OMFITlib_cgyro_task_catalog as catalog
import OMFITlib_cgyro_task_cleanup as cleanup
import OMFITlib_cgyro_cleanup_state as transaction


class TaskCleanupTests(unittest.TestCase):
    def setUp(self):
        self.files = fixture.StorageCases('runTest')
        self.files.setUp()
        self.addCleanup(self.files.doCleanups)
        self.addCleanup(self.files.tearDown)
        self.module = dict(RUN_DB={}, RUN_HISTORY={}, SETTINGS={'SETUP': {}})
        self.make_scan('old', 101, (.1, -.1), ion='T')
        self.make_scan('new', 102, (.2,), ion='T')
        self.make_scan('theta', 103, (.1,), ion='T', axis='N_THETA')
        self.make_scan('hydrogen', 104, (.1,), ion='H')
        self.make_scan('ordinary', 105, (.1,), ion='BASE')
        self.module['RUN_MANIFEST'] = copy.deepcopy(self.module['RUN_HISTORY']['old']['manifest'])
        self.module['RUN_BATCH'] = dict(tokens=['old', 'new', 'theta', 'hydrogen', 'ordinary'],
                                       focus_token='old', case_ids=[], batch_id='b')

    def make_scan(self, token, job, kys, ion='T', axis='N_ENERGY', server='tyadmin09'):
        case = self.files.indexed_scan(self.module, token, ion, name=axis, values=(8,), ky_count=len(kys))
        info = case['__INFO__']
        info.update(job_id=str(job), server=server, status='published')
        payload = case[axis]['8']['lin']
        refs = list(payload.values())
        payload.clear()
        for (point, row), ky, ref in zip(case['__TASKS__'].items(), kys, refs):
            row['result_path'][-1] = str(ky)
            row['values']['KY'] = ky
            payload[str(ky)] = ref
        run = self.module['RUN_DB'].setdefault('Jet', {})
        existing = fixture.archive_api.catalog_runs(self.module).get('Jet', {}).get(info['case_id'], {})
        merged = fixture.archive_api.combine_cases([existing]) if existing else {}
        fixture.archive_api.store_scan(merged, case, info, case['__TASKS__'])
        fixture.archive_api.install_case(run, info['case_id'], merged)
        manifest = dict(info, run_token=token, status='published', points=list(case['__TASKS__']))
        self.module['RUN_HISTORY'][token] = dict(manifest=copy.deepcopy(manifest))
        fixture.db_api.run_records(self.module, dict)[token] = dict(manifest=manifest)
        return case

    def delete(self, tokens, module=None, factory=dict):
        module = self.module if module is None else module
        report = cleanup.preview_tasks(module, tokens)
        return cleanup.remove_tasks(module, tokens, report, report['confirmation'], factory)

    def public_rows(self, module=None):
        module = self.module if module is None else module
        return [(rid, cid, name, row['run_token'], fixture.archive_api.point_coordinate(row))
                for rid, cases in fixture.archive_api.catalog_runs(module).items() for cid, case in cases.items()
                for name, info, tasks in fixture.archive_api.case_scans(case) for row in tasks.values()]

    def test_delete_only_one_job_preserves_other_ky_parameters_isotopes_and_direct_scans(self):
        before = self.public_rows()
        for factory in (dict, OMFITMapping):
            module = treeify(copy.deepcopy(self.module), factory)
            with self.subTest(factory=factory):
                report = self.delete(['old'], module, factory)
                self.assertEqual(report['archived_points'], 2)
                self.assertEqual(self.public_rows(module), [r for r in before if r[3] != 'old'])
                group = module['RUN_DB']['Jet']['nr=1_rho=0.33']
                self.assertIsInstance(group, factory)
                self.assertIn('H', group)
                self.assertIn('T', group)
                self.assertIn('N_ENERGY', group)
                self.assertIn('N_THETA', group['T'])
                self.assertEqual(set(module['RUN_HISTORY']), {'new', 'theta', 'hydrogen', 'ordinary'})
                self.assertEqual(module['RUN_MANIFEST'], {})
                self.assertEqual(module['RUN_BATCH'], {})

    def test_deleting_direct_radius_scan_cannot_drop_neighboring_isotopes(self):
        before = self.public_rows()
        self.delete(['ordinary'])
        self.assertEqual(self.public_rows(), [r for r in before if r[3] != 'ordinary'])
        self.assertEqual(set(self.module['RUN_DB']['Jet']['nr=1_rho=0.33']), {'T', 'H'})

    def test_deleted_header_is_rebound_to_a_retained_point_source(self):
        self.delete(['new'])
        case = self.module['RUN_DB']['Jet']['nr=1_rho=0.33']['T']
        record = case['__SCANS__']['N_ENERGY']
        self.assertEqual(record['info']['run_token'], 'old')
        self.assertEqual(record['info']['job_id'], '101')
        self.assertEqual(record['info']['merged_run_tokens'], ['old'])
        self.assertEqual(record['info']['points'], 2)
        self.assertEqual(len(record['tasks']), 2)

    def test_same_coordinate_now_owned_by_newer_job_is_not_deleted_with_old_record(self):
        self.make_scan('replacement', 106, (.1,), ion='T')
        before = self.public_rows()
        self.delete(['old'])
        self.assertEqual(self.public_rows(), [r for r in before if r[3] != 'old'])
        self.assertTrue(any(r[3] == 'replacement' and r[-1][-1][-1] == .1 for r in self.public_rows()))

    def test_unarchived_task_without_scheduler_number_can_be_explicitly_deleted(self):
        token = 'draft'
        manifest = dict(run_token=token, runid='Jet', case_id='nr=2__rho=0.5__ion=BASE',
                        status='failed', job_id='', server='tyadmin09')
        self.module['RUN_HISTORY'][token] = dict(manifest=manifest)
        ref = fixture.storage.store_result(self.module, self.files.result('unfinished', b'unfinished'))
        fixture.db_api.run_records(self.module)[token] = dict(manifest=manifest, cases={'p000001': ref})
        old_count = len(fixture.storage.result_pool(self.module))
        rows = {r['token']: r for r in catalog.task_catalog(self.module)}
        self.assertEqual(rows[token]['retained_points'], 1)
        self.assertEqual(rows[token]['jobs'], [])
        self.delete([token])
        self.assertNotIn(token, fixture.db_api.run_records(self.module))
        self.assertEqual(len(fixture.storage.result_pool(self.module)), old_count - 1)

    def test_shared_physical_owner_and_source_directories_survive(self):
        old_case = self.module['RUN_DB']['Jet']['nr=1_rho=0.33']['T']
        row = next(r for r in old_case['__SCANS__']['N_ENERGY']['tasks'].values() if r['run_token'] == 'old')
        ref = fixture.continuation.point_result(old_case, row)
        owner = fixture.storage.resolve_result(self.module, ref)
        self.module['RUN_DB']['UnclassifiedKeep'] = dict(opaque_reference=ref)
        self.delete(['old'])
        self.assertIs(fixture.storage.resolve_result(self.module, ref), owner)
        self.assertTrue(Path(owner.filename).is_dir())

    def test_two_servers_reusing_job_number_are_distinct_tasks(self):
        self.make_scan('other_cluster', 101, (.4,), ion='D', server='login117')
        rows = {r['token']: r for r in catalog.task_catalog(self.module)}
        self.assertEqual(rows['old']['jobs'], rows['other_cluster']['jobs'])
        self.delete(['old'])
        self.assertIn('other_cluster', self.module['RUN_HISTORY'])
        self.assertTrue(any(row[3] == 'other_cluster' for row in self.public_rows()))

    def test_retry_chain_is_disclosed_as_one_logical_task_and_removed_explicitly(self):
        for source in (self.module['RUN_HISTORY']['old']['manifest'],
                       fixture.db_api.run_records(self.module)['old']['manifest'], self.module['RUN_MANIFEST']):
            source['attempts'] = [dict(job_id='99', workDir='/old_attempt')]
        report = cleanup.preview_tasks(self.module, ['old'])
        self.assertEqual(report['tasks'][0]['jobs'], ['101', '99'])
        self.delete(['old'])
        self.assertNotIn('old', self.module['RUN_HISTORY'])

    def test_empty_duplicate_missing_selection_and_wrong_confirmation_cannot_delete(self):
        for tokens in (None, [], ['old', 'old'], ['missing'], [''], 'old', [True]):
            with self.subTest(tokens=tokens), self.assertRaises(ValueError):
                cleanup.preview_tasks(self.module, tokens)
        preview = cleanup.preview_tasks(self.module, ['old'])
        for expected, answer in ((None, preview['confirmation']), (preview, ''), (preview, 'DELETE')):
            with self.assertRaises(ValueError):
                cleanup.remove_tasks(self.module, ['old'], expected, answer)
        self.assertIn('old', self.module['RUN_HISTORY'])

    def test_metadata_changes_same_point_count_invalidate_modal_preview(self):
        report = cleanup.preview_tasks(self.module, ['old'])
        case = self.module['RUN_DB']['Jet']['nr=1_rho=0.33']['T']
        row = next(r for r in case['__SCANS__']['N_ENERGY']['tasks'].values() if r['run_token'] == 'old')
        row['final_time'] = 120  # Same token, number of points and archives.
        with self.assertRaisesRegex(ValueError, '已变化'):
            cleanup.remove_tasks(self.module, ['old'], report, report['confirmation'])
        self.assertIn('old', self.module['RUN_HISTORY'])

    def test_local_collection_busy_and_retained_continuation_block_deletion(self):
        current = self.module['RUN_MANIFEST']
        current['collection_status'] = 'collecting'
        with self.assertRaisesRegex(ValueError, '本地操作'):
            cleanup.preview_tasks(self.module, ['old'])
        current.pop('collection_status')
        self.module['RUN_HISTORY']['new']['manifest']['continuation'] = dict(source_token='old')
        with self.assertRaisesRegex(ValueError, '依赖'):
            cleanup.preview_tasks(self.module, ['old'])
        self.delete(['old', 'new'])
        self.assertIn('theta', self.module['RUN_HISTORY'])

    def test_conflicting_token_identity_and_ambiguous_merged_rows_fail_closed(self):
        entry = fixture.db_api.run_records(self.module)['old']['manifest']
        entry['server'] = 'other_cluster'
        with self.assertRaisesRegex(ValueError, '身份存在冲突'):
            cleanup.preview_tasks(self.module, ['old'])
        entry['server'] = 'tyadmin09'
        case = self.module['RUN_DB']['Jet']['nr=1_rho=0.33']['T']
        row = next(r for r in case['__SCANS__']['N_ENERGY']['tasks'].values() if r['run_token'] == 'old')
        row.pop('run_token')
        with self.assertRaisesRegex(ValueError, '缺少逐点任务身份'):
            cleanup.preview_tasks(self.module, ['old'])

    def test_abort_after_native_write_and_after_pool_pruning_restore_exact_objects(self):
        class AbortOnPop(OMFITMapping):
            failed = False
            def pop(self, key, *args):
                result = super().pop(key, *args)
                if key == 'old' and not self.failed:
                    self.failed = True
                    raise KeyboardInterrupt('native delete abort')
                return result
        history = self.module['RUN_HISTORY'] = AbortOnPop(self.module['RUN_HISTORY'])
        archive = self.module['RUN_DB']['Jet']
        record = history['old']
        with self.assertRaisesRegex(KeyboardInterrupt, 'native delete abort'):
            self.delete(['old'])
        self.assertIs(self.module['RUN_DB']['Jet'], archive)
        self.assertIs(history['old'], record)
        self.assertFalse(fixture.db_api.run_is_deleted(self.module, 'old'))
        owners = dict(fixture.storage.result_pool(self.module))
        original = cleanup.prune_storage
        def after_prune(module):
            original(module)
            self.assertLess(len(fixture.storage.result_pool(module)), len(owners))
            raise KeyboardInterrupt('after prune abort')
        with patch.object(cleanup, 'prune_storage', after_prune):
            with self.assertRaisesRegex(KeyboardInterrupt, 'after prune abort'):
                self.delete(['old'])
        self.assertIs(self.module['RUN_DB']['Jet'], archive)
        self.assertEqual(fixture.storage.result_pool(self.module), owners)
        self.assertIs(history['old'], record)
        self.assertFalse(fixture.db_api.run_is_deleted(self.module, 'old'))

    def test_stale_window_save_collect_and_continue_cannot_revive_deleted_task(self):
        import OMFITlib_cgyro_queue as queue
        import OMFITlib_cgyro_continue as continuation
        old = copy.deepcopy(self.module['RUN_MANIFEST'])
        self.delete(['old'])
        self.module['RUN_MANIFEST'] = old  # A cached old callback/finally handler.
        queue.save_current(self.module)
        self.assertNotIn('old', self.module['RUN_HISTORY'])
        self.assertNotIn('old', fixture.db_api.run_records(self.module))
        with self.assertRaisesRegex(ValueError, 'explicitly deleted'):
            queue.require_retained_run(self.module, 'old')
        with self.assertRaisesRegex(ValueError, 'explicitly deleted'):
            continuation.saved_run(self.module, 'old')
        self.assertNotIn('old', {r['token'] for r in catalog.task_catalog(self.module)})

    def test_cleared_focus_does_not_hide_other_active_jobs_from_whole_project_safety(self):
        from OMFITlib_result_cleanup import active_jobs
        self.module['RUN_HISTORY']['new']['manifest']['status'] = 'submitted'
        self.delete(['old'])
        self.assertEqual(self.module['RUN_BATCH'], {})
        self.assertTrue(any('new' in label for label in active_jobs({'CGYRO_scan': self.module})))

    def test_preview_does_not_read_solver_files_or_array_methods(self):
        with patch.object(fixture.storage, 'resolve_result', side_effect=AssertionError('result read')):
            report = cleanup.preview_tasks(self.module, ['old'])
        self.assertEqual(report['archived_points'], 2)
        self.assertEqual(len(report['revision']), 64)

    def test_rebound_header_uses_retained_source_fixed_parameters(self):
        for entry in (self.module['RUN_HISTORY']['old'], fixture.db_api.run_records(self.module)['old']):
            entry['manifest']['fixed_parameters'] = dict(N_THETA=16)
        self.module['RUN_MANIFEST']['fixed_parameters'] = dict(N_THETA=16)
        case = self.module['RUN_DB']['Jet']['nr=1_rho=0.33']['T']
        case['__SCANS__']['N_ENERGY']['info']['fixed_parameters'] = dict(N_THETA=64)
        self.delete(['new'])
        info = self.module['RUN_DB']['Jet']['nr=1_rho=0.33']['T']['__SCANS__']['N_ENERGY']['info']
        self.assertEqual(info['fixed_parameters'], dict(N_THETA=16))

    def test_public_only_continuation_ancestry_protects_parent_without_history(self):
        self.module['RUN_HISTORY'].pop('new')
        fixture.db_api.run_records(self.module).pop('new')
        case = self.module['RUN_DB']['Jet']['nr=1_rho=0.33']['T']
        case['__SCANS__']['N_ENERGY']['info']['continuations'] = [dict(source_token='old')]
        with self.assertRaisesRegex(ValueError, '保留归档仍记录续算来源'):
            cleanup.preview_tasks(self.module, ['old'])
        self.assertIn('old', self.module['RUN_HISTORY'])


if __name__ == '__main__':
    unittest.main()
