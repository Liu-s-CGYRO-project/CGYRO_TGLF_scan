"""Endpoint-scoped server detection with isolated queue and native-tree fixtures."""
import copy
from pathlib import Path
import sys
import unittest

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(path) for path in (REPO / 'CGYRO_TGLF_scan').rglob('LIB')]
from OMFITlib_server_capabilities import (TOOLS, VERSION, adapt_draft, matching_profile, parse_probe,
    probe_script, resource_issues, summary, time_seconds)
from OMFITlib_cgyro_launch import launch_spec, validate_checkpoint_runtime
from OMFITlib_gacode_installations import PROGRAMS, program_environment, program_guard
import test_cgyro_launch as launch_tests


def output(queues=None, status='ok'):
    rows = ['OMFIT_SERVER\t{}\tlogin-test\t256\t1024\t4096\t8192\tunlimited'.format(VERSION)]
    rows += ['OMFIT_SERVER_TOOL\t{}\t{}'.format(name, '/usr/bin/' + name if name in ('sbatch', 'sinfo') else '')
             for name in TOOLS]
    rows += ['OMFIT_SERVER_QUEUE\t' + row for row in (queues if queues is not None else
             ['normal*|64|128000|01:00:00|up|32|5'])]
    return rows + ['OMFIT_SERVER_SLURM\t' + status, 'OMFIT_SERVER_END']


