"""Isolated file/metadata tests; no OMFIT GUI, scheduler or solver is started.

The minimal native stand-ins only own temporary paths. They do not claim to
validate real OMFIT serialization, reparenting, lazy loading or solver restarts.
Run with: python -B -m unittest discover -s tests -p test_cgyro_storage.py
"""
import ast
import copy
from datetime import datetime, timezone
import hashlib
import importlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
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


class OMFITlazyLoad:
    """The native wrapper protocol for a persisted metadata pickle, not a file reader."""
    def __init__(self, payload, failure=None, parent=None, key=None):
        self.tp, self.payload, self.failure = 'OMFITpickle', payload, failure
        self.parent, self.key = parent, key

    def __lazy_load__(self):
        if self.failure is not None:
            raise self.failure
        if self.parent is not None:
            self.parent[self.key] = self.payload
        return self.payload

    def __getattr__(self, name):
        return getattr(self.__lazy_load__(), name)

    def __iter__(self):
        return iter(self.__lazy_load__())

    def __getitem__(self, key):
        return self.__lazy_load__()[key]


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
archive_api = importlib.import_module('OMFITlib_cgyro_archive')
queue_api = importlib.import_module('OMFITlib_cgyro_queue')
db_api = importlib.import_module('OMFITlib_cgyro_db')
scratch = importlib.import_module('OMFITlib_cgyro_scratch')


