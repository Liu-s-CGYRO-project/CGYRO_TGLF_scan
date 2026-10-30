"""Reject invalid escapes without importing scientific readers or GUI scripts."""
import ast
from pathlib import Path
import sys
import tempfile
import unittest
import warnings

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'tools'))
from check_omfit_api import validate_project_api


class SourceEscapeTests(unittest.TestCase):
    def test_production_python_has_no_invalid_escapes_and_remains_python39_syntax(self):
        for folder in ('CGYRO_TGLF_scan', 'OMFITtemplates'):
            for path in sorted((REPO / folder).rglob('*.py')):
                with self.subTest(file=path.relative_to(REPO)), warnings.catch_warnings():
                    warnings.simplefilter('error', SyntaxWarning)
                    warnings.simplefilter('error', DeprecationWarning)
                    ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path), feature_version=(3, 9))

    def test_build_check_rejects_new_invalid_escapes(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'plot.py'
            path.write_text("label = '\\gamma'\n", encoding='utf-8')
            with self.assertRaises((SyntaxError, SyntaxWarning, DeprecationWarning)):
                validate_project_api(folder)


if __name__ == '__main__':
    unittest.main()