class CapabilityTests(unittest.TestCase):
    def config(self, **changes):
        value = dict(server='user@cluster', tunnel='', scheduler='slurm', queue='normal',
                     nodes=2, cores=16, cpus_per_task=1, wall_time='01:00:00')
        value.update(changes)
        return value

    def profile(self, config=None, **changes):
        value = parse_probe(output(), config or self.config())
        value.update(changes)
        return value

    def mixed(self, limit='UNLIMITED'):
        return ['normal*|32|126536|01:00:00|up|{}|3'.format(limit),
                'normal*|64|255500|01:00:00|up|{}|2'.format(limit)]

    def test_queue_capacity_uses_scheduler_nodes_and_partition_cap(self):
        value = self.profile()
        self.assertEqual(value['login_cpus'], 256)
        self.assertEqual(value['partitions']['normal']['cpus_per_node'], 32)
        self.assertEqual(value['partitions']['normal']['memory_mib'], 128000)
        self.assertEqual(resource_issues(self.config(), value), [])
        self.assertTrue(resource_issues(self.config(cores=64), value))

    def test_mixed_partition_accepts_64_cpus_independent_of_report_order(self):
        for rows in (self.mixed(), list(reversed(self.mixed()))):
            profile = parse_probe(output(rows), self.config())
            row = profile['partitions']['normal']
            self.assertEqual(row['cpus_per_node'], 64)
            self.assertEqual(row['cpu_counts'], [32, 64])
            self.assertEqual(row['node_count'], 5)
            self.assertEqual(resource_issues(self.config(cores=64), profile), [])
            config = self.config(cores=64)
            self.assertEqual(adapt_draft(config, profile), [])
            self.assertEqual(config['cores'], 64)

    def test_mixed_capacity_still_respects_real_partition_cpu_limit(self):
        for limit in ('32', '48'):
            profile = parse_probe(output(self.mixed(limit)), self.config())
            row = profile['partitions']['normal']
            self.assertEqual(row['cpus_per_node'], int(limit))
            self.assertEqual(row['cpu_counts'], [32, 64])
            self.assertTrue(resource_issues(self.config(cores=64), profile))
            self.assertEqual(resource_issues(self.config(cores=int(limit)), profile), [])

    def test_multinode_request_counts_only_shapes_large_enough_for_each_node(self):
        profile = parse_probe(output(self.mixed()), self.config())
        self.assertEqual(resource_issues(self.config(nodes=2, cores=32, cpus_per_task=2), profile), [])
        issues = resource_issues(self.config(nodes=3, cores=32, cpus_per_task=2), profile)
        self.assertEqual(len(issues), 1)
        self.assertIn('节点共 2 个', issues[0])
        self.assertEqual(resource_issues(self.config(nodes=5, cores=32), profile), [])

    def test_summary_shows_mixed_hardware_and_separate_task_limit(self):
        profile = parse_probe(output(self.mixed('48')), self.config())
        text = '\n'.join(summary(self.config(), profile))
        self.assertIn('32 / 64 CPU/节点', text)
        self.assertIn('最多可申请 48 CPU/节点', text)
        self.assertIn('126536–255500', text)

    def test_only_invalid_128_cpu_draft_is_clamped_to_64_on_mixed_partition(self):
        profile = parse_probe(output(self.mixed()), self.config())
        config = self.config(cores=64, cpus_per_task=2)
        self.assertEqual(adapt_draft(config, profile), ['MPI/节点 64 → 32'])
        self.assertEqual((config['cores'], config['cpus_per_task']), (32, 2))

    def test_old_collapsed_profile_is_invalidated_after_code_update(self):
        config, profile = self.config(), self.profile()
        profile['version'] = 1
        self.assertEqual(matching_profile(config, dict(capabilities=profile)), {})
        with self.assertRaises(ValueError):
            parse_probe([line.replace('OMFIT_SERVER\t2\t', 'OMFIT_SERVER\t1\t')
                         for line in output()], config)

    def test_conflicting_partition_policy_and_malformed_counts_fail_before_mutation(self):
        for queues in (self.mixed()[:1] + ['normal*|64|255500|01:00:00|up|32|2'],
                       ['normal*|64|255500|01:00:00|up|UNLIMITED|bad'],
                       ['normal*|64|255500|01:00:00|up|32+|2']):
            with self.subTest(queues=queues), self.assertRaises(ValueError):
                parse_probe(output(queues), self.config())

    def test_empty_node_group_cannot_inflate_partition_capacity(self):
        rows = ['normal*|32|126536|01:00:00|up|UNLIMITED|3',
                'normal*|128|255500|01:00:00|up|UNLIMITED|0']
        profile = parse_probe(output(rows), self.config())
        self.assertEqual(profile['partitions']['normal']['cpus_per_node'], 32)
        self.assertTrue(resource_issues(self.config(cores=64), profile))

    def test_launch_validates_actual_ranks_even_if_ui_cores_alias_is_stale(self):
        profile = parse_probe(output(self.mixed()), self.config())
        config = dict(self.config(cores=16), ntasks_per_node=128,
                      executable='cgyro -e . -n 128 -nomp 1', server_capabilities=profile)
        with self.assertRaisesRegex(ValueError, '超过队列'):
            launch_spec(config)
        config.update(cores=128, ntasks_per_node=64)
        self.assertEqual(launch_spec(config)['mpi_ranks'], 128)

    def test_truncated_and_malformed_results_are_rejected(self):
        for rows in (output()[:-1], output()[:1], output(queues=['normal|oops|2|01:00:00|up|32']),
                     output(queues=['normal|32|2|01:00:00|up'])):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                parse_probe(rows, self.config())

    def test_unavailable_slurm_does_not_fabricate_limits_from_login_node(self):
        value = parse_probe(output(queues=[], status='unavailable'), self.config())
        config = self.config(cores=10000)
        self.assertEqual(adapt_draft(config, value), [])
        self.assertEqual(config['cores'], 10000)
        self.assertEqual(resource_issues(config, value), [])
        self.assertTrue(any('未读取' in line for line in summary(config, value)))

    def test_profile_cannot_be_reused_on_another_endpoint_or_tunnel(self):
        config, profile = self.config(), self.profile()
        self.assertEqual(matching_profile(config, dict(capabilities=profile)), profile)
        for change in (dict(server='other@cluster'), dict(tunnel='another-jump')):
            self.assertEqual(matching_profile(self.config(**change), dict(capabilities=profile)), {})

    def test_valid_user_mpi_and_threads_are_preserved(self):
        config = self.config(cores=8, cpus_per_task=2)
        previous = copy.deepcopy(config)
        self.assertEqual(adapt_draft(config, self.profile()), [])
        self.assertEqual(config, previous)

    def test_explicit_scan_clamps_only_invalid_draft_resources_and_time(self):
        config = self.config(cores=64, cpus_per_task=2, wall_time='24:00:00')
        changes = adapt_draft(config, self.profile())
        self.assertEqual((config['nodes'], config['cores'], config['cpus_per_task']), (2, 16, 2))
        self.assertEqual(config['wall_time'], '01:00:00')
        self.assertEqual(len(changes), 2)
        self.assertEqual(resource_issues(config, self.profile()), [])
        before = dict(executable='cgyro -e . -n 128 -nomp 2', environment='same')
        with self.assertRaisesRegex(ValueError, 'Checkpoint used 128 MPI'):
            validate_checkpoint_runtime(before, dict(executable='cgyro -e . -n 32 -nomp 2', environment='same'))

    def test_threads_cannot_leave_zero_mpi_slots(self):
        config = self.config(cores=16, cpus_per_task=128)
        adapt_draft(config, self.profile())
        self.assertEqual((config['cores'], config['cpus_per_task']), (1, 32))

    def test_unlimited_requested_time_is_capped_when_partition_is_finite(self):
        config = self.config(wall_time='UNLIMITED')
        self.assertTrue(resource_issues(config, self.profile()))
        adapt_draft(config, self.profile())
        self.assertEqual(config['wall_time'], '01:00:00')

    def test_only_a_blank_queue_uses_the_unique_default(self):
        config = self.config(queue='')
        self.assertEqual(adapt_draft(config, self.profile()), ['队列 → normal'])
        config = self.config(queue='explicit-other')
        self.assertEqual(adapt_draft(config, self.profile()), [])
        self.assertEqual(config['queue'], 'explicit-other')
        self.assertTrue(resource_issues(config, self.profile()))

    def test_new_submission_rechecks_bound_profile_and_rejects_later_invalid_edits(self):
        config = dict(self.config(cores=64), ntasks_per_node=64,
                      executable='cgyro -e . -n 128 -nomp 1', server_capabilities=self.profile())
        with self.assertRaisesRegex(ValueError, '超过队列'):
            launch_spec(config)
        config.update(ntasks_per_node=16, cores=16)
        self.assertEqual(launch_spec(config)['mpi_ranks'], 32)

    def test_slurm_time_forms_and_unlimited(self):
        for value, expected in [('60', 3600), ('01:30', 90), ('01:00:00', 3600),
                                ('2-03:04:05', 183845), ('1-02:30', 95400), ('UNLIMITED', None)]:
            self.assertEqual(time_seconds(value), expected)

    def test_real_shell_probe_does_not_submit_or_source_environment(self):
        fixture = '''set -e
TaskCapabilityDir=$(mktemp -d /tmp/omfit-cap-test.XXXXXX)
trap 'case "$TaskCapabilityDir" in /tmp/omfit-cap-test.*) rm -rf -- "$TaskCapabilityDir";; esac' EXIT
cat > "$TaskCapabilityDir/sinfo" <<'SH'
#!/bin/sh
printf 'normal*|64|128000|01:00:00|up|32|5\\n'
SH
cat > "$TaskCapabilityDir/sbatch" <<'SH'
#!/bin/sh
echo UNEXPECTED_SUBMIT
exit 90
SH
chmod u+x "$TaskCapabilityDir/sinfo" "$TaskCapabilityDir/sbatch"
export PATH="$TaskCapabilityDir:$PATH"
'''
        result = launch_tests.LaunchTests().bash(fixture + probe_script())
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn('UNEXPECTED_SUBMIT', result.stdout)
        value = parse_probe(result.stdout.splitlines(), self.config())
        self.assertEqual(value['partitions']['normal']['cpus_per_node'], 32)

    def test_real_shell_mixed_partition_preserves_64_cpu_request_without_submission(self):
        fixture = '''set -e
TaskCapabilityDir=$(mktemp -d /tmp/omfit-cap-test.XXXXXX)
trap 'case "$TaskCapabilityDir" in /tmp/omfit-cap-test.*) rm -rf -- "$TaskCapabilityDir";; esac' EXIT
cat > "$TaskCapabilityDir/sinfo" <<'SH'
#!/bin/sh
printf 'normal*|32|126536|01:00:00|up|UNLIMITED|3\\nnormal*|64|255500|01:00:00|up|UNLIMITED|2\\n'
SH
cat > "$TaskCapabilityDir/sbatch" <<'SH'
#!/bin/sh
echo UNEXPECTED_SUBMIT
exit 90
SH
chmod u+x "$TaskCapabilityDir/sinfo" "$TaskCapabilityDir/sbatch"
export PATH="$TaskCapabilityDir:$PATH"
'''
        result = launch_tests.LaunchTests().bash(fixture + probe_script())
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn('UNEXPECTED_SUBMIT', result.stdout)
        profile = parse_probe(result.stdout.splitlines(), self.config())
        config = self.config(cores=64)
        self.assertEqual(resource_issues(config, profile), [])
        self.assertEqual(adapt_draft(config, profile), [])

    def test_execution_guard_checks_helpers_and_platform_without_running_mpi(self):
        fixture = '''set -e
TaskGuardDir=$(mktemp -d /tmp/omfit-guard-test.XXXXXX)
trap 'case "$TaskGuardDir" in /tmp/omfit-guard-test.*) rm -rf -- "$TaskGuardDir";; esac' EXIT
export GACODE_ROOT="$TaskGuardDir/gacode" GACODE_PLATFORM=FIXTURE
mkdir -p "$GACODE_ROOT/cgyro/bin" "$GACODE_ROOT/cgyro/src" "$GACODE_ROOT/shared/bin" "$GACODE_ROOT/platform/exec" "$TaskGuardDir/bin"
for file in cgyro/bin/cgyro cgyro/src/cgyro shared/bin/gacode_getversion shared/bin/gacode_printversion shared/bin/gacode_sim_warn; do
  printf '#!/bin/sh\\nexit 99\\n' > "$GACODE_ROOT/$file"
  chmod u+x "$GACODE_ROOT/$file"
done
printf '#!/bin/sh\\nmpiexec -np 32 cgyro\\n' > "$GACODE_ROOT/platform/exec/exec.FIXTURE"
chmod u+x "$GACODE_ROOT/platform/exec/exec.FIXTURE"
printf '#!/bin/sh\\necho UNEXPECTED_MPI\\nexit 99\\n' > "$TaskGuardDir/bin/mpiexec"
chmod u+x "$TaskGuardDir/bin/mpiexec"
export PATH="$TaskGuardDir/bin:$PATH"
'''
        guard = program_guard('cgyro')
        result = launch_tests.LaunchTests().bash(fixture + guard + 'echo GUARD_OK\n')
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn('GUARD_OK', result.stdout)
        self.assertNotIn('UNEXPECTED_MPI', result.stdout)
        result = launch_tests.LaunchTests().bash(fixture + 'chmod u-x "$GACODE_ROOT/shared/bin/gacode_sim_warn"\n' + guard)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Missing CGYRO executable', result.stdout)

    def test_execution_guard_rejects_missing_direct_mpi_launcher(self):
        # Isolate PATH so an MPI installed on the test host cannot mask failure.
        fixture = '''set -e
TaskGuardDir=$(mktemp -d /tmp/omfit-mpi-guard-test.XXXXXX)
trap 'case "$TaskGuardDir" in /tmp/omfit-mpi-guard-test.*) /bin/rm -rf -- "$TaskGuardDir";; esac' EXIT
export GACODE_ROOT="$TaskGuardDir/gacode" GACODE_PLATFORM=FIXTURE
mkdir -p "$GACODE_ROOT/cgyro/bin" "$GACODE_ROOT/cgyro/src" "$GACODE_ROOT/shared/bin" "$GACODE_ROOT/platform/exec" "$TaskGuardDir/bin"
for file in cgyro/bin/cgyro cgyro/src/cgyro shared/bin/gacode_getversion shared/bin/gacode_printversion shared/bin/gacode_sim_warn; do
  printf '#!/bin/sh\\nexit 99\\n' > "$GACODE_ROOT/$file"
  chmod u+x "$GACODE_ROOT/$file"
done
printf '#!/bin/sh\\nexec mpiexec -np 32 cgyro\\n' > "$GACODE_ROOT/platform/exec/exec.FIXTURE"
chmod u+x "$GACODE_ROOT/platform/exec/exec.FIXTURE"
ln -s "$(command -v awk)" "$TaskGuardDir/bin/awk"
export PATH="$TaskGuardDir/bin"
'''
        result = launch_tests.LaunchTests().bash(fixture + program_guard('cgyro'))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Missing MPI launcher after environment setup: mpiexec', result.stdout)

    def test_new_preflight_does_not_invalidate_the_same_checkpoint_environment(self):
        legacy_guard = '''[ -n "${GACODE_ROOT:-}" ] || { echo "GACODE_ROOT is not set for CGYRO." >&2; exit 1; }
[ -f "$GACODE_ROOT"/cgyro/bin/cgyro ] && [ -x "$GACODE_ROOT"/cgyro/bin/cgyro ] || { printf "Missing CGYRO executable: %s/cgyro/bin/cgyro\\n" "$GACODE_ROOT" >&2; exit 1; }
[ -f "$GACODE_ROOT"/cgyro/src/cgyro ] && [ -x "$GACODE_ROOT"/cgyro/src/cgyro ] || { printf "Missing CGYRO executable: %s/cgyro/src/cgyro\\n" "$GACODE_ROOT" >&2; exit 1; }'''
        setup = 'export GACODE_ROOT=/original\nsource /original/environment.sh'
        previous = dict(executable='cgyro -e . -n 16 -nomp 1', environment=setup + '\n' + legacy_guard)
        current = dict(previous, environment=program_environment(dict(environment=setup), 'cgyro'))
        validate_checkpoint_runtime(previous, current)
        changed = dict(current, environment=current['environment'].replace('/original', '/different'))
        with self.assertRaisesRegex(ValueError, 'environment'):
            validate_checkpoint_runtime(previous, changed)
        customized = dict(current, environment=current['environment'] + '\nexport USER_CHANGE=1')
        with self.assertRaisesRegex(ValueError, 'environment'):
            validate_checkpoint_runtime(previous, customized)


