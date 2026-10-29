"""Code-update browser repair and native expression reopen/read boundaries.

Native SortedDict and expression methods are unchanged source extractions;
the surrounding project and update transaction use isolated host adapters.
"""
import ast
import builtins
import importlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_cgyro_storage as fixture

payload = importlib.import_module('OMFITlib_cgyro_payload')
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
                           and node.name in ('__init__', '_value_', '_godeep', '__deepcopy__')]
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
            LIB={'OMFITlib_cgyro_payload': SimpleNamespace(importCode=lambda **kwargs: payload)})
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

    def plan(self, version='1.24.38'):
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


if __name__ == '__main__':
    unittest.main()
