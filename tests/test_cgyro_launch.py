"""Resource regressions, including the observed 9788077 submission mismatch."""
import ast
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / 'CGYRO_TGLF_scan/LIB')]
from OMFITlib_cgyro_launch import (command_template, launch_spec, command_layout,
    slurm_guard, validate_slurm_script, validate_checkpoint_runtime)


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
                             dir_list=['p000001'], slurm_guard=slurm_guard)
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
unzip() { printf 'input fixture\\n' > "$4/input.cgyro"; }
cgyro() {
  printf 'ARGV %s\\n' "$*"
  printf 'OMP %s %s\\n' "$OMP_NUM_THREADS" "$OMP_THREAD_LIMIT"
  printf 'grid fixture\\n' > out.cgyro.grids
  printf 'time fixture\\n' > out.cgyro.time
}
'''
        result = self.bash(fixture + script + '\ncat p000001/run_log\ncat p000001/cgyro.exit\n')
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn('ARGV -e . -n 32 -nomp 1', result.stdout)
        self.assertIn('OMP 1 1', result.stdout)
        self.assertTrue(result.stdout.rstrip().endswith('0'), result.stdout)


if __name__ == '__main__':
    unittest.main()
