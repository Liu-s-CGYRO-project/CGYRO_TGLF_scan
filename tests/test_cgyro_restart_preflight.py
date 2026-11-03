"""Version-specific histories are checked only for selected restart owners."""
import copy
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import test_cgyro_storage  # Isolated native adapters.
import OMFITlib_cgyro_restart_preflight as preflight


class RestartPreflightTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.runtime = dict(environment='export GACODE_ROOT=/selected', executable='cgyro -e . -n 32 -nomp 2')
        self.cache = {}
        self.args = (self.runtime, object(), 'cluster', '/work', '', self.cache)

    def response(self, state='required', code=0):
        def remote(*args, **kwargs):
            kwargs['std_out'].append('CGYRO_RESTART_DEBUG|' + state + '\n')
            return code
        return remote

    def check(self):
        preflight.check_debug_history(str(self.directory), 'p000001', *self.args)

    def test_complete_selected_history_never_queries_the_server(self):
        (self.directory / preflight.DEBUG_TIMING).write_text('original timer stream\n')
        with patch.object(preflight, 'native_remote_execute', side_effect=AssertionError('remote query')):
            self.check()
        self.assertEqual(self.cache, {})

    def test_missing_required_history_is_rejected_and_query_is_cached(self):
        with patch.object(preflight, 'native_remote_execute', side_effect=self.response()) as remote:
            for _ in range(2):
                with self.assertRaisesRegex(ValueError, 'p000001.*out.cgyro.timing.debug'):
                    self.check()
        self.assertEqual(remote.call_count, 1)
        self.assertIn('command -v', remote.call_args.args[2])
        self.assertNotIn('cgyro -e .', remote.call_args.args[2])

    def test_standard_and_unidentified_installations_do_not_invent_histories(self):
        for state in ('absent', 'unknown'):
            self.cache.clear()
            with patch.object(preflight, 'native_remote_execute', side_effect=self.response(state)):
                self.check()
            self.assertFalse((self.directory / preflight.DEBUG_TIMING).exists())

    def test_failed_query_is_not_a_successful_requirement_cache(self):
        with patch.object(preflight, 'native_remote_execute', side_effect=self.response(code=1)):
            with self.assertRaisesRegex(RuntimeError, 'no job submitted'):
                self.check()
        self.assertEqual(self.cache, {})

    def test_one_bad_point_does_not_block_complete_point_or_inspect_unselected_owner(self):
        good = self.directory / 'good'
        good.mkdir()
        (good / preflight.DEBUG_TIMING).write_text('original history\n')
        plan = dict(points=['bad', 'good'], sources={
            'bad': dict(mode='checkpoint', directory=str(self.directory)),
            'good': dict(mode='checkpoint', directory=str(good)),
            'unselected': dict(mode='checkpoint_zip', zip='/must-not-read.zip')},
            scope={'planned': ['bad', 'good', 'unselected']})
        coverage = copy.deepcopy(plan['scope'])
        with patch.object(preflight, 'native_remote_execute', side_effect=self.response()) as remote:
            preflight.filter_restart_points(plan, *self.args)
        self.assertEqual(plan['points'], ['good'])
        self.assertEqual(set(plan['rejected']), {'bad'})
        self.assertEqual(plan['scope'], coverage)
        self.assertEqual(remote.call_count, 1)

    def test_checkpoint_zip_is_checked_without_unpacking_or_changing_it(self):
        path = self.directory / 'point.zip'
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr(preflight.DEBUG_TIMING, 'timer history\n')
        before = path.read_bytes()
        plan = dict(points=['p000001'], sources={'p000001': dict(mode='checkpoint_zip', zip=str(path))})
        with patch.object(preflight, 'native_remote_execute', side_effect=AssertionError('remote query')):
            preflight.filter_restart_points(plan, *self.args)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(list(self.directory.iterdir()), [path])

    def test_fresh_retained_input_needs_no_restart_history(self):
        plan = dict(points=['fresh'], sources={'fresh': dict(mode='fresh', zip='/checked-by-prepare.zip')})
        with patch.object(preflight, 'native_remote_execute', side_effect=AssertionError('remote query')):
            preflight.filter_restart_points(plan, *self.args)
        self.assertEqual(plan['points'], ['fresh'])

    def test_all_invalid_points_are_reported_without_an_empty_submission(self):
        plan = dict(points=['one', 'two'], sources={point: dict(mode='checkpoint', directory=str(self.directory))
                                                  for point in ('one', 'two')})
        with patch.object(preflight, 'native_remote_execute', side_effect=self.response()):
            with self.assertRaisesRegex(ValueError, 'no job submitted'):
                preflight.filter_restart_points(plan, *self.args)
        self.assertEqual(set(plan['rejected']), {'one', 'two'})


class InstalledHistoryProbeTests(unittest.TestCase):
    def test_real_shell_probes_selected_installation_without_running_solver(self):
        for kind, expected in (('custom', 'required'), ('standard', 'absent'), ('wrapper', 'unknown')):
            with self.subTest(kind=kind):
                runtime = dict(environment='export GACODE_ROOT="$probe_dir/gacode"\n'
                                           'export PATH="$GACODE_ROOT/cgyro/bin:$PATH"',
                               executable='cgyro -e . -n 32 -nomp 2')
                setup = r'''set -eu
probe_dir=$(mktemp -d)
trap 'rm -r -- "$probe_dir"' EXIT
mkdir -p "$probe_dir/gacode/cgyro/bin" "$probe_dir/gacode/cgyro/src" "$probe_dir/wrapper"
printf '#!/bin/sh\necho SOLVER_MUST_NOT_RUN >&2\nexit 67\n' > "$probe_dir/gacode/cgyro/bin/cgyro"
chmod +x "$probe_dir/gacode/cgyro/bin/cgyro"
'''
                marker = preflight.DEBUG_TIMING if kind == 'custom' else 'ordinary timer stream'
                setup += "printf '%s\\n' '" + marker + "' > \"$probe_dir/gacode/cgyro/src/cgyro\"\n"
                if kind == 'wrapper':
                    setup += 'cp "$probe_dir/gacode/cgyro/bin/cgyro" "$probe_dir/wrapper/cgyro"\n'
                    runtime['environment'] += '\nexport PATH="$probe_dir/wrapper:$PATH"'
                command = ['wsl.exe', '-d', 'Ubuntu', '--', '/bin/bash', '-s'] if os.name == 'nt' else ['/bin/bash', '-s']
                result = subprocess.run(command, input=(setup + preflight.requirement_command(runtime)).encode(),
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
                self.assertEqual(result.returncode, 0, result.stderr.decode())
                self.assertEqual(result.stdout.decode().strip(), 'CGYRO_RESTART_DEBUG|' + expected)
                self.assertNotIn(b'SOLVER_MUST_NOT_RUN', result.stderr)


if __name__ == '__main__':
    unittest.main()
