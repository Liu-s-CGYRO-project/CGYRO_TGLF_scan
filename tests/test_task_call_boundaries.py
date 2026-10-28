"""Nested project tasks must preserve the caller's local refresh boundary."""
import ast
from pathlib import Path
import sys
import unittest
import warnings

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'tools'))
import build_project as builder


def receiver_branch(receiver):
    """Follow the receiver's lookup chain, ignoring strings in its arguments."""
    while isinstance(receiver, (ast.Subscript, ast.Attribute)):
        if isinstance(receiver, ast.Subscript) and isinstance(receiver.slice, ast.Constant):
            if receiver.slice.value in ('SCRIPTS', 'GUIS'):
                return receiver.slice.value
        receiver = receiver.value
    return None


class ProjectTaskBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        module = REPO / 'CGYRO_TGLF_scan'
        cls.sources = set(module.rglob('*.py'))
        # Native scripts may have no .py extension; use the existing saved tree.
        for row in builder.parse_tree((module / 'OMFITsave.txt').read_bytes()):
            if row.ref and row.kind.startswith('OMFITpython'):
                cls.sources.add((module / row.ref).resolve())

    def test_project_script_calls_do_not_bypass_local_finish(self):
        failures = []
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', SyntaxWarning)
            for path in sorted(self.sources):
                tree = ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))
                for node in ast.walk(tree):
                    if (isinstance(node, ast.Attribute) and node.attr == 'run'
                            and receiver_branch(node.value)):
                        failures.append('{}:{}'.format(path.relative_to(REPO), node.lineno))
        self.assertEqual(failures, [], 'Use task_action/gui_view for explicit project script entries')

    def test_scoped_helpers_are_available_in_every_native_module(self):
        # A host Python sys.path import can pass while native OMFIT's current-root
        # LIB resolution fails. Check both full-project and standalone installers.
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', SyntaxWarning)
            warnings.simplefilter('ignore', DeprecationWarning)
            for base in (REPO, REPO / 'CGYRO_TGLF_scan'):
                with self.subTest(base=base.name):
                    rows = builder.parse_tree((base / 'OMFITsave.txt').read_bytes())
                    builder.validate_library_imports(rows, base)


if __name__ == '__main__':
    unittest.main()
