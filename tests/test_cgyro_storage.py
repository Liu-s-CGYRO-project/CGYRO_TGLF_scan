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
reference_api = importlib.import_module('OMFITlib_cgyro_reference')


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

    def reference_scan(self, module, token):
        source = self.indexed_scan(module, token, 'BASE', values=(32,), ky_count=2)
        info = copy.deepcopy(source['__INFO__'])
        info['scan_dimensions'] = 0
        info['scan_axes'][0]['fixed'] = True
        result = {}
        archive_api.store_scan(result, source, info, source['__TASKS__'])
        return result

    def publisher(self):
        path = REPO / 'CGYRO_TGLF_scan/CGYRO_scan/SCRIPTS/CGYROScan.py'
        definitions = [node for node in ast.parse(path.read_text(encoding='utf-8')).body
                       if isinstance(node, ast.FunctionDef)]
        namespace = dict(copy=copy, datetime=datetime, timezone=timezone, OMFITtree=dict,
                         copy_result_tree=reference_api.copy_result_tree,
                         continuation_case=continuation.continuation_case,
                         point_result=continuation.point_result, save_current=queue_api.save_current,
                         compact_storage=storage.compact_storage, prune_storage=storage.prune_storage,
                         retire_superseded=storage.retire_superseded, reference_id=storage.reference_id,
                         store_result=storage.store_result, resolve_result=storage.resolve_result,
                         run_cases=db_api.run_cases, recover_archives=storage.recover_archives)
        for name in ('canonical_case_key', 'catalog_runs', 'clean_run_id', 'combine_cases',
                     'grouped_case_path', 'install_case', 'matching_cases', 'output_final_time',
                     'scan_key', 'store_scan', 'validate_preserved_scans'):
            namespace[name] = getattr(archive_api, name)
        exec(compile(ast.Module(body=definitions, type_ignores=[]), str(path), 'exec'), namespace)
        return namespace['publish_loaded_run']

    def browsable_expressions(self):
        class OMFITexpression:
            def __init__(self, *args):
                raise AssertionError('Native constructor would evaluate the output')
            def __getattr__(self, name):
                raise AssertionError('Browser expression unexpectedly evaluated: ' + name)
            def __deepcopy__(self, memo):
                raise AssertionError('Metadata operation copied/evaluated a browser expression')
        class OMFITiterableExpression(OMFITexpression):
            pass
        base = types.ModuleType('omfit_classes.omfit_base')
        base.OMFITiterableExpression = OMFITiterableExpression
        return patch.dict(sys.modules, {base.__name__: base})

    def result_readers(self):
        from collections import OrderedDict
        path = REPO / 'CGYRO_TGLF_scan/LIB/OMFITlib_cgyro_results.py'
        definitions = [node for node in ast.parse(path.read_text(encoding='utf-8')).body
                       if isinstance(node, ast.FunctionDef) and node.name in ('_stable_keys', '_run_options', '_result_node')]
        namespace = dict(OrderedDict=OrderedDict, catalog_runs=archive_api.catalog_runs,
                         latest_cases=archive_api.latest_cases, case_scans=archive_api.case_scans,
                         case_destination=archive_api.case_destination, legacy_branch=db_api.legacy_branch,
                         run_records=db_api.run_records, storage_state=storage.storage_state,
                         stopped_context=continuation.stopped_context,
                         resolve_result=storage.resolve_result, record_options=lambda records: dict(records))
        exec(compile(ast.Module(body=definitions, type_ignores=[]), str(path), 'exec'), namespace)
        return namespace

    def test_original_scans_move_out_of_base_and_only_reference_stays(self):
        root = {}
        theta = self.indexed_scan(root, 'base_theta', 'BASE', values=(16, 32), ky_count=2)
        energy = self.indexed_scan(root, 'base_energy', 'BASE', 'N_ENERGY', (8,), 2)
        reference = self.reference_scan(root, 'base_reference')
        group = {'BASE': archive_api.combine_cases([theta, energy, reference])}
        for ion in ('H', 'D', 'T'):
            group[ion] = self.indexed_scan(root, 'same_'+ion, ion, values=(16,), ky_count=1)
        root['RUN_DB']['Jet'] = {'nr=1_rho=0.33': group}
        owners = set(storage.result_pool(root))
        cid = theta['__INFO__']['case_id']
        self.assertEqual(archive_api.case_destination(root, 'Jet', cid, theta['__INFO__']),
                         ['Jet', 'nr=1_rho=0.33', 'BASE'])
        storage.consolidate_storage(root)
        group = root['RUN_DB']['Jet']['nr=1_rho=0.33']
        self.assertEqual({key for key in group if not key.startswith('__')},
                         {'N_THETA', 'N_ENERGY', 'BASE', 'H', 'D', 'T'})
        self.assertEqual(set(group['__SCANS__']), {'N_THETA', 'N_ENERGY'})
        self.assertEqual({key for key in group['BASE'] if not key.startswith('__')}, {'KY_ONLY'})
        case = archive_api.catalog_runs(root)['Jet'][cid]
        self.assertEqual(set(case['__SCANS__']), {'N_THETA', 'N_ENERGY', 'KY_ONLY'})
        self.assertNotIn('H', case)
        self.assertEqual(archive_api.case_destination(root, 'Jet', cid), ['Jet', 'nr=1_rho=0.33'])
        readers = self.result_readers()
        records, _ = readers['_run_options']({'CGYRO_scan': root})
        self.assertEqual(records['base_reference']['destination'], ['Jet', 'nr=1_rho=0.33', 'BASE'])
        self.assertEqual(records['base_theta']['destination'], ['Jet', 'nr=1_rho=0.33'])
        before = {}
        for scan, info, tasks in archive_api.case_scans(case):
            before[scan] = {archive_api.point_coordinate(row): continuation.point_result(case, row)
                            for row in tasks.values()}
            for row in tasks.values():
                self.assertIsInstance(readers['_result_node']({'CGYRO_scan': root}, records[info['run_token']], row), OMFITcgyro)
        storage.consolidate_storage(root)
        repeated = archive_api.catalog_runs(root)['Jet'][cid]
        self.assertEqual({scan: {archive_api.point_coordinate(row): continuation.point_result(repeated, row)
                                for row in tasks.values()} for scan, _, tasks in archive_api.case_scans(repeated)}, before)
        self.assertEqual(set(storage.result_pool(root)), owners)

    def test_ordinary_original_scan_without_reference_has_no_base_child(self):
        root = {}
        case = self.indexed_scan(root, 'original_only', 'BASE', values=(16,), ky_count=2)
        cid = case['__INFO__']['case_id']
        root['RUN_DB']['Jet'] = {'nr=1_rho=0.33': {'BASE': case}}
        storage.consolidate_storage(root)
        group = root['RUN_DB']['Jet']['nr=1_rho=0.33']
        self.assertNotIn('BASE', group)
        self.assertIn('N_THETA', group)
        self.assertEqual(archive_api.grouped_case_path(cid, case['__INFO__']), ['nr=1_rho=0.33'])
        self.assertEqual(archive_api.case_destination(root, 'Jet', cid), ['Jet', 'nr=1_rho=0.33'])

    def test_direct_layout_honors_native_mapping_get_update_contract(self):
        from omfit_mapping import OMFITMapping, treeify
        root = {}
        theta = self.indexed_scan(root, 'native_base', 'BASE', values=(16,), ky_count=1)
        reference = self.reference_scan(root, 'native_reference')
        root['RUN_DB']['Jet'] = {'nr=1_rho=0.33': {'BASE':archive_api.combine_cases([theta, reference])}}
        root = treeify(root, OMFITMapping)
        storage.recover_archives(root, storage.resolve_result, OMFITMapping)
        case = archive_api.catalog_runs(root)['Jet'][theta['__INFO__']['case_id']]
        self.assertEqual(set(case['__SCANS__']), {'N_THETA', 'KY_ONLY'})
        self.assertEqual(archive_api.case_destination(root, 'Jet', theta['__INFO__']['case_id'],
                                                    theta['__INFO__']), ['Jet', 'nr=1_rho=0.33'])
        self.assertIsInstance(root['RUN_DB']['Jet']['nr=1_rho=0.33'], OMFITMapping)

    def test_legacy_original_scan_suffix_resolves_before_migration(self):
        root = {}
        case = self.indexed_scan(root, 'base_suffix', 'BASE', values=(16,), ky_count=1)
        case['N_THETA_BASE'] = case.pop('N_THETA')
        for row in case['__TASKS__'].values():
            row['result_path'][0] = 'N_THETA_BASE'
        root['RUN_DB']['Jet'] = {'nr=1_rho=0.33': {'BASE':case}}
        cid = case['__INFO__']['case_id']
        self.assertEqual(archive_api.case_destination(root, 'Jet', cid, case['__INFO__']),
                         ['Jet', 'nr=1_rho=0.33', 'BASE'])
        storage.consolidate_storage(root)
        self.assertIn('N_THETA', root['RUN_DB']['Jet']['nr=1_rho=0.33'])
        self.assertNotIn('BASE', root['RUN_DB']['Jet']['nr=1_rho=0.33'])

    def test_unopened_base_metadata_migrates_without_losing_owners(self):
        root = {}
        case = self.indexed_scan(root, 'lazy_base', 'BASE', values=(16,), ky_count=1)
        group = {'BASE':OMFITlazyLoad(case)}
        root['RUN_DB']['Jet'] = {'nr=1_rho=0.33':OMFITlazyLoad(group)}
        owners = set(storage.result_pool(root))
        storage.consolidate_storage(root)
        self.assertIn('N_THETA', root['RUN_DB']['Jet']['nr=1_rho=0.33'])
        self.assertNotIn('BASE', root['RUN_DB']['Jet']['nr=1_rho=0.33'])
        self.assertEqual(set(storage.result_pool(root)), owners)

    def test_base_migration_abort_restores_old_catalog_and_references(self):
        root = {}
        case = self.indexed_scan(root, 'abort_base', 'BASE', values=(16,), ky_count=2)
        original = {'nr=1_rho=0.33': {'BASE':case}}
        class FailOnce(dict):
            fail = True
            def __setitem__(self, key, value):
                if key == 'Jet' and self.fail:
                    self.fail = False
                    raise KeyboardInterrupt('Abort during BASE migration')
                super().__setitem__(key, value)
        db = FailOnce(root['RUN_DB'])
        dict.__setitem__(db, 'Jet', original)
        root['RUN_DB'] = db
        owners = set(storage.result_pool(root))
        with self.assertRaises(KeyboardInterrupt):
            storage.recover_archives(root, storage.resolve_result)
        self.assertIs(db['Jet'], original)
        self.assertEqual(set(storage.result_pool(root)), owners)
        for row in case['__TASKS__'].values():
            self.assertIsInstance(storage.resolve_result(root, continuation.point_result(case, row)), OMFITcgyro)

    def test_mixed_old_base_and_direct_scan_consolidate_all_coordinates(self):
        root = {}
        direct = self.indexed_scan(root, 'direct_old', 'BASE', values=(16,), ky_count=2)
        nested = self.indexed_scan(root, 'nested_old', 'BASE', values=(32,), ky_count=2)
        group = dict(direct, BASE=nested)
        root['RUN_DB']['Jet'] = {'nr=1_rho=0.33': group}
        owners = set(storage.result_pool(root))
        with self.assertRaisesRegex(ValueError, 'consolidation'):
            archive_api.catalog_runs(root)
        storage.consolidate_storage(root)
        group = root['RUN_DB']['Jet']['nr=1_rho=0.33']
        self.assertNotIn('BASE', group)
        self.assertEqual(set(group['N_THETA']), {'16', '32'})
        self.assertEqual(len(group['__SCANS__']['N_THETA']['tasks']), 4)
        self.assertEqual(set(storage.result_pool(root)), owners)

    def test_actual_collection_keeps_direct_scans_reference_isotopes_and_new_ky(self):
        root, publish = {}, self.publisher()
        def collect(token, names, ky=.1, ion='BASE', reference=False):
            values = dict(zip(names, (16, 32, 48)))
            path = []
            for name in names:
                path.extend([name, str(values[name])])
            path.extend(['lin', str(ky)])
            axes = [dict(name=name, values=[values[name]], linked=[], fixed=reference) for name in names]
            root['RUN_MANIFEST'] = dict(run_token=token, status='loaded', collection_status='ready',
                dimensions=len(names), scan_dimensions=0 if reference else len(names), scan_axes=axes,
                case_tag='case', case_id='nr=1__rho=0.33__ion='+ion, nr=1, rho=.33, mass=ion, runid='Jet',
                workDir='/runs/'+token, server='fixture', points=['p000001'], loaded_points=['p000001'],
                point_table={'p000001':dict(values=dict(values, KY=ky), result_path=path)})
            root['Cases'] = {'case': {'p000001':self.result(token, token.encode())}}
            publish(root)
        collect('normal_theta', ['N_THETA'])
        collect('original_reference', ['N_THETA'], reference=True)
        collect('normal_two', ['N_ENERGY', 'N_XI'])
        collect('normal_three', ['N_ENERGY', 'N_XI', 'N_RADIAL'])
        collect('isotope_d', ['N_THETA'], ion='D')
        collect('normal_extra_ky', ['N_THETA'], ky=.2)
        group = root['RUN_DB']['Jet']['nr=1_rho=0.33']
        self.assertEqual(set(group['__SCANS__']), {'N_THETA', 'N_ENERGY__N_XI', 'N_ENERGY__N_XI__N_RADIAL'})
        self.assertEqual(set(group['BASE']['__SCANS__']), {'KY_ONLY'})
        self.assertEqual(set(group['D']['__SCANS__']), {'N_THETA'})
        self.assertEqual({row['values']['KY'] for row in group['__SCANS__']['N_THETA']['tasks'].values()}, {.1, .2})
        self.assertEqual(len(storage.result_pool(root)), 6)
        readers = self.result_readers()
        records, _ = readers['_run_options']({'CGYRO_scan':root})
        for token, entry in records.items():
            for row in entry.get('tasks', {}).values():
                self.assertIsInstance(readers['_result_node']({'CGYRO_scan':root}, entry, row), OMFITcgyro)
        for token in ('original_reference', 'normal_two', 'normal_three', 'isotope_d', 'normal_extra_ky'):
            _, _, view = continuation.archived_case(root, token)
            self.assertTrue(view['__TASKS__'])

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
        self.assertEqual(storage.storage_state(root)['case_layout'], 'radius-scans')
        self.assertEqual(storage.storage_state(root)['version'], 6)

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

    def test_nonfinite_final_time_cannot_replace_a_completed_coordinate(self):
        root = {}
        old = self.indexed_scan(root, 'finite_old', 'T', values=(16,), ky_count=1)
        new = self.indexed_scan(root, 'nonfinite_new', 'T', values=(16,), ky_count=1)
        old_row, new_row = old['__TASKS__']['p000001'], new['__TASKS__']['p000001']
        old_row.update(final_time=0, status='loaded', resume_pending=False)
        new_row.update(status='partial', resume_pending=True)
        branch, tasks = old['N_THETA'], old['__TASKS__']
        for value in (float('nan'), float('inf'), -float('inf')):
            with self.subTest(final_time=value):
                new_row['final_time'] = value
                with self.assertRaisesRegex(ValueError, 'Non-finite archived final time'):
                    archive_api.store_scan(old, new, new['__INFO__'], new['__TASKS__'])
                self.assertIs(old['N_THETA'], branch)
                self.assertIs(old['__TASKS__'], tasks)
                self.assertEqual(old_row['final_time'], 0)
        # A finite zero is a valid sample, not a missing-time sentinel.
        new_row.update(final_time=0, status='loaded', resume_pending=False)
        archive_api.store_scan(old, new, new['__INFO__'], new['__TASKS__'])
        self.assertEqual(old['__TASKS__']['p000001']['run_token'], 'nonfinite_new')

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

    def test_recovery_rollback_restores_other_catalogs_after_one_restore_fails(self):
        root = {}
        case = self.indexed_scan(root, 'recover_rollback', 'T', values=(16,), ky_count=1)
        cid = case['__INFO__']['case_id']
        original = {cid: case}
        other = self.indexed_scan(root, 'recover_other', 'D', values=(16,), ky_count=1)
        other['__INFO__']['runid'] = 'Other'
        original_other = {other['__INFO__']['case_id']: other}
        previous_state = root['RUN_DB'][db_api.STATE]
        previous_pending = {}
        original_abort = KeyboardInterrupt('Abort after recovery installation')
        class FailingDB(dict):
            def __setitem__(self, key, value):
                if key == 'Jet' and value is original:
                    raise OSError('Jet restoration rejected')
                super().__setitem__(key, value)
                if key == db_api.STATE and value is not previous_state:
                    raise original_abort
        db = FailingDB(root['RUN_DB'])
        dict.update(db, Jet=original, Other=original_other)
        dict.__setitem__(db, db_api.PENDING, previous_pending)
        root['RUN_DB'] = db
        with self.assertRaises(KeyboardInterrupt) as caught:
            storage.recover_archives(root, storage.resolve_result)
        self.assertIs(caught.exception, original_abort)
        self.assertIs(db['Other'], original_other)
        self.assertIs(db[db_api.STATE], previous_state)
        self.assertEqual(db[db_api.PENDING], previous_pending)
        self.assertIn('Jet restoration rejected', original_abort.cgyro_rollback_errors[0])
        # The replacement that could not be undone still resolves its owner.
        storage.resolve_result(root, db['Jet']['nr=1_rho=0.33']['T']['N_THETA']['16']['lin']['0.01'])

    def test_failed_renamed_archive_rollback_keeps_public_and_private_owners_reachable(self):
        for abort_stage in ('source_removal', 'state_assignment'):
            with self.subTest(abort_stage=abort_stage):
                root = {}
                case = self.indexed_scan(root, 'renamed_' + abort_stage, 'T', values=(16,), ky_count=1)
                private = storage.store_result(root, self.result('private_' + abort_stage, b'private'))
                case['__CUSTOM__'] = private
                original = {case['__INFO__']['case_id']: case}
                old_name = 'Jet [partial abcd]'
                previous_state = root['RUN_DB'][db_api.STATE]
                original_abort = KeyboardInterrupt('Abort after ' + abort_stage)

                class FailingDB(dict):
                    def __delitem__(self, key):
                        super().__delitem__(key)
                        if key == old_name and abort_stage == 'source_removal':
                            raise original_abort
                    def __setitem__(self, key, value):
                        if key == old_name and value is original:
                            raise OSError('old archive name restoration rejected')
                        super().__setitem__(key, value)
                        if key == db_api.STATE and value is not previous_state and abort_stage == 'state_assignment':
                            raise original_abort

                db = FailingDB(root['RUN_DB'])
                dict.__setitem__(db, old_name, original)
                dict.__setitem__(db, db_api.PENDING, {})
                root['RUN_DB'] = db
                with self.assertRaises(KeyboardInterrupt) as caught:
                    storage.recover_archives(root, storage.resolve_result)
                self.assertIs(caught.exception, original_abort)
                self.assertNotIn(old_name, db)
                result = db['Jet']['nr=1_rho=0.33']['T']['N_THETA']['16']['lin']['0.01']
                storage.resolve_result(root, result)
                self.assertIn(private, list(db[db_api.PENDING].values()))
                self.assertEqual(storage.prune_storage(root), 0)
                self.assertEqual(len(storage.result_pool(root)), 2)
                self.assertIn('old archive name restoration rejected', original_abort.cgyro_rollback_errors[0])

    def test_failed_pending_restore_keeps_its_new_public_archive_reachable(self):
        for after_write in (False, True):
            with self.subTest(after_write=after_write):
                root = {}
                case = self.indexed_scan(root, 'pending_restore_' + str(after_write), 'T', values=(16,), ky_count=1)
                previous_pending = {'legacy_case': case}
                previous_state = root['RUN_DB'][db_api.STATE]
                original_abort = KeyboardInterrupt('Abort after pending recovery')
                class FailingDB(dict):
                    def __setitem__(self, key, value):
                        if key == db_api.PENDING and value is previous_pending:
                            if after_write:
                                super().__setitem__(key, value)
                            raise OSError('old pending restoration rejected')
                        super().__setitem__(key, value)
                        if key == db_api.STATE and value is not previous_state:
                            raise original_abort
                db = FailingDB(root['RUN_DB'])
                dict.__setitem__(db, db_api.PENDING, previous_pending)
                root['RUN_DB'] = db
                with self.assertRaises(KeyboardInterrupt) as caught:
                    storage.recover_archives(root, storage.resolve_result)
                self.assertIs(caught.exception, original_abort)
                result = db['Jet']['nr=1_rho=0.33']['T']['N_THETA']['16']['lin']['0.01']
                storage.resolve_result(root, result)
                self.assertEqual(storage.prune_storage(root), 0)
                self.assertEqual(len(storage.result_pool(root)), 1)
                self.assertIn('old pending restoration rejected', original_abort.cgyro_rollback_errors[0])

    def test_first_pending_write_abort_keeps_its_source_before_public_installation(self):
        root = {}
        case = self.indexed_scan(root, 'pending_first_write', 'T', values=(16,), ky_count=1)
        previous_pending = {'legacy_case': case}
        original_abort = KeyboardInterrupt('Abort after transitional pending assignment')
        class FailingDB(dict):
            def __setitem__(self, key, value):
                if key == db_api.PENDING:
                    if value is previous_pending:
                        raise OSError('old pending restoration rejected')
                    super().__setitem__(key, value)
                    raise original_abort
                super().__setitem__(key, value)
        db = FailingDB(root['RUN_DB'])
        dict.__setitem__(db, db_api.PENDING, previous_pending)
        root['RUN_DB'] = db
        with self.assertRaises(KeyboardInterrupt) as caught:
            storage.recover_archives(root, storage.resolve_result)
        self.assertIs(caught.exception, original_abort)
        self.assertNotIn('Jet', db)
        self.assertIs(db[db_api.PENDING]['legacy_case'], case)
        self.assertEqual(storage.prune_storage(root), 0)
        self.assertEqual(len(storage.result_pool(root)), 1)
        self.assertIn('old pending restoration rejected', original_abort.cgyro_rollback_errors[0])

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

    def test_freeze_preserves_submission_script_when_target_assignment_aborts(self):
        for error_type, after_write in ((KeyboardInterrupt, False), (KeyboardInterrupt, True),
                                       (OSError, False), (OSError, True)):
            with self.subTest(error_type=error_type.__name__, after_write=after_write):
                original_error = error_type('frozen input assignment interrupted')
                class RejectInput(dict):
                    def __setitem__(self, key, value):
                        if after_write:
                            super().__setitem__(key, value)
                        raise original_error
                manifest = dict(run_token='freeze')
                script = OMFITpath(self.base / 'scan.pbs')
                Path(script.filename).write_text('#!/bin/bash\n', encoding='utf-8')
                cases, inputs = {'scan.pbs': script}, RejectInput()
                root = {'RUN_DB': {db_api.STATE: dict(version=db_api.STORAGE_SCHEMA_VERSION),
                    db_api.RUNS: {'freeze': dict(manifest=manifest, cases=cases, inputs=inputs)}}}
                with self.assertRaises(error_type) as caught:
                    db_api.freeze_run_inputs(root, manifest)
                self.assertIs(caught.exception, original_error)
                self.assertIs(cases['scan.pbs'], script)
                self.assertEqual(inputs, {'scan.pbs': script} if after_write else {})

    def test_successful_freeze_moves_script_without_copying_it(self):
        manifest = dict(run_token='freeze')
        script = OMFITpath(self.base / 'scan.pbs')
        record = dict(manifest=manifest, cases={'scan.pbs': script})
        root = {'RUN_DB': {db_api.STATE: dict(version=db_api.STORAGE_SCHEMA_VERSION),
                          db_api.RUNS: {'freeze': record}}}
        db_api.freeze_run_inputs(root, manifest)
        self.assertEqual(record['cases'], {})
        self.assertEqual(set(record['inputs']), {'scan.pbs'})
        self.assertIs(record['inputs']['scan.pbs'], script)

    def test_freeze_keeps_destination_if_source_removal_aborts(self):
        original_abort = KeyboardInterrupt('source removal interrupted')
        class AbortOnRemoval(dict):
            def pop(self, key, *args):
                super().pop(key, *args)
                raise original_abort
        manifest = dict(run_token='freeze')
        script = OMFITpath(self.base / 'scan.pbs')
        cases = AbortOnRemoval({'scan.pbs': script})
        record = dict(manifest=manifest, cases=cases)
        root = {'RUN_DB': {db_api.STATE: dict(version=db_api.STORAGE_SCHEMA_VERSION),
                          db_api.RUNS: {'freeze': record}}}
        with self.assertRaises(KeyboardInterrupt) as caught:
            db_api.freeze_run_inputs(root, manifest)
        self.assertIs(caught.exception, original_abort)
        self.assertIs(record['inputs']['scan.pbs'], script)

    def test_freeze_missing_token_does_not_create_a_placeholder_run(self):
        root = {}
        with self.assertRaisesRegex(ValueError, 'Missing frozen CGYRO run token'):
            db_api.freeze_run_inputs(root, {})
        self.assertEqual(root, {})

    def test_retired_snapshot_rejects_stale_current_and_history_dialogs(self):
        manifest = dict(run_token='retired', collection_status='partial')
        root = dict(RUN_MANIFEST=manifest, RUN_DB={db_api.RUNS: {
            'retired': dict(manifest=manifest, payload_retired=True)}})
        # The current-view shortcut must not bypass the authoritative tombstone.
        with patch.object(continuation, 'result_view', side_effect=AssertionError('resolved retired payload')):
            for current in (manifest, dict(run_token='newer')):
                root['RUN_MANIFEST'] = current
                with self.subTest(current=current['run_token']):
                    with self.assertRaisesRegex(ValueError, 'superseded.*retired'):
                        continuation.saved_run(root, 'retired')

    def test_stopped_child_rejects_retired_ancestor_instead_of_guessing_public_ids(self):
        child = dict(run_token='child', collection_status='partial',
                     continuation=dict(source_token='ancestor'))
        root = dict(RUN_MANIFEST=child, RUN_DB={db_api.RUNS: {
            'child': dict(manifest=child),
            'ancestor': dict(manifest=dict(run_token='ancestor'), payload_retired=True)}})
        with self.assertRaisesRegex(ValueError, 'superseded.*retired'):
            continuation.stopped_context(root, 'child')

    def test_retired_snapshot_cannot_be_reactivated_recollected_or_refrozen(self):
        retry = importlib.import_module('OMFITlib_cgyro_retry')
        manifest = dict(run_token='retired', status='failed', collection_status='partial', batch_id='batch')
        root = dict(RUN_MANIFEST=copy.deepcopy(manifest), RUN_DB={db_api.STATE: {'version': 4},
            db_api.RUNS: {'retired': dict(manifest=copy.deepcopy(manifest), payload_retired=True)}},
            RUN_HISTORY={'retired': {'manifest': copy.deepcopy(manifest)}},
            RUN_BATCH=dict(batch_id='batch', tokens=['retired']))
        original = copy.deepcopy(root)
        with patch.object(queue_api, 'compact_storage', side_effect=AssertionError('compacted retired input')), \
                patch.object(queue_api, 'freeze_run_inputs', side_effect=AssertionError('refroze retired input')):
            queue_api.save_current(root)
        for action in (lambda: queue_api.activate_run(root, 'retired'),
                       lambda: retry.collect_current(root, None, dict, None, None)):
            with self.assertRaisesRegex(ValueError, 'superseded.*retired'):
                action()
        self.assertEqual(root, original)

    def test_batch_collection_skips_retired_snapshot_and_reads_other_case(self):
        workflow = importlib.import_module('OMFITlib_cgyro_workflow')
        old = dict(run_token='old', status='failed', collection_status='partial',
                   batch_id='batch', case_id='old_case', job_id='1')
        current = dict(run_token='current', status='failed', collection_status='partial',
                       batch_id='batch', case_id='current_case', job_id='2')
        setup = dict(irun=1, idownsync=0)
        root = dict(SETTINGS=dict(SETUP=setup), RUN_MANIFEST=old,
            RUN_HISTORY={'old': {'manifest': old}, 'current': {'manifest': current}},
            RUN_BATCH=dict(batch_id='batch', tokens=['old', 'current'], case_ids=['old_case', 'current_case']),
            RUN_DB={db_api.STATE: {'version': 4}, db_api.RUNS: {
                'old': dict(manifest=old, payload_retired=True), 'current': dict(manifest=current)}})
        calls = []
        def run_script(title, name, **kwargs):
            calls.append((root['RUN_MANIFEST']['run_token'], name, kwargs))
        with patch.object(workflow, 'save_current'):
            workflow.collect_batch(root, run_script)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], 'current')
        self.assertEqual(calls[0][1], 'CGYROScan.py')
        self.assertIs(calls[0][2]['allow_solver_retries'], False)
        self.assertEqual(setup, dict(irun=1, idownsync=0))

    def test_indexed_bookkeeping_does_not_recopy_or_replace_storage_metadata(self):
        root = {}
        ref = storage.store_result(root, self.result('stable_index'))
        root['RUN_DB']['Jet'] = {'point': ref}
        first = storage.compact_storage(root)
        state = storage.storage_state(root)
        with patch.object(storage, 'deepcopy', side_effect=AssertionError('copied unchanged storage state')), \
                patch.object(storage, 'archive_inventory', side_effect=AssertionError('read indexed result files')):
            second = storage.compact_storage(root)
        self.assertIs(storage.storage_state(root), state)
        self.assertEqual(second, first)

        # A later legacy import must invalidate the no-change path naturally;
        # no persistent "already compacted" marker may suppress its conversion.
        root['RUN_DB']['Jet']['new_point'] = self.result('imported_after_indexing', b'new spectrum')
        report = storage.compact_storage(root)
        self.assertEqual(report['converted_copies'], 1)
        self.assertEqual(report['physical_results'], 2)
        self.assertIsNotNone(storage.reference_id(root['RUN_DB']['Jet']['new_point']))

    def test_prune_abort_restores_result_and_file_owners_with_size_metadata(self):
        class AbortAfterDelete(dict):
            armed = True
            def __delitem__(self, key):
                super().__delitem__(key)
                if self.armed:
                    self.armed = False
                    raise KeyboardInterrupt('after owner deletion')
        class AbortAfterPop(dict):
            armed = True
            def pop(self, key, default=None):
                result = super().pop(key, default)
                if self.armed:
                    self.armed = False
                    raise KeyboardInterrupt('after file-size deletion')
                return result
        for stage in ('owner', 'file-size'):
            with self.subTest(stage=stage):
                root = {}
                retained = storage.store_result(root, self.result('live_' + stage, b'live'))
                storage.store_result(root, self.result('stale_' + stage, b'stale'))
                root['RUN_DB']['Jet'] = {'point': retained}
                pool, state = storage.result_pool(root), storage.storage_state(root)
                packed = self.base / ('orphan_' + stage + '.zip')
                packed.write_bytes(b'orphan input')
                digest = hashlib.sha256(packed.read_bytes()).hexdigest()
                pool[files.FILE_STORE] = {digest: OMFITpath(packed)}
                state['file_bytes'] = {digest: packed.stat().st_size}
                if stage == 'owner':
                    root['RUN_DB'][db_api.POOL] = pool = AbortAfterDelete(pool)
                else:
                    state['file_bytes'] = AbortAfterPop(state['file_bytes'])
                owners = dict(pool)
                file_owners = dict(pool[files.FILE_STORE])
                metadata = copy.deepcopy(dict(state))
                with self.assertRaises(KeyboardInterrupt):
                    storage.prune_storage(root)
                for key, owner in owners.items():
                    self.assertIs(pool[key], owner)
                self.assertEqual(pool[files.FILE_STORE], file_owners)
                self.assertEqual(dict(state), metadata)
                self.assertTrue(packed.is_file())
                self.assertEqual(storage.prune_storage(root), 2)
                self.assertIsNotNone(storage.resolve_result(root, retained))
                self.assertTrue(packed.is_file())

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
                         copy_result_tree=reference_api.copy_result_tree,
                         continuation_case=continuation.continuation_case,
                         point_result=continuation.point_result, save_current=queue_api.save_current,
                         compact_storage=storage.compact_storage, prune_storage=storage.prune_storage,
                         store_result=storage.store_result, resolve_result=storage.resolve_result,
                         retire_superseded=storage.retire_superseded, reference_id=storage.reference_id,
                         run_cases=db_api.run_cases, recover_archives=storage.recover_archives)
        for name in ('canonical_case_key', 'catalog_runs', 'clean_run_id', 'combine_cases', 'grouped_case_path', 'install_case', 'matching_cases', 'output_final_time', 'scan_key', 'store_scan', 'validate_preserved_scans'):
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

    def test_browsable_publisher_retains_prior_h_energy_point_when_new_ky_is_collected(self):
        # Reproduce the user's (8, 0.1) failure through the real publisher.
        # Browser expressions are different objects after each index rebuild;
        # their identities are not the identity of the scientific result.
        root, publish = {}, self.publisher()
        def collect(token, ky):
            root['RUN_MANIFEST'] = dict(run_token=token, status='loaded', collection_status='ready',
                dimensions=1, scan_axes=[dict(name='N_ENERGY', values=[8], linked=[])],
                case_tag='case', case_id='nr=1__rho=0.33__ion=H', nr=1, rho=.33, mass='H', runid='Jet',
                workDir='/runs/' + token, server='fixture', points=['p000001'], loaded_points=['p000001'],
                point_table={'p000001': dict(values={'N_ENERGY': 8, 'KY': ky},
                                            result_path=['N_ENERGY', '8', 'lin', str(ky)])})
            root['Cases'] = {'case': {'p000001': self.result(token, token.encode())}}
            publish(root)
        with self.browsable_expressions():
            collect('browsable_h_old', .1)
            old = archive_api.catalog_runs(root)['Jet']['nr=1__rho=0.33__ion=H']
            original = storage.reference_id(old['N_ENERGY']['8']['lin']['0.1'])
            collect('browsable_h_new', .2)
            case = archive_api.catalog_runs(root)['Jet']['nr=1__rho=0.33__ion=H']
            self.assertEqual(len(case['__TASKS__']), 2)
            self.assertEqual(storage.reference_id(case['N_ENERGY']['8']['lin']['0.1']), original)
            self.assertEqual({row['values']['KY'] for row in case['__TASKS__'].values()}, {.1, .2})

    def test_browsable_retention_preserves_signed_ky_for_one_two_and_three_axes(self):
        with self.browsable_expressions():
            for dimensions in (1, 2, 3):
                with self.subTest(dimensions=dimensions):
                    names = ['N_ENERGY', 'N_XI', 'N_THETA'][:dimensions]
                    axes = [dict(name=n, values=[v], linked=[]) for n, v in zip(names, (8, 16, 32))]
                    def case(token, ky, digest):
                        path = [item for pair in zip(names, ('8', '16', '32')) for item in pair] + ['lin', str(ky)]
                        payload = {}
                        node = payload
                        for part in path[:-1]:
                            node = node.setdefault(part, {})
                        node[path[-1]] = reference_api.make_reference(digest)
                        info = dict(run_token=token, scan_axes=axes, parameters=[names[0]], dimensions=dimensions)
                        rows = {'p000001': dict(result_path=path, run_token=token)}
                        result = {}
                        archive_api.store_scan(result, payload, info, rows)
                        return result
                    old = case('old', .1, 'a' * 64)
                    incoming = case('incoming', -.1, 'b' * 64)
                    merged = archive_api.combine_cases([old])
                    archive_api.store_scan(merged, incoming, incoming['__INFO__'], incoming['__TASKS__'])
                    key = archive_api.scan_key(incoming['__INFO__'])
                    archive_api.validate_preserved_scans([old], merged, key, incoming['__TASKS__'])
                    self.assertEqual(len(merged['__TASKS__']), 2)
                    preserved = next(row for row in merged['__TASKS__'].values() if row['run_token'] == 'old')
                    self.assertEqual(archive_api.point_coordinate(preserved)[1][-1], .1)
                    # A different owner at an unchanged coordinate must still
                    # be rejected; ignoring the browser link cannot waive it.
                    node = merged
                    for part in preserved['result_path'][:-1]:
                        node = node[part]
                    node[preserved['result_path'][-1]] = reference_api.make_reference('c' * 64)
                    with self.assertRaisesRegex(ValueError, 'prior parameter/ky'):
                        archive_api.validate_preserved_scans([old], merged, key, incoming['__TASKS__'])

    def test_retention_guard_checks_payload_identity_in_other_parameter_scans(self):
        root = {}
        old = self.indexed_scan(root, 'kept_axis', 'H', values=(16,), ky_count=1)
        incoming = self.indexed_scan(root, 'new_axis', 'H', name='N_ENERGY', values=(8,), ky_count=1)
        with self.browsable_expressions():
            merged = archive_api.combine_cases([old])
            archive_api.store_scan(merged, incoming, incoming['__INFO__'], incoming['__TASKS__'])
            archive_api.validate_preserved_scans([old], merged, 'N_ENERGY', incoming['__TASKS__'])
            merged['N_THETA']['16']['lin']['0.01'] = reference_api.make_reference('d' * 64)
            with self.assertRaisesRegex(ValueError, 'retained scan'):
                archive_api.validate_preserved_scans([old], merged, 'N_ENERGY', incoming['__TASKS__'])

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

    def test_temp_limit_is_only_checked_at_operation_start(self):
        (self.base / 'existing').write_bytes(b'x' * 90)
        report = scratch.space_report(self.base, tmp_root=self.base)
        self.assertEqual(report['used_bytes'], 90)
        with patch.object(scratch, 'space_report', return_value=report), patch.object(scratch, 'LIMIT_BYTES', 100):
            scratch.check_start_capacity(self.base)
            # This run may temporarily pass its initial usage limit.
            scratch.ensure_capacity(self.base, 11)
            report['used_bytes'] = 101
            with self.assertRaisesRegex(RuntimeError, '100 GiB'):
                scratch.check_start_capacity(self.base)
        self.assertEqual((self.base / 'existing').read_bytes(), b'x' * 90)

    def test_84_point_preparation_checks_free_space_without_full_temp_walks(self):
        with patch.object(scratch, 'directory_bytes', side_effect=AssertionError('Repeated /tmp walk')):
            for number in range(84):
                report = scratch.ensure_capacity(self.base / ('p%06d.zip' % number), 1024)
                self.assertIsNone(report['used_bytes'])
                self.assertFalse(report['start_limit_applied'])

    def test_runtime_free_space_failure_does_not_remove_existing_results(self):
        original = self.base / 'previous-result'
        original.write_bytes(b'unchanged')
        with patch.object(scratch.shutil, 'disk_usage', return_value=types.SimpleNamespace(free=4)):
            with self.assertRaisesRegex(RuntimeError, 'Insufficient free space'):
                scratch.ensure_capacity(self.base / 'next-copy', 5)
        self.assertEqual(original.read_bytes(), b'unchanged')

    def test_hdt_batch_requests_start_limit_only_for_first_case(self):
        path = REPO / 'CGYRO_TGLF_scan/LIB/OMFITlib_project.py'
        project_class = next(node for node in ast.parse(path.read_text(encoding='utf-8')).body
                             if isinstance(node, ast.ClassDef) and node.name == 'ProjectActions')
        method = next(node for node in project_class.body if isinstance(node, ast.FunctionDef) and node.name == 'run_cgyro')
        scope = dict(copy=copy, MODULES={'cgyro': ('CGYRO_scan',)},
                     module=lambda root, name: root['CGYRO_scan'],
                     cgyro_input_issues=lambda root: [], runtime_issues=lambda root, code: [],
                     retry_limit=lambda node: 0, pending_runs=lambda node: [],
                     uuid=types.SimpleNamespace(uuid4=lambda: types.SimpleNamespace(hex='c' * 32)))
        exec(compile(ast.Module(body=[method], type_ignores=[]), str(path), 'exec'), scope)
        plan = [dict(nr=1, rho=.33, ion_case=ion, case_id='nr=1__rho=0.33__ion=' + ion) for ion in 'HDT']
        node = dict(SETTINGS=dict(SETUP=dict(icgyro=1, idimrun=1, irun=0, idownsync=1),
                                 PHYSICS=dict(restart_mode=0),
                                 REMOTE_SETUP=dict(serverPicker='cluster', cluster=dict(scheduler='slurm'))),
                    INPUTS={}, BATCH_INPUTS={'1': {ion: types.SimpleNamespace(duplicate=lambda: {}) for ion in 'HDT'}})
        calls = []
        class Harness:
            factory = dict
            root = {'CGYRO_scan': node}
            settings = {}
            def prepare_cgyro_batch(self, install_first=False):
                return plan
            def _record(self, *args, **kwargs):
                return dict(kwargs)
            def call(self, title, path, **kwargs):
                calls.append(kwargs)
                node['RUN_MANIFEST'] = dict(status='submitted', stop_requested=False)
            def _collect_cgyro_queue(self, automatic=False):
                return [item['case_id'] for item in plan]
        scope['run_cgyro'](Harness())
        self.assertEqual([call['check_temp_start'] for call in calls], [True, False, False])
        self.assertEqual(node['SETTINGS']['SETUP']['irun'], 0)
        self.assertEqual(node['SETTINGS']['SETUP']['idownsync'], 1)
        self.assertNotIn('input.cgyro', node['INPUTS'])

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

    def test_layout_rollback_restores_other_branches_after_state_restore_fails(self):
        cases = {'case': {'point': self.result('layout_rollback')}}
        previous_state = {'version': 0}
        original_abort = KeyboardInterrupt('Abort after removing legacy Cases')

        class RejectStateRestore(dict):
            def __setitem__(self, key, value):
                if key == db_api.STATE and value is previous_state:
                    raise OSError('state restore rejected')
                super().__setitem__(key, value)

        class AbortAfterRemoval(dict):
            def pop(self, key, *args):
                value = super().pop(key, *args)
                if key == 'Cases':
                    raise original_abort
                return value

        db = RejectStateRestore({db_api.STATE: previous_state})
        history = {'old': {'manifest': {'status': 'published'}}}
        root = AbortAfterRemoval(RUN_DB=db, Cases=cases, RUN_HISTORY=history)
        with self.assertRaises(KeyboardInterrupt) as caught:
            db_api.ensure_layout(root)
        self.assertIs(caught.exception, original_abort)
        self.assertIs(root['Cases'], cases)
        self.assertIs(root['RUN_HISTORY'], history)
        self.assertNotIn(db_api.LEGACY, db)
        self.assertNotIn(db_api.RUNS, db)
        self.assertIn('state restore rejected', original_abort.cgyro_rollback_errors[0])

    def test_migration_rejects_different_same_token_snapshots_before_writing(self):
        for source in ('RUN_HISTORY', 'Cases'):
            with self.subTest(source=source):
                original = {'p000001': {reference_api.REF: 'a' * 64}}
                incoming = {'p000002': {reference_api.REF: 'b' * 64}}
                manifest = dict(run_token='same', case_tag='case')
                record = dict(manifest=manifest, cases=original)
                db = {db_api.STATE: dict(version=db_api.STORAGE_SCHEMA_VERSION),
                      db_api.RUNS: {'same': record}}
                root = dict(RUN_DB=db, RUN_MANIFEST=manifest)
                old_source = ({'same': dict(manifest=manifest, cases=incoming)} if source == 'RUN_HISTORY'
                              else {'case': incoming})
                root[source] = old_source
                with self.assertRaisesRegex(ValueError, 'Conflicting CGYRO case snapshots'):
                    db_api.ensure_layout(root)
                self.assertIs(root['RUN_DB'], db)
                self.assertIs(db[db_api.RUNS]['same'], record)
                self.assertIs(record['cases'], original)
                self.assertIs(root[source], old_source)

    def test_migration_accepts_equivalent_reference_snapshots_without_loading(self):
        original = {'p000001': {reference_api.REF: 'a' * 64}}
        incoming = copy.deepcopy(original)
        manifest = dict(run_token='same', case_tag='case')
        root = dict(RUN_DB={db_api.STATE: dict(version=db_api.STORAGE_SCHEMA_VERSION),
                            db_api.RUNS: {'same': dict(manifest=manifest, cases=original)}},
                    RUN_MANIFEST=manifest,
                    RUN_HISTORY={'same': dict(manifest=manifest, cases=incoming)},
                    Cases={'case': copy.deepcopy(original)})
        db_api.ensure_layout(root)
        self.assertEqual(db_api.run_cases(root), original)
        self.assertNotIn('Cases', root)
        self.assertNotIn('cases', root['RUN_HISTORY']['same'])

    def test_compaction_rollback_preserves_new_owners_if_branch_restore_fails(self):
        for reject_restore in (False, True):
            with self.subTest(reject_restore=reject_restore):
                first = {'result': self.result('compact_first_' + str(reject_restore), b'first')}
                second = {'result': self.result('compact_second_' + str(reject_restore), b'second')}
                previous_state = dict(version=db_api.STORAGE_SCHEMA_VERSION,
                                      checkpoint_policy=storage.CHECKPOINT_POLICY_VERSION)
                original_abort = KeyboardInterrupt('Abort after compaction state assignment')

                class FailingDB(dict):
                    def __setitem__(self, key, value):
                        if key == 'Jet' and value is first and reject_restore:
                            raise OSError('public branch restore rejected')
                        super().__setitem__(key, value)
                        if key == db_api.STATE and value is not previous_state:
                            raise original_abort

                db = FailingDB(Jet=first, Other=second)
                dict.__setitem__(db, db_api.STATE, previous_state)
                root = {'RUN_DB': db}
                with self.assertRaises(KeyboardInterrupt) as caught:
                    storage.compact_storage(root)
                self.assertIs(caught.exception, original_abort)
                self.assertIs(db['Other'], second)
                self.assertIs(db[db_api.STATE], previous_state)
                if reject_restore:
                    owned = storage.resolve_result(root, db['Jet']['result'])
                    self.assertEqual((Path(owned.filename) / 'out.cgyro.freq').read_bytes(), b'first')
                    self.assertIn('public branch restore rejected', original_abort.cgyro_rollback_errors[0])
                else:
                    self.assertIs(db['Jet'], first)
                    self.assertEqual(storage.result_pool(root), {})

    def test_layout_keeps_migrated_payload_if_original_location_cannot_be_restored(self):
        result = self.result('migration_remaining_owner')
        cases = {'case': {'point': result}}
        original_abort = KeyboardInterrupt('Abort after removing the original owner')

        class RejectOriginalRestore(dict):
            def pop(self, key, *args):
                value = super().pop(key, *args)
                if key == 'Cases':
                    raise original_abort
                return value
            def __setitem__(self, key, value):
                if key == 'Cases':
                    raise OSError('original location is not writable')
                super().__setitem__(key, value)

        root = RejectOriginalRestore(Cases=cases)
        with self.assertRaises(KeyboardInterrupt) as caught:
            db_api.ensure_layout(root)
        self.assertIs(caught.exception, original_abort)
        self.assertNotIn('Cases', root)
        retained = root['RUN_DB'][db_api.LEGACY]['Cases']['case']['point']
        self.assertIs(retained, result)
        self.assertTrue(Path(retained.filename).is_dir())
        self.assertIn('original location is not writable', original_abort.cgyro_rollback_errors[0])

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

    def test_browsable_reference_never_evaluates_during_metadata_operations(self):
        root = {}
        plain = storage.store_result(root, self.result('browse'))
        key = plain['__RESULT_REF__']
        root['RUN_DB']['Jet'] = {'point': plain}
        with self.browsable_expressions():
            with patch.object(storage, 'archive_inventory', side_effect=AssertionError('Must not reread output')):
                storage.compact_storage(root, browse=True)
            ref = root['RUN_DB']['Jet']['point']
            self.assertEqual(set(ref), {'__RESULT_REF__', 'data'})
            self.assertEqual(storage.reference_id(ref), key)
            self.assertIs(storage.result_view(root, ref), storage.result_pool(root)[key])
            self.assertEqual(storage.prune_storage(root), 0)
            storage.clean_staging(root)
            native = db_api._native(ref, dict)
            self.assertEqual(storage.reference_id(native), key)
            db_api._rebind(native)
            destination = {}
            archive_api._install_point(destination, ['N_THETA', '16', 'lin', '0.1'], ref, dict)
            self.assertEqual(storage.reference_id(destination['N_THETA']['16']['lin']['0.1']), key)
            updater = migration.ArchiveIndex()
            updater.cgyro_pool = storage.result_pool(root)
            self.assertTrue(updater.cgyro_payload(ref))
            updater.check()

    def test_copy_result_tree_preserves_metadata_and_native_owner_semantics(self):
        from omfit_mapping import OMFITMapping
        class Metadata(dict):
            pass
        owner_copies = []
        class Reader(OMFITcgyro):
            def __deepcopy__(self, memo):
                owner_copies.append(self)
                return Reader(self.filename)
        with self.browsable_expressions():
            ref = reference_api.make_reference('a' * 64)
            reader = Reader(self.base)
            metadata = Metadata({'/runs/input.cgyro': [1, 2]})
            source = {'points': [ref, (ref,)], 'metadata': metadata, 'reader': reader}
            result = reference_api.copy_result_tree(OMFITlazyLoad(source), OMFITMapping)
            self.assertIsInstance(result, OMFITMapping)
            self.assertIsInstance(result['metadata'], Metadata)
            result['metadata']['/runs/input.cgyro'].append(3)
            self.assertEqual(metadata['/runs/input.cgyro'], [1, 2])
            self.assertEqual(owner_copies, [reader])
            self.assertIsInstance(result['reader'], Reader)
            self.assertIsNot(result['reader'], reader)
            copied = result['points'][0]
            self.assertEqual(storage.reference_id(copied), 'a' * 64)
            self.assertIsNot(copied['data'], ref['data'])
            self.assertIs(copied, result['points'][1][0])
            with self.assertRaisesRegex(ValueError, 'Invalid CGYRO result reference'):
                reference_api.copy_result_tree({'point': dict(ref, unexpected=123)})

    def test_result_view_preserves_custom_reads_and_isolates_metadata(self):
        reads = []
        class CountedPoint(dict):
            def __getitem__(self, key):
                if key == 'balloon':
                    reads.append(key)
                return super().__getitem__(key)
        source = {'metadata': {'values': [1]}, 'point': CountedPoint(balloon={'phi': [2]})}
        view = storage.result_view({}, source)
        self.assertEqual(reads, [])
        self.assertIsInstance(view['point'], CountedPoint)
        view['metadata']['values'].append(3)
        view['point']['balloon']['phi'].append(4)
        self.assertEqual(reads, ['balloon'])
        self.assertEqual(source['metadata']['values'], [1])
        self.assertEqual(dict.__getitem__(source['point'], 'balloon')['phi'], [2])

    def test_mixed_compaction_copies_existing_reference_branch_without_reading_owner(self):
        with self.browsable_expressions():
            root = {}
            ref = storage.store_result(root, self.result('mixed_indexed'))
            key, owner = storage.reference_id(ref), storage.resolve_result(root, ref)
            raw = self.result('mixed_raw', b'new spectrum')
            root['RUN_DB']['Jet'] = {'indexed': {'point': ref}, 'imported': raw}
            with patch.object(storage, 'archive_inventory', wraps=storage.archive_inventory) as inventory:
                report = storage.compact_storage(root)
            self.assertEqual(inventory.call_count, 1)
            self.assertEqual(inventory.call_args.args, (raw.filename,))
            self.assertEqual(report['physical_results'], 2)
            self.assertEqual(storage.reference_id(root['RUN_DB']['Jet']['indexed']['point']), key)
            self.assertIs(storage.result_pool(root)[key], owner)

    def test_unindexed_archive_combination_rebuilds_browsable_reference(self):
        with self.browsable_expressions():
            ref = reference_api.make_reference('b' * 64)
            combined = archive_api.combine_cases([{'legacy': {'lin': {'0.1': ref}}}])
            copied = combined['legacy']['lin']['0.1']
            self.assertEqual(storage.reference_id(copied), 'b' * 64)
            self.assertIsNot(copied['data'], ref['data'])

    def test_publication_of_browsable_points_keeps_one_owner(self):
        root, publish = {}, self.publisher()
        root['RUN_MANIFEST'] = dict(run_token='publish_browse', status='loaded', collection_status='ready',
            dimensions=1, scan_dimensions=1, scan_axes=[dict(name='N_THETA', values=[16], linked=[])],
            case_tag='case', case_id='nr=1__rho=0.33__ion=T', nr=1, rho=.33, mass='T', runid='Jet',
            workDir='/runs/publish_browse', server='fixture', points=['p000001'], loaded_points=['p000001'],
            point_table={'p000001': dict(values={'N_THETA': 16, 'KY': .1},
                                         result_path=['N_THETA', '16', 'lin', '0.1'])})
        with self.browsable_expressions():
            ref = storage.store_result(root, self.result('publish_browse'))
            db_api.set_run_cases(root, root['RUN_MANIFEST'], {'p000001': ref})
            owner = storage.resolve_result(root, ref)
            publish(root)
            case = archive_api.catalog_runs(root)['Jet']['nr=1__rho=0.33__ion=T']
            saved = case['N_THETA']['16']['lin']['0.1']
            self.assertEqual(storage.reference_id(saved), storage.reference_id(ref))
            self.assertEqual(len(storage.result_pool(root)), 1)
            self.assertIs(storage.resolve_result(root, saved), owner)
            self.assertEqual(root['RUN_MANIFEST']['status'], 'published')

    def test_collection_abort_restores_browsable_partial_point(self):
        retry = importlib.import_module('OMFITlib_cgyro_retry')
        root = {'RUN_MANIFEST': dict(run_token='partial_browse', case_tag='case',
                                    status='loaded', collection_status='partial')}
        with self.browsable_expressions():
            ref = storage.store_result(root, self.result('partial_browse'))
            db_api.set_run_cases(root, root['RUN_MANIFEST'], {'p000001': ref})
            owner = storage.resolve_result(root, ref)
            def abort_read():
                db_api.run_cases(root).clear()
                root['RUN_MANIFEST']['collection_status'] = 'incomplete'
                raise KeyboardInterrupt('Aborted collection')
            root['SCRIPTS'] = {'downsync.py': types.SimpleNamespace(run=abort_read)}
            with self.assertRaisesRegex(KeyboardInterrupt, 'Aborted collection'):
                retry.collect_current(root, None, dict, None, None)
            restored = db_api.run_cases(root)['p000001']
            self.assertEqual(root['RUN_MANIFEST']['collection_status'], 'partial')
            self.assertEqual(storage.reference_id(restored), storage.reference_id(ref))
            self.assertIsNot(restored['data'], ref['data'])
            self.assertIs(storage.resolve_result(root, restored), owner)
            self.assertEqual(len(storage.result_pool(root)), 1)

    def test_reference_rejects_modified_browser_expression_or_extra_payload(self):
        class OMFITexpression:
            def __init__(self, code):
                self.expression = code
        root = {}
        plain = storage.store_result(root, self.result('bad-browse'))
        key = plain['__RESULT_REF__']
        updater = migration.ArchiveIndex()
        updater.cgyro_pool = storage.result_pool(root)
        for extra in ({'data': OMFITexpression("root['RUN_DB'].clear()")},
                      {'data': storage.result_pool(root)[key]},
                      {'unexpected': 123}):
            broken = dict(plain, **extra)
            with self.assertRaisesRegex(ValueError, 'Invalid CGYRO result reference'):
                storage.reference_id(broken)
            with self.assertRaisesRegex(ValueError, 'Invalid CGYRO result reference'):
                updater.cgyro_payload(broken)


if __name__ == '__main__':
    unittest.main()