class DetectionActionTests(unittest.TestCase):
    tree_factory = dict

    def setUp(self):
        import test_cgyro_storage  # Isolated native-file adapters; no real project.
        from test_project import fixture
        from omfit_mapping import treeify
        from OMFITlib_project import ProjectActions
        from OMFITlib_project_runtime import initialize_runtime
        self.root = treeify(fixture(), self.tree_factory)
        self.actions = ProjectActions(self.root, self.tree_factory)
        self.config = initialize_runtime(self.root, self.tree_factory)
        self.config.update(dict(serverPicker='cluster', server='user@cluster', tunnel='',
            workDir='/work/user/OMFITtmp', scheduler='slurm', queue='normal', environment='true',
            gacode_scan_dir='/shared', cores=128, cpus_per_task=2, wall_time='24:00:00',
            gacode_installs={}))
        self.actions.runtime_server_issues = lambda **kwargs: []
        self.calls = []

    def remote(self, server, command, directory, **kwargs):
        self.calls.append(command)
        paths = list(dict.fromkeys(path for _, files in PROGRAMS.values() for path in files))
        kwargs['std_out'].extend(['OMFIT_GACODE\t/shared/gacode\t1\t1\t' + '\t'.join('1' for _ in paths),
                                 'OMFIT_GACODE_END'] + output(queues=getattr(self, 'queue_rows', None)))
        return 0

    def test_detect_updates_only_draft_and_apply_binds_profile_without_touching_results(self):
        from OMFITlib_project_runtime import apply_runtime, shared_issues
        marker = object()
        cg = self.root['CGYRO_scan']
        cg['RUN_DB'] = {'retained': marker}
        cg['RUN_MANIFEST'] = {'job_id': 'old_job', 'runtime': {'executable': 'cgyro -e . -n 128 -nomp 2'}}
        original = copy.deepcopy(cg['RUN_MANIFEST'])
        self.actions.remote_execute = self.remote
        detection = self.actions.detect_gacode()
        self.assertEqual(len(self.calls), 1)
        self.assertIn('OMFIT_SERVER', self.calls[0])
        self.assertEqual(self.config['cores'], 16)
        self.assertEqual(cg['RUN_MANIFEST'], original)
        self.assertIs(cg['RUN_DB']['retained'], marker)
        apply_runtime(self.root, self.tree_factory)
        selected = cg['SETTINGS']['REMOTE_SETUP']['cluster']
        self.assertEqual(selected['server_capabilities'], detection['capabilities'])
        self.assertEqual(selected['executable'], 'cgyro -e . -n 16 -nomp 2')
        self.assertEqual(shared_issues(self.root), [])
        detection['capabilities']['checked'] = 'changed'
        self.assertEqual(shared_issues(self.root), [])
        self.assertEqual(cg['RUN_MANIFEST'], original)
        self.assertIs(cg['RUN_DB']['retained'], marker)

    def test_incomplete_capability_scan_keeps_previous_inventory_and_config(self):
        previous = copy.deepcopy(self.config)
        self.root['PROJECT_STATE']['gacode_detection'] = {'old': 'kept'}
        def interrupted(*args, **kwargs):
            self.remote(*args, **kwargs)
            kwargs['std_out'].pop()  # Missing the completion marker.
            return 0
        self.actions.remote_execute = interrupted
        with self.assertRaisesRegex(ValueError, '未完成'):
            self.actions.detect_gacode()
        self.assertEqual(self.config, previous)
        self.assertEqual(self.root['PROJECT_STATE']['gacode_detection'], {'old': 'kept'})

    def test_detect_apply_and_launch_preserve_64_cpu_request_on_mixed_partition(self):
        from OMFITlib_project_runtime import apply_runtime, shared_issues
        self.queue_rows = ['normal*|64|255500|01:00:00|up|UNLIMITED|2',
                           'normal*|32|126536|01:00:00|up|UNLIMITED|3']
        self.config.update(nodes=1, cores=64, cpus_per_task=1, wall_time='01:00:00')
        self.actions.remote_execute = self.remote
        detection = self.actions.detect_gacode()
        self.assertEqual(self.config['cores'], 64)
        self.assertNotIn('MPI/节点', str(detection['capabilities'].get('draft_changes', [])))
        apply_runtime(self.root, self.tree_factory)
        selected = self.root['CGYRO_scan']['SETTINGS']['REMOTE_SETUP']['cluster']
        self.assertEqual(selected['ntasks_per_node'], 64)
        self.assertEqual(launch_spec(selected)['mpi_ranks'], 64)
        self.assertEqual(shared_issues(self.root), [])

    def test_unsaved_server_edit_never_probes_the_previous_endpoint(self):
        self.actions.settings['server_draft'] = {}
        self.actions.remote_execute = self.remote
        with self.assertRaisesRegex(ValueError, '服务器'):
            self.actions.detect_gacode()
        self.assertEqual(self.calls, [])


if __name__ == '__main__':
    unittest.main()
