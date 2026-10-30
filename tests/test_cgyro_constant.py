"""One optional constant: real input preparation, indexes, publication and restart."""
import copy
import json
import hashlib
from pathlib import Path
import unittest
import zipfile
from unittest.mock import patch

import test_cgyro_storage as fixtures
import test_cgyro_preflight as preflight
import test_cgyro_result_identity as identities
import test_cgyro_job_recovery as jobs
import test_project as project_tests
from OMFITlib_cgyro_archive import (canonical_case_key, case_constants, case_parts,
    grouped_case_id, grouped_case_path, case_sources, catalog_runs)
from OMFITlib_cgyro_parameters import apply_parameters, constant_parameters, initialize_parameters
from OMFITlib_cgyro_present import case_caption
from OMFITlib_cgyro_result_index import result_records, find_record, select_result
from OMFITlib_cgyro_continue import continuation_plan, prepare_point

archive, storage, db = fixtures.archive_api, fixtures.storage, fixtures.db_api


def configure(physics, name='BETAE_UNIT', value=.0001):
    physics['constant_parameter'] = name
    physics.setdefault('fixed_parameters', {})[name] = dict(enabled=False, value=value)


class ConstantPlanTests(unittest.TestCase):
    def test_constant_is_applied_to_each_input_without_adding_a_scan_axis(self):
        root = preflight.fixture(('BASE', 'T'), radii=2)
        physics = root['CGYRO_scan']['SETTINGS']['PHYSICS']
        configure(physics)
        self.assertEqual(preflight.plan.cgyro_plan_issues(root), [])
        summary = preflight.plan.cgyro_plan_summary(root)
        self.assertEqual(summary['total_points'], 16)
        self.assertEqual([axis['name'] for axis in summary['axes']], ['N_THETA'])
        for row in preflight.plan.cgyro_sources(root):
            source = preflight.plan.read(root, row['path'])
            for ion in ('BASE', 'T'):
                result, settings, _, fixed = preflight.plan._cgyro_case_input(root, row, source, ion, physics, 1)
                self.assertEqual(result['BETAE_UNIT'], .0001)
                self.assertEqual(fixed['BETAE_UNIT'], .0001)
                self.assertEqual(constant_parameters(settings), {'BETAE_UNIT': .0001})
            self.assertNotIn('BETAE_UNIT', source)

    def test_optional_off_keeps_existing_input_and_archive_name(self):
        physics = {'1d': {'Para': 'N_THETA'}, 'fixed_parameters': {}}
        source = {'BETAE_UNIT': .003, 'N_THETA': 32}
        initialize_parameters(physics, source)
        self.assertEqual(apply_parameters(source, physics, 1), {})
        self.assertEqual(source['BETAE_UNIT'], .003)
        self.assertEqual(grouped_case_path('nr=1__rho=0.33__ion=BASE'), ['nr=1_rho=0.33'])

    def test_constant_cannot_also_be_an_axis_or_linked_parameter(self):
        for axis in ('Para', 'Para2'):
            root = preflight.fixture(radii=1)
            physics = root['CGYRO_scan']['SETTINGS']['PHYSICS']
            configure(physics)
            physics['1d'][axis] = 'BETAE_UNIT'
            physics['1d']['Range' if axis == 'Para' else 'Range2'] = [.0001, .0002]
            with self.subTest(axis=axis):
                self.assertIn('不能同时', preflight.plan.cgyro_plan_issues(root)[0])

    def test_constant_accepts_one_scalar_and_retains_integer_parameter_type(self):
        physics = {'1d': {'Para': 'N_ENERGY'}, 'fixed_parameters': {}}
        for value in ([.0001, .0002], float('nan'), float('inf')):
            configure(physics, value=value)
            with self.subTest(value=value), self.assertRaises(ValueError):
                constant_parameters(physics)
        configure(physics, 'N_THETA', 32.)
        source = {'N_ENERGY': 8}
        self.assertEqual(apply_parameters(source, physics, 1), {'N_THETA': 32})
        self.assertIs(type(source['N_THETA']), int)

    def test_workflow_controls_and_ky_scaled_timestep_cannot_be_constants(self):
        physics = {'1d': {'Para': 'N_ENERGY'}, 'fixed_parameters': {}}
        for name in ('MAX_TIME', 'RESTART_STEP', 'MPI_RANK_ORDER'):
            configure(physics, name, 100)
            with self.subTest(name=name), self.assertRaises(ValueError):
                constant_parameters(physics)
        configure(physics, 'DELTA_T', .01)
        physics['scale_time_with_ky'] = True
        with self.assertRaisesRegex(ValueError, '关闭'):
            apply_parameters({'N_ENERGY': 8, 'MAX_TIME': 1200}, physics, 1)


