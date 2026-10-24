"""File-level compaction: persistent identities, private readers and rollback."""
import copy
from collections import OrderedDict
import hashlib
import importlib
import json
import shutil
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_cgyro_storage as fixture

storage, db = fixture.storage, fixture.db_api
payload = importlib.import_module('OMFITlib_cgyro_payload')


class FileDedupTests(unittest.TestCase):
    setUp, tearDown = fixture.StorageCases.setUp, fixture.StorageCases.tearDown
    browsable_expressions = fixture.StorageCases.browsable_expressions

    def result(self, name, content):
        reader = fixture.StorageCases.result(self, name, content)
        (Path(reader.filename) / 'input.cgyro').write_bytes(b'KY=0.1\n')
        return reader

    def pair(self):
        root = {}
        refs = [storage.store_result(root, self.result('first', b'1 2 3\n')),
                storage.store_result(root, self.result('second', b'4 5 6\n'))]
        root['RUN_DB']['__UNCLASSIFIED__'] = dict(enumerate(refs))
        return root, refs

    def pack(self, root):
        with patch.object(payload, 'ensure_capacity', return_value={}):
            return payload.pack_results(root, storage.directory_inventory)

    def test_shared_file_survives_one_owner_pruned_and_last_owner_releases_it(self):
        root, refs = self.pair()
        keys = [storage.reference_id(ref) for ref in refs]
        self.assertEqual(self.pack(root), 2)
        pool = storage.result_pool(root)
        shared = hashlib.sha256(b'KY=0.1\n').hexdigest()
        self.assertEqual(len(pool['__FILES__']), 3)
        self.assertEqual(set(pool) - {'__FILES__'}, set(keys))
        root['RUN_DB']['__UNCLASSIFIED__'].pop(0)
        storage.prune_storage(root)
        self.assertIn(shared, pool['__FILES__'])
        self.assertEqual(len(pool['__FILES__']), 2)
        root['RUN_DB']['__UNCLASSIFIED__'].clear()
        storage.prune_storage(root)
        self.assertFalse(pool['__FILES__'])

    def test_reader_bytes_identical_and_edits_do_not_touch_shared_owner(self):
        root, refs = self.pair()
        self.pack(root)
        with patch.object(payload, 'ensure_capacity', return_value={}):
            first = storage.resolve_result(root, refs[0])
            second = storage.resolve_result(root, refs[1])
        self.assertNotEqual(first.filename, second.filename)
        self.assertEqual((Path(first.filename) / 'out.cgyro.freq').read_bytes(), b'1 2 3\n')
        (Path(first.filename) / 'input.cgyro').write_text('KY=999\n')
        self.assertEqual((Path(second.filename) / 'input.cgyro').read_text(), 'KY=0.1\n')
        shared = hashlib.sha256(b'KY=0.1\n').hexdigest()
        self.assertEqual(Path(storage.result_pool(root)['__FILES__'][shared].filename).read_bytes(), b'KY=0.1\n')
        # An edited view is disposable, not an edit to immutable archive data.
        rebuilt = storage.resolve_result(root, refs[0])
        self.assertEqual((Path(rebuilt.filename) / 'input.cgyro').read_text(), 'KY=0.1\n')

    def test_repeat_compaction_and_queue_indexing_do_not_copy_or_hash_payloads(self):
        root, refs = self.pair()
        self.pack(root)
        with patch.object(payload, '_copy_verified', side_effect=AssertionError('copy')):
            with patch.object(storage, 'directory_inventory', side_effect=AssertionError('hash')):
                self.assertEqual(self.pack(root), 0)
                self.assertEqual(storage.compact_storage(root)['physical_results'], 2)
                self.assertEqual(storage.prune_storage(root), 0)

    def test_runtime_catalog_and_small_time_probe_do_not_expand_result_directories(self):
        root, refs = self.pair()
        self.pack(root)
        with patch.object(payload, 'materialize_owner', side_effect=AssertionError('directory expansion')):
            view = storage.result_view(root, {'point': refs[0]})
            self.assertIsInstance(view['point'], fixture.OMFITcgyro)
            self.assertIsNone(fixture.archive_api.output_final_time(view['point']))
            # Continuation publication can reattach a retained result view
            # without copying its files or pretending it is an unindexed file.
            self.assertEqual(storage.reference_id(storage.store_result(root, view['point'])),
                             storage.reference_id(refs[0]))

    def test_new_results_reuse_the_file_pool_after_compaction(self):
        root, refs = self.pair()
        self.pack(root)
        ref = storage.store_result(root, self.result('third', b'7 8 9\n'))
        pool = storage.result_pool(root)
        self.assertTrue(payload.is_packed(pool[storage.reference_id(ref)]))
        self.assertEqual(len(pool['__FILES__']), 4)

    def test_missing_blob_aborts_pruning_before_removing_any_other_owner(self):
        root, refs = self.pair()
        self.pack(root)
        pool = storage.result_pool(root)
        del pool['__FILES__'][hashlib.sha256(b'KY=0.1\n').hexdigest()]
        before = set(pool)
        root['RUN_DB']['__UNCLASSIFIED__'].pop(0)
        with self.assertRaisesRegex(ValueError, 'Missing physical CGYRO result file'):
            storage.prune_storage(root)
        self.assertEqual(set(pool), before)

    def test_tampered_bytes_and_unsafe_or_wrong_identity_manifests_are_rejected(self):
        root, refs = self.pair()
        self.pack(root)
        pool, key = storage.result_pool(root), storage.reference_id(refs[0])
        original = copy.deepcopy(pool[key])
        for name in ('../escape', '/absolute', 'C:/escape', 'folder\\escape', 'x/../escape'):
            bad = copy.deepcopy(original)
            rows = json.loads(bad['inventory'])
            rows[0][0] = name
            bad['inventory'] = json.dumps(rows)
            with self.assertRaises(ValueError):
                payload.inventory(bad, payload.content_key(rows))
        pool[key]['inventory'] = '[]'
        with self.assertRaises(ValueError):
            storage.resolve_result(root, refs[0])
        pool[key] = original
        shared = hashlib.sha256(b'KY=0.1\n').hexdigest()
        Path(pool['__FILES__'][shared].filename).write_bytes(b'KY=9.9\n')
        with self.assertRaisesRegex(ValueError, 'changed while copying'):
            storage.resolve_result(root, refs[0]).filename

    def test_abort_during_manifest_commit_restores_original_owners_and_file_index(self):
        root, refs = self.pair()
        original = dict(storage.result_pool(root))
        blocked = storage.reference_id(refs[1])
        class InterruptedPool(dict):
            def __setitem__(self, key, value):
                super().__setitem__(key, value)
                if key == blocked and payload.is_packed(value):
                    raise KeyboardInterrupt('abort during manifest installation')
        root['RUN_DB'][db.POOL] = pool = InterruptedPool(original)
        state = copy.deepcopy(storage.storage_state(root))
        with self.assertRaises(KeyboardInterrupt):
            self.pack(root)
        self.assertEqual(set(pool), set(original))
        for key in original:
            self.assertIs(pool[key], original[key])
        self.assertEqual(storage.storage_state(root), state)

    def test_modified_old_owner_cannot_be_repacked_under_its_old_identity(self):
        root, refs = self.pair()
        (Path(storage.resolve_result(root, refs[0]).filename) / 'input.cgyro').write_text('KY=99\n')
        before = dict(storage.result_pool(root))
        with self.assertRaisesRegex(ValueError, 'Stored CGYRO result was modified'):
            self.pack(root)
        self.assertEqual(set(storage.result_pool(root)), set(before))
        for key in before:
            self.assertIs(storage.result_pool(root)[key], before[key])

    def test_native_browser_and_updater_accept_packed_owner_without_extra_persistent_reader(self):
        root, refs = self.pair()
        self.pack(root)
        with self.browsable_expressions():
            ref = fixture.reference_api.make_reference(storage.reference_id(refs[0]))
            root['LIB'] = {'OMFITlib_cgyro_payload': SimpleNamespace(importCode=lambda **kwargs: payload)}
            before = set(storage.result_pool(root))
            reader = eval(ref['data'].expression, {'root': root})
            self.assertIsInstance(reader, fixture.OMFITcgyro)
            self.assertEqual(set(storage.result_pool(root)), before)
            updater = fixture.migration.ArchiveIndex()
            updater.cgyro_pool = storage.result_pool(root)
            self.assertTrue(updater.cgyro_payload(ref))
            self.assertEqual(updater.input_identity(ref)[0]['KY'], .1)

    def test_storage_report_counts_unique_bytes_instead_of_logical_copies(self):
        root, refs = self.pair()
        self.pack(root)
        report = storage.compact_storage(root)
        self.assertEqual(report['physical_results'], 2)
        self.assertEqual(report['physical_bytes'], len(b'KY=0.1\n1 2 3\n4 5 6\n'))
        self.assertEqual(report['file_dedup_bytes'], len(b'KY=0.1\n'))
        self.assertEqual(report['input_zip_bytes'], 0)

    def test_persisted_manifest_reopens_without_original_paths_or_runtime_cache(self):
        # Portable metadata/file fixture; native saver/loader is validated
        # separately. This checks that no original directory is an implicit
        # dependency of the packed representation.
        root, refs = self.pair()
        self.pack(root)
        pool = storage.result_pool(root)
        saved = self.base / 'saved-files'
        saved.mkdir()
        metadata = {key: owner for key, owner in pool.items() if key != '__FILES__'}
        metadata = json.loads(json.dumps(metadata))
        blobs = {}
        for digest, owner in pool['__FILES__'].items():
            target = saved / digest
            shutil.copyfile(owner.filename, target)
            blobs[digest] = fixture.OMFITpath(target)
        # All original owners and cached views cease to be usable.
        for child in list(self.base.iterdir()):
            if child == saved:
                continue
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
        payload.native_readers._cgyro_file_views = OrderedDict()
        reopened = {'RUN_DB': {db.POOL: dict(metadata, __FILES__=blobs)}}
        for ref, expected in zip(refs, (b'1 2 3\n', b'4 5 6\n')):
            result = storage.resolve_result(reopened, ref)
            self.assertEqual((Path(result.filename) / 'out.cgyro.freq').read_bytes(), expected)
            self.assertEqual((Path(result.filename) / 'input.cgyro').read_bytes(), b'KY=0.1\n')


if __name__ == '__main__':
    unittest.main()
