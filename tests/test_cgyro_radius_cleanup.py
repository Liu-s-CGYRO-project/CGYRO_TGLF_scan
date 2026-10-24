"""Delete one radius with real pool references and injected transaction faults."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'CGYRO_TGLF_scan/LIB'))
import test_cgyro_storage as fixture
from omfit_mapping import OMFITMapping, treeify
import OMFITlib_cgyro_radius_cleanup as cleanup
import OMFITlib_cgyro_queue as queue


def manifest(token, rho=.99, runid='Jet', nr=11, status='submitted_or_finished'):
    return dict(run_token=token, runid=runid, nr=nr, rho=rho, mass='BASE', status=status,
                case_id='nr={}__rho={}__ion=BASE'.format(nr, rho), job_id=token,
                collection_status='pending', batch_id='batch')


class RadiusCleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        fixture.OMFITpath.directory = self.temp.name
        self.module = dict(SETTINGS={'SETUP': {}}, RUN_DB={}, RUN_HISTORY={})
        self.owner_paths = []
        self.shared = self.result('shared', b'1 2 3\n')
        self.only_old = self.result('old-only', b'4 5 6\n')
        db = self.module['RUN_DB']
        db['Jet'] = {'nr=11_rho=0.99': {'H': {'N_THETA': self.shared}, 'T': {'N_XI': self.only_old}},
                     'nr=1_rho=0.33': {'H': {'N_THETA': self.shared}}}
        db['Other'] = {'nr=11_rho=0.99': {'D': {'N_THETA': self.shared}}}
        fixture.db_api.run_records(self.module, dict).update({
            token: {'manifest': manifest(token, rho, nr=nr), 'cases': {}, 'inputs': {}}
            for token, rho, nr in [('9537283', .99, 11), ('9545932', .99, 11), ('9817420', .33, 1)]})
        self.module['RUN_HISTORY'] = {token: {'manifest': copy.deepcopy(record['manifest'])}
            for token, record in fixture.db_api.run_records(self.module).items()}
        self.module['RUN_MANIFEST'] = copy.deepcopy(self.module['RUN_HISTORY']['9817420']['manifest'])
        self.module['RUN_BATCH'] = dict(batch_id='batch', tokens=['9537283', '9545932', '9817420'],
            case_ids=[entry['manifest']['case_id'] for entry in self.module['RUN_HISTORY'].values()],
            focus_token='9817420', completed=[], errors=[])

    def result(self, name, content):
        directory = Path(self.temp.name) / name
        directory.mkdir()
        (directory / 'input.cgyro').write_text('KY=.1\n', encoding='utf-8')
        (directory / 'out.cgyro.freq').write_bytes(content)
        self.owner_paths.append(directory)
        return fixture.storage.store_result(self.module, fixture.OMFITcgyro(directory))

    def test_preview_is_metadata_only_and_includes_archives_and_both_jobs(self):
        before = fixture.storage.result_pool(self.module)
        report = cleanup.preview_radius(self.module, 'Jet', .99)
        self.assertEqual(report['jobs'], ['9537283', '9545932'])
        self.assertEqual(report['archives'], ['Jet/nr=11_rho=0.99'])
        self.assertEqual(self.module['RUN_MANIFEST']['job_id'], '9817420')
        self.assertIs(fixture.storage.result_pool(self.module), before)
        self.assertEqual(len(before), 2)

    def test_delete_releases_only_unshared_owner_and_preserves_other_radii_and_runs(self):
        for factory in (dict, OMFITMapping):
            with self.subTest(factory=factory):
                module = treeify(copy.deepcopy(self.module), factory)
                selected = fixture.storage.resolve_result(module, self.shared)
                cleanup.remove_radius(module, 'Jet', .99, factory=factory)
                self.assertNotIn('nr=11_rho=0.99', module['RUN_DB']['Jet'])
                self.assertIn('nr=1_rho=0.33', module['RUN_DB']['Jet'])
                self.assertIn('nr=11_rho=0.99', module['RUN_DB']['Other'])
                self.assertEqual(set(module['RUN_HISTORY']), {'9817420'})
                self.assertEqual(set(fixture.db_api.run_records(module)), {'9817420'})
                self.assertEqual(module['RUN_BATCH']['tokens'], ['9817420'])
                self.assertEqual(module['RUN_MANIFEST']['job_id'], '9817420')
                self.assertIs(fixture.storage.resolve_result(module, self.shared), selected)
                self.assertEqual(len(fixture.storage.result_pool(module)), 1)
                self.assertTrue(all(path.is_dir() for path in self.owner_paths))

    def test_nearby_rho_and_same_rho_different_nr_are_not_substring_matches(self):
        self.module['RUN_HISTORY']['nearby'] = {'manifest': manifest('nearby', .990001)}
        self.module['RUN_HISTORY']['other-index'] = {'manifest': manifest('other-index', .99, nr=12)}
        cleanup.remove_radius(self.module, 'Jet', .99, nr='11')
        self.assertIn('nearby', self.module['RUN_HISTORY'])
        self.assertIn('other-index', self.module['RUN_HISTORY'])

    def test_removing_focused_radius_does_not_implicitly_select_another_job(self):
        self.module['RUN_BATCH']['focus_token'] = '9537283'
        self.module['RUN_MANIFEST'] = copy.deepcopy(self.module['RUN_HISTORY']['9537283']['manifest'])
        cleanup.remove_radius(self.module, 'Jet', .99)
        self.assertEqual(self.module['RUN_MANIFEST'], {})
        self.assertEqual(self.module['RUN_BATCH'], {})
        self.assertIn('9817420', self.module['RUN_HISTORY'])

    def test_shared_ancestry_and_operation_in_progress_block_deletion(self):
        self.module['RUN_HISTORY']['9817420']['manifest']['continuation'] = {'source_token': '9537283'}
        with self.assertRaisesRegex(ValueError, 'depends on this radius'):
            cleanup.remove_radius(self.module, 'Jet', .99)
        self.assertIn('9537283', self.module['RUN_HISTORY'])
        self.module['RUN_HISTORY']['9817420']['manifest'].pop('continuation')
        self.module['RUN_HISTORY']['9537283']['manifest']['status'] = 'uploading'
        with self.assertRaisesRegex(ValueError, 'operation in progress'):
            cleanup.remove_radius(self.module, 'Jet', .99)

    def test_conflicting_record_identity_is_rejected_before_removal(self):
        record = fixture.db_api.run_records(self.module)['9537283']
        record['manifest'] = manifest('9537283', .33, nr=1)
        with self.assertRaisesRegex(ValueError, 'Conflicting history'):
            cleanup.remove_radius(self.module, 'Jet', .99)
        self.assertIn('nr=11_rho=0.99', self.module['RUN_DB']['Jet'])

    def test_invalid_identity_empty_radius_and_changed_preview_are_rejected(self):
        for runid, rho in (('', .99), ('__RUNS__', .99), ('Jet', None), ('Jet', float('nan'))):
            with self.subTest(runid=runid, rho=rho), self.assertRaises(ValueError):
                cleanup.remove_radius(self.module, runid, rho)
        preview = cleanup.preview_radius(self.module, 'Jet', .99)
        self.module['RUN_HISTORY']['9537283']['manifest']['job_id'] = 'changed'
        with self.assertRaisesRegex(ValueError, 'changed'):
            cleanup.remove_radius(self.module, 'Jet', .99, expected=preview)
        self.assertIn('9537283', self.module['RUN_HISTORY'])

    def test_abort_during_pruning_restores_archive_history_batch_and_owners(self):
        archives = self.module['RUN_DB']['Jet']['nr=11_rho=0.99']
        pool = fixture.storage.result_pool(self.module)
        old_batch = self.module['RUN_BATCH']
        old_history = self.module['RUN_HISTORY']['9537283']
        with patch.object(cleanup, 'prune_storage', side_effect=KeyboardInterrupt('prune abort')):
            with self.assertRaisesRegex(KeyboardInterrupt, 'prune abort'):
                cleanup.remove_radius(self.module, 'Jet', .99)
        self.assertIs(self.module['RUN_DB']['Jet']['nr=11_rho=0.99'], archives)
        self.assertIs(self.module['RUN_BATCH'], old_batch)
        self.assertIs(self.module['RUN_HISTORY']['9537283'], old_history)
        self.assertIs(fixture.storage.result_pool(self.module), pool)
        self.assertEqual(len(pool), 2)

    def test_active_job_checks_for_whole_project_include_parked_history(self):
        from OMFITlib_result_cleanup import active_jobs
        self.module['RUN_HISTORY']['9537283']['manifest']['status'] = 'submitted'
        self.module['RUN_HISTORY']['9817420']['manifest']['status'] = 'published'
        self.module['RUN_MANIFEST']['status'] = 'published'
        self.assertTrue(active_jobs({'CGYRO_scan': self.module}))
        self.assertEqual([token for token, _ in queue.queue_records(self.module)], ['9817420'])

    def test_native_pop_that_mutates_before_abort_is_rolled_back(self):
        class AbortAfterPop(OMFITMapping):
            failed = False
            def pop(self, key, *default):
                value = super().pop(key, *default)
                if key == '9537283' and not self.failed:
                    self.failed = True
                    raise KeyboardInterrupt('after native pop')
                return value
        history = AbortAfterPop(self.module['RUN_HISTORY'])
        self.module['RUN_HISTORY'] = history
        old = history['9537283']
        public = self.module['RUN_DB']['Jet']['nr=11_rho=0.99']
        with self.assertRaisesRegex(KeyboardInterrupt, 'after native pop'):
            cleanup.remove_radius(self.module, 'Jet', .99)
        self.assertIs(history['9537283'], old)
        self.assertIs(self.module['RUN_DB']['Jet']['nr=11_rho=0.99'], public)
        self.assertEqual(len(fixture.storage.result_pool(self.module)), 2)

    def test_abort_after_pruning_commits_restores_the_last_owner(self):
        original = cleanup.prune_storage
        owner = fixture.storage.resolve_result(self.module, self.only_old)
        def prune_then_abort(module):
            original(module)
            self.assertEqual(len(fixture.storage.result_pool(module)), 1)
            raise KeyboardInterrupt('after prune committed')
        with patch.object(cleanup, 'prune_storage', prune_then_abort):
            with self.assertRaisesRegex(KeyboardInterrupt, 'after prune committed'):
                cleanup.remove_radius(self.module, 'Jet', .99)
        self.assertIs(fixture.storage.resolve_result(self.module, self.only_old), owner)
        self.assertIn('nr=11_rho=0.99', self.module['RUN_DB']['Jet'])
        self.assertIn('9537283', self.module['RUN_HISTORY'])

    def test_conflicting_public_radius_and_raw_owner_do_not_load_result_arrays(self):
        self.module['RUN_DB']['Jet']['nr=11_rho=0.99']['H']['__INFO__'] = dict(rho=.33, runid='Jet')
        with self.assertRaisesRegex(ValueError, 'conflicting radius metadata'):
            cleanup.preview_radius(self.module, 'Jet', .99)
        class UnreadResult(fixture.OMFITcgyro):
            def get(self, *args, **kwargs):
                raise AssertionError('Result data was read during metadata preview')
        self.module['RUN_DB']['Jet'].pop('nr=11_rho=0.99')
        self.module['RUN_DB']['Jet']['nr=11__rho=0.99__ion=H'] = UnreadResult(self.owner_paths[0])
        report = cleanup.preview_radius(self.module, 'Jet', .99)
        self.assertIn('Jet/nr=11__rho=0.99__ion=H', report['archives'])


if __name__ == '__main__':
    unittest.main()