class ConstantWorkbenchTests(unittest.TestCase):
    tree_factory = dict
    setUp = project_tests.ProjectTest.setUp
    send = project_tests.ProjectTest.send

    def test_constant_survives_parameter_refresh_save_reload_and_input_preparation(self):
        self.send()
        physics = self.cg['SETTINGS']['PHYSICS']
        source = self.transfer['Transfer_file']['input.cgyro']
        source.update(BETAE_UNIT=.00848771, N_ENERGY=32, rho=.33)
        physics['1d'] = dict(Para='N_THETA', Range=[24, 32])
        ui = project_tests.UI(self.root)
        view = project_tests.ProjectUI(self.actions, ui)
        rows = project_tests.project.sync_cgyro_choices(self.root, self.actions.settings)
        for beta in (.0001, 0):
            with self.subTest(beta=beta):
                configure(physics, value=beta)
                view.render_cgyro_scan_settings(self.cg, rows)
                view.render_cgyro_parameters(self.cg, rows)
                self.assertEqual(physics['fixed_parameters']['BETAE_UNIT'], dict(enabled=False, value=beta))
                physics['fixed_parameters']['N_ENERGY']['value'] = 48
                self.actions.edit_cgyro_parameter('N_ENERGY')
                view.render_cgyro_parameters(self.cg, rows)
                view.render_cgyro_scan_settings(self.cg, rows)
                # Use persisted settings, with none of the original UI objects.
                physics = json.loads(json.dumps(physics))
                self.cg['SETTINGS']['PHYSICS'] = physics
                project_tests.ProjectUI(self.actions, project_tests.UI(self.root)).render_cgyro_parameters(self.cg, rows)
                plan = self.actions.prepare_cgyro_batch()
                self.assertEqual(plan[0]['constant_parameters'], {'BETAE_UNIT': beta})
                self.assertEqual(self.cg['BATCH_INPUTS']['1']['BASE']['BETAE_UNIT'], beta)
                self.assertEqual(self.cg['BATCH_INPUTS']['1']['BASE']['N_ENERGY'], 48)
                self.assertEqual(source['BETAE_UNIT'], .00848771)

    def test_page_inherit_does_not_reset_constant_but_explicit_all_inherit_does(self):
        self.send()
        physics = self.cg['SETTINGS']['PHYSICS']
        self.transfer['Transfer_file']['input.cgyro'].update(BETAE_UNIT=.00848771, N_ENERGY=32)
        configure(physics)
        rows = project_tests.project.sync_cgyro_choices(self.root, self.actions.settings)
        source = project_tests.project.read(self.root, rows[0]['path'])
        initialize_parameters(physics, source)
        physics['fixed_parameters']['N_ENERGY'].update(enabled=True, value=48)
        self.actions.reset_cgyro_parameters(['BETAE_UNIT', 'N_ENERGY'], rows[0]['key'])
        self.assertEqual(physics['fixed_parameters']['BETAE_UNIT'], dict(enabled=False, value=.0001))
        self.assertEqual(physics['fixed_parameters']['N_ENERGY'], dict(enabled=False, value=32))
        self.actions.inherit_cgyro_parameters()
        project_tests.ProjectUI(self.actions, project_tests.UI(self.root)).render_cgyro_parameters(self.cg, rows)
        self.assertEqual(physics['constant_parameter'], '')
        self.assertEqual(physics['fixed_parameters']['BETAE_UNIT'], dict(enabled=False, value=.00848771))

    def test_prepared_case_and_local_controls_share_the_fixed_parameter_value(self):
        self.send()
        physics = self.cg['SETTINGS']['PHYSICS']
        configure(physics)
        physics['1d'] = dict(Para='N_THETA', Range=[24, 32])
        self.transfer['Transfer_file']['input.cgyro']['rho'] = .33
        plan = self.actions.prepare_cgyro_batch()
        self.assertEqual(plan[0]['case_id'], 'nr=1__rho=0.33__ion=BASE__constant=BETAE_UNIT=0.0001')
        self.assertEqual(plan[0]['constant_parameters'], {'BETAE_UNIT': .0001})
        self.assertEqual(self.cg['BATCH_INPUTS']['1']['BASE']['BETAE_UNIT'], .0001)
        ui = project_tests.UI(self.root)
        view = project_tests.ProjectUI(self.actions, ui)
        rows = project_tests.project.sync_cgyro_choices(self.root, self.actions.settings)
        view.render_cgyro_scan_settings(self.cg, rows)
        entries = [(args, kwargs) for kind, args, kwargs in ui.events if kind == 'Entry' and '固定值' in str(args)]
        self.assertEqual(len(entries), 1)
        self.assertIn("['fixed_parameters']['BETAE_UNIT']['value']", entries[0][0][0])
        self.assertFalse(entries[0][1]['updateGUI'])
        self.assertFalse(entries[0][1]['refresh_tree'])


