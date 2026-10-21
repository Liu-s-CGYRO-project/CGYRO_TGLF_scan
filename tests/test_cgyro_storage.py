"""Isolated file/metadata tests; no OMFIT GUI, scheduler or solver is started.

The minimal native stand-ins only own temporary paths. They do not claim to
validate real OMFIT serialization, reparenting, lazy loading or solver restarts.
Run with: python -B -m unittest discover -s tests -p test_cgyro_storage.py
"""
import copy
import hashlib
import importlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import types
import unittest
import zipfile

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'CGYRO_TGLF_scan/LIB'))
sys.path.insert(0, str(REPO / 'OMFITtemplates/LIB'))


class OMFITobject:
    pass


class OMFITpath(OMFITobject):
    directory = None

    def __init__(self, filename, **properties):
        if not filename:
            handle, filename = tempfile.mkstemp(dir=self.directory)
            import os
            os.close(handle)
        self.filename = str(filename)
        self.OMFITproperties = properties


class OMFITcgyro(OMFITobject):
    def __init__(self, filename, **properties):
        self.filename = str(filename or tempfile.mkdtemp(dir=OMFITpath.directory))
        self.OMFITproperties = properties
        self.test_mode = False


class OMFITgacode(dict, OMFITobject):
    def __init__(self, filename):
        super().__init__(UNSAVED_EDIT=42)
        self.filename = str(filename)


# Keep these stand-ins scoped to the isolated test process.
native = types.ModuleType('omfit_classes')
native.__path__ = []
sys.modules['omfit_classes'] = native
for name, cls in (('omfit_path', OMFITpath), ('omfit_gacode', OMFITcgyro)):
    module = types.ModuleType('omfit_classes.' + name)
    setattr(module, cls.__name__, cls)
    sys.modules[module.__name__] = module

storage = importlib.import_module('OMFITlib_cgyro_storage')
files = importlib.import_module('OMFITlib_cgyro_storage_files')
migration = importlib.import_module('OMFITlib_template_migration')
continuation = importlib.import_module('OMFITlib_cgyro_continue')


