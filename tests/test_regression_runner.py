"""Environment failures stay distinct from code regressions and never pass."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'tools'))
import run_isolated_suite as isolated
import run_regressions as runner


class EnvironmentTests(unittest.TestCase):
    def test_missing_omfit_requires_explicit_adapters_not_just_source(self):
        suite = REPO / 'tests/test_project.py'
        with patch.object(isolated.importlib.util, 'find_spec', return_value=None):
            with self.assertRaisesRegex(ValueError, 'explicit --adapters'):
                isolated.check_environment(suite, REPO)
            isolated.check_environment(suite, REPO, adapters=True)

    def test_unavailable_shell_is_reported_before_suite_loading(self):
        with patch.object(isolated.subprocess, 'run', side_effect=FileNotFoundError('bash')):
            with self.assertRaisesRegex(ValueError, 'Required shell is unavailable: bash'):
                isolated.check_environment(REPO / 'tests/test_cgyro_job_recovery.py', None)

    def test_shell_probe_reports_nonzero_and_timeout_without_running_solver(self):
        for result in (subprocess.CompletedProcess([], 1, b'not installed'), subprocess.TimeoutExpired(['bash'], 10)):
            kwargs = {'side_effect': result} if isinstance(result, Exception) else {'return_value': result}
            with self.subTest(result=result), patch.object(isolated.subprocess, 'run', **kwargs) as run:
                with self.assertRaisesRegex(ValueError, 'Required shell'):
                    isolated.check_shell(['bash'])
                self.assertEqual(run.call_args.args[0], ['bash', '-c', 'exit 0'])

    def test_headless_tk_is_environment_failure(self):
        with patch.object(isolated.sys, 'platform', 'linux'), patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, 'require DISPLAY'):
                isolated.check_environment(REPO / 'tests/test_tk_callbacks.py', None)

    def test_pure_metadata_suite_does_not_require_shell_or_tk_or_omfit(self):
        with patch.object(isolated, 'check_shell', side_effect=AssertionError('unneeded shell')):
            isolated.check_environment(REPO / 'tests/test_project_history.py', None)


class RunnerProcessTests(unittest.TestCase):
    def execute(self, source):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            path = directory / 'test_environment_fixture.py'
            path.write_text(source, encoding='utf-8')
            row = runner.run_suite(path, REPO, directory, dict(os.environ, PYTHONDONTWRITEBYTECODE='1'), 15, False, None)
            output = (directory / row['log']).read_text(encoding='utf-8')
            return row, output

    def test_missing_external_import_has_one_environment_reason_and_no_tests(self):
        row, output = self.execute('raise ModuleNotFoundError("fixture dependency", name="omfit_classes")\n')
        self.assertEqual(row['exit_code'], isolated.ENVIRONMENT_EXIT)
        self.assertEqual(row['status'], 'environment_error')
        self.assertEqual(row['tests'], 0)
        self.assertEqual(len(row['environment_errors']), 1)
        self.assertIn('Missing dependency omfit_classes', output)
        self.assertNotIn('Traceback', output)

    def test_missing_project_module_is_a_code_failure(self):
        row, output = self.execute('raise ModuleNotFoundError("fixture code", name="OMFITlib_missing_fixture")\n')
        self.assertEqual(row['status'], 'failed')
        self.assertEqual(row['environment_errors'], [])
        self.assertIn('ModuleNotFoundError', output)

    def test_all_skipped_is_not_a_success(self):
        row, _ = self.execute('import unittest\nclass Fixture(unittest.TestCase):\n'
            '    @unittest.skip("platform unavailable")\n    def test_one(self): pass\n')
        self.assertEqual(row['status'], 'environment_error')
        self.assertEqual(row['skipped'], 1)
        self.assertIn('All tests skipped', row['environment_errors'][0])

    def test_empty_suite_is_not_a_success(self):
        row, _ = self.execute('import unittest\n')
        self.assertEqual(row['status'], 'failed')
        self.assertNotEqual(row['exit_code'], 0)
        self.assertEqual(row['tests'], 0)

    def test_actual_assertion_failure_stays_a_code_failure(self):
        row, _ = self.execute('import unittest\nclass Fixture(unittest.TestCase):\n'
            '    def test_one(self): self.fail("fixture failure")\n')
        self.assertEqual(row['status'], 'failed')
        self.assertEqual(row['failures'], 1)
        self.assertEqual(row['environment_errors'], [])

    def test_executed_passing_suite_remains_successful(self):
        row, _ = self.execute('import unittest\nclass Fixture(unittest.TestCase):\n'
            '    def test_one(self): self.assertTrue(True)\n')
        self.assertEqual(row['status'], 'passed')
        self.assertEqual(row['tests'], 1)
        self.assertEqual(row['exit_code'], 0)


if __name__ == '__main__':
    unittest.main()
