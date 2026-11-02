"""Unsupported source is diagnosed without executing it or writing a file."""
import ast
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'tools'))
import repair_omfit_file_menu as repair


def source_fixture():
    return ('class OMFITgui:\n    def dropdownMenu(self):\n' + repair.OLD_UPDATE +
            '    def OMFITmodules(self):\n        top = tk.Toplevel(self.rootGUI)\n' +
            repair.MODULE_LOOKUP).encode('utf-8')


class SourcePatchTests(unittest.TestCase):
    def test_parse_and_compile_failures_have_one_readable_contract(self):
        for invalid in (b"s += 'Python' %\nvalue\n", b'return\n'):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(ValueError, 'Unrecognized or unparsable.*no change made:.*line'):
                    repair.patched_source(invalid + source_fixture())

    def test_already_patched_source_is_still_checked_for_syntax_errors(self):
        ready = repair.patched_source(source_fixture())
        with self.assertRaisesRegex(ValueError, 'unparsable'):
            repair.patched_source(b'broken =\n' + ready)

    def test_candidate_compile_failure_has_same_contract(self):
        with patch.object(repair, 'NEW_UPDATE', '        def invalid(:\n'):
            with self.assertRaisesRegex(ValueError, 'unparsable.*no change made'):
                repair.patched_source(source_fixture())

    def test_unrecognized_class_fails_without_stopiteration(self):
        with self.assertRaisesRegex(ValueError, 'Unrecognized native module dialog'):
            repair.patched_source(source_fixture().replace(b'class OMFITgui:', b'class CustomGUI:'))

    def test_supported_patch_is_python39_idempotent_and_keeps_line_endings(self):
        for newline in (b'\n', b'\r\n'):
            source = source_fixture().replace(b'\n', newline)
            updated = repair.patched_source(source)
            ast.parse(updated, feature_version=(3, 9))
            self.assertEqual(repair.patched_source(updated), updated)
            self.assertEqual(b'\r\n' in updated, newline == b'\r\n')

    def test_cli_syntax_failure_preserves_source_and_does_not_create_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            original, output = directory / 'omfit_gui.py', directory / 'candidate.py'
            content = b"s += 'Python' %\nexecutable\n" + source_fixture()
            original.write_bytes(content)
            result = subprocess.run([sys.executable, '-B', str(REPO / 'tools/repair_omfit_file_menu.py'),
                                     '--source', str(original), '--output', str(output)],
                                    capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 2)
            self.assertIn('no change made', result.stderr)
            self.assertNotIn('Traceback', result.stderr)
            self.assertFalse(output.exists())
            self.assertEqual(original.read_bytes(), content)
