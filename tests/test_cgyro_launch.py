"""Resource regressions, including the observed 9788077 submission mismatch."""
import ast
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import posixpath
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
import zipfile

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / 'CGYRO_TGLF_scan/LIB')]
from OMFITlib_cgyro_launch import (command_template, launch_spec, command_layout,
    slurm_guard, slurm_process_limits, upgrade_slurm_limits, validate_slurm_script,
    validate_checkpoint_runtime)


class LaunchTests(unittest.TestCase):
    def config(self, **changes):
        result = dict(scheduler='slurm', nodes=1, ntasks_per_node=32, cpus_per_task=1,
                      executable='cgyro -e . -n 16 -nomp 1 -mpinuma 16')
        result.update(changes)
        return result

    def test_observed_allocation_32_literal_launch_16_uses_all_requested_cpus(self):
        spec = launch_spec(self.config())
        self.assertEqual(spec['executable'], 'cgyro -e . -n 32 -nomp 1')
        self.assertEqual((spec['mpi_ranks'], spec['threads'], spec['total_cpus']), (32, 1, 32))

    def test_hybrid_and_multiple_nodes_have_one_resource_budget(self):
        spec = launch_spec(self.config(nodes=2, ntasks_per_node=16, cpus_per_task=2))
        self.assertEqual(spec['executable'], 'cgyro -e . -n 32 -nomp 2')
        self.assertEqual(spec['total_cpus'], 64)

    def test_missing_n_and_nomp_are_explicit_in_the_launch(self):
        self.assertEqual(launch_spec(self.config(executable='cgyro -e .'))['executable'],
                         'cgyro -e . -n 32 -nomp 1')

    def test_quotes_variables_other_arguments_and_comments_survive(self):
        command = '"${GACODE_ROOT}/cgyro/bin/cgyro" -e "input directory" -n 16 -nomp 2 # user note'
        rendered = launch_spec(self.config(executable=command))['executable']
        self.assertIn('"${GACODE_ROOT}/cgyro/bin/cgyro"', rendered)
        self.assertIn('-e "input directory"', rendered)
        self.assertEqual(shlex.split(rendered, comments=True)[-4:], ['-n', '32', '-nomp', '1'])
        self.assertTrue(rendered.endswith('# user note'))

    def test_environment_preamble_remains_separate(self):
        command = 'export MY_SETTING=1\ncgyro -e . -n 16'
        self.assertEqual(command_template(command),
                         'export MY_SETTING=1\ncgyro -e . -n {mpi} -nomp {threads}')

    def test_trusted_shell_substitutions_are_preserved_without_execution(self):
        for value in ('"$(printf chosen)"', '`hostname`', '"${GACODE_ROOT}/runs"'):
            with self.subTest(value=value):
                self.assertEqual(command_template('cgyro -e ' + value),
                                 'cgyro -e ' + value + ' -n {mpi} -nomp {threads}')

    def test_top_level_shell_control_is_not_a_single_solver_invocation(self):
        for tail in ('; echo extra', '| tee extra', '&& echo extra', '&'):
            with self.subTest(tail=tail), self.assertRaisesRegex(ValueError, 'inline shell control'):
                command_template('cgyro -e . ' + tail)

    def test_ambiguous_parallel_arguments_fail_before_submission(self):
        for command in ['cgyro -e . -n 16 -n 32', 'cgyro -e . -nomp 0',
                        'cgyro -e . -n "$CUSTOM_MPI"', 'mpirun -np 16 ./cgyro 0']:
            with self.subTest(command=command), self.assertRaises(ValueError):
                launch_spec(self.config(executable=command))

    def test_standalone_local_command_keeps_its_explicit_rank_count(self):
        spec = launch_spec(dict(scheduler='local', executable='cgyro -e . -n 1'),
                           dict(num_nodes=1, num_cores=32))
        self.assertEqual(spec['mpi_ranks'], 1)

    def test_actual_checkpoint_counts_override_historically_wrong_allocation(self):
        previous = self.config(environment='source /chosen/gacode')
        fixed = dict(previous, executable=launch_spec(previous)['executable'])
        with self.assertRaisesRegex(ValueError, 'Checkpoint used 16 MPI'):
            validate_checkpoint_runtime(previous, fixed)
        restored = dict(previous, ntasks_per_node=16, executable='cgyro -e . -n 16 -nomp 1')
        validate_checkpoint_runtime(previous, restored)
        restored['environment'] = 'source /different/gacode'
        with self.assertRaisesRegex(ValueError, 'environment'):
            validate_checkpoint_runtime(previous, restored)

    def test_cancelled_unstarted_points_may_use_the_corrected_larger_allocation(self):
        previous = self.config(environment='source /chosen/gacode')
        fixed = dict(previous, executable=launch_spec(previous)['executable'])
        # Frozen inputs with no samples/checkpoint can start at 32 MPI safely.
        validate_checkpoint_runtime(previous, fixed, has_checkpoint=False)
        with self.assertRaisesRegex(ValueError, 'Checkpoint used 16 MPI'):
            validate_checkpoint_runtime(previous, fixed, has_checkpoint=True)

    def test_frozen_retry_script_cannot_repeat_the_old_mismatch(self):
        script = '#!/bin/bash\n#SBATCH --nodes=1\n#SBATCH --ntasks-per-node=32\n#SBATCH --cpus-per-task=1\ncgyro -e . -n 16 -nomp 1 -mpinuma 16 > run_log 2>&1\n'
        with self.assertRaisesRegex(ValueError, 'requests 32 MPI.*starts 16 MPI'):
            validate_slurm_script(script)
        script = script.replace('-n 16', '-n 32')
        self.assertEqual(validate_slurm_script(script)['mpi_ranks'], 32)

    def test_saved_thread_mismatch_and_conflicting_headers_are_rejected(self):
        script = '#SBATCH --nodes=1\n#SBATCH --ntasks-per-node=16\n#SBATCH --cpus-per-task=2\ncgyro -e . -n 16 -nomp 1\n'
        with self.assertRaises(ValueError):
            validate_slurm_script(script)
        with self.assertRaises(ValueError):
            validate_slurm_script('#SBATCH --ntasks=8\n' + script.replace('-nomp 1', '-nomp 2'))

    def bash(self, source):
        command = ['wsl.exe', '-d', 'Ubuntu', '--', '/bin/bash', '-s'] if os.name == 'nt' else ['/bin/bash', '-s']
        result = subprocess.run(command, input=source.encode('utf-8'), stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, timeout=20)
        result.stdout = result.stdout.decode('utf-8', errors='replace')
        return result

    def test_real_shell_launches_with_matched_arguments_and_thread_environment(self):
        # A shell fixture records invocation, without running a solver or MPI.
        spec = launch_spec(self.config())
        script = 'set -e\nexport SLURM_NTASKS=32 SLURM_CPUS_PER_TASK=1\n'
        script += slurm_guard(spec)
        script += 'export OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1\n'
        script += 'cgyro() { printf "ARGV %s\\n" "$*"; printf "OMP %s %s\\n" "$OMP_NUM_THREADS" "$OMP_THREAD_LIMIT"; }\n'
        script += spec['executable'] + '\n'
        result = self.bash(script)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn('ARGV -e . -n 32 -nomp 1', result.stdout)
        self.assertIn('OMP 1 1', result.stdout)

    def test_real_shell_blocks_wrong_slurm_allocation_before_the_solver(self):
        script = 'export SLURM_NTASKS=16 SLURM_CPUS_PER_TASK=1\n'
        script += slurm_guard(launch_spec(self.config()))
        script += 'echo SOLVER_STARTED\n'
        result = self.bash(script)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('SOLVER_STARTED', result.stdout)
        self.assertIn('CGYRO resource mismatch', result.stdout)

    def test_soft_limits_fit_restrictive_hard_limits_without_changing_them(self):
        script = 'set -e\nulimit -Sn 1024\nulimit -Hn 4096\nulimit -Ss 4096\nulimit -Hs 8192\n'
        script += slurm_process_limits()
        script += 'printf "LIMITS %s %s %s %s\\n" "$(ulimit -Sn)" "$(ulimit -Hn)" "$(ulimit -Ss)" "$(ulimit -Hs)"\necho SOLVER_REACHED\n'
        result = self.bash(script)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn('LIMITS 4096 4096 8192 8192', result.stdout)
        self.assertIn('SOLVER_REACHED', result.stdout)

    def test_larger_inherited_soft_limit_is_preserved(self):
        script = 'set -e\nulimit -Sn 65536\nulimit -Hn 131072\n'
        script += slurm_process_limits()
        script += 'printf "LIMITS %s %s\\n" "$(ulimit -Sn)" "$(ulimit -Hn)"\n'
        result = self.bash(script)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn('LIMITS 65536 131072', result.stdout)

    def test_cluster_denial_is_advisory_under_set_e(self):
        script = '''set -e
ulimit -Sn 1024
ulimit -Hn 4096
ulimit -Ss 4096
ulimit -Hs 8192
ulimit() {
  if [ "$#" -gt 1 ] && { [ "$1" = -Sn ] || [ "$1" = -Ss ]; }; then return 1; fi
  builtin ulimit "$@"
}
'''
        script += slurm_process_limits()
        script += 'printf "LIMITS %s %s %s %s\\n" "$(ulimit -Sn)" "$(ulimit -Hn)" "$(ulimit -Ss)" "$(ulimit -Hs)"\necho SOLVER_REACHED\n'
        result = self.bash(script)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn('cannot raise soft limit', result.stdout)
        self.assertIn('LIMITS 1024 4096 4096 8192', result.stdout)
        self.assertIn('SOLVER_REACHED', result.stdout)

    def test_old_retry_preamble_is_repaired_without_changing_original_or_mpi(self):
        header = '#!/bin/bash\n#SBATCH --nodes=1\n#SBATCH --ntasks-per-node=32\n#SBATCH --cpus-per-task=1\n'
        original = header + 'set -e\nulimit -n 65535\nulimit -s unlimited\ncgyro -e . -n 32 -nomp 1\n'
        snapshot = original
        fixed = upgrade_slurm_limits(original)
        self.assertEqual(original, snapshot)
        before, after = validate_slurm_script(original), validate_slurm_script(fixed)
        self.assertEqual((before['mpi_ranks'], before['threads']),
                         (after['mpi_ranks'], after['threads']))
        self.assertEqual(upgrade_slurm_limits(fixed), fixed)
        fixture = 'set -e\nulimit -Sn 1024\nulimit -Hn 4096\ncgyro() { echo SOLVER_REACHED; }\n'
        failed = self.bash(fixture + original)
        self.assertNotEqual(failed.returncode, 0, failed.stdout)
        self.assertNotIn('SOLVER_REACHED', failed.stdout)
        result = self.bash(fixture + fixed)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn('SOLVER_REACHED', result.stdout)

    def test_custom_limit_policy_is_not_rewritten_and_ambiguous_blocks_fail(self):
        custom = 'set -e\nulimit -Sn 2048\ncgyro -e . -n 32\n'
        self.assertEqual(upgrade_slurm_limits(custom), custom)
        block = 'set -e\nulimit -n 65535\nulimit -s unlimited\n'
        user_environment = '#!/bin/bash\n#SBATCH --nodes=1\nsource /user/setup\n' + block
        self.assertEqual(upgrade_slurm_limits(user_environment), user_environment)
        with self.assertRaisesRegex(ValueError, 'Ambiguous'):
            upgrade_slurm_limits(block + block)

    def test_advisory_limits_do_not_hide_a_real_solver_failure(self):
        script = 'set -e\n' + slurm_process_limits()
        script += 'cgyro() { return 7; }\ncgyro\necho AFTER_SOLVER\n'
        result = self.bash(script)
        self.assertEqual(result.returncode, 7, result.stdout)
        self.assertNotIn('AFTER_SOLVER', result.stdout)

    def test_actual_retry_preparation_repairs_limits_and_retains_frozen_inputs(self):
        # Execute the real preparation function with isolated file/UI adapters.
        # The scheduler boundary records the prepared files; no job is sent.
        path = REPO / 'CGYRO_TGLF_scan/LIB/OMFITlib_cgyro_retry.py'
        tree = ast.parse(path.read_text(encoding='utf-8'))
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                        and node.name == 'submit_retry')
        original = ('#!/bin/bash\n#SBATCH --nodes=1\n#SBATCH --ntasks=16\n'
                    '#SBATCH --ntasks-per-node=16\n#SBATCH --cpus-per-task=1\n'
                    '#SBATCH --array=0-1%40\nset -e\nulimit -n 65535\nulimit -s unlimited\n'
                    'cgyro -e . -n 16 -nomp 1\n')
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = base / 'scan.pbs'
            source.write_bytes(original.encode('utf-8'))
            packed = base / 'p000001.zip'
            payload = b'N_ENERGY=8\n'
            with zipfile.ZipFile(packed, 'w') as archive:
                archive.writestr('input.cgyro', payload)
            manifest = dict(local_workDir=str(base), workDir='/original/run', scheduler='slurm',
                points=['p000001', 'p000002'], job_id='125749', status='failed',
                input_sha256={'p000001': {'input.cgyro': hashlib.sha256(payload).hexdigest()}},
                submit_script_sha256=hashlib.sha256(source.read_bytes()).hexdigest())
            root, prepared = dict(RUN_MANIFEST=manifest), []

            def executor(root, ui, factory, reader, inputs, local, command):
                script = Path(inputs[0]).read_bytes()
                self.assertEqual(hashlib.sha256(script).hexdigest(), manifest['retry_script_sha256'])
                self.assertEqual(command, 'sbatch --array=0%40 scan.pbs')
                self.assertIn(b'# OMFIT CGYRO soft process limits v1', script)
                self.assertEqual(validate_slurm_script(script.decode())['mpi_ranks'], 16)
                prepared.append(script)
                manifest.update(job_id='next_job', status='submitted', submission_uncertain=False)

            namespace = dict(os=os, posixpath=posixpath, tempfile=tempfile, uuid=uuid, hashlib=hashlib,
                re=re, shutil=shutil, zipfile=zipfile, deepcopy=deepcopy, datetime=datetime, timezone=timezone,
                validate_slurm_script=validate_slurm_script, upgrade_slurm_limits=upgrade_slurm_limits,
                retryable_points=lambda root: ['p000001'], save_current=lambda *args: None,
                execute_submission=executor,
                submission_file=lambda root, manifest, kind, point=None: str(source if kind == 'scan.pbs' else packed))
            exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), 'exec'), namespace)
            for attempt in range(2):
                namespace['submit_retry'](root, None, dict, str, str, ['p000001'])
            self.assertEqual(source.read_bytes(), original.encode('utf-8'))
            self.assertEqual(manifest['submit_script_sha256'], hashlib.sha256(source.read_bytes()).hexdigest())
            self.assertEqual(manifest['retry_count'], 2)
            self.assertEqual(manifest['point_workdirs']['p000002'], '/original/run')
            self.assertEqual(manifest['attempts'][1]['script_sha256'], hashlib.sha256(prepared[0]).hexdigest())
            self.assertEqual(prepared[0], prepared[1])
            with zipfile.ZipFile(packed) as archive:
                self.assertEqual(archive.read('input.cgyro'), payload)

    def test_actual_submission_script_matches_32_mpi_and_runs_one_array_element(self):
        path = REPO / 'CGYRO_TGLF_scan/CGYRO_scan/SCRIPTS/subscan_lin.py'
        tree = ast.parse(path.read_text(encoding='utf-8'))
        definitions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in
                       ('cfg_get', 'cfg_str', 'required_cfg', 'required_cfg_int', 'config_error', 'script_fragment')]
        selected, active = [], False
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'environment'
                                                    for target in node.targets):
                active = True
            if active:
                selected.append(node)
                if isinstance(node, ast.With):
                    break  # The real script has just written scan.pbs.
        config = self.config(environment='true', queue='normal', w='01:00:00', array_parallel=60)
        with tempfile.TemporaryDirectory() as temporary:
            namespace = dict(os=os, server_setup=config, setup={}, manifest={}, local_submit=False,
                             execution=launch_spec(config), submit_workdir=temporary,
                             dir_list=['p000001'], slurm_guard=slurm_guard,
                             slurm_process_limits=slurm_process_limits)
            exec(compile(ast.Module(body=definitions + selected, type_ignores=[]), str(path), 'exec'), namespace)
            script = (Path(temporary) / 'scan.pbs').read_text()
        self.assertIn('#SBATCH --ntasks=32\n', script)
        self.assertIn('#SBATCH --ntasks-per-node=32\n', script)
        self.assertEqual(validate_slurm_script(script)['mpi_ranks'], 32)
        fixture = '''set -e
TaskFixtureDir=$(mktemp -d /tmp/omfit-launch-test.XXXXXX)
trap 'case "$TaskFixtureDir" in /tmp/omfit-launch-test.*) rm -rf -- "$TaskFixtureDir";; esac' EXIT
cd "$TaskFixtureDir"
export SLURM_NTASKS=32 SLURM_CPUS_PER_TASK=1 SLURM_ARRAY_TASK_ID=0
ulimit -Sn 1024
ulimit -Hn 4096
ulimit -Ss 4096
ulimit -Hs 8192
unzip() { printf 'input fixture\\n' > "$4/input.cgyro"; }
cgyro() {
  printf 'ARGV %s\\n' "$*"
  printf 'OMP %s %s\\n' "$OMP_NUM_THREADS" "$OMP_THREAD_LIMIT"
  printf 'grid fixture\\n' > out.cgyro.grids
  printf 'time fixture\\n' > out.cgyro.time
}
'''
        result = self.bash(fixture + script + '\ncat p000001/run_log\nprintf "LIMITS %s %s %s %s\\n" "$(ulimit -Sn)" "$(ulimit -Hn)" "$(ulimit -Ss)" "$(ulimit -Hs)"\ncat p000001/cgyro.exit\n')
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn('ARGV -e . -n 32 -nomp 1', result.stdout)
        self.assertIn('OMP 1 1', result.stdout)
        self.assertIn('LIMITS 4096 4096 8192 8192', result.stdout)
        self.assertTrue(result.stdout.rstrip().endswith('0'), result.stdout)


if __name__ == '__main__':
    unittest.main()