class ConstantIndexTests(unittest.TestCase):
    def test_numeric_spellings_and_full_parameter_name_roundtrip(self):
        for name in ('BETAE_UNIT', 'BETAE_UNIT_SCALE', 'DLNTDR_1'):
            cid = canonical_case_key('nr=1__rho=0.330000__ion=T', {'constant_parameters': {name: .0001}})
            path = grouped_case_path(cid)
            self.assertEqual(path, ['nr=1_rho=0.33_{}=0.0001'.format(name), 'T'])
            self.assertEqual(grouped_case_id(path[0], 'T'), cid)
            self.assertEqual(case_parts(cid), ('1', '0.33', 'T'))
            self.assertEqual(canonical_case_key(cid.replace('=0.0001', '=1e-4')), cid)
            self.assertEqual(grouped_case_path(cid + '__run=abcdef01'), path)
            self.assertIn(name + '=0.0001', case_caption(cid))

    def test_distinct_finite_values_are_not_rounded_into_one_case(self):
        case = 'nr=1__rho=0.33__ion=T'
        first = canonical_case_key(case, {'constant_parameters': {'BETAE_UNIT': .0001}})
        second = canonical_case_key(case, {'constant_parameters': {'BETAE_UNIT': .00010000000000000002}})
        self.assertNotEqual(first, second)
        self.assertNotEqual(grouped_case_path(first), grouped_case_path(second))
        with self.assertRaisesRegex(ValueError, 'disagrees'):
            case_constants(first, {'constant_parameters': {'BETAE_UNIT': .0002}})


