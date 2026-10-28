"""RUN_DB version selection with real v3 files; no scheduler or solver calls."""
import copy
import ast
import hashlib
import json
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

import test_cgyro_storage as fixtures
import test_checkpoint_resources as checkpoints
from test_checkpoint_resources import Input
from OMFITlib_cgyro_result_index import (result_records, select_result, selected_result,
                                        find_record, scan_scope, result_identity, release_published_results)
from OMFITlib_cgyro_continue import continuation_plan, prepare_point
from OMFITlib_cgyro_payload import pack_results
from OMFITlib_cgyro_input_identity import cache_parameters, cache_competing_parameters, read_parameters

storage, db, archive = fixtures.storage, fixtures.db_api, fixtures.archive_api


class ResultIdentityTests(unittest.TestCase):
    setUp = checkpoints.ResourceContinuationTests.setUp

    def test_direct_selection_and_header_lists_do_not_enumerate_other_point_tables(self):
        class ClosedTable(dict):
            def items(self):
                raise AssertionError('unselected point table traversed')
            def values(self):
                raise AssertionError('unselected point table traversed')
            def __iter__(self):
                raise AssertionError('unselected point table traversed')
        module = {}
        info, row, ref = self.result(module, 'target')
        case = self.public(module, info, row, ref)
        db.run_records(module).clear()
        selected = next(iter(result_records(module, include_tasks=False)))
        unrelated = copy.deepcopy(case)
        unrelated['__SCANS__']['N_ENERGY']['tasks'] = ClosedTable()
        unrelated['__TASKS__'] = ClosedTable()
        module['RUN_DB']['Other'] = {'nr=1_rho=0.33': {'T': unrelated}}
        self.assertEqual(len(result_records(module, include_tasks=False)), 2)
        entry = find_record(module, selected)
        self.assertEqual(entry['runid'], 'Jet')
        self.assertEqual(len(entry['tasks']), 1)
        self.assertEqual(set(archive.catalog_runs(module, 'Jet', info['case_id'])), {'Jet'})
        import OMFITlib_cgyro_task_catalog as catalog
        catalog.task_catalog(module)  # Task list also uses header counts.

    def test_collection_summary_and_verified_recollection_reuse_survive_metadata_roundtrip(self):
        import OMFITlib_cgyro_retry as retry
        import numpy as np
        module = {}
        info, row, ref = self.result(module, 'summary')
        owner = fixtures.OMFITcgyro(self.base / 'summary')
        values = dict(t=np.array([0., .1, .2, .3]), n_time=4)
        with patch.object(fixtures.OMFITcgyro, '__getitem__', lambda obj, name: values[name], create=True):
            stored = storage.store_result(module, owner, summary_row=row)
        summary = row['result_summary']
        self.assertEqual(summary['sample_count'], 4)
        self.assertEqual(summary['final_time'], .3)
        self.assertTrue(summary['checkpoint_available'])
        self.assertGreater(summary['file_sizes']['bin.cgyro.restart'], 0)
        self.assertNotIn('omega', summary)
        manifest = dict(info, workDir='/run/original', point_table={'p000001': row})
        row['source_directory'] = '/run/original/p000001'
        module['RUN_MANIFEST'] = manifest
        db.run_records(module)['summary']['cases'] = {'p000001': stored}
        manifest = json.loads(json.dumps(manifest))
        with patch.object(storage, 'archive_inventory', side_effect=AssertionError('rehash immutable files')):
            self.assertEqual(storage.store_result(module, stored), stored)
            self.assertEqual(retry.collected_points(module, manifest), {'p000001'})
            manifest['point_workdirs'] = {'p000001': '/run/retry'}
            self.assertEqual(retry.collected_points(module, manifest), set())

    def test_legacy_pending_header_does_not_open_its_point_table(self):
        class ClosedTable(dict):
            def items(self):
                raise AssertionError('legacy point table traversed for header')
            def values(self):
                raise AssertionError('legacy point table traversed for header')
        module = {}
        info, row, ref = self.result(module, 'legacy')
        record = db.run_records(module)['legacy']
        record['manifest'] = dict(info, status='cancelled', collection_status='partial', point_table=ClosedTable())
        record['cases'] = {'p000001': ref}
        entries = result_records(module, include_tasks=False)
        self.assertIn('version:legacy', entries)
        self.assertNotIn('tasks', entries['version:legacy'])

    def test_scoped_bookkeeping_does_not_compute_global_storage_totals(self):
        module = {}
        info, row, ref = self.result(module, 'scoped')
        with patch.object(storage, '_storage_totals', side_effect=AssertionError('global inventory scan')):
            report = storage.compact_storage(module, run_token='scoped')
        self.assertEqual(report['scope'], 'run')

    def test_failed_longer_continuation_cannot_replace_a_valid_point(self):
        module = {}
        info, row, old = self.result(module, 'failed-old')
        row.update(solver_status='max_time', final_time=.3)
        case = self.public(module, info, row, old)
        new_info, new_row, new = self.result(module, 'failed-new')
        new_row.update(solver_status='failed', final_time=.8, status='partial', scheduler_state='FAILED')
        archive.store_scan(case, {'N_ENERGY': {'8': {'lin': {'0.1': new}}}}, new_info,
                           {'p000001': new_row}, prefer_progress=True)
        self.assertEqual(case['N_ENERGY']['8']['lin']['0.1'], old)

    def test_collection_rejects_mismatched_input_before_caching_identity(self):
        module = {}
        info, row, _ = self.result(module, 'mismatched-input', generated={'MASS_1': 1.})
        directory = self.base / 'mismatched-input'
        original = (directory / 'input.cgyro').read_bytes()
        for change, expected in (({'N_ENERGY': 10}, 'disagrees with input.cgyro: N_ENERGY'),
                                 ({'MASS_1': 2.}, 'disagrees with input.cgyro')):
            with self.subTest(change=change):
                (directory / 'input.cgyro').write_bytes(original)
                data = Input(directory / 'input.cgyro')
                data.update(change)
                data.deploy(directory / 'input.cgyro')
                uncached = dict(row)
                for name in ('input_parameters', 'input_parameter_source', 'input_parameter_sha256'):
                    uncached.pop(name, None)
                with self.assertRaisesRegex(ValueError, expected):
                    cache_parameters(uncached, info, fixtures.OMFITcgyro(directory))
                self.assertNotIn('input_parameters', uncached)

    def test_collection_checks_frozen_input_hash_without_requiring_generated_input(self):
        module = {}
        info, row, _ = self.result(module, 'legacy-mismatched-input')
        directory = self.base / 'legacy-mismatched-input'
        owner = fixtures.OMFITcgyro(directory)
        row['input_sha256'] = hashlib.sha256((directory / 'input.cgyro').read_bytes()).hexdigest()
        self.assertEqual(cache_parameters(row, info, owner)['N_ENERGY'], 8)
        self.assertNotIn('input_parameters', row)  # No guessed solver defaults for legacy files.
        data = Input(directory / 'input.cgyro')
        data['N_ENERGY'] = 10
        data.deploy(directory / 'input.cgyro')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            cache_parameters(row, info, owner)
        row.pop('input_sha256')
        with self.assertRaisesRegex(ValueError, 'coordinate: N_ENERGY'):
            cache_parameters(row, info, owner)
        (directory / 'input.cgyro').write_text('KY=0.1\n')
        self.assertEqual(cache_parameters(row, info, owner), {'KY': .1})
        self.assertNotIn('input_parameters', row)

    def result(self, module, token, ky=.1, input_energy=8, corrupt=False, extra_values=None, generated=None):
        directory = self.base / token
        shutil.copytree(self.original, directory)
        data = Input(directory / 'input.cgyro')
        data['KY'], data['N_ENERGY'] = ky, input_energy
        data.update(extra_values or {})
        data.update({name: value for name, value in (generated or {}).items() if name in data})
        data.deploy(directory / 'input.cgyro')
        if generated is not None:
            expanded = dict(data, **generated)
            (directory / 'input.cgyro.gen').write_text(''.join('{:.17g} {}\n'.format(value, name) for name, value in expanded.items()))
        (directory / 'out.cgyro.info').write_text('Version ' + token + '\nLinear terminated at max time\n')
        if corrupt:
            (directory / 'bin.cgyro.restart').write_bytes(b'broken checkpoint')
        ref = storage.store_result(module, fixtures.OMFITcgyro(directory))
        row = dict(values={'N_ENERGY': 8, 'KY': ky}, result_path=['N_ENERGY', '8', 'lin', str(ky)],
                   final_time=.3, status='loaded', run_token=token)
        row['values'].update(extra_values or {})
        if generated is not None:
            cache_parameters(row, {}, fixtures.OMFITcgyro(directory))
        info = dict(run_token=token, runid='Jet', case_id='nr=1__rho=0.33__ion=T',
                    nr=1, source_nr=1, mass='T', ion_case='T', rho=.33,
                    dimensions=1, scan_dimensions=1, scan_axes=[dict(name='N_ENERGY', values=[8])],
                    runtime=self.previous, server='test', case_tag='linear',
                    points=['p000001'], loaded_points=['p000001'], partial_points=[],
                    point_table={'p000001': copy.deepcopy(row)}, status='published', collection_status='complete')
        db.run_records(module, dict)[token] = dict(manifest=info, cases={'p000001': ref}, retained_result_version=True)
        return info, row, ref

    def test_generated_defaults_distinguish_physical_points_beyond_scan_axes(self):
        from OMFITlib_cgyro_scan_view import comparison_case_view
        module = {}
        info, row, first = self.result(module, 'profile-a', generated={'MASS_1': 1., 'ERROR_TOL': 1e-4})
        case = self.public(module, info, row, first)
        other_info, other_row, second = self.result(module, 'profile-b', generated={'MASS_1': 1.5, 'ERROR_TOL': 1e-4})
        archive.store_scan(case, {'N_ENERGY': {'8': {'lin': {'0.1': second}}}}, other_info, {'p000001': other_row})
        self.assertEqual(len(case['__TASKS__']), 2)
        view, selected, _, errors = comparison_case_view(case, {'N_ENERGY': [8]},
            {'N_ENERGY': dict(values={'MASS_1': [1.5]})})
        self.assertFalse(errors)
        self.assertEqual(view[next(iter(selected))][8.]['lin']['0.1'], second)

    def test_equal_generated_inputs_share_one_owner_across_scan_views(self):
        for continuation, converged, winner in ((False, True, 'new'), (True, True, 'old'), (True, False, 'new')):
            with self.subTest(continuation=continuation, converged=converged):
                module = {}
                suffix = str(continuation) + str(converged)
                info, row, old = self.result(module, 'cross-old-' + suffix, generated={'ERROR_TOL': 1e-4})
                row.update(final_time=.3, solver_status='converged' if converged else 'max_time')
                case = self.public(module, info, row, old)
                other_info, other_row, other = self.result(module, 'cross-other-' + suffix, ky=-.1, generated={'ERROR_TOL': 1e-4})
                archive.store_scan(case, {'N_ENERGY': {'8': {'lin': {'-0.1': other}}}}, other_info, {'p000001': other_row})
                prior = copy.deepcopy(case)
                new_info, new_row, new = self.result(module, 'cross-new-' + suffix, generated={'ERROR_TOL': 1e-4})
                new_info['scan_axes'] = [dict(name='N_XI', values=[4])]
                new_row.update(values={'N_XI': 4, 'KY': .1}, result_path=['N_XI', '4', 'lin', '0.1'],
                               final_time=.4, solver_status='max_time')
                new_row['result_info'] = copy.deepcopy(new_info)
                incoming = {'p000001': new_row}
                archive.store_scan(case, {'N_XI': {'4': {'lin': {'0.1': new}}}}, new_info, incoming, prefer_progress=continuation)
                archive.share_matching_inputs(case, new_info, incoming, prefer_progress=continuation)
                archive.validate_preserved_scans([prior], case, 'N_XI', incoming)
                chosen = old if winner == 'old' else new
                self.assertEqual(case['N_ENERGY']['8']['lin']['0.1'], chosen)
                self.assertEqual(case['N_XI']['4']['lin']['0.1'], chosen)
                self.assertEqual(case['N_ENERGY']['8']['lin']['-0.1'], other)
                self.assertEqual(set(case['__SCANS__']), {'N_ENERGY', 'N_XI'})
                self.assertEqual(sum(len(rows) for _, _, rows in archive.case_scans(case)), 3)

    def test_legacy_job_alias_uses_only_verified_same_owner_parameters_for_retirement(self):
        module = {}
        info, row, old = self.result(module, 'alias-old', generated={'ERROR_TOL': 1e-4})
        db.run_records(module)['alias-old']['manifest']['point_table']['p000001'].pop('input_parameters')
        prior = self.public(module, info, row, old)
        other_info, other_row, _ = self.result(module, 'alias-other', ky=-.1)
        next_info, next_row, new = self.result(module, 'alias-new', generated={'ERROR_TOL': 1e-4})
        current = self.public(module, next_info, next_row, new)
        removed = release_published_results(module, current, verified_cases=[prior])
        self.assertIn(storage.reference_id(old), removed)
        self.assertNotIn('p000001', db.run_records(module)['alias-old']['cases'])
        self.assertIn('p000001', db.run_records(module)['alias-other']['cases'])

    def test_generated_parameter_index_queries_open_no_result_files(self):
        module = {}
        info, row, ref = self.result(module, 'metadata-gen', generated={'ERROR_TOL': 1e-4})
        self.public(module, info, row, ref)
        with patch('builtins.open', side_effect=AssertionError('Index query opened a result file')):
            entries = result_records(module)
            entry = next(iter(entries.values()))
            selected = select_result(module, entry, 'p000001')
            self.assertEqual(selected['row']['input_parameters']['ERROR_TOL'], 1e-4)

    def test_generated_control_changes_replace_the_same_point_but_tolerance_does_not(self):
        module = {}
        info, row, first = self.result(module, 'controls-a', generated={'ERROR_TOL': 1e-4, 'MPI_RANK_ORDER': 1})
        case = self.public(module, info, row, first)
        info2, row2, second = self.result(module, 'controls-b', generated={'ERROR_TOL': 1e-4, 'MPI_RANK_ORDER': 2, 'MAX_TIME': 1200})
        archive.store_scan(case, {'N_ENERGY': {'8': {'lin': {'0.1': second}}}}, info2, {'p000001': row2})
        self.assertEqual(len(case['__TASKS__']), 1)
        self.assertEqual(case['N_ENERGY']['8']['lin']['0.1'], second)
        info3, row3, third = self.result(module, 'controls-c', generated={'ERROR_TOL': 1e-5})
        archive.store_scan(case, {'N_ENERGY': {'8': {'lin': {'0.1': third}}}}, info3, {'p000001': row3})
        self.assertEqual(len(case['__TASKS__']), 2)

    def test_generated_input_mismatch_rejects_only_that_selected_point(self):
        module = {}
        _, _, ref = self.result(module, 'mismatch-gen', generated={'ERROR_TOL': 1e-4})
        path = Path(storage.resolve_result(module, ref).filename) / 'input.cgyro'
        with path.open('a') as handle:
            handle.write('ERROR_TOL=1e-5\n')
        with self.assertRaisesRegex(ValueError, 'input.cgyro.gen disagrees'):
            continuation_plan(module, 'mismatch-gen', ['p000001'], 1.)

    def test_generated_defaults_are_frozen_into_restart_input(self):
        module = {}
        self.result(module, 'defaults', generated={'ERROR_TOL': 1e-5, 'MASS_1': 1.5})
        plan = continuation_plan(module, 'defaults', ['p000001'], 1.)
        current, _, _ = prepare_point(module, plan, 'p000001', str(self.base / 'defaults-stage'), Input, runtime=self.current)
        self.assertEqual((current['ERROR_TOL'], current['MASS_1'], current['MAX_TIME']), (1e-5, 1.5, 1.))

    def test_restart_keeps_integer_defaults_in_solver_readable_form(self):
        class TypedInput(Input):
            """Match OMFIT's type-sensitive save; :g would hide this regression."""
            def __init__(self, filename=None, values=None):
                if values is None:
                    values = {key: ast.literal_eval(value) for key, value in
                              (line.split('=', 1) for line in Path(filename).read_text().splitlines())}
                super().__init__(filename, values)

            def duplicate(self):
                return TypedInput(values=dict(self))

            def deploy(self, filename):
                Path(filename).write_text(''.join('{}={}\n'.format(key, value) for key, value in self.items()))
                self.filename = str(filename)

        module = {}
        integers = dict(E_FIX=2, RESTART_STEP=10, RESTART_PRESERVATION_MODE=3, MPIIO_STRIPE_FACTOR=0,
                        PROFILE_MODEL=1, COLLISION_FIELD_MAX_L=-2, FULL_T_ASYM_PRINT_FLAG=0)
        self.result(module, 'typed-defaults', generated=dict(integers, ERROR_TOL=1e-5, MASS_1=1.5))
        plan = continuation_plan(module, 'typed-defaults', ['p000001'], 1.)
        stage = self.base / 'typed-stage'
        current, _, _ = prepare_point(module, plan, 'p000001', str(stage), TypedInput, runtime=self.current)
        saved = dict(line.split('=', 1) for line in (stage / 'input.cgyro').read_text().splitlines())
        for name, value in integers.items():
            self.assertIs(type(current[name]), int, name)
            self.assertEqual(saved[name], str(value), name)
        self.assertEqual(float(saved['ERROR_TOL']), 1e-5)
        self.assertEqual(float(saved['MASS_1']), 1.5)

    def test_input_parser_preserves_integer_and_real_tokens_without_rounding(self):
        tokens = {'RESTART_STEP': '10', 'COLLISION_FIELD_MAX_L': '-2', 'PROFILE_MODEL': '+1',
                  'LARGE_INTEGER': '9007199254740993', 'UP_THETA': '1.0',
                  'MASS_1': '1D0', 'ERROR_TOL': '1.000D-4', 'KY': '-0.5'}
        for generated in (False, True):
            with self.subTest(generated=generated):
                path = self.base / 'typed-input'
                path.write_text(''.join((value + ' ' + name if generated else name + '=' + value) + '\n'
                                        for name, value in tokens.items()))
                values, digest = read_parameters(path, generated=generated)
                self.assertEqual(digest, hashlib.sha256(path.read_bytes()).hexdigest())
                for name in ('RESTART_STEP', 'COLLISION_FIELD_MAX_L', 'PROFILE_MODEL', 'LARGE_INTEGER'):
                    self.assertIs(type(values[name]), int, name)
                    self.assertEqual(values[name], int(tokens[name]))
                for name in ('UP_THETA', 'MASS_1', 'ERROR_TOL', 'KY'):
                    self.assertIs(type(values[name]), float, name)
                self.assertEqual(values['ERROR_TOL'], 1e-4)

    def test_old_generated_input_is_read_only_for_competing_coordinates(self):
        module = {}
        info, row, first = self.result(module, 'cache-a', generated={'ERROR_TOL': 1e-4})
        row.pop('input_parameters')
        case = self.public(module, info, row, first)
        other_info, other_row, other = self.result(module, 'cache-other', ky=-.1)
        other_case = self.public(module, other_info, other_row, other)
        case = archive.combine_cases([case, other_case])
        new_info, new_row, new = self.result(module, 'cache-new', generated={'ERROR_TOL': 1e-4})
        reads = []
        def resolve(node):
            self.assertEqual(node, first)
            reads.append(node)
            return storage.resolve_result(module, node)
        cache_competing_parameters(case, new_info, {'p000001': new_row}, resolve)
        self.assertEqual(len(reads), 1)
        archive.store_scan(case, {'N_ENERGY': {'8': {'lin': {'0.1': new}}}}, new_info, {'p000001': new_row})
        self.assertEqual(len(case['__TASKS__']), 2)

    def test_input_parser_normalizes_fortran_numbers_and_rejects_duplicates(self):
        path = self.base / 'numeric.gen'
        path.write_text('1.000D-4 ERROR_TOL\n-0.5 KY\n')
        values, _ = read_parameters(path, generated=True)
        self.assertEqual(values, {'ERROR_TOL': 1e-4, 'KY': -.5})
        path.write_text('1 ERROR_TOL\n2 ERROR_TOL\n')
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            read_parameters(path, generated=True)

    def test_rounded_legacy_paths_keep_the_exact_saved_coordinates(self):
        case = {}
        info = dict(scan_axes=[dict(name='Q', values=[1.234561, 1.234562])], dimensions=1)
        for index, value in enumerate((1.234561, 1.234562)):
            row = dict(result_path=['Q', '1.23456', 'lin', '0.10000'], values={'Q': value, 'KY': .1})
            archive.store_scan(case, {'Q': {'1.23456': {'lin': {'0.10000': {'__RESULT_REF__': str(index) * 64}}}}},
                               info, {'p000001': row})
        self.assertEqual(len(case['__TASKS__']), 2)
        self.assertEqual({r['values']['Q'] for r in case['__TASKS__'].values()}, {1.234561, 1.234562})
        self.assertEqual(len({tuple(r['result_path']) for r in case['__TASKS__'].values()}), 2)

    def test_fixed_parameter_collisions_remain_distinct_through_merge_plot_and_restart(self):
        from OMFITlib_cgyro_scan_view import comparison_case_view
        module = {}
        old_info, old_row, old = self.result(module, 'tol-loose', extra_values={'ERROR_TOL': 1e-4})
        first = self.public(module, old_info, old_row, old)
        info, row, tight = self.result(module, 'tol-tight', extra_values={'ERROR_TOL': 1e-5})
        second = self.public(module, info, row, tight)
        case = archive.combine_cases([first, second])
        archive.install_case(module['RUN_DB']['Jet'], info['case_id'], case)
        self.assertEqual(len(case['__TASKS__']), 2)
        self.assertEqual(len({tuple(r['result_path']) for r in case['__TASKS__'].values()}), 2)
        self.assertTrue(all('coordinate_path' in r for r in case['__TASKS__'].values()))
        view, selected, _, errors = comparison_case_view(case, {'N_ENERGY': [8]},
            {'N_ENERGY': dict(values={'ERROR_TOL': [1e-5]})})
        self.assertFalse(errors)
        self.assertEqual(len(selected), 1)
        self.assertEqual(view[next(iter(selected))][8.]['lin']['0.1'], tight)
        module['RUN_DB'].pop('__RUNS__')
        entry = next(iter(result_records(module).values()))
        plan = continuation_plan(module, entry['selection_key'], list(entry['tasks']), 1.)
        for point in plan['points']:
            current, metadata, _ = prepare_point(module, plan, point, str(self.base / ('stage-' + point)), Input, runtime=self.current)
            self.assertEqual(current['ERROR_TOL'], metadata['values']['ERROR_TOL'])
            self.assertEqual(metadata['coordinate_path'][0], 'N_ENERGY')
        # A new run at one exact tolerance replaces just that coordinate.
        next_info, next_row, replacement = self.result(module, 'tol-new', extra_values={'ERROR_TOL': 1e-5})
        archive.store_scan(case, {'N_ENERGY': {'8': {'lin': {'0.1': replacement}}}}, next_info, {'p000001': next_row})
        self.assertEqual(len(case['__TASKS__']), 2)
        owners = {storage.reference_id(fixtures.continuation.point_result(case, r)) for r in case['__TASKS__'].values()}
        self.assertEqual(owners, {storage.reference_id(old), storage.reference_id(replacement)})

    def test_staging_detects_a_valid_checkpoint_changed_after_selection(self):
        module = {}
        _, _, ref = self.result(module, 'stage-race')
        plan = continuation_plan(module, 'stage-race', ['p000001'], 1.)
        path = Path(storage.resolve_result(module, ref).filename) / 'bin.cgyro.restart'
        content = bytearray(path.read_bytes()); content[-1] ^= 1
        path.write_bytes(content)
        with self.assertRaisesRegex(ValueError, 'checkpoint changed'):
            prepare_point(module, plan, 'p000001', str(self.base / 'race-stage'), Input, runtime=self.current)

    def test_stale_ancestor_time_does_not_set_the_selected_results_restart_target(self):
        module = {}
        info, row, ref = self.result(module, 'own-time')
        row['continuation'] = dict(source_token='missing', previous_final_time=9999.)
        self.public(module, info, row, ref)
        module['RUN_DB'].pop('__RUNS__')
        entry = next(iter(result_records(module).values()))
        plan = continuation_plan(module, entry['selection_key'], ['p000001'], 1.)
        _, metadata, _ = prepare_point(module, plan, 'p000001', str(self.base / 'own-stage'), Input, runtime=self.current)
        self.assertEqual(metadata['continuation']['previous_final_time'], .3)

    def test_missing_legacy_convergence_cache_reads_only_the_competing_point(self):
        module = {}
        info, row, ref = self.result(module, 'legacy-status')
        (Path(storage.resolve_result(module, ref).filename) / 'out.cgyro.info').write_text('Linear converged\n')
        first = self.public(module, info, row, ref)
        other_info, other_row, other = self.result(module, 'legacy-other', ky=-.1)
        second = self.public(module, other_info, other_row, other)
        case = archive.combine_cases([first, second])
        reads = []
        def resolve(node):
            reads.append(storage.reference_id(node))
            self.assertEqual(node, ref)
            return storage.resolve_result(module, node)
        archive.cache_merge_status(case, info, {'p000001': row}, resolve)
        self.assertEqual(reads, [storage.reference_id(ref)])
        incoming, task, new = self.result(module, 'later-unconverged')
        task.update(final_time=1200., solver_status='max_time')
        archive.store_scan(case, {'N_ENERGY': {'8': {'lin': {'0.1': new}}}}, incoming, {'p000001': task}, prefer_progress=True)
        self.assertEqual(case['N_ENERGY']['8']['lin']['0.1'], ref)

    def test_publishing_does_not_retire_an_active_jobs_retry_files(self):
        module = {}
        self.result(module, 'active')
        record = db.run_records(module)['active']
        record['manifest'].update(status='submitted_or_finished', collection_status='partial',
            scheduler_sync=dict(active=True, terminal=False, outcome='running'))
        record['inputs'] = {'p000001': {'zip': 'live-input'}}
        info, row, ref = self.result(module, 'public')
        case = self.public(module, info, row, ref)
        release_published_results(module, case)
        self.assertIn('p000001', record['cases'])
        self.assertIn('p000001', record['inputs'])
        self.assertNotIn('retired_points', record)

    def public(self, module, info, row, ref):
        case = {}
        payload = {'N_ENERGY': {'8': {'lin': {str(row['values']['KY']): ref}}}}
        archive.store_scan(case, payload, info, {'p000001': row})
        archive.install_case(module['RUN_DB'].setdefault('Jet', {}), info['case_id'], case)
        return case

    def test_public_checkpoint_survives_all_job_records_missing(self):
        module = {}
        info, row, ref = self.result(module, 'gone-parent')
        self.public(module, info, row, ref)
        module['RUN_DB'].pop('__RUNS__')
        module['RUN_HISTORY'] = {'poison': object()}
        entry = next(iter(result_records(module).values()))
        plan = continuation_plan(module, entry['selection_key'], ['p000001'], 1.)
        self.assertEqual(plan['selections']['p000001']['result_id'], storage.reference_id(ref))
        current, _, _ = prepare_point(module, plan, 'p000001', str(self.base / 'stage'), Input, runtime=self.current)
        self.assertEqual(current['MAX_TIME'], 1.)

    def test_same_point_id_in_different_jobs_never_supplies_missing_point(self):
        module = {}
        self.result(module, 'positive', ky=.1)
        _, _, negative = self.result(module, 'negative', ky=-.1)
        plan = continuation_plan(module, 'negative', ['p000001'], 1.)
        self.assertEqual(plan['rows']['p000001']['values']['KY'], -.1)
        self.assertEqual(plan['selections']['p000001']['result_id'], storage.reference_id(negative))
        with self.assertRaisesRegex(ValueError, 'Unindexed'):
            continuation_plan(module, 'negative', ['p000002'], 1.)

    def test_dialog_rejects_replaced_result_without_substituting_current_files(self):
        module = {}
        info, row, old = self.result(module, 'old')
        self.public(module, info, row, old)
        entry = next(e for e in result_records(module).values() if e['kind'] == 'scan')
        binding = select_result(module, entry, 'p000001')
        second_info, second_row, new = self.result(module, 'new')
        self.public(module, second_info, second_row, new)
        module['RUN_DB'].pop('__RUNS__')
        with self.assertRaisesRegex(ValueError, 'replaced'):
            continuation_plan(module, 'stale dialog label', ['p000001'], 1.,
                              selections={'p000001': binding}, scope=scan_scope(entry))
        # Closing the stale dialog and explicitly selecting current RUN_DB data works.
        latest = next(iter(result_records(module).values()))
        plan = continuation_plan(module, latest['selection_key'], ['p000001'], 1.)
        self.assertEqual(plan['selections']['p000001']['result_id'], storage.reference_id(new))

    def test_only_selected_point_files_are_read(self):
        module = {}
        info, row, ref = self.result(module, 'chosen')
        self.public(module, info, row, ref)
        _, _, other = self.result(module, 'unselected', ky=-.1)
        owner = storage.resolve_result(module, other)
        class Unreadable(fixtures.OMFITcgyro):
            @property
            def filename(self):
                raise AssertionError('Unselected files accessed')
        module['RUN_DB']['__STORE__'][storage.reference_id(other)] = object.__new__(Unreadable)
        plan = continuation_plan(module, 'chosen', ['p000001'], 1.)
        prepare_point(module, plan, 'p000001', str(self.base / 'only-selected'), Input, runtime=self.current)
        self.assertTrue(Path(owner.filename).is_dir())

    def test_bad_selected_input_does_not_block_good_selected_point(self):
        module = {}
        self.result(module, 'good')
        self.result(module, 'wrong-input', input_energy=16)
        good = select_result(module, find_record(module, 'good'), 'p000001')
        bad = select_result(module, find_record(module, 'wrong-input'), 'p000001')
        plan = continuation_plan(module, 'explicit selection', ['p000001', 'p000002'], 1.,
                                 selections={'p000001': good, 'p000002': bad}, scope=scan_scope(find_record(module, 'good')))
        self.assertEqual(plan['points'], ['p000001'])
        self.assertIn('N_ENERGY', plan['rejected']['p000002'])
        with self.assertRaisesRegex(ValueError, 'N_ENERGY'):
            continuation_plan(module, 'wrong-input', ['p000001'], 1.)

    def test_bad_selected_checkpoint_is_blocked_without_parent(self):
        module = {}
        info, row, ref = self.result(module, 'damaged', corrupt=True)
        self.public(module, info, row, ref)
        module['RUN_DB'].pop('__RUNS__')
        entry = next(iter(result_records(module).values()))
        with self.assertRaisesRegex(ValueError, 'checkpoint'):
            continuation_plan(module, entry['selection_key'], ['p000001'], 1.)

    def test_changed_native_checkpoint_bytes_fail_stored_checksum(self):
        module = {}
        _, _, ref = self.result(module, 'changed')
        path = Path(storage.resolve_result(module, ref).filename) / 'bin.cgyro.restart'
        data = bytearray(path.read_bytes())
        data[-1] ^= 1  # Still a finite payload and a structurally valid header.
        path.write_bytes(data)
        with self.assertRaisesRegex(ValueError, 'checksum'):
            continuation_plan(module, 'changed', ['p000001'], 1.)

    def test_full_identity_checks_signed_ky_links_radius_and_ion(self):
        module = {}
        info, row, _ = self.result(module, 'identity')
        info['scan_axes'][0]['linked'] = [dict(name='N_XI')]
        with self.assertRaisesRegex(ValueError, 'Missing linked'):
            result_identity(info, row)
        row['values']['N_XI'] = 4
        first = result_identity(info, row)
        row['result_path'][-1] = '-0.1'
        with self.assertRaisesRegex(ValueError, 'KY'):
            result_identity(info, row)
        row['values']['KY'] = -.1
        self.assertNotEqual(first, result_identity(info, row))
        info['case_id'] = 'nr=1__rho=0.33__ion=D'
        with self.assertRaisesRegex(ValueError, 'ion configuration'):
            result_identity(info, row)
        info['ion_case'] = 'D'
        self.assertNotEqual(first['case_id'], result_identity(info, row)['case_id'])
        info['rho'] = .99
        with self.assertRaisesRegex(ValueError, 'radius'):
            result_identity(info, row)

    def test_fresh_scan_always_replaces_even_a_longer_converged_result(self):
        module = {}
        info, row, old = self.result(module, 'fresh-old')
        row.update(final_time=600., solver_status='converged')
        case = self.public(module, info, row, old)
        incoming, task, new = self.result(module, 'fresh-new')
        task.update(final_time=1., solver_status='failed', status='partial', resume_pending=True)
        payload = {'N_ENERGY': {'8': {'lin': {'0.1': new}}}}
        archive.store_scan(case, payload, incoming, {'p000001': task})
        self.assertEqual(case['N_ENERGY']['8']['lin']['0.1'], new)
        self.assertEqual(len(case['__TASKS__']), 1)
        candidates = release_published_results(module, case)
        storage.prune_storage(module, result_ids=candidates)
        self.assertNotIn(storage.reference_id(old), module['RUN_DB']['__STORE__'])
        self.assertEqual(len(result_records(module)), 1)
        self.assertIn('fresh-old', db.run_records(module))  # Provenance is still available.

    def test_continuation_prefers_solver_convergence_then_simulated_time(self):
        scenarios = [
            ('converged', 30., 'max_time', 600., 'old'),
            ('failed', 600., 'converged', 30., 'new'),
            ('converged', 40., 'converged', 30., 'old'),
            ('converged', 30., 'converged', 40., 'new'),
            ('max_time', 40., 'failed', 30., 'old'),
            ('failed', 30., 'max_time', 40., 'new'),
            ('failed', 0., 'failed', None, 'old'),
            ('unknown', None, 'failed', 0., 'new'),
        ]
        for number, (old_state, old_time, new_state, new_time, winner) in enumerate(scenarios):
            with self.subTest(scenario=number):
                module = {}
                info, row, old = self.result(module, 'policy-old-' + str(number))
                row.update(solver_status=old_state, final_time=old_time, status='loaded')
                case = self.public(module, info, row, old)
                incoming, task, new = self.result(module, 'policy-new-' + str(number))
                # Slurm COMPLETED/collection status does not prove convergence.
                task.update(solver_status=new_state, final_time=new_time, scheduler_state='COMPLETED',
                            status='partial', resume_pending=True)
                payload = {'N_ENERGY': {'8': {'lin': {'0.1': new}}}}
                archive.store_scan(case, payload, incoming, {'p000001': task}, prefer_progress=True)
                self.assertEqual(case['N_ENERGY']['8']['lin']['0.1'], old if winner == 'old' else new)
                candidates = release_published_results(module, case)
                storage.prune_storage(module, result_ids=candidates)
                self.assertEqual(len(module['RUN_DB']['__STORE__']), 1)
                self.assertEqual(len(result_records(module)), 1)

    def test_one_point_merge_retains_other_signed_ky_and_does_not_open_it(self):
        module = {}
        info, row, positive = self.result(module, 'positive-old')
        first = self.public(module, info, row, positive)
        negative_info, negative_row, negative = self.result(module, 'negative-kept', ky=-.1)
        second = self.public(module, negative_info, negative_row, negative)
        case = archive.combine_cases([first, second])
        archive.install_case(module['RUN_DB']['Jet'], info['case_id'], case)
        current, task, replacement = self.result(module, 'positive-new')
        before = copy.deepcopy(case['N_ENERGY']['8']['lin']['-0.1'])
        payload = {'N_ENERGY': {'8': {'lin': {'0.1': replacement}}}}
        with patch.object(storage, 'resolve_result', side_effect=AssertionError('Read unselected result')):
            archive.store_scan(case, payload, current, {'p000001': task}, prefer_progress=True)
            candidates = release_published_results(module, case)
            storage.prune_storage(module, result_ids=candidates)
        self.assertEqual(case['N_ENERGY']['8']['lin']['-0.1'], before)
        self.assertEqual(len(case['__TASKS__']), 2)
        self.assertEqual(len(module['RUN_DB']['__STORE__']), 2)

    def test_packed_files_and_literal_index_reopen_without_old_directories(self):
        """Persistence boundary, independent of native GUI serialization tests."""
        module = {}
        info, row, ref = self.result(module, 'persist')
        self.public(module, info, row, ref)
        pack_results(module, storage.directory_inventory)
        pool = module['RUN_DB']['__STORE__']
        owners = pool.pop('__FILES__')
        persisted = json.loads(json.dumps(module))
        pool['__FILES__'] = owners
        saved = self.base / 'saved-files'; saved.mkdir()
        relocated = {}
        for key, owner in owners.items():
            target = saved / key
            shutil.copyfile(owner.filename, target)
            relocated[key] = fixtures.OMFITpath(target)
        persisted['RUN_DB']['__STORE__']['__FILES__'] = relocated
        persisted['RUN_DB'].pop('__RUNS__')
        entry = next(iter(result_records(persisted).values()))
        plan = continuation_plan(persisted, entry['selection_key'], ['p000001'], 1.)
        self.assertEqual(plan['selections']['p000001']['result_id'], storage.reference_id(ref))
        prepare_point(persisted, plan, 'p000001', str(self.base / 'reopened-stage'), Input, runtime=self.current)


if __name__ == '__main__':
    unittest.main()
