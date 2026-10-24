"""Exercise the unchanged OMFIT executor with a desktop-style environment.

The supplied source provides execute and remote_execute. Only transport and
the process runner are adapters; no SSH, scheduler, or solver is launched.
"""
import ast
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO.parents[2] / 'OMFIT-source-ASIPP_unstable/omfit'
sys.path.insert(0, str(REPO / 'CGYRO_TGLF_scan/LIB'))
import test_cgyro_job_recovery as fixture
import OMFITlib_cgyro_job_probe as probe
import OMFITlib_cgyro_run_state as state


class NativeRemoteEnvironmentTests(unittest.TestCase):
    def setUp(self):
        path = SOURCE / 'omfit_classes/OMFITx.py'
        self.assertTrue(path.is_file(), 'Provide --omfit-source to the regression runner')
        self.calls = []
        self.return_code = 0
        self.error = None
        self.working_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.working_directory.cleanup)
        namespace = dict(os=os, OMFITascii=type('UnusedAscii', (), {}), SERVER={'localhost': {}},
            setup_ssh_tunnel=lambda *args, **kwargs: ('user', '', '22'),
            evalExpr=lambda value: self.working_directory.name if value == fixture.WORKDIR else value,
            printd=lambda *args, **kwargs: None, _system=self.system)
        functions = [node for node in ast.parse(path.read_text(encoding='utf-8')).body
                     if isinstance(node, ast.FunctionDef) and node.name in ('execute', 'remote_execute')]
        self.assertEqual({node.name for node in functions}, {'execute', 'remote_execute'})
        for node in functions:
            node.decorator_list = []
        exec(compile(ast.Module(body=functions, type_ignores=[]), str(path), 'exec'), namespace)
        self.native = SimpleNamespace(remote_execute=namespace['remote_execute'])

    def system(self, command, **kwargs):
        self.calls.append((command, kwargs))
        if self.error is not None:
            raise self.error
        if kwargs.get('std_out') is not None:
            output = (fixture.identity_text() if '_USER_BEGIN__' in command else
                'CGYRO_QUEUE_OK\nCGYRO_ACCOUNT_OK\n'
                'CGYRO_STATE|123_0|COMPLETED|0:0\nCGYRO_STATE|123_1|COMPLETED|0:0\n')
            kwargs['std_out'].append(output)
        return self.return_code

    def test_original_native_executor_reproduces_missing_shell_before_process(self):
        with patch.dict(os.environ):
            os.environ.pop('SHELL', None)
            with self.assertRaisesRegex(KeyError, 'SHELL'):
                self.native.remote_execute('user@cluster', ':', '/', '', quiet=True, use_bang_command=False)
        self.assertEqual(self.calls, [])

    def test_recovery_and_status_use_native_local_route_without_shell(self):
        previous_directory = os.getcwd()
        with patch.dict(os.environ):
            os.environ.pop('SHELL', None)
            text = probe.remote_text(self.native, fixture.ENDPOINT, probe.identity_command('123'))
            self.assertEqual(probe.parse_identity(text, '123')['token'], fixture.TOKEN)
            # Simulate an independent later action, with SHELL absent again.
            os.environ.pop('SHELL')
            manifest = dict(fixture.manifest(), job_id='123', status='submitted')
            result = state.refresh_run_state(dict(RUN_MANIFEST=manifest,
                SETTINGS={'REMOTE_SETUP': dict(fixture.ENDPOINT)}), self.native)
            self.assertEqual(result['outcome'], 'completed')
            self.assertEqual(os.environ['SHELL'], '/bin/bash')
        self.assertEqual(os.getcwd(), previous_directory)
        self.assertEqual(len(self.calls), 2)
        for command, options in self.calls:
            self.assertTrue(options['ignoreReturnCode'])
            self.assertEqual(options['executable'], 'OMFITbash')
            self.assertIn('Open terminal', options['extraButtons'])
            self.assertNotIn('sbatch ', command)
            self.assertNotIn('scancel ', command)

    def test_existing_shell_is_preserved_and_empty_shell_gets_default(self):
        for supplied, expected in (('/bin/zsh', '/bin/zsh'), ('', '/bin/bash')):
            with self.subTest(shell=supplied), patch.dict(os.environ, {'SHELL': supplied}):
                probe.remote_text(self.native, fixture.ENDPOINT, probe.identity_command('123'))
                self.assertEqual(os.environ['SHELL'], expected)

    def test_native_nonzero_return_and_abort_remain_visible(self):
        previous_directory = os.getcwd()
        with patch.dict(os.environ):
            os.environ.pop('SHELL', None)
            self.return_code = 23
            with self.assertRaisesRegex(RuntimeError, 'recovery query failed'):
                probe.remote_text(self.native, fixture.ENDPOINT, ':')
            self.error = KeyboardInterrupt('native abort')
            with self.assertRaisesRegex(KeyboardInterrupt, 'native abort'):
                probe.remote_text(self.native, fixture.ENDPOINT, ':')
        self.assertEqual(os.getcwd(), previous_directory)
        self.assertEqual(len(self.calls), 2)


if __name__ == '__main__':
    unittest.main()
