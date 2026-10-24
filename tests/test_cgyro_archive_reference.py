"""Archive equality with unchanged OMFIT expression comparison operators.

The source methods are compiled as-is; expression resolution is an instrumented
host boundary. No OMFIT application, result reader or scheduler is started.
"""
import ast
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO.parents[2] / 'OMFIT-source-ASIPP_unstable/omfit'
sys.path.insert(0, str(REPO / 'CGYRO_TGLF_scan/LIB'))
import test_cgyro_storage as fixture
import OMFITlib_cgyro_reference as reference


class NativeExpressionReferenceTests(unittest.TestCase):
    def setUp(self):
        source = SOURCE / 'omfit_classes/omfit_base.py'
        tree = ast.parse(source.read_text(encoding='utf-8'))
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'OMFITexpression')
        methods = [node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name in ('__eq__', '__ne__')]
        self.assertEqual({node.name for node in methods}, {'__eq__', '__ne__'})
        namespace = {}
        exec(compile(ast.Module(body=methods, type_ignores=[]), str(source), 'exec'), namespace)
        evaluations = self.evaluations = []
        class OMFITexpression:
            def _value_(self):
                evaluations.append(self)
                return object()  # Independent native expression resolutions.
        OMFITexpression.__eq__, OMFITexpression.__ne__ = namespace['__eq__'], namespace['__ne__']
        class OMFITiterableExpression(OMFITexpression):
            pass
        module = types.ModuleType('omfit_classes.omfit_base')
        module.OMFITiterableExpression = OMFITiterableExpression
        self.patch = patch.dict(sys.modules, {module.__name__: module})
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_equal_owner_digests_ignore_native_expression_equality_and_cache(self):
        original = reference.make_reference('a' * 64)
        rebuilt = reference.copy_result_tree(original)
        # The old guard's dict comparison invokes the real native __eq__ and
        # reports different indexes despite identical scientific owner keys.
        self.assertNotEqual(original, rebuilt)
        self.assertTrue(self.evaluations)
        self.evaluations.clear()
        original['data'].lastEval = object()
        self.assertTrue(reference.same_result_reference(original, rebuilt))
        self.assertEqual(self.evaluations, [])
        self.assertTrue(reference.same_result_reference(original, {reference.REF: 'a' * 64}))
        self.assertFalse(reference.same_result_reference(original, reference.make_reference('b' * 64)))
        self.assertEqual(self.evaluations, [])

    def test_tampered_browser_or_extra_fields_are_rejected_even_for_same_object(self):
        broken = reference.make_reference('a' * 64)
        broken['data'].expression = "root['RUN_DB'].clear()"
        extra = dict(reference.make_reference('a' * 64), extra='unverified payload')
        for value in (broken, extra, {reference.REF: 'invalid digest'}):
            with self.subTest(keys=list(value)), self.assertRaises(ValueError):
                reference.same_result_reference(value, value)
        self.assertEqual(self.evaluations, [])

    def test_unindexed_native_files_require_exact_owner_identity_not_a_shared_filename(self):
        first = fixture.OMFITcgyro('/unused/result')
        second = fixture.OMFITcgyro('/unused/result')
        self.assertTrue(reference.same_result_reference(first, first))
        self.assertFalse(reference.same_result_reference(first, second))
        self.assertFalse(reference.same_result_reference(None, None))
        self.assertFalse(reference.same_result_reference({}, {}))


if __name__ == '__main__':
    unittest.main()
