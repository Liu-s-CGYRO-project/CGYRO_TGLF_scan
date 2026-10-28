"""Native result paths, dimension separation, selected reads and old projects."""
import copy
import pickle
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
from omfit_mapping import OMFITMapping, treeify

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'CGYRO_TGLF_scan/LIB'))
sys.path.insert(0, str(REPO / 'OMFITtemplates/LIB'))
from OMFITlib_tglf_workbench import initialize, plan, scan_parameter_names
from OMFITlib_tglf_records import at, point_current, point_result, result_location, restore_native_results, run_records
from OMFITlib_plot_sources import run_choices, source_dimension, tglf_results
import OMFITlib_tglf_cache as native_cache
import test_cgyro_storage  # Explicit native reader stand-ins for cleanup dependencies.
from OMFITlib_result_cleanup import active_jobs, clear_results
from OMFITlib_template_migration import ArchiveIndex


def payload(value=2.):
    return {'gbflux': {'data': np.array([('elec', 1., value, 3.)],
        dtype=[('species', 'U12'), ('Gam/Gam_GB', float), ('Q/Q_GB', float), ('Pi/Pi_GB', float)])},
        'eigenvalue_spectrum': dict(ky=np.array([.1, .2]), freq=np.array([[1., 2.]]), gamma=np.array([[3., 4.]]))}


class Unread(dict):
    def __getitem__(self, key):
        raise AssertionError('Unselected payload read')

    def __deepcopy__(self, memo):
        raise AssertionError('Unselected payload copied')


class ScanTree(OMFITMapping):
    def sort(self, **kw):
        pass