class StorageCases(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        OMFITpath.directory = self.temporary.name
        # Capacity behavior is checked separately against only this test's
        # temporary directory, never by scanning the developer's whole /tmp.
        for module in (storage, files):
            override = patch.object(module, 'ensure_capacity', return_value={})
            override.start()
            self.addCleanup(override.stop)

    def tearDown(self):
        self.temporary.cleanup()

    def compact(self, root):
        if 'Cases' in root and 'RUN_MANIFEST' not in root:
            root['RUN_MANIFEST'] = dict(run_token='current', case_tag='case')
        return storage.compact_storage(root)

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

    def indexed_scan(self, module, token, ion, name='N_THETA', values=(16, 32, 48, 64), ky_count=16):
        case, tasks = {}, {}
        for value in values:
            for number in range(ky_count):
                point = 'p{:06d}'.format(len(tasks) + 1)
                ky = (number + 1) / 100.
                path = [name, str(value), 'lin', str(ky)]
                node = case.setdefault(name, {}).setdefault(str(value), {}).setdefault('lin', {})
                node[str(ky)] = storage.store_result(module, self.result(token + point,
                    (token + str(value) + str(ky)).encode()))
                tasks[point] = dict(result_path=path, values={name: value, 'KY': ky})
        cid = 'nr=1__rho=0.33__ion=' + ion
        info = dict(runid='Jet', case_id=cid, run_token=token, source_nr=1, rho=.33,
                    ion_case=ion, dimensions=1, scan_dimensions=1,
                    scan_axes=[dict(name=name, values=list(values), linked=[])])
        archive_api.store_scan(case, case, info, tasks)
        return case

    def test_recover_user_unclassified_hdt_scans_into_run_db_only(self):
        source = {}
        h = self.indexed_scan(source, 'h_energy', 'H', 'N_ENERGY', (8, 16, 24, 32), 15)
        d = self.indexed_scan(source, 'd_theta', 'D')
        t = self.indexed_scan(source, 't_theta', 'T')
        root = dict(RESULT_STORE=storage.result_pool(source), RESULT_STORAGE=storage.storage_state(source),
                    LEGACY_UNCLASSIFIED={'Jet %2F H': h, 'Jet %2F D': d, 'Jet %2F T': t},
                    RUN_DB={})
        report = storage.consolidate_storage(root)
        self.assertEqual(report['recovered_archives'], 3)
        self.assertEqual(report['unresolved_archives'], 0)
        self.assertEqual(len(storage.result_pool(root)), 188)
        run = root['RUN_DB']['Jet']
        for ion, key, count in (('H', 'N_ENERGY', 60), ('D', 'N_THETA', 64), ('T', 'N_THETA', 64)):
            case = run['nr=1_rho=0.33'][ion]
            self.assertEqual(len(case['__SCANS__'][key]['tasks']), count)
        self.assertFalse(any(key in root for key in db_api.OLD_BRANCHES))
        self.assertEqual(storage.consolidate_storage(root)['recovered_archives'], 0)

    def test_recovery_merges_revisions_without_visible_suffixes(self):
        root = {}
        first = self.indexed_scan(root, 'theta_old', 'T', values=(16,), ky_count=1)
        second = self.indexed_scan(root, 'theta_new', 'T', values=(16,), ky_count=1)
        cid = first['__INFO__']['case_id']
        root['RUN_DB']['Jet'] = {cid: first}
        root['LEGACY_UNCLASSIFIED'] = {'old revision': second}
        report = storage.consolidate_storage(root)
        self.assertEqual(report['recovered_archives'], 1)
        self.assertEqual(root['RUN_DB']['Jet']['nr=1_rho=0.33']['T']['__INFO__']['run_token'], 'theta_old')
        self.assertEqual(len(storage.result_pool(root)), 1)
        visible = [key for key in root['RUN_DB'] if not key.startswith('__')]
        self.assertEqual(visible, ['Jet'])

    def test_generated_run_folders_merge_without_losing_scans_or_radii(self):
        root = {}
        scans = [(ion, token, name, value) for ion, token, name, value in (
            ('H', 'h_theta', 'N_THETA', 16), ('H', 'h_energy', 'N_ENERGY', 8),
            ('D', 'd_theta', 'N_THETA', 16), ('T', 't_theta', 'N_THETA', 16),
            ('T', 't_revision', 'N_THETA', 32), ('T', 't_recovered', 'N_THETA', 48),
            ('T', 't_energy', 'N_ENERGY', 8), ('H', 'other_radius', 'N_THETA', 16))]
        cases = {token: self.indexed_scan(root, token, ion, name, (value,), 1)
                 for ion, token, name, value in scans}
        cid = lambda ion: 'nr=1__rho=0.33__ion=' + ion
        other = cases['other_radius']
        other['__INFO__'].update(case_id='nr=2__rho=0.66__ion=H', source_nr=2, rho=.66)
        root['RUN_DB'].update({
            'Jet': {cid('H'): cases['h_theta'], cid('D'): cases['d_theta'], cid('T'): cases['t_theta'],
                    'nr=2__rho=0.66__ion=H': other},
            'Jet [legacy revision 2]': {cid('T'): cases['t_revision']},
            'Jet [partial 3fdce673]': {cid('T'): cases['t_energy']},
            'Jet [partial 1535d4da] [recovered 086c682d]': {cid('T'): cases['t_recovered']},
            'Jet [recovered abcd]': {cid('H'): cases['h_energy']}})
        unknown = {'lin': {'0.01': cases['h_theta']['N_THETA']['16']['lin']['0.01']}}
        root['RUN_DB']['Legacy OUTPUTScan'] = {'unknown': unknown}
        private = storage.store_result(root, self.result('private_output', b'private output'))
        root['RUN_DB']['Jet']['__CUSTOM__'] = private
        cases['h_theta']['__CUSTOM__'] = private
        root['RUN_DB']['Jet']['nr=3_rho=0.9'] = {'__CUSTOM__': private}
        storage.consolidate_storage(root)
        self.assertEqual([key for key in root['RUN_DB'] if not key.startswith('__')], ['Jet'])
        jet = root['RUN_DB']['Jet']
        self.assertEqual(set(jet), {'nr=1_rho=0.33', 'nr=2_rho=0.66'})
        self.assertEqual(set(jet['nr=1_rho=0.33']), {'H', 'D', 'T'})
        self.assertEqual(set(jet['nr=1_rho=0.33']['H']['__SCANS__']), {'N_THETA', 'N_ENERGY'})
        theta = jet['nr=1_rho=0.33']['T']['__SCANS__']['N_THETA']['tasks']
        self.assertEqual({row['values']['N_THETA'] for row in theta.values()}, {16, 32, 48})
        self.assertEqual(len(storage.result_pool(root)), len(cases) + 1)
        storage.resolve_result(root, private)
        self.assertTrue(root['RUN_DB'][db_api.PENDING])  # No identity was guessed for raw output.
        def coordinates():
            return {(cid, key): {archive_api.point_coordinate(row): continuation.point_result(case, row)
                    for row in tasks.values()}
                    for cid, case in archive_api.catalog_runs(root)['Jet'].items()
                    for key, _, tasks in archive_api.case_scans(case)}
        before = copy.deepcopy(coordinates())
        owners = set(storage.result_pool(root))
        storage.consolidate_storage(root)
        self.assertEqual(coordinates(), before)
        self.assertEqual(set(storage.result_pool(root)), owners)
        self.assertEqual(storage.storage_state(root)['case_layout'], 'radius-ion')
        self.assertEqual(storage.storage_state(root)['version'], 5)

    def test_partial_aliases_keep_the_most_advanced_readable_coordinate(self):
        root = {}
        def timed(token, final_time, partial):
            case = self.indexed_scan(root, token, 'T', values=(16,), ky_count=1)
            row = case['__TASKS__']['p000001']
            result = storage.resolve_result(root, continuation.point_result(case, row))
            if final_time is not None:
                (Path(result.filename) / 'out.cgyro.time').write_text(str(final_time) + '\n', encoding='utf-8')
            row.update(status='partial' if partial else 'loaded', resume_pending=partial)
            case['__INFO__']['collection_status'] = 'partial' if partial else 'complete'
            return case
        complete = timed('complete', 100, False)
        short = timed('short', 80, True)
        cid = complete['__INFO__']['case_id']
        root['RUN_DB'].update({'Jet': {cid: complete}, 'Jet [partial abcd]': {cid: short}})
        storage.consolidate_storage(root)
        row = root['RUN_DB']['Jet']['nr=1_rho=0.33']['T']['__TASKS__']['p000001']
        self.assertEqual((row['run_token'], row['final_time']), ('complete', 100))
        advanced, unknown = timed('advanced', 120, True), timed('unknown', None, True)
        root['RUN_DB'].update({'Jet [partial dcba]': {cid: advanced}, 'Jet [recovered abcd]': {cid: unknown}})
        storage.consolidate_storage(root)
        row = root['RUN_DB']['Jet']['nr=1_rho=0.33']['T']['__TASKS__']['p000001']
        self.assertEqual((row['run_token'], row['final_time']), ('advanced', 120))
        self.assertTrue(row['resume_pending'])

    def test_merged_point_ids_reserve_unstarted_original_tasks(self):
        root = {}
        old = self.indexed_scan(root, 'old_ids', 'T', values=(16,), ky_count=1)
        new = self.indexed_scan(root, 'new_ids', 'T', values=(32,), ky_count=1)
        new['__INFO__']['planned_points'] = ['p000001', 'p000002']
        destination = archive_api.combine_cases([old])
        archive_api.store_scan(destination, new, new['__INFO__'], new['__TASKS__'])
        self.assertEqual(set(destination['__TASKS__']), {'p000001', 'p000003'})
        self.assertEqual(destination['__TASKS__']['p000003']['source_point_id'], 'p000001')
        self.assertEqual(destination['__TASKS__']['p000003']['run_token'], 'old_ids')

    def test_grouping_abort_restores_original_public_catalog(self):
        root = {}
        case = self.indexed_scan(root, 'abort_grouping', 'T', values=(16,), ky_count=1)
        cid = case['__INFO__']['case_id']
        original = {cid: case}
        class FailOnce(dict):
            fail = True
            def __setitem__(self, key, value):
                if key == 'Jet' and self.fail:
                    self.fail = False
                    raise KeyboardInterrupt('Abort during grouped catalog installation')
                super().__setitem__(key, value)
        db = FailOnce(root['RUN_DB'])
        dict.__setitem__(db, 'Jet', original)
        root['RUN_DB'] = db
        state = db[db_api.STATE]
        with self.assertRaises(KeyboardInterrupt):
            storage.recover_archives(root, storage.resolve_result)
        self.assertIs(root['RUN_DB']['Jet'], original)
        self.assertIs(root['RUN_DB'][db_api.STATE], state)
        storage.resolve_result(root, case['N_THETA']['16']['lin']['0.01'])

    def test_unknown_public_name_never_overwrites_retained_source(self):
        root = {}
        first = storage.store_result(root, self.result('unknown_first', b'first'))
        second = storage.store_result(root, self.result('unknown_second', b'second'))
        root['RUN_DB']['Unknown'] = first
        root['RUN_DB'][db_api.PENDING] = {'Unknown': second}
        storage.consolidate_storage(root)
        pending = root['RUN_DB'][db_api.PENDING]
        self.assertEqual(pending['Unknown'], second)
        self.assertEqual(pending['Unknown [2]'], first)
        self.assertEqual(len(storage.result_pool(root)), 2)

    def test_grouped_readers_and_stopped_resume_use_distinct_point_tables(self):
        root = {}
        old = self.indexed_scan(root, 'prior_grid', 'T', values=(16,), ky_count=1)
        new = self.indexed_scan(root, 'stopped_grid', 'T', values=(32,), ky_count=1)
        cid = new['__INFO__']['case_id']
        new['__INFO__']['planned_points'] = ['p000001', 'p000002']
        table = copy.deepcopy(new['__TASKS__'])
        table['p000002'] = dict(values={'N_THETA': 48, 'KY': .01},
                               result_path=['N_THETA', '48', 'lin', '0.01'])
        bundle, members = self.bundle('stopped_original', zip_only=True)
        manifest = dict(new['__INFO__'], nr=1, mass='T', case_tag='case',
                        status='cancelled', collection_status='partial', points=list(table),
                        loaded_points=['p000001'], partial_points=[], point_table=table,
                        workDir='/original/stopped_grid', local_workDir=str(self.base / 'missing'),
                        input_sha256={'p000002': {key: hashlib.sha256(value).hexdigest()
                                                for key, value in members.items()}})
        root['RUN_MANIFEST'] = manifest
        root['Cases'] = {'case': {'p000001': continuation.point_result(new, table['p000001']),
                                 'p000002': bundle}}
        queue_api.save_current(root)
        merged = archive_api.combine_cases([old])
        archive_api.store_scan(merged, new, new['__INFO__'], new['__TASKS__'])
        root['RUN_DB']['Jet'] = {'nr=1_rho=0.33': {'T': merged}}
        storage.storage_state(root)['case_layout'] = 'radius-ion'
        root['RUN_DB'][db_api.LEGACY] = {'RUN_INDEX': {'obsolete': dict(runid='Jet [partial abcd]', case_id=cid)}}
        context = continuation.stopped_context(root, 'stopped_grid')
        self.assertEqual(set(context['rows']), {'p000001', 'p000002'})
        self.assertEqual(set(context['results']), {'p000001'})
        self.assertEqual(context['unfinished'], {'p000002'})
        self.assertEqual(context['rows']['p000002']['values']['N_THETA'], 48)
        self.assertEqual(continuation.resume_source(root, 'stopped_grid', 'p000002', context)['mode'], 'checkpoint_zip')

        # Execute real reader definitions without Tk, a Figure or an OMFIT session.
        path = REPO / 'CGYRO_TGLF_scan/LIB/OMFITlib_cgyro_results.py'
        names = {'_stable_keys', '_run_options', '_result_node'}
        definitions = [node for node in ast.parse(path.read_text(encoding='utf-8')).body
                       if isinstance(node, ast.FunctionDef) and node.name in names]
        from collections import OrderedDict
        namespace = dict(OrderedDict=OrderedDict, catalog_runs=archive_api.catalog_runs,
                         latest_cases=archive_api.latest_cases, case_scans=archive_api.case_scans,
                         case_destination=archive_api.case_destination, legacy_branch=db_api.legacy_branch,
                         run_records=db_api.run_records, storage_state=storage.storage_state,
                         stopped_context=continuation.stopped_context,
                         resolve_result=storage.resolve_result, record_options=lambda records: dict(records))
        exec(compile(ast.Module(body=definitions, type_ignores=[]), str(path), 'exec'), namespace)
        parent = {'CGYRO_scan': root}
        records, _ = namespace['_run_options'](parent)
        self.assertNotIn('obsolete', records)
        entry = records['stopped_grid']
        self.assertEqual(entry['destination'], ['Jet', 'nr=1_rho=0.33', 'T'])
        self.assertEqual(set(entry['tasks']), {'p000001', 'p000003'})
        self.assertEqual(set(entry['resume_tasks']), {'p000001', 'p000002'})
        for row in entry['tasks'].values():
            self.assertIsInstance(namespace['_result_node'](parent, entry, row), OMFITcgyro)
        self.assertEqual(archive_api.case_destination(root, 'Jet', cid), entry['destination'])

    def test_missing_owner_prevents_recovery_and_pruning(self):
        root = {}
        case = self.indexed_scan(root, 'missing_owner', 'D', values=(16,), ky_count=1)
        ref = case['N_THETA']['16']['lin']['0.01']
        ref['__RESULT_REF__'] = 'f' * 64
        root['LEGACY_UNCLASSIFIED'] = {'uncertain': case}
        owners = dict(storage.result_pool(root))
        with self.assertRaisesRegex(ValueError, 'Missing physical'):
            storage.consolidate_storage(root)
        self.assertEqual(storage.result_pool(root), owners)
        self.assertIn('uncertain', root['RUN_DB'][db_api.PENDING])

    def test_manager_reads_unopened_native_metadata_without_misclassification(self):
        root = {}
        case = self.indexed_scan(root, 'lazy_meta', 'D', values=(16,), ky_count=1)
        record = case['__SCANS__']['N_THETA']
        tasks = record['tasks']
        record['tasks'] = OMFITlazyLoad(tasks, parent=record, key='tasks')
        ref = case['N_THETA']['16']['lin']['0.01']
        digest = ref['__RESULT_REF__']
        ref['__RESULT_REF__'] = OMFITlazyLoad(digest, parent=ref, key='__RESULT_REF__')
        legacy = dict(RESULT_STORE=storage.result_pool(root), RUN_DB={'Jet': {case['__INFO__']['case_id']: case}})
        updater = migration.ArchiveIndex()
        self.assertIsNone(updater.cgyro(legacy))
        updater.check()
        self.assertEqual(updater.issues, [])

    def test_manager_parses_composite_axis_name_once(self):
        node = self.result('two_axes')
        data = {'8': {'N_XI': {'16': {'lin': {'0.1': node}}}}}
        axes, _, points = migration.ArchiveIndex().points('N_ENERGY__N_XI', data)
        self.assertEqual(axes, ['N_ENERGY', 'N_XI'])
        self.assertEqual(len(points), 1)

    def test_download_keeps_original_retry_zip_only_inside_run_db(self):
        bundle, members = self.bundle('download', zip_only=True)
        manifest = dict(run_token='download', case_tag='case', batch_id='batch', status='submitted',
                        collection_status='pending', local_workDir=str(self.base / 'missing'))
        root = dict(RUN_MANIFEST=manifest, Cases={'case': {'p000001': bundle}},
                    RUN_BATCH=dict(batch_id='batch', tokens=['download']))
        queue_api.save_current(root)
        frozen = storage.submission_file(root, manifest, 'zip', point='p000001')
        db_api.run_cases(root)['p000001'] = storage.store_result(root, self.result('download_output'))
        manifest.update(collection_status='partial', status='cancelled')
        queue_api.save_current(root)
        self.assertEqual(storage.submission_file(root, manifest, 'zip', point='p000001'), frozen)
        with zipfile.ZipFile(frozen) as handle:
            self.assertEqual(handle.read('input.cgyro'), members['input.cgyro'])
        self.assertNotIn('Cases', root)
        self.assertNotIn('cases', root['RUN_HISTORY']['download'])
        queue_api.activate_run(root, 'download')
        self.assertIsNotNone(storage.resolve_result(root, db_api.run_cases(root)['p000001']))

    def test_migrated_completed_ancestor_keeps_manifest_in_run_db(self):
        source = {}
        case = self.indexed_scan(source, 'ancestor', 'D', values=(16,), ky_count=1)
        cid = case['__INFO__']['case_id']
        manifest = dict(run_token='ancestor', runid='Jet', case_id=cid, status='published')
        root = dict(RESULT_STORE=storage.result_pool(source), RESULT_STORAGE=storage.storage_state(source),
                    RUN_DB={'Jet': {cid: case}}, RUN_HISTORY={'ancestor': {'manifest': manifest}})
        storage.compact_storage(root)
        saved, cases = continuation.saved_run(root, 'ancestor')
        self.assertEqual(saved['run_token'], 'ancestor')
        self.assertEqual(cases, {})
        self.assertEqual(continuation.archived_case(root, 'ancestor')[:2], ('Jet', cid))

    def test_legacy_outputs_share_owner_and_distinct_results_survive(self):
        first, same, other = self.result('first'), self.result('same'), self.result('other', b'0 3 4\n')
        root = {'RUN_DB': {'point': first}, 'LEGACY_UNCLASSIFIED': {'unknown': same},
                'OUTPUTS': {'point': other}}
        report = self.compact(root)
        self.assertEqual(report['physical_results'], 2)
        self.assertEqual(root['RUN_DB']['point'], root['RUN_DB'][db_api.PENDING]['unknown'])
        self.assertNotEqual(root['RUN_DB']['point'], db_api.legacy_outputs(root)['point'])
        self.assertNotIn('LEGACY_UNCLASSIFIED', root)
        self.assertNotIn('OUTPUTS', root)
        for original in (first, same, other):
            self.assertTrue((Path(original.filename) / 'out.cgyro.freq').is_file())
        self.assertEqual(self.compact(root)['converted_copies'], 0)

    def test_prune_keeps_results_referenced_by_unopened_archive(self):
        root = {}
        ref = storage.store_result(root, self.result('unopened'))
        root['RUN_DB']['Jet'] = {'case': OMFITlazyLoad({'N_THETA': {'16': ref}})}
        owners = dict(storage.result_pool(root))
        self.assertEqual(storage.prune_storage(root), 0)
        self.assertEqual(storage.result_pool(root), owners)
        self.assertIs(storage.resolve_result(root, ref), owners[ref['__RESULT_REF__']])

    def test_unreadable_metadata_aborts_prune_before_removing_any_owner(self):
        root = {}
        storage.store_result(root, self.result('unreadable'))
        root['RUN_DB']['Jet'] = OMFITlazyLoad(None, ValueError('unreadable archive metadata'))
        owners = dict(storage.result_pool(root))
        with self.assertRaisesRegex(ValueError, 'unreadable archive metadata'):
            storage.prune_storage(root)
        self.assertEqual(storage.result_pool(root), owners)

    def test_prune_keeps_file_and_result_refs_in_persisted_sequences(self):
        root = {}
        ref = storage.store_result(root, self.result('sequence'))
        bundle, _ = self.bundle('sequence_zip', zip_only=True)
        root['Cases'] = {'case': {'p000001': bundle}}
        self.compact(root)
        zip_ref = copy.deepcopy(db_api.run_cases(root)['p000001']['zip'])
        db_api.run_records(root)['current'].pop('cases', None)
        root['RUN_HISTORY'] = {'old': OMFITlazyLoad({'retained': [(ref, zip_ref)]})}
        self.assertEqual(storage.prune_storage(root), 0)
        self.assertEqual(len(storage.result_pool(root)['__FILES__']), 1)

    def test_manual_archive_retains_other_axes_when_point_ids_repeat(self):
        # Execute only the real publisher's function definitions, never the
        # submission/downsync entry statements or any remote command.
        path = REPO / 'CGYRO_TGLF_scan/CGYRO_scan/SCRIPTS/CGYROScan.py'
        tree = ast.parse(path.read_text(encoding='utf-8'))
        selected = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
        namespace = dict(copy=copy, datetime=datetime, timezone=timezone, OMFITtree=dict,
                         continuation_case=continuation.continuation_case,
                         point_result=continuation.point_result, save_current=queue_api.save_current,
                         compact_storage=storage.compact_storage, prune_storage=storage.prune_storage,
                         store_result=storage.store_result, resolve_result=storage.resolve_result,
                         run_cases=db_api.run_cases, recover_archives=storage.recover_archives)
        for name in ('canonical_case_key', 'catalog_runs', 'clean_run_id', 'combine_cases', 'grouped_case_path', 'matching_cases', 'output_final_time', 'scan_key', 'store_scan', 'validate_preserved_scans'):
            namespace[name] = getattr(archive_api, name)
        exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), 'exec'), namespace)
        root = {}
        case_id = 'nr=1__rho=0.33__ion=T'

        def collect(token, names, content, ky=.1):
            values = dict(zip(names, [16, 32, 48]))
            point_path = []
            for name in names:
                point_path.extend([name, str(values[name])])
            point_path.extend(['lin', str(ky)])
            root['RUN_MANIFEST'] = dict(run_token=token, status='loaded', collection_status='ready',
                dimensions=len(names), scan_axes=[dict(name=name, values=[values[name]], linked=[]) for name in names],
                case_tag='case', case_id=case_id, nr=1, rho=.33, mass='T', runid='Jet',
                workDir='/runs/' + token, server='fixture', points=['p000001'], loaded_points=['p000001'],
                point_table={'p000001': dict(values=dict(values, KY=ky), result_path=point_path)})
            root['Cases'] = {'case': {'p000001': self.result(token, content)}}
            namespace['publish_loaded_run'](root)

        collect('theta', ['N_THETA'], b'theta')
        original = copy.deepcopy(archive_api.catalog_runs(root)['Jet'][case_id]['N_THETA'])
        collect('energy_xi', ['N_ENERGY', 'N_XI'], b'energy_xi')
        collect('three_axes', ['N_ENERGY', 'N_XI', 'N_RADIAL'], b'three_axes')
        collect('energy_again', ['N_ENERGY', 'N_XI'], b'energy_again')
        case = archive_api.catalog_runs(root)['Jet'][case_id]
        self.assertEqual(set(case['__SCANS__']), {'N_THETA', 'N_ENERGY__N_XI', 'N_ENERGY__N_XI__N_RADIAL'})
        self.assertEqual(case['N_THETA'], original)
        self.assertEqual(len(storage.result_pool(root)), 3)
        for _, _, tasks in archive_api.case_scans(case):
            self.assertEqual(list(tasks), ['p000001'])
            node = case
            for part in tasks['p000001']['result_path']:
                node = node[part]
            storage.resolve_result(root, node)
        for names in (['N_THETA'], ['N_ENERGY', 'N_XI'], ['N_ENERGY', 'N_XI', 'N_RADIAL']):
            collect('extra_ky_' + str(len(names)), names, b'extra' + str(len(names)).encode(), ky=.2)
            case = archive_api.catalog_runs(root)['Jet'][case_id]
            scan = '__'.join(names)
            tasks = case['__SCANS__'][scan]['tasks']
            self.assertEqual({row['values']['KY'] for row in tasks.values()}, {.1, .2})
            self.assertEqual(len(tasks), 2)
            # Incoming IDs stay tied to that job; retained collisions have a
            # distinct archive ID and retain their original source identity.
            self.assertEqual(tasks['p000001']['values']['KY'], .2)
            older = [row for row in tasks.values() if row['values']['KY'] == .1][0]
            self.assertEqual(older['source_point_id'], 'p000001')
            old_ref = copy.deepcopy(continuation.point_result(case, older))
            collect('overlap_' + str(len(names)), names, b'overlap' + str(len(names)).encode(), ky=.2)
            case = archive_api.catalog_runs(root)['Jet'][case_id]
            tasks = case['__SCANS__'][scan]['tasks']
            self.assertEqual(len(tasks), 2)
            older = [row for row in tasks.values() if row['values']['KY'] == .1][0]
            self.assertEqual(continuation.point_result(case, older), old_ref)
        # A broken/custom merge cannot replace the installed case or hide its
        # other axes. Validation runs before assigning RUN_DB and pruning.
        installed = archive_api.catalog_runs(root)['Jet'][case_id]
        def coordinates(case):
            return {key: {archive_api.point_coordinate(row): continuation.point_result(case, row)
                          for row in tasks.values()} for key, _, tasks in archive_api.case_scans(case)}
        before = copy.deepcopy(coordinates(installed))
        namespace['combine_cases'] = lambda *args: {}
        with self.assertRaisesRegex(ValueError, 'Archive retention check failed'):
            collect('blocked_merge', ['N_ENERGY', 'N_XI'], b'blocked')
        self.assertEqual(coordinates(archive_api.catalog_runs(root)['Jet'][case_id]), before)

    def test_retention_guard_rejects_discarded_ky_in_same_parameter_scan(self):
        root = {}
        old = self.indexed_scan(root, 'old_ky', 'T', values=(16,), ky_count=2)
        incoming = self.indexed_scan(root, 'new_ky', 'T', values=(16,), ky_count=1)
        info, tasks = incoming['__INFO__'], incoming['__TASKS__']
        # Deliberately bypass the upsert to emulate the former whole-scan replace.
        with self.assertRaisesRegex(ValueError, 'prior parameter/ky'):
            archive_api.validate_preserved_scans([old], incoming, 'N_THETA', tasks)
        merged = archive_api.combine_cases([old])
        archive_api.store_scan(merged, incoming, info, tasks)
        archive_api.validate_preserved_scans([old], merged, 'N_THETA', tasks)
        self.assertEqual(len(merged['__TASKS__']), 2)

    def test_compaction_keeps_path_keyed_metadata_as_plain_mapping(self):
        class NativeKeys(dict):
            def __setitem__(self, key, value):
                if '/' in str(key):
                    raise ValueError('native tree key contains slash')
                super().__setitem__(key, value)

        bundle, _ = self.bundle('metadata_paths', zip_only=True)
        manifest = dict(run_token='metadata', status='submitted', case_tag='case',
                        files={'/server/path/input.cgyro': 'digest'})
        root = dict(RUN_MANIFEST=manifest, Cases={'case': {'p000001': bundle}})
        storage.compact_storage(root, NativeKeys)
        saved = db_api.run_records(root)['metadata']['manifest']
        self.assertEqual(saved['files']['/server/path/input.cgyro'], 'digest')
        storage.storage_state(root)['recovery'] = {'kept': True}
        storage.compact_storage(root, NativeKeys)
        self.assertEqual(storage.storage_state(root)['recovery'], {'kept': True})

    def test_temp_limit_stops_before_copy_and_counts_existing_files(self):
        (self.base / 'existing').write_bytes(b'x' * 90)
        report = scratch.space_report(self.base, tmp_root=self.base)
        self.assertEqual(report['used_bytes'], 90)
        with patch.object(scratch, 'space_report', return_value=report), patch.object(scratch, 'LIMIT_BYTES', 100):
            scratch.ensure_capacity(self.base, 10)
            with self.assertRaisesRegex(RuntimeError, '100 GiB'):
                scratch.ensure_capacity(self.base, 11)
        self.assertEqual((self.base / 'existing').read_bytes(), b'x' * 90)

    def test_staging_cleanup_requires_verified_zip_and_protects_live_reader(self):
        token, point = 'a' * 32, 'p000001'
        run = self.base / 'runs' / token
        stage = run / 'staging' / point
        stage.mkdir(parents=True)
        payload = b'KY=0.1\n'
        expanded = stage / 'input.cgyro'
        expanded.write_bytes(payload)
        packed = run / (point + '.zip')
        with zipfile.ZipFile(packed, 'w') as archive:
            archive.writestr('input.cgyro', payload)
        checksums = {'input.cgyro': hashlib.sha256(payload).hexdigest()}
        with self.assertRaisesRegex(ValueError, 'still owned'):
            scratch.clean_stage(run, token, point, packed, checksums, [expanded])
        expanded.write_bytes(b'different')
        with self.assertRaisesRegex(ValueError, 'differs'):
            scratch.clean_stage(run, token, point, packed, checksums)
        self.assertTrue(stage.exists())
        expanded.write_bytes(payload)
        self.assertEqual(scratch.clean_stage(run, token, point, packed, checksums), len(payload))
        self.assertFalse(stage.exists())
        self.assertTrue(packed.exists())
        with self.assertRaisesRegex(ValueError, 'unowned'):
            scratch.clean_stage(run.parent, token, point, packed, checksums)

    def test_consolidation_cleans_expansion_before_allocating_owners(self):
        token, point = 'b' * 32, 'p000001'
        bundle, members = self.bundle('preclean', zip_only=True)
        work = self.base / 'runs' / token
        stage = work / 'staging' / point
        stage.mkdir(parents=True)
        for name, data in members.items():
            (stage / name).write_bytes(data)
        manifest = dict(run_token=token, case_tag='case', status='submitted',
                        local_workDir=str(work), input_sha256={point:{name:hashlib.sha256(data).hexdigest() for name,data in members.items()}})
        root = dict(RUN_MANIFEST=manifest, Cases={'case': {point:bundle}})
        original_zip = Path(bundle['zip'].filename)
        old_check = storage.ensure_capacity
        def checked(*args, **kwargs):
            self.assertFalse(stage.exists(), 'reproducible expansion should be freed first')
            return old_check(*args, **kwargs)
        with patch.object(files, 'ensure_capacity', side_effect=checked):
            report = storage.consolidate_storage(root)
        self.assertEqual(report['staging_bytes_removed'], sum(map(len,members.values())))
        self.assertTrue(original_zip.exists())
        self.assertTrue(Path(storage.submission_file(root, manifest, 'zip', point=point)).exists())

    def test_zip_snapshot_dedup_removes_only_identical_plain_expanded_files(self):
        first, members = self.bundle('one')
        second = copy.deepcopy(first)
        root = {'Cases': {'case': {'p000001': first}}, 'RUN_HISTORY': {'token': {'cases': {'p000001': second}}}}
        source = Path(first['zip'].filename).read_bytes()
        report = self.compact(root)
        current = db_api.run_cases(root)['p000001']
        saved = db_api.run_cases(root, {'run_token': 'token'})['p000001']
        self.assertEqual(current['zip'], saved['zip'])
        self.assertEqual(len(storage.result_pool(root)['__FILES__']), 1)
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
        self.assertEqual(self.compact(root)['converted_input_zips'], 0)

    def test_different_expanded_checkpoint_is_preserved(self):
        bundle, _ = self.bundle('changed', different=True)
        root = {'Cases': {'case': {'p000001': bundle}}}
        report = self.compact(root)
        result = db_api.run_cases(root)['p000001']
        self.assertEqual(Path(result['bin.cgyro.restart'].filename).read_bytes(), b'a different checkpoint')
        self.assertEqual(report['retained_expanded_files'], 1)

    def test_invalid_zip_leaves_original_trees_installed(self):
        good, _ = self.bundle('good')
        bad, _ = self.bundle('bad')
        Path(bad['zip'].filename).write_bytes(b'not a zip')
        cases = {'case': {'p000001': good, 'p000002': bad}}
        root = {'Cases': cases}
        with self.assertRaises(zipfile.BadZipFile):
            self.compact(root)
        self.assertIs(db_api.run_cases(root)['p000001']['zip'], good['zip'])
        self.assertIs(db_api.run_cases(root)['p000002']['zip'], bad['zip'])
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
            self.compact(root)
        self.assertIs(root['Cases'], cases)
        self.assertIs(root['RUN_HISTORY'], history)
        self.assertNotIn('RESULT_STORE', root)
        self.assertNotIn('RESULT_STORAGE', root)

    def test_dangling_index_prevents_pruning_any_owner(self):
        bundle, _ = self.bundle('dangling', zip_only=True)
        root = {'Cases': {'case': {'p000001': bundle}}}
        self.compact(root)
        owners = dict(storage.result_pool(root)['__FILES__'])
        root['Cases'] = {'bad': {'__FILE_REF__': 'f' * 64}}
        with self.assertRaises(ValueError):
            storage.prune_storage(root)
        self.assertEqual(storage.result_pool(root)['__FILES__'], owners)

    def test_unreferenced_zip_pruned_only_from_tree(self):
        bundle, _ = self.bundle('prune', zip_only=True)
        root = {'Cases': {'case': {'p000001': bundle}}}
        self.compact(root)
        owned = next(iter(storage.result_pool(root)['__FILES__'].values()))
        db_api.run_records(root)['current'].pop('cases', None)
        self.assertEqual(storage.prune_storage(root), 1)
        self.assertTrue(Path(owned.filename).is_file())
        self.assertTrue(Path(bundle['zip'].filename).is_file())

    def test_cancel_resume_uses_saved_zip_when_old_workdir_is_gone(self):
        bundle, members = self.bundle('resume', zip_only=True)
        manifest = dict(run_token='token', case_tag='case', local_workDir=str(self.base / 'missing'),
                        input_sha256={'p000001': {k: hashlib.sha256(v).hexdigest() for k, v in members.items()}})
        root = {'RUN_MANIFEST': manifest, 'Cases': {'case': {'p000001': bundle}}}
        self.compact(root)
        disposable = (self.base / 'resume').resolve()
        self.assertEqual(disposable.parent, self.base.resolve())
        shutil.rmtree(disposable)  # Only the checked disposable fixture folder.
        saved = storage.result_view(root, db_api.run_cases(root))
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
        root['RUN_DB']['Jet'] = {case_id: case}
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