class ConstantResultTests(unittest.TestCase):
    result = identities.ResultIdentityTests.result
    public = identities.ResultIdentityTests.public

    def setUp(self):
        identities.ResultIdentityTests.setUp(self)
        native_path = patch.object(fixtures.OMFITpath, 'directory', str(self.base))
        native_path.start()
        self.addCleanup(native_path.stop)

    def constant_result(self, module, token, beta, ky=.1):
        info, row, ref = self.result(module, token, ky=ky, extra_values={'BETAE_UNIT': beta},
                                     generated={'BETAE_UNIT': beta})
        info.update(constant_parameters={'BETAE_UNIT': beta}, fixed_parameters={'BETAE_UNIT': beta})
        info['case_id'] = canonical_case_key(info['case_id'], info)
        info['point_table'] = {'p000001': copy.deepcopy(row)}
        self.public(module, info, row, ref)
        return info, row, ref

    def test_two_constants_and_plain_case_remain_directly_selectable_after_metadata_reload(self):
        module = {}
        plain_info, plain_row, plain_ref = self.result(module, 'plain')
        self.public(module, plain_info, plain_row, plain_ref)
        first, _, first_ref = self.constant_result(module, 'beta1', .0001)
        second, _, second_ref = self.constant_result(module, 'beta2', .0002)
        module['RUN_DB']['Jet'] = json.loads(json.dumps(module['RUN_DB']['Jet']))
        module['RUN_DB'].pop('__RUNS__')
        headers = result_records(module, include_tasks=False)
        self.assertEqual(len(headers), 3)
        self.assertEqual(set(catalog_runs(module)['Jet']), {plain_info['case_id'], first['case_id'], second['case_id']})
        for info, expected in ((plain_info, plain_ref), (first, first_ref), (second, second_ref)):
            entry = next(h for h in headers.values() if h['case_id'] == info['case_id'])
            selected = find_record(module, entry['selection_key'])
            binding = select_result(module, selected, 'p000001')
            self.assertEqual(binding['result_id'], storage.reference_id(expected))
            self.assertEqual([cid for cid, _, _ in case_sources(module, 'Jet', info['case_id'])['Jet']], [info['case_id']])

    def test_restart_uses_only_the_selected_constants_files_without_job_history(self):
        module = {}
        first, _, first_ref = self.constant_result(module, 'chosen', .0001)
        _, _, other = self.constant_result(module, 'closed', .0002)
        module['RUN_DB'].pop('__RUNS__')
        class Unreadable(fixtures.OMFITcgyro):
            @property
            def filename(self):
                raise AssertionError('unselected constant files accessed')
        module['RUN_DB']['__STORE__'][storage.reference_id(other)] = object.__new__(Unreadable)
        headers = result_records(module, include_tasks=False)
        entry = next(e for e in headers.values() if e['case_id'] == first['case_id'])
        plan = continuation_plan(module, entry['selection_key'], ['p000001'], 1.)
        current, _, _ = prepare_point(module, plan, 'p000001', str(self.base / 'stage'),
                                     identities.Input, runtime=self.current)
        self.assertEqual(current['BETAE_UNIT'], .0001)
        self.assertEqual(plan['source_case_id'], first['case_id'])
        self.assertEqual(plan['info']['constant_parameters'], {'BETAE_UNIT': .0001})
        self.assertEqual(plan['selections']['p000001']['result_id'], storage.reference_id(first_ref))

    def test_explicit_archive_maintenance_keeps_constant_groups_and_reference_ids(self):
        module = {}
        one, _, first = self.constant_result(module, 'retain1', .0001)
        two, _, second = self.constant_result(module, 'retain2', .0002)
        module['RUN_DB'].pop('__RUNS__')
        storage.recover_archives(module, storage.resolve_result)
        headers = result_records(module, include_tasks=False)
        self.assertEqual(len(headers), 2)
        for info, ref in ((one, first), (two, second)):
            header = next(entry for entry in headers.values() if entry['case_id'] == info['case_id'])
            entry = find_record(module, header['selection_key'])
            self.assertEqual(select_result(module, entry, 'p000001')['result_id'], storage.reference_id(ref))

    def test_inconsistent_constant_input_is_rejected(self):
        module = {}
        info, _, ref = self.constant_result(module, 'bad', .0001)
        owner = storage.resolve_result(module, ref)
        card = identities.Input(Path(owner.filename) / 'input.cgyro')
        card['BETAE_UNIT'] = .0002
        card.deploy(Path(owner.filename) / 'input.cgyro')
        entry = next(e for e in result_records(module, include_tasks=False).values() if e['case_id'] == info['case_id'])
        with self.assertRaisesRegex(ValueError, 'input|BETAE_UNIT'):
            continuation_plan(module, entry['selection_key'], ['p000001'], 1.)


