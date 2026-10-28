"""Result callbacks after OMFIT removes its temporary LIB importer.

The unchanged native executor supplies library registration, dependency injection
and cleanup. File readers use the existing temporary-file adapters. A rejecting
finder prevents the repository's ordinary Python path from hiding late imports.
This exercises callback bodies without claiming a complete desktop session.
"""
from contextlib import contextmanager
import ast
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import test_cgyro_result_identity as fixtures
import test_cgyro_storage as storage_fixtures
from test_checkpoint_resources import Input

REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO.parents[2] / 'OMFIT-source-ASIPP_unstable/omfit'
sys.path.insert(0, str(REPO / 'tools'))
from validate_native_execution import NativeHost


class RejectCallbackImports:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith('OMFITlib_'):
            raise AssertionError('Callback tried to reimport unloaded library: ' + fullname)
        return None


class ResultCallbackImportTests(unittest.TestCase):
    def setUp(self):
        if not (SOURCE / 'omfit_classes/omfit_python.py').is_file():
            self.skipTest('The supplied OMFIT source is required')
        self.host = NativeHost(SOURCE)
        self.files = fixtures.ResultIdentityTests('runTest')
        self.files.setUp()
        self.addCleanup(self.files.doCleanups)

    @contextmanager
    def callbacks(self, imports):
        """Load through native LIB nodes, then call after the hook has gone."""
        previous = {name: module for name, module in sys.modules.items()
                    if name.startswith('OMFITlib_')}
        paths, hooks = list(sys.path), list(sys.meta_path)
        libraries = {path.resolve() for path in (REPO / 'CGYRO_TGLF_scan').rglob('LIB')}
        libraries.add((REPO / 'OMFITtemplates/LIB').resolve())
        try:
            for name in previous:
                del sys.modules[name]
            sys.path[:] = [path for path in paths if Path(path).resolve() not in libraries]
            exported = self.host.execute(imports)
            self.assertEqual(sys.meta_path, hooks)
            self.assertFalse(any(name.startswith('OMFITlib_') for name in sys.modules))
            sys.meta_path.insert(0, RejectCallbackImports())
            with patch.dict(sys.modules, {'omfit_classes.utils_base': self.host.registry}):
                yield exported
            self.assertFalse(any(name.startswith('OMFITlib_') for name in sys.modules))
        finally:
            sys.meta_path[:] = hooks
            sys.path[:] = paths
            for name in list(sys.modules):
                if name.startswith('OMFITlib_'):
                    del sys.modules[name]
            sys.modules.update(previous)

    def public_point(self, module, token='chosen', ky=.1):
        info, row, reference = self.files.result(module, token, ky=ky, generated={'ERROR_TOL': 1e-4, 'RESTART_STEP': 10})
        case = self.files.public(module, info, row, reference)
        return info, row, reference, case

    def test_result_list_scope_and_completion_survive_native_import_cleanup(self):
        module = {}
        info, row, _, _ = self.public_point(module)
        with self.callbacks('from OMFITlib_cgyro_result_index import result_records, scan_scope, scan_completion') as api:
            entry = next(iter(api['result_records'](module).values()))
            scope = api['scan_scope'](entry)
            self.assertEqual(scope['coordinates'][0]['values']['ERROR_TOL'], 1e-4)
            self.assertEqual(scope['coordinates'][0]['values']['KY'], .1)
            self.assertTrue(api['scan_completion'](info, {'p000001': row}, scope))

    def test_selected_checkpoint_restarts_after_parent_records_are_gone(self):
        module = {}
        self.public_point(module)
        module['RUN_DB'].pop('__RUNS__')
        module['RUN_HISTORY'] = {}
        with self.callbacks('from OMFITlib_cgyro_result_index import result_records\n'
                            'from OMFITlib_cgyro_continue import continuation_plan, prepare_point') as api:
            entry = next(iter(api['result_records'](module).values()))
            plan = api['continuation_plan'](module, entry['selection_key'], ['p000001'], 1.)
            with patch.dict(api['prepare_point'].__globals__, {'ensure_capacity': lambda *a: {}}):
                current, metadata, names = api['prepare_point'](
                    module, plan, 'p000001', str(self.files.base / 'stage'), Input,
                    runtime=self.files.current)
            self.assertEqual(current['MAX_TIME'], 1.)
            self.assertEqual(current['ERROR_TOL'], 1e-4)
            self.assertIs(type(current['RESTART_STEP']), int)
            self.assertEqual(current['RESTART_STEP'], 10)
            self.assertEqual(metadata['continuation']['checkpoint']['time'], .3)
            self.assertIn('out.cgyro.timing', names)

    def test_task_catalog_and_result_deletion_keep_other_signed_ky(self):
        module = {}
        self.public_point(module, 'positive', .1)
        self.public_point(module, 'negative', -.1)
        with self.callbacks('from OMFITlib_cgyro_task_catalog import task_catalog\n'
                            'from OMFITlib_cgyro_task_cleanup import preview_tasks, remove_tasks\n'
                            'from OMFITlib_cgyro_result_index import result_records') as api:
            self.assertEqual({row['token'] for row in api['task_catalog'](module)}, {'positive', 'negative'})
            preview = api['preview_tasks'](module, ['positive'], delete_results=True)
            api['remove_tasks'](module, ['positive'], preview, preview['confirmation'])
            rows = [row for entry in api['result_records'](module).values() for row in entry['tasks'].values()]
            self.assertTrue(rows)
            self.assertTrue(all(row['values']['KY'] == -.1 for row in rows))

    def test_archive_replacement_and_input_summary_are_callback_safe(self):
        module = {}
        info, row, ref, case = self.public_point(module)
        destination = {}
        owner = fixtures.storage.resolve_result(module, ref)
        with self.callbacks('from OMFITlib_cgyro_archive import store_scan\n'
                            'from OMFITlib_cgyro_input_identity import cache_parameters, cache_competing_parameters') as api:
            cached = copy.deepcopy(row)
            cached.pop('input_parameters')
            api['cache_parameters'](cached, info, owner)
            self.assertEqual(cached['input_parameters']['ERROR_TOL'], 1e-4)
            api['store_scan'](destination, case, info, {'p000001': cached})
            saved = destination['__SCANS__']['N_ENERGY']['tasks']['p000001']
            saved.pop('input_parameters')
            api['cache_competing_parameters'](destination, info, {'p000001': cached}, lambda node: owner)
            self.assertEqual(saved['input_parameters']['ERROR_TOL'], 1e-4)

    def test_each_dependency_entry_loads_without_native_circular_imports(self):
        entries = dict(archive='point_values', input_identity='cache_parameters',
                       recover='recover_archives', storage='store_result', result_index='scan_scope',
                       task_catalog='task_catalog', task_cleanup='preview_tasks', recovery_manifest='_point_index')
        for name, callback in entries.items():
            with self.subTest(library=name), self.callbacks('import OMFITlib_cgyro_' + name + ' as library') as api:
                self.assertTrue(callable(getattr(api['library'], callback)))

    def test_collection_summary_and_legacy_recovery_run_after_import_cleanup(self):
        module = {}
        info, _, ref, _ = self.public_point(module)
        owner = fixtures.storage.resolve_result(module, ref)
        key = fixtures.storage.reference_id(ref)
        with self.callbacks('from OMFITlib_cgyro_storage import _collection_summary\n'
                            'from OMFITlib_cgyro_recover import recover_archives\n'
                            'from OMFITlib_cgyro_recovery_manifest import _point_index') as api:
            with patch.object(storage_fixtures.OMFITcgyro, '__getitem__',
                              lambda obj, name: {'t': [.1, .2, .3], 'n_time': 3}[name], create=True):
                summary = api['_collection_summary'](module, key, owner, [('out.cgyro.time', 24, 'cached')])
            self.assertEqual(summary['sample_count'], 3)
            self.assertEqual(summary['final_time'], .3)
            self.assertEqual(summary['solver_status'], 'max_time')
            self.assertTrue(summary['checkpoint_available'])
            manifest = copy.deepcopy(info)
            manifest['point_table']['p000001']['result_path'] = ['N_ENERGY', '8.00000', 'lin', '0.10000']
            self.assertEqual(api['_point_index'](manifest), ['p000001'])
            api['recover_archives'](module, lambda root, node: owner)
            self.assertIn('Jet', module['RUN_DB'])

    def test_registered_library_functions_do_not_defer_omfit_library_imports(self):
        violations = []
        for path in (REPO / 'CGYRO_TGLF_scan').rglob('*.py'):
            if path.parent.name != 'LIB':
                continue
            tree = ast.parse(path.read_text(encoding='utf-8'))
            for function in ast.walk(tree):
                if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                for node in ast.walk(function):
                    names = ([node.module or ''] if isinstance(node, ast.ImportFrom) else
                             [alias.name for alias in node.names] if isinstance(node, ast.Import) else [])
                    if any(name.startswith('OMFITlib_') for name in names):
                        violations.append('{}:{}: {}'.format(path.relative_to(REPO), node.lineno, names))
        self.assertEqual(violations, [], '\n'.join(violations))


if __name__ == '__main__':
    unittest.main(verbosity=2)
