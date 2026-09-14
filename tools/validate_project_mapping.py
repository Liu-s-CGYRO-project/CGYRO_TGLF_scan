"""Run project regressions with an unchanged OMFIT SortedDict class on Linux.

Usage: python3 tools/validate_project_mapping.py /path/to/omfit/omfit_classes/sortedDict.py

Loads the native class, helpers and lazy-loading decorators via AST, avoiding
framework startup and its global pickle patches. Documentation registries and
the class registry have isolated host adapters. UI bindings and solver calls
remain test adapters; this is not a full OMFIT session or a solver acceptance test.
"""
import argparse
import ast
import hashlib
import io
import json
import os
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'tests'))
import test_native_mapping as tests


def validate(source):
    source = Path(source).resolve()
    raw = source.read_text(encoding='utf-8')
    base = source.with_name('utils_base.py')
    base_raw = base.read_text(encoding='utf-8')
    selected = {'isinstance_str', 'hasattr_no_dynaLoad', '_available_to_user_math',
                '_available_to_user_util', '_available_to_user_plot'}
    helpers = [node for node in ast.parse(base_raw).body
               if isinstance(node, ast.FunctionDef) and node.name in selected]
    assert {node.name for node in helpers} == selected
    namespace = dict(__name__='native_sorted_dict_validation', os=os, sys=sys,
                     OMFITaux={'dynaLoad_switch': True, 'OMFITmath_functions': [],
                               'OMFITutil_functions': [], 'OMFITplot_functions': []})
    exec(compile(ast.Module(body=helpers, type_ignores=[]), str(base), 'exec'), namespace)
    nodes = []
    for node in ast.parse(raw).body:
        if isinstance(node, ast.ImportFrom) and node.module == 'omfit_classes.utils_base':
            continue
        nodes.append(node)
        if isinstance(node, ast.ClassDef) and node.name == 'SortedDict':
            native_class = node
            break
    else:
        raise ValueError('SortedDict class missing from supplied source')
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), 'exec'), namespace)
    factory = namespace['SortedDict']
    registry = ModuleType('omfit_classes.utils_base')
    registry._loaded_classes = set()
    classes = (tests.NativeProjectTest, tests.NativeMultiInputTest, tests.NativeIntegrationTest)
    stream = io.StringIO()
    with patch.dict(sys.modules, {'omfit_classes.utils_base': registry}):
        originals = [cls.tree_factory for cls in classes]
        try:
            for cls in classes:
                cls.tree_factory = factory
            suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(cls) for cls in classes)
            result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
        finally:
            for cls, original in zip(classes, originals):
                cls.tree_factory = original
    report = dict(python=sys.version.split()[0], omfit_source=str(source),
                  source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                  native_class_sha256=hashlib.sha256(ast.get_source_segment(raw, native_class).encode()).hexdigest(),
                  native_class_unmodified=True, native_lazy_loading=True,
                  tests=result.testsRun, failures=len(result.failures), errors=len(result.errors),
                  skipped=len(result.skipped), complete_omfit_session_tested=False, solver_executed=False)
    return report, stream.getvalue(), result.wasSuccessful()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sorted_dict_source', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    report, log, passed = validate(args.sorted_dict_source)
    content = json.dumps(report, indent=2, ensure_ascii=False) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding='utf-8')
        args.output.with_suffix('.log').write_text(log, encoding='utf-8')
    print(log)
    print(content)
    raise SystemExit(0 if passed else 1)