class ConstantPublicationTests(unittest.TestCase):
    setUp = fixtures.StorageCases.setUp
    tearDown = fixtures.StorageCases.tearDown
    result = fixtures.StorageCases.result
    publisher = fixtures.StorageCases.publisher

    def test_partial_continuation_replaces_only_its_constant_group_and_coordinate(self):
        root, publish = {}, self.publisher()
        def attempt(token, beta, kys, time):
            cid = canonical_case_key('nr=1__rho=0.33__ion=BASE', {'constant_parameters': {'BETAE_UNIT': beta}})
            table, cases = {}, {}
            for index, ky in enumerate(kys, 1):
                point = 'p{:06d}'.format(index)
                table[point] = dict(values={'N_THETA': 32, 'KY': ky},
                                    result_path=['N_THETA', '32', 'lin', str(ky)])
                owner = self.result(token + point, parameters={'N_THETA': 32, 'KY': ky, 'BETAE_UNIT': beta})
                Path(owner.filename, 'out.cgyro.time').write_text('0\n{}\n'.format(time))
                cases[point] = owner
            manifest = dict(run_token=token, status='loaded', collection_status='ready',
                dimensions=1, scan_dimensions=1, scan_axes=[dict(name='N_THETA', values=[32], linked=[])],
                case_tag='case', case_id=cid, nr=1, rho=.33, mass='BASE', runid='Jet', server='fixture',
                constant_parameters={'BETAE_UNIT': beta}, fixed_parameters={'BETAE_UNIT': beta},
                workDir='/runs/' + token, job_id='job-' + token,
                points=list(table), loaded_points=list(table), point_table=table)
            root['RUN_MANIFEST'], root['Cases'] = manifest, {'case': cases}
            return manifest
        first = copy.deepcopy(attempt('a', .0001, [.1, -.1], 30))
        publish(root)
        attempt('b', .0002, [.1], 30)
        publish(root)
        old = copy.deepcopy(root['RUN_DB']['Jet'])
        child = attempt('child', .0001, [.1], 40)
        child['continuation'] = dict(source_token='missing-parent', source_runid='Jet',
            source_case_id=first['case_id'], points=child['points'], source_points=first['points'])
        publish(root)
        current = root['RUN_DB']['Jet']
        self.assertEqual(set(current), {'nr=1_rho=0.33_BETAE_UNIT=0.0001', 'nr=1_rho=0.33_BETAE_UNIT=0.0002'})
        self.assertEqual(current['nr=1_rho=0.33_BETAE_UNIT=0.0002'], old['nr=1_rho=0.33_BETAE_UNIT=0.0002'])
        before = old['nr=1_rho=0.33_BETAE_UNIT=0.0001']['N_THETA']['32']['lin']
        after = current['nr=1_rho=0.33_BETAE_UNIT=0.0001']['N_THETA']['32']['lin']
        self.assertEqual(after['-0.1'], before['-0.1'])
        self.assertNotEqual(after['0.1'], before['0.1'])


class ConstantRecoveryTests(unittest.TestCase):
    def test_job_manifest_roundtrip_preserves_and_validates_constant(self):
        frozen = jobs.manifest()
        frozen.update(constant_parameters={'BETAE_UNIT': .0001}, fixed_parameters={'BETAE_UNIT': .0001})
        frozen['case_id'] = canonical_case_key(frozen['case_id'], frozen)
        decoded = jobs.schema.read_manifest(json.dumps(dict(schema=1, manifest=frozen)))
        validated = jobs.schema.validate_manifest(decoded, jobs.WORKDIR, jobs.SCRIPT)
        self.assertEqual(validated['constant_parameters'], {'BETAE_UNIT': .0001})
        self.assertEqual(grouped_case_path(validated['case_id']), ['nr=1_rho=0.33_BETAE_UNIT=0.0001', 'T'])
        decoded['fixed_parameters']['BETAE_UNIT'] = .0002
        with self.assertRaisesRegex(ValueError, 'constant'):
            jobs.schema.validate_manifest(decoded, jobs.WORKDIR, jobs.SCRIPT)

    def test_recovery_zip_checks_the_frozen_constant_even_with_a_valid_hash(self):
        import tempfile
        row = dict(values={'N_THETA': 16, 'KY': .1, 'BETAE_UNIT': .0001})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'p000001.zip'
            for beta in (.0001, .0002):
                content = jobs.INPUT + ('BETAE_UNIT={}\n'.format(beta)).encode()
                with zipfile.ZipFile(path, 'w') as packed:
                    packed.writestr('input.cgyro', content)
                expected = {'input.cgyro': hashlib.sha256(content).hexdigest()}
                if beta == .0001:
                    jobs.schema.verify_input_zip(str(path), expected, row)
                else:
                    with self.assertRaisesRegex(ValueError, 'BETAE_UNIT'):
                        jobs.schema.verify_input_zip(str(path), expected, row)


if __name__ == '__main__':
    unittest.main()
