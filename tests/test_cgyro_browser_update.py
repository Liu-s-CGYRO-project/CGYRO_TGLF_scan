"""Code-update browser repair and native expression reopen/read boundaries.

Native SortedDict and expression methods are unchanged source extractions;
the surrounding project and update transaction use isolated host adapters.
"""
import ast
import builtins
import copy
import importlib
import json
import pickle
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import test_cgyro_storage as fixture

payload = importlib.import_module('OMFITlib_cgyro_payload')
browser = importlib.import_module('OMFITlib_cgyro_browser')

def browser_libraries():
    return {
        'OMFITlib_cgyro_browser': SimpleNamespace(filename=browser.__file__, importCode=lambda **kwargs: browser),
        'OMFITlib_cgyro_payload': SimpleNamespace(filename=payload.__file__, importCode=lambda **kwargs: payload),
    }

live = importlib.import_module('OMFITlib_template_live')
migration = fixture.migration
SOURCE = fixture.REPO.parents[2] / 'OMFIT-source-ASIPP_unstable/omfit'
sys.path.insert(0, str(fixture.REPO / 'tools'))
from validate_project_mapping import load_native_mapping


class BrowserUpdateTests(unittest.TestCase):
    def setUp(self):
        native_mapping, registry, _ = load_native_mapping(SOURCE / 'omfit_classes/sortedDict.py')
        registry_patch = patch.dict(sys.modules, {'omfit_classes.utils_base': registry})
        registry_patch.start()
        self.addCleanup(registry_patch.stop)
        self.reads = []
        reads = self.reads

        class OMFITcgyro(native_mapping, fixture.OMFITobject):
            def __init__(self, key):
                native_mapping.__init__(self)
                self.result_key, self.dynaLoad = key, True

            def load(self):
                reads.append(self.result_key)
                self.dynaLoad = False
                self['freq'] = 'selected result'

        source = SOURCE / 'omfit_classes/omfit_base.py'
        definition = next(node for node in ast.parse(source.read_text(encoding='utf-8')).body
                          if isinstance(node, ast.ClassDef) and node.name == 'OMFITexpression')
        definition.body = [node for node in definition.body if isinstance(node, ast.FunctionDef)
                           and node.name in ('__init__', '_value_', '_godeep', '__deepcopy__', '__getstate__')]
        self.namespace = dict(OMFITexpressionsReturnNone=False, OMFITexception=ValueError,
            OMFITunevaluatedExpression=type('OMFITunevaluatedExpression', (), {}),
            OMFITexpressionError=type('OMFITexpressionError', (Exception,), {}))
        exec(compile(ast.Module(body=[definition], type_ignores=[]), str(source), 'exec'), self.namespace)
        self.expression_type = self.namespace['OMFITexpression']
        self.namespace['OMFITiterableExpression'] = type('OMFITiterableExpression', (self.expression_type,), {})
        self.expression_type.__value__ = lambda expression, dependencies: eval(
            expression.expression, {'root': self.root})
        self.keys = ['a' * 64, 'b' * 64]
        self.owners = {key: OMFITcgyro(key) for key in self.keys}
        self.root = dict(RUN_DB={'__STORAGE__': {'version': 4}, '__STORE__': self.owners,
            'Jet': {str(i): self.reference(key) for i, key in enumerate(self.keys)}},
            LIB=browser_libraries())
        reader_patch = patch.object(payload.native_readers, 'OMFITcgyro', OMFITcgyro)
        reader_patch.start()
        self.addCleanup(reader_patch.stop)

    def expression(self, code):
        result = object.__new__(self.expression_type)
        result.expression, result.lastEval = code, None
        return result

    def reference(self, key):
        return {'__RESULT_REF__': key,
                'data': self.expression("root['RUN_DB']['__STORE__']['" + key + "']")}

    def plan(self, version='1.24.58'):
        # Exercise the actual archive hook, apply, stale check and rollback;
        # no template package or GUI is needed for these narrow data operations.
        plan = object.__new__(live.LivePlan)
        plan.omfit = {'CGYRO_TGLF_scan': {'CGYRO_scan': self.root}}
        plan.prepared = SimpleNamespace(release=dict(roots=['CGYRO_TGLF_scan'],
            id='cgyro-tglf', author='tdxy-liu', version=version))
        plan.operations, plan.guards, plan.relocations = [], [], {}
        plan.scaffold, plan.bare_output_source, plan.applied = None, live.MISSING, False
        plan.archive_index = migration.ArchiveIndex()
        plan._archives()
        return plan

    def test_old_saved_link_reads_on_classification_repaired_link_reopens_without_read(self):
        first = self.root['RUN_DB']['Jet']['0']
        first['data']._value_()  # Exact native reopen classification, no data request.
        self.assertEqual(self.reads, [self.keys[0]])
        self.owners[self.keys[0]].clear()
        self.owners[self.keys[0]].dynaLoad = True
        self.reads.clear()
        self.plan().apply(lambda *args: None)
        # Native save records expression text; constructor runs while evaluation
        # is disabled on reopen, then _load explicitly evaluates each expression.
        saved = json.loads(json.dumps([row['data'].expression
                                      for row in self.root['RUN_DB']['Jet'].values()]))
        self.namespace['OMFITexpressionsReturnNone'] = True
        reopened = [self.expression_type(code) for code in saved]
        self.namespace['OMFITexpressionsReturnNone'] = False
        readers = [expression._value_() for expression in reopened]
        self.assertEqual(self.reads, [])
        self.assertEqual(readers[0]['freq'], 'selected result')
        self.assertEqual(self.reads, [self.keys[0]])
        self.assertTrue(self.owners[self.keys[1]].dynaLoad)
        self.assertIs(self.root['RUN_DB']['__STORE__'], self.owners)

    def test_repair_skips_store_file_leaves_and_metadata_expressions(self):
        class OMFITobject(dict):
            def keys(self):
                raise AssertionError('File reader inspected')
            items = values = keys
        self.root['RUN_DB']['unindexed_file'] = OMFITobject()
        self.root['RUN_DB']['unrelated'] = self.expression('unexpected()')
        pending = self.reference(self.keys[0])
        self.root['RUN_DB']['__RUNS__'] = {'token': {'cases': {'p000001': pending}}}
        with patch.object(payload, 'materialize_owner', side_effect=AssertionError('Result read')):
            with patch.object(fixture.storage, 'directory_inventory', side_effect=AssertionError('File hash')):
                plan = self.plan()
                self.assertEqual(len(plan.operations), 3)
                plan.apply(lambda *args: None)
        self.assertEqual(self.reads, [])
        self.assertTrue(fixture.reference_api.browse_current(pending['data'], self.keys[0]))

    def test_repair_is_idempotent_and_keeps_missing_or_custom_browser_entries(self):
        current = self.reference(self.keys[0])
        current['data'] = self.expression(fixture.reference_api.browse_code(self.keys[0]))
        plain = {'__RESULT_REF__': self.keys[1]}
        custom = self.reference(self.keys[0])
        custom['data'] = self.expression('user_supplied_expression')
        self.root['RUN_DB']['retained'] = dict(current=current, plain=plain, custom=custom)
        before = current['data'], custom['data']
        self.plan().apply(lambda *args: None)
        self.assertEqual(self.plan().operations, [])
        self.assertIs(current['data'], before[0])
        self.assertIs(custom['data'], before[1])
        self.assertEqual(set(plain), {'__RESULT_REF__'})

    def test_changed_reference_invalidates_update_without_touching_owners(self):
        plan = self.plan()
        first = self.root['RUN_DB']['Jet']['0']
        first['__RESULT_REF__'] = self.keys[1]
        with self.assertRaisesRegex(ValueError, '预览后已改变'):
            plan.apply(lambda *args: None)
        self.assertEqual(self.reads, [])
        self.assertIs(self.root['RUN_DB']['__STORE__'], self.owners)

    def test_interrupted_update_restores_each_original_link(self):
        before = [row['data'] for row in self.root['RUN_DB']['Jet'].values()]
        def interrupted(plan, undo):
            if not undo:
                raise KeyboardInterrupt('cancel update')
        with self.assertRaisesRegex(KeyboardInterrupt, 'cancel update'):
            self.plan().apply(interrupted)
        for row, original in zip(self.root['RUN_DB']['Jet'].values(), before):
            self.assertIs(row['data'], original)
        self.assertEqual(self.reads, [])

    def test_update_can_be_undone_without_loading_any_result(self):
        before = [row['data'] for row in self.root['RUN_DB']['Jet'].values()]
        plan = self.plan()
        plan.apply(lambda *args: None)
        plan.undo(lambda *args: None)
        for row, original in zip(self.root['RUN_DB']['Jet'].values(), before):
            self.assertIs(row['data'], original)
        self.assertEqual(self.reads, [])

    def test_older_target_without_deferred_contract_keeps_original_expressions(self):
        self.assertEqual(self.plan(version='1.24.19').operations, [])
        self.assertEqual(self.reads, [])

    def test_metadata_classification_never_calls_native_expression_isinstance(self):
        def native_isinstance(value, classes):
            if any(base.__name__ == 'OMFITexpression' for base in type(value).__mro__):
                raise AssertionError('Native isinstance would evaluate this expression')
            return builtins.isinstance(value, classes)
        self.root['RUN_DB']['other'] = self.expression('unexpected()')
        with patch.object(migration, 'isinstance', native_isinstance):
            plan = self.plan()
            plan.apply(lambda *args: None)
            plan.undo(lambda *args: None)
        self.assertEqual(self.reads, [])

    def test_update_retires_both_old_links_and_repeated_payload_imports(self):
        for key, row in zip(self.keys, self.root['RUN_DB']['Jet'].values()):
            row['data'] = self.expression(fixture.reference_api.legacy_browse_code(key))
        self.plan().apply(lambda *args: None)
        for key, row in zip(self.keys, self.root['RUN_DB']['Jet'].values()):
            self.assertEqual(row['data'].expression, fixture.reference_api.browse_code(key))
            self.assertTrue(fixture.reference_api.validate_reference(row, key))
        self.assertEqual(self.plan().operations, [])
        self.assertEqual(self.reads, [])

    def test_previous_release_keeps_its_supported_browser_contract(self):
        self.plan(version='1.24.57').apply(lambda *args: None)
        for key, row in zip(self.keys, self.root['RUN_DB']['Jet'].values()):
            self.assertEqual(row['data'].expression, fixture.reference_api.legacy_browse_code(key))
            self.assertTrue(fixture.reference_api.validate_reference(row, key))

    def test_reopen_many_links_imports_bootstrap_once_and_never_reads_payloads(self):
        code = fixture.reference_api.browse_code(self.keys[0])
        task = self.root['LIB']['OMFITlib_cgyro_browser']
        task.importCode = Mock(return_value=browser)
        heavy = self.root['LIB']['OMFITlib_cgyro_payload']
        heavy.importCode = Mock(return_value=payload)
        with patch.object(payload, 'inventory', side_effect=AssertionError('inventory read')), \
                patch.object(payload, 'sources', side_effect=AssertionError('file stat/hash')):
            readers = [self.expression(code)._value_() for _ in range(709)]
        self.assertEqual(task.importCode.call_count, 1)
        heavy.importCode.assert_not_called()
        self.assertEqual(self.reads, [])
        self.assertIs(readers[0], readers[-1])
        self.assertEqual(readers[0]['freq'], 'selected result')
        self.assertEqual(readers[1]['freq'], 'selected result')
        heavy.importCode.assert_called_once()
        self.assertEqual(self.reads, [self.keys[0]])
        # A new native load restores source files/expression text, not task
        # attributes. A second open must start a separate runtime cache.
        self.root['LIB'] = browser_libraries()
        new_task = self.root['LIB']['OMFITlib_cgyro_browser']
        new_task.importCode = Mock(return_value=browser)
        reopened = self.expression(json.loads(json.dumps(code)))._value_()
        self.assertIsNot(reopened, readers[0])
        new_task.importCode.assert_called_once()

    def test_code_edit_and_code_node_replacement_invalidate_bootstrap(self):
        task = self.root['LIB']['OMFITlib_cgyro_browser']
        task.importCode = Mock(return_value=browser)
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'browser.py'
            source.write_text('# before', encoding='utf-8')
            task.filename = str(source)
            code = fixture.reference_api.browse_code(self.keys[0])
            first = self.expression(code)._value_()
            source.write_text('# after: different size', encoding='utf-8')
            second = self.expression(code)._value_()
            self.assertIsNot(first, second)
            self.assertEqual(task.importCode.call_count, 2)
            self.root['LIB'] = browser_libraries()
            third = self.expression(code)._value_()
            self.assertIsNot(second, third)
        self.assertEqual(self.reads, [])

    def test_two_projects_with_same_digest_never_share_a_reader(self):
        code = fixture.reference_api.browse_code(self.keys[0])
        first = self.expression(code)._value_()
        previous = self.root
        self.root = dict(RUN_DB={'__STORE__': dict(self.owners)}, LIB=browser_libraries())
        second = self.expression(code)._value_()
        self.assertIsNot(first, second)
        self.assertEqual(payload.deferred_key(previous, first), self.keys[0])
        with self.assertRaisesRegex(ValueError, 'another CGYRO module'):
            payload.deferred_key(previous, second)

    def test_changed_or_removed_owner_is_not_hidden_by_runtime_cache(self):
        code = fixture.reference_api.browse_code(self.keys[0])
        first = eval(code, {'root': self.root})
        self.owners[self.keys[0]] = type(self.owners[self.keys[0]])(self.keys[0])
        second = eval(code, {'root': self.root})
        self.assertIsNot(first, second)
        del self.owners[self.keys[0]]
        with self.assertRaisesRegex(ValueError, 'Missing physical CGYRO result'):
            eval(code, {'root': self.root})

    def test_migration_and_reference_generate_identical_expression_text(self):
        for key in self.keys:
            self.assertEqual(migration.browser_codes(key)[-1], fixture.reference_api.browse_code(key))

    def test_template_apply_and_undo_drop_reader_dependency_caches(self):
        class OMFITpythonTask(SimpleNamespace):
            pass
        for name, node in self.root['LIB'].items():
            self.root['LIB'][name] = OMFITpythonTask(**vars(node))
        plan = self.plan()
        for action in (plan.apply, plan.undo):
            browser_task = self.root['LIB']['OMFITlib_cgyro_browser']
            payload_task = self.root['LIB']['OMFITlib_cgyro_payload']
            browser_task._cgyro_browser_entry = object()
            payload_task._cgyro_payload_api = object()
            action(lambda *args: None)
            self.assertFalse(hasattr(browser_task, '_cgyro_browser_entry'))
            self.assertFalse(hasattr(payload_task, '_cgyro_payload_api'))
        self.assertEqual(self.reads, [])

    def test_selected_reader_cache_observes_source_edit_and_update_invalidation(self):
        task = self.root['LIB']['OMFITlib_cgyro_payload']
        task.importCode = Mock(return_value=payload)
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'payload.py'
            source.write_text('# before', encoding='utf-8')
            task.filename = str(source)
            first = browser.payload_api(self.root)
            self.assertIs(browser.payload_api(self.root), first)
            task.importCode.assert_called_once()
            source.write_text('# after: reader code edit', encoding='utf-8')
            browser.payload_api(self.root)
            self.assertEqual(task.importCode.call_count, 2)
            del task._cgyro_payload_api
            browser.payload_api(self.root)
            self.assertEqual(task.importCode.call_count, 3)

    def test_update_and_undo_route_retained_legacy_proxy_through_current_library_only(self):
        class OMFITpythonTask(SimpleNamespace):
            pass
        for name, task in list(self.root['LIB'].items()):
            self.root['LIB'][name] = OMFITpythonTask(**vars(task))
        key = self.keys[0]
        # A pre-1.24.64 view captured these callbacks in its class closure.
        stale = Mock(return_value={'implementation': 'stale'})
        retained = browser.deferred_view(self.root, key, stale, stale)
        payload.resolve_owner(self.root, key, defer_native=True)
        cache = payload.native_readers._cgyro_deferred_views
        cache[(id(self.root), key, id(self.owners[key]))] = retained
        other = dict(RUN_DB={'__STORE__': self.owners}, LIB=browser_libraries())
        untouched = payload.resolve_owner(other, key, defer_native=True)
        task = self.root['LIB']['OMFITlib_cgyro_payload']
        current = SimpleNamespace(clear_runtime=payload.clear_runtime,
                                  materialize_owner=Mock(return_value={'implementation': 'new'}),
                                  browser_file=Mock(return_value='new selected file'))
        task.importCode = Mock(return_value=current)
        plan = self.plan()
        with patch.object(payload, 'sources', side_effect=AssertionError('result inspection')):
            plan.apply(lambda *args: None)
        self.assertEqual(self.reads, [])
        self.assertEqual(retained['implementation'], 'new')
        self.assertEqual(retained._payload_file('input.cgyro'), 'new selected file')
        current.materialize_owner.assert_called_once_with(self.root, key)
        current.browser_file.assert_called_once_with(self.root, key, 'input.cgyro')
        self.assertNotIn('_payload_reader', object.__getattribute__(untouched, '__dict__'))
        # Undo may restore a pre-hook release; retained proxies must still use
        # that restored library, rather than the callback captured before update.
        restored = SimpleNamespace(materialize_owner=Mock(return_value={'implementation': 'restored'}))
        task.importCode = Mock(return_value=restored)
        plan.undo(lambda *args: None)
        self.assertEqual(retained['implementation'], 'restored')
        stale.assert_not_called()
        self.assertEqual(self.reads, [])

    def test_failed_update_rebinds_retained_proxy_again_on_rollback(self):
        class OMFITpythonTask(SimpleNamespace):
            pass
        for name, task in list(self.root['LIB'].items()):
            self.root['LIB'][name] = OMFITpythonTask(**vars(task))
        retained = payload.resolve_owner(self.root, self.keys[0], defer_native=True)
        task = self.root['LIB']['OMFITlib_cgyro_payload']
        new_api = SimpleNamespace(clear_runtime=payload.clear_runtime,
                                  materialize_owner=Mock(return_value={'implementation': 'new'}))
        old_api = SimpleNamespace(clear_runtime=payload.clear_runtime,
                                  materialize_owner=Mock(return_value={'implementation': 'old'}))
        task.importCode = Mock(return_value=new_api)
        def refresh(plan, undo):
            if not undo:
                self.assertEqual(retained['implementation'], 'new')
                task.importCode.return_value = old_api
                raise RuntimeError('refresh failed')
        with self.assertRaisesRegex(live.TemplateError, 'refresh failed'):
            self.plan().apply(refresh)
        self.assertEqual(retained['implementation'], 'old')
        self.assertEqual(self.reads, [])

    def test_native_save_state_excludes_runtime_functions_readers_and_owners(self):
        source = SOURCE / 'omfit_classes/startup_framework.py'
        cls = next(node for node in ast.parse(source.read_text(encoding='utf-8')).body
                   if isinstance(node, ast.ClassDef) and node.name == 'OMFITobject')
        method = next(node for node in cls.body if isinstance(node, ast.FunctionDef)
                      and node.name == '__save_kw__')
        namespace = {}
        exec(compile(ast.Module(body=[method], type_ignores=[]), str(source), 'exec'), namespace)
        code = fixture.reference_api.browse_code(self.keys[0])
        expression = self.expression(code)
        expression._value_()['freq']
        self.assertEqual(expression.__getstate__(), {'expression': code})
        for name, attribute in (('OMFITlib_cgyro_browser', '_cgyro_browser_entry'),
                                ('OMFITlib_cgyro_payload', '_cgyro_payload_api')):
            task = self.root['LIB'][name]
            task.OMFITproperties = {'modifyOriginal': False}
            self.assertTrue(hasattr(task, attribute))
            self.assertEqual(namespace['__save_kw__'](task), {'modifyOriginal': False})

    def test_invalid_selected_manifest_still_fails_without_reading_other_results(self):
        self.owners[self.keys[0]] = {'__CGYRO_FILES__': 1, 'inventory': '[]', 'test_mode': False}
        reader = eval(fixture.reference_api.browse_code(self.keys[0]), {'root': self.root})
        self.assertEqual(self.reads, [])
        with self.assertRaisesRegex(ValueError, 'Empty CGYRO file manifest'):
            reader['freq']
        self.assertEqual(self.reads, [])

    def test_native_code_copy_discards_runtime_caches_without_visiting_results(self):
        class Uncopyable:
            def __reduce__(self):
                raise AssertionError('Copy visited the cached project/reader')
        cache = browser.RuntimeCache(lookup=Uncopyable(), api=Uncopyable())
        self.assertEqual(copy.deepcopy(cache), {})
        self.assertEqual(pickle.loads(pickle.dumps(cache)), {})
        code = fixture.reference_api.browse_code(self.keys[0])
        task = self.root['LIB']['OMFITlib_cgyro_browser']
        task._cgyro_browser_entry = copy.deepcopy(cache)
        self.assertEqual(eval(code, {'root': self.root})['freq'], 'selected result')


if __name__ == '__main__':
    unittest.main()