class NativeStorageTests(unittest.TestCase):
    def setUp(self):
        self.source = dict(NS=2, ZS_1=-1., ZS_2=1., SAT_RULE=0, XNUE=.1, BETAE=.01)
        self.root = dict(SETTINGS={'WORKBENCH': {}}, CGYRO_scan={'RUN_DB': {'untouched': [42]}},
                         TGLF_scan={'TGLF': {'FILES': {'input.tglf': self.source},
                                               'SCRIPTS': {}, 'SETTINGS': {'REMOTE_SETUP': {}}}})
        self.scan = self.root['TGLF_scan']
        self.settings, _ = initialize(self.root)
        self.settings.update(source='current', mode='1d', parameter1='SAT_RULE', values1=[0, 1], value_mode1='list',
                             parameter2='XNUE', values2=[.1, .2], value_mode2='list',
                             parameter3='BETAE', values3=[.01, .02], value_mode3='list')

    def execute(self, fail=None):
        def batch(**kw):
            for index, key in enumerate(kw['runIDs']):
                kw['results'][key] = ({'_load_error': 'failed', 'run_log': 'diagnostic'} if index == fail else payload(index + 2))
        self.scan['TGLF']['SCRIPTS']['runTGLFbatch'] = SimpleNamespace(run=batch)
        prepared = plan(self.root, self.settings)
        script = REPO / 'CGYRO_TGLF_scan/TGLF_scan/SCRIPTS/run_workbench.py'
        namespace = dict(root=self.scan, project_root=self.root, plan=prepared,
                         defaultVars=lambda **kw: None, OMFITtree=dict, print=lambda *a: None)
        if fail is None:
            exec(compile(script.read_text(encoding='utf-8'), str(script), 'exec'), namespace)
        else:
            with self.assertRaisesRegex(RuntimeError, 'failed'):
                exec(compile(script.read_text(encoding='utf-8'), str(script), 'exec'), namespace)
        return self.scan['_workbench_runs'][self.settings['result_run']]

    def test_one_two_three_dimensions_are_separate_and_native_ordered(self):
        for mode, key, coordinate in (
                ('1d', 'scanResults', ['SAT_RULE', 1]),
                ('2d', 'scanResults2D', ['XNUE+SAT_RULE', .2, 1]),
                ('3d', 'scanResults3D', ['BETAE+XNUE+SAT_RULE', .02, .2, 1])):
            self.settings['mode'] = mode
            record = self.execute()
            node = at(self.scan, ['TGLF', key + '_spectra'] + coordinate)
            self.assertIsNotNone(node)
            np.testing.assert_array_equal(at(self.scan, ['TGLF', key] + coordinate), node['gbflux']['data'])
            self.assertEqual(len(record['points']), 2 ** int(mode[0]))
            self.assertTrue(all('result' not in p and 'input' not in p for p in record['points'].values()))
            self.assertNotIn('RUN_DB', self.scan)
        self.assertEqual(self.root['CGYRO_scan']['RUN_DB'], {'untouched': [42]})
        self.assertEqual(scan_parameter_names(self.settings), {'SAT_RULE', 'XNUE', 'BETAE'})

    def test_radial_and_single_file_native_shapes(self):
        self.scan['input.tglf'] = {.3: dict(self.source), .5: dict(self.source)}
        self.settings.update(source='radial', radius_mode='all', mode='2d')
        self.execute()
        self.assertIn(.3, self.scan['scanResults2D'])
        self.assertIn(.5, self.scan['scanResults2D_spectra'])
        self.settings['mode'] = 'single'
        self.execute()
        self.assertIn('data', self.scan['Experimental_fluxes'][.3])
        self.assertIn('eigenvalue_spectrum', self.scan['Experimental_spectra'][.5])
        self.settings.update(source='current')
        record = self.execute()
        self.assertIs(point_result(self.scan, record['points']['p000001']), self.scan['TGLF']['FILES'])

    def test_transfer_inputs_with_same_radius_are_not_mixed(self):
        self.root['Transfer_tool'] = {'OUTPUTS': {'Profiles_gen': {
            'input.tglf_1': dict(self.source), 'input.tglf_2': dict(self.source, BETAE=.3)},
            'Particle_processing': {'local_inputs': {'input.tglf_1': {'rho': .3}, 'input.tglf_2': {'rho': .3}}}}}
        initialize(self.root)
        self.settings.update(source='transfer', selected={'transfer:1': True, 'transfer:2': True})
        with self.assertRaisesRegex(ValueError, '半径重复'):
            plan(self.root, self.settings)
        self.assertNotIn('_workbench_runs', self.scan)

    def transfer_inputs(self):
        self.root['Transfer_tool'] = {'OUTPUTS': {'Profiles_gen': {
            'input.tglf_1': dict(self.source), 'input.tglf_2': dict(self.source, BETAE=.3)},
            'Particle_processing': {'local_inputs': {'input.tglf_1': {'rho': .3}, 'input.tglf_2': {'rho': .5}}}}}
        initialize(self.root)
        self.settings.update(source='transfer', selected={'transfer:1': True, 'transfer:2': True})

    def legacy_transfer_record(self):
        self.transfer_inputs()
        record = self.execute()
        for point in record['points'].values():
            old_path = point['result_path']
            result = at(self.scan, old_path[:-1]).pop(old_path[-1])
            flux = [old_path[0].replace('_spectra', '')] + old_path[1:]
            at(self.scan, flux[:-1]).pop(flux[-1])
            self.scan['_workbench_index'].pop(tuple(old_path))
            source = next(s for s in record['plan']['sources'] if list(s['path']) == point['source'])
            scope = self.scan.setdefault('sourceResults', {}).setdefault(source['key'], {})
            local = [old_path[0]] + old_path[2:]
            for path, value in ((local, result), ([flux[0]] + flux[2:], result['gbflux']['data'])):
                parent = scope
                for part in path[:-1]:
                    parent = parent.setdefault(part, {})
                parent[path[-1]] = value
            scope.setdefault('_workbench_index', {})[tuple(local)] = point['owner']
            point.update(result_path=['sourceResults', source['key']] + local,
                         owner_path=['sourceResults', source['key'], '_workbench_index'], owner_key=local)
        self.scan.pop('input.tglf', None)
        return record

    def test_transfer_scans_write_outer_native_branches_in_all_dimensions(self):
        self.transfer_inputs()
        for mode, branch, coordinate in (
                ('1d', 'scanResults', ['SAT_RULE', 1]),
                ('2d', 'scanResults2D', ['XNUE+SAT_RULE', .2, 1]),
                ('3d', 'scanResults3D', ['BETAE+XNUE+SAT_RULE', .02, .2, 1])):
            self.settings['mode'] = mode
            record = self.execute()
            for radius in (.3, .5):
                result = at(self.scan, [branch + '_spectra', radius] + coordinate)
                self.assertIsNotNone(result)
                np.testing.assert_array_equal(at(self.scan, [branch, radius] + coordinate), result['gbflux']['data'])
                self.assertEqual(self.scan['input.tglf'][radius]['SAT_RULE'], 0)
                self.assertIs(self.scan['input.tglf'][radius]['USE_TRANSPORT_MODEL'], True)
            self.assertNotIn('sourceResults', self.scan)
            self.assertNotIn('RUN_DB', self.scan)
            self.assertTrue(all(p['result_path'][0] == branch + '_spectra' for p in record['points'].values()))

    def test_transfer_failed_point_preserves_existing_native_result(self):
        self.transfer_inputs()
        old = self.execute()
        point = old['points']['p000001']
        result = point_result(self.scan, point)
        new = self.execute(fail=0)
        self.assertIs(point_result(self.scan, point), result)
        self.assertEqual(new['status'], 'partial')
        self.assertFalse(point_current(self.scan, old['points']['p000002']))
        self.assertEqual(set(self.scan['scanResults']), {.3, .5})

    def test_restore_only_selected_record_without_recalculation_or_old_copies(self):
        record = self.legacy_transfer_record()
        self.scan['sourceResults']['unrelated'] = Unread()
        self.scan['_workbench_runs']['unrelated'] = Unread()
        report = restore_native_results(self.scan, record)
        self.assertEqual(report, dict(moved=4, conflicts=[], unavailable=[]))
        self.assertEqual(set(self.scan['scanResults']), {.3, .5})
        self.assertEqual(self.scan['sourceResults']['transfer:1']['scanResults_spectra']['SAT_RULE'], {})
        point = record['points']['p000001']
        self.assertIn("TGLF_scan['scanResults_spectra'][0.3]['SAT_RULE'][0]", result_location(point))
        self.assertIs(point_result(self.scan, point), self.scan['scanResults_spectra'][.3]['SAT_RULE'][0])
        self.assertIsNot(self.scan['input.tglf'][.3], point_result(self.scan, point)['input.tglf'])
        self.assertEqual(self.scan['input.tglf'][.3]['SAT_RULE'], 0)
        self.scan.pop('_workbench_runs')
        self.assertIn('legacy:1D', run_choices(self.root).values())
        self.assertEqual(tglf_results(self.root, {'result_source': 'legacy:1D'})[.3]['SAT_RULE'][0]['gbflux']['data'][0]['Q/Q_GB'], 2.)

    def test_restore_conflict_preserves_both_results_and_old_reference(self):
        record = self.legacy_transfer_record()
        old = record['points']['p000001']
        old_path = list(old['result_path'])
        existing = payload(99.)
        self.scan['scanResults_spectra'][.3]['SAT_RULE'][0] = existing
        report = restore_native_results(self.scan, record)
        self.assertEqual(report['moved'], 3)
        self.assertEqual(len(report['conflicts']), 1)
        self.assertIs(self.scan['scanResults_spectra'][.3]['SAT_RULE'][0], existing)
        self.assertEqual(old['result_path'], old_path)
        self.assertTrue(point_current(self.scan, old))

    def test_restored_references_survive_strict_mapping_serialization(self):
        record = self.legacy_transfer_record()
        self.scan['TGLF']['SCRIPTS'] = {}
        reopened = pickle.loads(pickle.dumps(treeify(self.root, OMFITMapping)))
        module = reopened['TGLF_scan']
        saved = module['_workbench_runs'][record['id']]
        self.assertEqual(restore_native_results(module, saved)['moved'], 4)
        again = pickle.loads(pickle.dumps(reopened))['TGLF_scan']
        point = again['_workbench_runs'][record['id']]['points']['p000001']
        self.assertTrue(point_current(again, point))
        self.assertEqual(point_result(again, point)['input.tglf']['BETAE'], .01)

    def test_transfer_missing_radius_stops_before_creating_a_run(self):
        self.transfer_inputs()
        self.root['Transfer_tool']['OUTPUTS']['Particle_processing']['local_inputs']['input.tglf_1'] = {}
        with self.assertRaisesRegex(ValueError, '半径元数据'):
            plan(self.root, self.settings)
        self.assertNotIn('_workbench_runs', self.scan)

    def test_restore_missing_source_radius_does_not_block_other_radius(self):
        record = self.legacy_transfer_record()
        record['plan']['sources'][0].pop('rho')
        report = restore_native_results(self.scan, record)
        self.assertEqual(report['moved'], 2)
        self.assertEqual(len(report['unavailable']), 2)
        self.assertTrue(point_current(self.scan, record['points']['p000001']))
        self.assertEqual(record['points']['p000001']['result_path'][0], 'sourceResults')
        self.assertEqual(record['points']['p000003']['result_path'][:2], ['scanResults_spectra', .5])

    def test_radial_plot_entries_pass_selected_native_maps_without_changing_child_results(self):
        for dimension, name, branch in (
                (1, 'plotScanAtRho', 'scanResults'),
                (2, 'plotScanAtRho', 'scanResults2D'),
                (1, 'plotScanSpecAtRho', 'scanResults_spectra')):
            with self.subTest(name=name, dimension=dimension):
                selected = {'SAT_RULE': {0: payload()}}
                other = Unread()
                baseline = dict(self.source)
                single = Unread({'single': payload()})
                calls = []
                fig = SimpleNamespace(get_axes=lambda: [object()], canvas=SimpleNamespace(draw=lambda: None))
                def plot(**kwargs):
                    calls.append(kwargs)
                    return {'fn': [fig]}
                child = self.scan['TGLF']
                child['SETTINGS']['PHYSICS'] = {'scanParameter': 'SAT_RULE'}
                child['scanResults'] = child['scanResults2D'] = child['scanResults_spectra'] = single
                child['PLOTS'] = {key: SimpleNamespace(plot=plot) for key in ('plotScan', 'plotScan2D', 'plotScanSpec')}
                original_input = child['FILES']['input.tglf']
                self.scan.update(SETTINGS={'PHYSICS': {'rho': .3, 'scanDimensions': dimension}},
                                 **{branch: {.3: selected, .5: other}, 'input.tglf': {.3: baseline, .5: other}})
                namespace = dict(root=self.scan, figure=lambda: fig, nan=float('nan'), cornernote=lambda *a, **kw: None)
                namespace['defaultVars'] = lambda **kw: [namespace.setdefault(key, value) for key, value in kw.items()]
                script = REPO / ('CGYRO_TGLF_scan/TGLF_scan/PLOTS/' + name + '.py')
                exec(compile(script.read_text(encoding='utf-8'), str(script), 'exec'), namespace)
                self.assertEqual(len(calls), 1)
                self.assertIs(calls[0]['results'], selected)
                if name == 'plotScanAtRho':
                    self.assertIs(calls[0]['inputTGLF'], baseline)
                self.assertIs(child['FILES']['input.tglf'], original_input)
                self.assertTrue(all(child[key] is single for key in ('scanResults', 'scanResults2D', 'scanResults_spectra')))

    def test_failed_download_retains_prior_native_point_and_other_dimensions(self):
        old = self.execute()
        point = old['points']['p000001']
        result = point_result(self.scan, point)
        new = self.execute(fail=0)
        self.assertEqual(new['status'], 'partial')
        self.assertIs(point_result(self.scan, point), result)
        self.assertFalse(point_current(self.scan, old['points']['p000002']))
        with self.assertRaisesRegex(ValueError, '替换'):
            point_result(self.scan, old['points']['p000002'])
        self.assertTrue(point_current(self.scan, new['points']['p000002']))
        self.settings.update(mode='2d')
        self.execute()
        self.assertIs(point_result(self.scan, point), result)

    def test_native_lookup_without_records_and_metadata_reads_without_payloads(self):
        record = self.execute()
        point = record['points']['p000002']
        parent = at(self.scan, point['result_path'][:-1])
        parent[point['result_path'][-1]] = Unread(payload())
        self.assertIn(record['id'], run_choices(self.root).values())
        state = {'result_source': record['id']}
        view = tglf_results(self.root, state)
        first = next(iter(view.values()))['SAT_RULE'][0]
        self.assertEqual(first['eigenvalue_spectrum']['gamma(1)'][0], 3.)
        # Deleting run metadata does not delete or make native results dependent on history.
        self.scan.pop('_workbench_runs')
        native = tglf_results(self.root, {'result_source': 'native:TGLF:1D'})
        self.assertEqual(native['TGLF']['SAT_RULE'][0]['eigenvalue_spectrum']['freq(1)'][1], 2.)

    def test_three_dimensions_plot_as_labelled_slices_without_losing_points(self):
        self.settings['mode'] = '3d'
        record = self.execute()
        for source in (record['id'], 'native:TGLF:3D'):
            self.assertEqual(source_dimension(self.root, source), '2D')
            view = tglf_results(self.root, {'result_source': source})
            self.assertEqual(len(view), 2)
            self.assertTrue(all('BETAE=' in label for label in view))
            count = sum(len(inner) for params in view.values() for outer in params.values() for inner in outer.values())
            self.assertEqual(count, 8)

    def test_uq_uses_native_sample_coordinates(self):
        self.settings.update(mode='uq', uq_count=1, samples=2, uq={'0': dict(name='XNUE', mean=.1, std=.02)})
        cp = SimpleNamespace(Normal=lambda *a: None, J=lambda *a: SimpleNamespace(sample=lambda *a: [[.08, .12]]))
        with patch.dict(sys.modules, {'chaospy': cp}):
            self.execute()
        self.assertEqual(set(self.scan['TGLF']['UQResults']['XNUE']), {'0.08', '0.12'})
        self.assertNotIn('scanResults', self.scan['TGLF'])

    def test_round_trip_paths_owner_keys_and_legacy_reader_survive(self):
        record = self.execute()
        # Native OMFIT mappings have stricter get() semantics than plain dicts.
        self.scan['TGLF']['SCRIPTS'] = {}
        reopened = pickle.loads(pickle.dumps(treeify(self.root, OMFITMapping)))
        scan = reopened['TGLF_scan']
        point = scan['_workbench_runs'][record['id']]['points']['p000001']
        self.assertTrue(point_current(scan, point))
        self.assertEqual(point_result(scan, point)['input.tglf']['SAT_RULE'], 0)
        scan['RUN_DB'] = {'old': dict(mode='1d', plan={'axes': [{'name': 'SAT_RULE'}]},
            points={'p': dict(status='complete', parameters={'SAT_RULE': 3}, result=payload(), label='old')})}
        view = tglf_results(reopened, {'result_source': 'old'})
        self.assertIn('old', run_records(scan))
        self.assertEqual(view['old']['SAT_RULE'][3]['eigenvalue_spectrum']['gamma(1)'][1], 4.)

    def test_template_update_does_not_read_or_relocate_native_tglf(self):
        native = Unread(scanResults=Unread(), scanResults2D_spectra=Unread(), scanResults3D=Unread(), RUN_DB=Unread())
        migration = ArchiveIndex()
        self.assertEqual(migration.tglf(native), {})
        self.assertFalse(migration.sources)

    def test_native_one_dimensional_rerun_keeps_other_dimension_references(self):
        one = self.execute()
        self.settings['mode'] = '2d'
        two = self.execute()
        self.settings['mode'] = '3d'
        three = self.execute()
        module = treeify(self.scan['TGLF'], ScanTree)
        self.scan['TGLF'] = module
        module['SETTINGS']['PHYSICS'] = dict(scanParameter='SAT_RULE', scanParameterRange=[0], single_Ti=False)
        module['LIB'] = {'OMFITlib_tglf_cache': SimpleNamespace(runNoGUI=lambda: vars(native_cache))}
        module['SCRIPTS']['runTGLFbatch'] = SimpleNamespace(
            run=lambda **kw: kw['results'].update({0: payload(99)}))
        script = REPO / 'CGYRO_TGLF_scan/TGLF_scan/TGLF/SCRIPTS/runTGLFscan.py'
        namespace = dict(root=module, scratch={}, OMFITtree=ScanTree, print=lambda *a: None, printe=lambda *a: None)
        namespace['defaultVars'] = lambda **kw: namespace.update(kw)
        exec(compile(script.read_text(encoding='utf-8'), str(script), 'exec'), namespace)
        self.assertFalse(point_current(self.scan, one['points']['p000001']))
        self.assertTrue(point_current(self.scan, two['points']['p000001']))
        self.assertTrue(point_current(self.scan, three['points']['p000001']))
        self.assertEqual(module['scanResults']['SAT_RULE'][0][0]['Q/Q_GB'], 99)

    def test_workbench_replacement_invalidates_only_its_native_cache(self):
        module = self.scan['TGLF']
        old = dict(reusable=True, sha256='old', solver_sha256='a' * 64)
        module['_scan_cache_provenance'] = {
            'scanResults': {'SAT_RULE': old, 'XNUE': old}, 'scanResults2D': {'other': old}}
        self.execute()
        self.assertNotIn('SAT_RULE', module['_scan_cache_provenance']['scanResults'])
        self.assertIs(module['_scan_cache_provenance']['scanResults']['XNUE'], old)
        self.assertIs(module['_scan_cache_provenance']['scanResults2D']['other'], old)
        module['_scan_cache_provenance']['scanResults2D'].update(
            {'XNUE+SAT_RULE': old, 'XNUE+SAT_RULE_rows': {'row': old}})
        self.settings['mode'] = '2d'
        self.execute()
        self.assertEqual(module['_scan_cache_provenance']['scanResults2D'], {'other': old})
        module['_scan_cache_provenance']['UQResults'] = old
        self.settings.update(mode='uq', uq_count=1, samples=2, uq={'0': dict(name='XNUE', mean=.1, std=.02)})
        cp = SimpleNamespace(Normal=lambda *a: None, J=lambda *a: SimpleNamespace(sample=lambda *a: [[.08, .12]]))
        with patch.dict(sys.modules, {'chaospy': cp}):
            self.execute()
        self.assertNotIn('UQResults', module['_scan_cache_provenance'])

        self.scan['input.tglf'] = {.3: dict(self.source), .5: dict(self.source)}
        self.scan['_scan_cache_provenance'] = {
            .3: {'scanResults': {'SAT_RULE': old}, 'scanResults2D': {'other': old}},
            .5: {'scanResults': {'SAT_RULE': old}}}
        self.settings.update(source='radial', radius_mode='single', radius=.3, mode='1d')
        self.execute()
        self.assertNotIn('SAT_RULE', self.scan['_scan_cache_provenance'][.3]['scanResults'])
        self.assertIs(self.scan['_scan_cache_provenance'][.5]['scanResults']['SAT_RULE'], old)
        self.assertIs(self.scan['_scan_cache_provenance'][.3]['scanResults2D']['other'], old)
        self.scan['_radial_cache_provenance'] = {.3: old, .5: old}
        self.settings['mode'] = 'single'
        self.execute()
        self.assertNotIn(.3, self.scan['_radial_cache_provenance'])
        self.assertIs(self.scan['_radial_cache_provenance'][.5], old)

    def test_native_scan_does_not_reuse_workbench_data_with_an_old_digest(self):
        module = self.scan['TGLF']
        digest = dict(reusable=True, sha256='old', solver_sha256='a' * 64)
        module['_scan_cache_provenance'] = {'scanResults': {'SAT_RULE': digest}}
        self.execute()  # Same coordinate, a different calculation owns its data now.
        module = treeify(module, ScanTree)
        self.scan['TGLF'] = module
        module['SETTINGS']['PHYSICS'] = dict(scanParameter='SAT_RULE', scanParameterRange=[0], single_Ti=False)
        module['LIB'] = {'OMFITlib_tglf_cache': SimpleNamespace(runNoGUI=lambda: dict(vars(native_cache),
                                                                                   provenance=lambda *a: digest))}
        submitted = []
        def batch(**kw):
            submitted.extend(kw['inputTGLF'])
            kw['results'].update({0: payload(99)})
        module['SCRIPTS']['runTGLFbatch'] = SimpleNamespace(run=batch)
        script = REPO / 'CGYRO_TGLF_scan/TGLF_scan/TGLF/SCRIPTS/runTGLFscan.py'
        namespace = dict(root=module, scratch={}, OMFITtree=ScanTree, print=lambda *a: None,
                         printe=lambda *a: None, OMFITx=SimpleNamespace(End=lambda: self.fail('Stale cache reused')))
        namespace['defaultVars'] = lambda **kw: namespace.update(kw)
        exec(compile(script.read_text(encoding='utf-8'), str(script), 'exec'), namespace)
        self.assertEqual(len(submitted), 1)
        self.assertEqual(module['scanResults']['SAT_RULE'][0][0]['Q/Q_GB'], 99)

    def test_radial_native_scan_preserves_single_file_results_and_partial_points(self):
        for dimension, name, branch, axes in (
                (1, 'runTGLFscan', 'scanResults', 'SAT_RULE'),
                (2, 'runTGLFscan2D', 'scanResults2D', 'XNUE+SAT_RULE'),
                ('UQ', 'runTGLFUQscan', 'UQResults', 'SAT_RULE_XNUE')):
            for fail in (False, True):
                with self.subTest(dimension=dimension, fail=fail):
                    single = Unread({'single': payload()})
                    single_index = {(branch + '_spectra', 'single'): 'saved:point'}
                    module = self.scan['TGLF']
                    module[branch] = single
                    module[branch + '_spectra'] = single
                    module['_workbench_index'] = single_index
                    native_cache_record = Unread({'unrelated': 'unchanged'})
                    module['_scan_cache_provenance'] = native_cache_record
                    self.scan['input.tglf'] = {.3: dict(self.source)}
                    self.scan['SETTINGS'] = {'PHYSICS': {'rho': .3, 'scanDimensions': dimension}}
                    module['SETTINGS']['PHYSICS'] = dict(scanParameter='SAT_RULE', scanParameter2D='XNUE',
                                                          scanParameters=['SAT_RULE', 'XNUE'])
                    old_path = (branch + '_spectra', .3, axes, 0)
                    unrelated = (branch + '_spectra', .5, axes, 0)
                    other_axes = (branch + '_spectra', .3, 'OTHER', 0)
                    self.scan['_workbench_index'] = {
                        old_path: 'old:point', unrelated: 'other:point', other_axes: 'other-axis:point'}
                    def run(**kw):
                        kw['results'][axes] = {'new': 99}
                        kw['results_spectra'][axes] = {'new': payload(99)}
                        kw['cache_records']['updated'] = True
                        if fail:
                            raise RuntimeError('synthetic partial failure')
                    module['SCRIPTS'][name] = SimpleNamespace(run=run)
                    self.scan['SCRIPTS'] = {'setup_UQ_inputs': SimpleNamespace(run=lambda: None)}
                    script = REPO / 'CGYRO_TGLF_scan/TGLF_scan/SCRIPTS/runScanAtRho.py'
                    namespace = dict(root=self.scan, copy=copy, OMFITtree=dict, printi=lambda *a: None)
                    if fail:
                        with self.assertRaisesRegex(RuntimeError, 'partial failure'):
                            exec(compile(script.read_text(encoding='utf-8'), str(script), 'exec'), namespace)
                    else:
                        exec(compile(script.read_text(encoding='utf-8'), str(script), 'exec'), namespace)
                    self.assertIs(module[branch], single)
                    self.assertIs(module[branch + '_spectra'], single)
                    self.assertIs(module['_workbench_index'], single_index)
                    self.assertEqual(single_index, {(branch + '_spectra', 'single'): 'saved:point'})
                    self.assertIs(module['_scan_cache_provenance'], native_cache_record)
                    self.assertEqual(self.scan[branch][.3][axes]['new'], 99)
                    self.assertEqual(self.scan[branch + '_spectra'][.3][axes]['new']['gbflux']['data'][0]['Q/Q_GB'], 99)
                    self.assertNotIn(old_path, self.scan['_workbench_index'])
                    self.assertIn(unrelated, self.scan['_workbench_index'])
                    self.assertIn(other_axes, self.scan['_workbench_index'])

    def test_cleanup_covers_native_three_dimensions_and_new_running_records(self):
        self.settings['mode'] = '3d'
        record = self.execute()
        record['status'] = 'running'
        self.assertTrue(active_jobs(self.root))
        with self.assertRaises(ValueError):
            clear_results(self.root)
        record['status'] = 'complete'
        clear_results(self.root)
        self.assertFalse(self.scan['TGLF']['scanResults3D'])
        self.assertFalse(self.scan['TGLF']['scanResults3D_spectra'])
        self.assertFalse(self.scan['_workbench_runs'])
        self.assertFalse(self.scan['TGLF']['_workbench_index'])


if __name__ == '__main__':
    unittest.main()