class StorageCases(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        OMFITpath.directory = self.temporary.name

    def tearDown(self):
        self.temporary.cleanup()

    def result(self, name, content=b'0 1 2\n'):
        directory = self.base / name
        directory.mkdir()
        (directory / 'input.cgyro').write_text('KY=0.1\n', encoding='utf-8')
        (directory / 'out.cgyro.freq').write_bytes(content)
        return OMFITcgyro(directory)

    def bundle(self, name, different=False, zip_only=False):
        directory = self.base / name
        directory.mkdir()
        members = {'input.cgyro': b'KY=0.1\nMAX_TIME=100\n',
                   'bin.cgyro.restart': b'checkpoint-bytes' * 100,
                   'out.cgyro.tag': b'1\n1.0\n', 'out.cgyro.time': b'1.0\n'}
        target = directory / 'p000001.zip'
        with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
            for key, value in members.items():
                archive.writestr(zipfile.ZipInfo(key), value)
                (directory / key).write_bytes(value)
        if different:
            (directory / 'bin.cgyro.restart').write_bytes(b'a different checkpoint')
        node = {'zip': OMFITpath(target)}
        if not zip_only:
            node.update({key: OMFITpath(directory / key) for key in members if key != 'input.cgyro'})
            node['input.cgyro'] = OMFITgacode(directory / 'input.cgyro')
        return node, members

    def test_legacy_outputs_share_owner_and_distinct_results_survive(self):
        first, same, other = self.result('first'), self.result('same'), self.result('other', b'0 3 4\n')
        root = {'RUN_DB': {'point': first}, 'LEGACY_UNCLASSIFIED': {'unknown': same},
                'OUTPUTS': {'point': other}}
        report = storage.compact_storage(root)
        self.assertEqual(report['physical_results'], 2)
        self.assertEqual(root['RUN_DB']['point'], root['LEGACY_UNCLASSIFIED']['unknown'])
        self.assertNotEqual(root['RUN_DB']['point'], root['OUTPUTS']['point'])
        for original in (first, same, other):
            self.assertTrue((Path(original.filename) / 'out.cgyro.freq').is_file())
        self.assertEqual(storage.compact_storage(root)['converted_copies'], 0)

    def test_zip_snapshot_dedup_removes_only_identical_plain_expanded_files(self):
        first, members = self.bundle('one')
        second = copy.deepcopy(first)
        root = {'Cases': {'case': {'p000001': first}}, 'RUN_HISTORY': {'token': {'cases': {'p000001': second}}}}
        source = Path(first['zip'].filename).read_bytes()
        report = storage.compact_storage(root)
        current = root['Cases']['case']['p000001']
        saved = root['RUN_HISTORY']['token']['cases']['p000001']
        self.assertEqual(current['zip'], saved['zip'])
        self.assertEqual(len(root['RESULT_STORE']['__FILES__']), 1)
        self.assertNotIn('bin.cgyro.restart', current)
        self.assertEqual(current['input.cgyro']['UNSAVED_EDIT'], 42)
        self.assertIsInstance(current['input.cgyro'], OMFITgacode)
        self.assertEqual(Path(first['zip'].filename).read_bytes(), source)
        self.assertGreater(report['expanded_input_bytes'], 0)
        # Plain JSON round-trip of the index models saving its literal data.
        index = json.loads(json.dumps(current['zip']))
        restored = storage.result_view(root, {'zip': index})
        with zipfile.ZipFile(restored['zip'].filename) as archive:
            self.assertEqual({key: archive.read(key) for key in archive.namelist()}, members)
        self.assertEqual(storage.compact_storage(root)['converted_input_zips'], 0)

    def test_different_expanded_checkpoint_is_preserved(self):
        bundle, _ = self.bundle('changed', different=True)
        root = {'Cases': {'case': {'p000001': bundle}}}
        report = storage.compact_storage(root)
        result = root['Cases']['case']['p000001']
        self.assertEqual(Path(result['bin.cgyro.restart'].filename).read_bytes(), b'a different checkpoint')
        self.assertEqual(report['retained_expanded_files'], 1)

    def test_invalid_zip_leaves_original_trees_installed(self):
        good, _ = self.bundle('good')
        bad, _ = self.bundle('bad')
        Path(bad['zip'].filename).write_bytes(b'not a zip')
        cases = {'case': {'p000001': good, 'p000002': bad}}
        root = {'Cases': cases}
        with self.assertRaises(zipfile.BadZipFile):
            storage.compact_storage(root)
        self.assertIs(root['Cases'], cases)
        self.assertNotIn('RESULT_STORE', root)
        self.assertNotIn('RESULT_STORAGE', root)

    def test_commit_exception_restores_old_branches_and_pool(self):
        first, _ = self.bundle('rollback')
        cases = {'case': {'p000001': first}}
        history = {'token': {'cases': copy.deepcopy(cases['case'])}}

        class FailOnce(dict):
            fail = True

            def __setitem__(self, key, value):
                if key == 'RUN_HISTORY' and self.fail:
                    self.fail = False
                    raise KeyboardInterrupt('simulate native Abort during tree replacement')
                super().__setitem__(key, value)

        root = FailOnce(Cases=cases, RUN_HISTORY=history)
        with self.assertRaises(KeyboardInterrupt):
            storage.compact_storage(root)
        self.assertIs(root['Cases'], cases)
        self.assertIs(root['RUN_HISTORY'], history)
        self.assertNotIn('RESULT_STORE', root)
        self.assertNotIn('RESULT_STORAGE', root)

    def test_dangling_index_prevents_pruning_any_owner(self):
        bundle, _ = self.bundle('dangling', zip_only=True)
        root = {'Cases': {'case': {'p000001': bundle}}}
        storage.compact_storage(root)
        owners = dict(root['RESULT_STORE']['__FILES__'])
        root['Cases'] = {'bad': {'__FILE_REF__': 'f' * 64}}
        with self.assertRaises(ValueError):
            storage.prune_storage(root)
        self.assertEqual(root['RESULT_STORE']['__FILES__'], owners)

    def test_unreferenced_zip_pruned_only_from_tree(self):
        bundle, _ = self.bundle('prune', zip_only=True)
        root = {'Cases': {'case': {'p000001': bundle}}}
        storage.compact_storage(root)
        owned = next(iter(root['RESULT_STORE']['__FILES__'].values()))
        root['Cases'] = {}
        self.assertEqual(storage.prune_storage(root), 1)
        self.assertTrue(Path(owned.filename).is_file())
        self.assertTrue(Path(bundle['zip'].filename).is_file())

    def test_cancel_resume_uses_saved_zip_when_old_workdir_is_gone(self):
        bundle, members = self.bundle('resume', zip_only=True)
        manifest = dict(run_token='token', case_tag='case', local_workDir=str(self.base / 'missing'),
                        input_sha256={'p000001': {k: hashlib.sha256(v).hexdigest() for k, v in members.items()}})
        root = {'RUN_MANIFEST': manifest, 'Cases': {'case': {'p000001': bundle}}}
        storage.compact_storage(root)
        disposable = (self.base / 'resume').resolve()
        self.assertEqual(disposable.parent, self.base.resolve())
        shutil.rmtree(disposable)  # Only the checked disposable fixture folder.
        saved = storage.result_view(root, root['Cases']['case'])
        context = dict(results={}, sources={'p000001': (manifest, saved)})
        origin = continuation.resume_source(root, 'token', 'p000001', context=context)
        self.assertEqual(origin['mode'], 'checkpoint_zip')
        self.assertEqual(origin['zip'], storage.submission_file(root, manifest, 'zip', point='p000001'))
        with zipfile.ZipFile(origin['zip']) as archive:
            self.assertEqual(archive.read('bin.cgyro.restart'), members['bin.cgyro.restart'])

    def test_updater_recognizes_existing_archive_reference(self):
        native_result = self.result('indexed')
        root = {}
        ref = storage.store_result(root, native_result)
        case_id = 'nr=1__rho=0.33__ion=T'
        info = dict(case_id=case_id, source_nr=1, rho=0.33, ion_case='T', dimensions=1,
                    scan_dimensions=1, scan_axes=[dict(name='N_THETA', values=[16], linked=[])])
        tasks = {'p000001': dict(result_path=['N_THETA', '16', 'lin', '0.1'])}
        case = {'N_THETA': {'16': {'lin': {'0.1': ref}}},
                '__SCANS__': {'N_THETA': dict(info=info, tasks=tasks)}}
        root['RUN_DB'] = {'Jet': {case_id: case}}
        updater = migration.ArchiveIndex()
        self.assertIsNone(updater.cgyro(root))
        self.assertEqual(updater.issues, [])
        updater.check()
        self.assertNotIn('LEGACY_UNCLASSIFIED', root)

    def test_lazy_identity_does_not_load_payload(self):
        class OMFITlazyLoad:
            def __init__(self, tp):
                self.tp = tp

            def __getattr__(self, name):
                raise AssertionError('Unexpected lazy load: ' + name)

        self.assertTrue(storage.is_result(OMFITlazyLoad('OMFITcgyro')))
        self.assertTrue(files.native_kind(OMFITlazyLoad('OMFITpath'), 'OMFITpath'))


if __name__ == '__main__':
    unittest.main()
