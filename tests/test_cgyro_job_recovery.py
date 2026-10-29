"""Recovery after losing OMFIT, without a scheduler submission or live cluster."""
import base64
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'CGYRO_TGLF_scan/LIB'))
import test_cgyro_storage  # Native reader doubles, not result data.
from omfit_mapping import OMFITMapping, treeify
import OMFITlib_cgyro_recovery_manifest as schema
import OMFITlib_cgyro_job_probe as probe
import OMFITlib_cgyro_job_recovery as recovery
import OMFITlib_cgyro_retry as retry
import OMFITlib_cgyro_continue as continuation
import OMFITlib_cgyro_queue as queue
import OMFITlib_cgyro_workflow as workflow
from OMFITlib_cgyro_db import ensure_layout

TOKEN = 'a' * 32
WORKDIR = '/work/user/OMFIT/runs/' + TOKEN
ENDPOINT = dict(server='user@cluster', tunnel='', serverPicker='cluster')
SCRIPT = '#!/bin/bash\ndir_list=(p000001 p000002)\n'
INPUT = b'N_THETA=16\nKY=0.1\n'


def point_input(point):
    return INPUT if point == 'p000001' else b'N_THETA=16\nKY=0.2\n'


def manifest():
    points = ['p000001', 'p000002']
    return dict(run_token=TOKEN, workDir=WORKDIR, local_workDir='/tmp/old-session', scheduler='slurm',
        server='user@cluster', case_tag='lincgyro', runid='Jet', nr=1, rho=.33, mass='T',
        case_id='nr=1__rho=0.33__ion=T', dimensions=1, scan_dimensions=1, points=points,
        scan_axes=[dict(name='N_THETA', values=[16])],
        point_table={point: dict(values={'N_THETA': 16, 'KY': ky},
                    result_path=['N_THETA', '16.00000', 'lin', format(ky, '.5f')])
                    for point, ky in zip(points, (.1, .2))},
        input_sha256={point: {'input.cgyro': hashlib.sha256(point_input(point)).hexdigest()} for point in points},
        submit_script_sha256=hashlib.sha256(SCRIPT.encode()).hexdigest(), status='prepared')


def framed(name, value):
    return '\n__CGYRO_RECOVERY_' + name + '_BEGIN__\n' + value + '\n__CGYRO_RECOVERY_' + name + '_END__\n'


def identity_text(user='user', directory=WORKDIR, queue=''):
    return (framed('USER', 'user\n') + framed('QUEUE', queue) + framed('ACCOUNT',
        '123_0|{}|COMPLETED|{}\n123_1|{}|COMPLETED|{}\n'.format(user, directory, user, directory)))


class FileOwner:
    def __init__(self, filename):
        self.filename = str(filename)


class Remote:
    """Only the read/query/download interface is available to the recovery API."""
    def __init__(self, directory, frozen=None, state='completed', sidecar=False):
        self.directory = Path(directory)
        self.frozen = manifest() if frozen is None else frozen
        self.state = state
        self.sidecar = sidecar
        self.downloads = 0
        self.calls = []
        self.directory.mkdir(parents=True, exist_ok=True)
        (self.directory / 'scan.pbs').write_bytes(SCRIPT.encode())
        for point in self.frozen['points']:
            with zipfile.ZipFile(self.directory / (point + '.zip'), 'w') as packed:
                packed.writestr('input.cgyro', point_input(point))

    def remote_execute(self, server, command, workdir, tunnel, **kwargs):
        self.calls.append(command)
        if '_USER_BEGIN__' in command:
            output = identity_text()
        elif '_SCRIPT_BEGIN__' in command:
            candidate = WORKDIR + '/' + schema.SIDECAR if self.sidecar else '/tmp/user/OMFIT/old/manifest.json'
            output = (framed('RECEIPT', 'Submitted batch job 123\n')
                + framed('SCRIPT', base64.b64encode(SCRIPT.encode()).decode())
                + framed('NONCE', self.frozen.get('submission_nonce', '') + '\n')
                + framed('CANDIDATES', candidate + '\n'))
        elif '_JSON_BEGIN__' in command:
            value = dict(schema=1, manifest=self.frozen) if self.sidecar else self.frozen
            output = framed('JSON', json.dumps(value))
        elif '_INPUTS_BEGIN__' in command:
            output = framed('INPUTS', '\n'.join(name.name + '|' + str(name.stat().st_size)
                                               for name in self.directory.iterdir()))
        else:
            output = 'CGYRO_QUEUE_OK\nCGYRO_ACCOUNT_OK\n'
            if self.state == 'active':
                output += 'CGYRO_QUEUE|123_1|RUNNING\n'
            for index in range(2):
                phase = 'CANCELLED' if self.state == 'cancelled' else 'COMPLETED'
                output += 'CGYRO_STATE|123_{}|{}|0:0\n'.format(index, phase)
        kwargs['std_out'].append(output)
        return 0

    def remote_downsync(self, server, paths, local, **kwargs):
        self.downloads += 1
        for path in paths:
            shutil.copyfile(self.directory / Path(path).name, Path(local) / Path(path).name)
        return 0


class ManifestTests(unittest.TestCase):
    def test_legacy_and_sidecar_read_validate_exact_script(self):
        for envelope in (manifest(), dict(schema=1, manifest=manifest())):
            value = schema.read_manifest(json.dumps(envelope))
            self.assertEqual(schema.validate_manifest(value, WORKDIR, SCRIPT)['run_token'], TOKEN)

    def test_invalid_job_ids_never_become_shell(self):
        for value in ('', '0', '-1', '123_2', '1; sbatch x', '$(id)', None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                probe.identity_command(value)
        self.assertIn('job_id=123 ', probe.identity_command(' 123 '))

    def test_invalid_manifest_boundaries_fail_before_import(self):
        changes = [dict(points=[]), dict(point_table={}), dict(points=['p000001', 'p000001']),
                   dict(runid='__STORE__'), dict(workDir='/other'), dict(scan_axes=[]),
                   dict(submit_script_sha256='0' * 64), dict(input_sha256={}),
                   dict(point_workdirs={'p000001': '/somewhere/else'})]
        for changeset in changes:
            value = manifest()
            value.update(changeset)
            with self.subTest(changes=changeset), self.assertRaises(ValueError):
                schema.validate_manifest(value, WORKDIR, SCRIPT)

    def test_changed_coordinate_nonfinite_and_duplicate_paths_rejected(self):
        for value in (float('nan'), float('inf'), 0, .7):
            frozen = manifest()
            frozen['point_table']['p000001']['values']['KY'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                schema.validate_manifest(frozen, WORKDIR, SCRIPT)
        frozen = manifest()
        frozen['point_table']['p000002'] = copy.deepcopy(frozen['point_table']['p000001'])
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            schema.validate_manifest(frozen, WORKDIR, SCRIPT)

    def test_json_duplicate_fields_and_unknown_schema_rejected(self):
        for text in ('{"points":[],"points":[1]}', '{"schema":2,"manifest":{}}', '[]'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                schema.read_manifest(text)

    def test_nondefault_archive_precision_and_signed_ky_are_preserved(self):
        frozen = manifest()
        for row in frozen['point_table'].values():
            row['values']['KY'] *= -1
            row['result_path'][1] = '16.0000000'
            row['result_path'][-1] = format(row['values']['KY'], '.7f')
        self.assertEqual(schema.validate_manifest(frozen, WORKDIR, SCRIPT), frozen)

    def test_atomic_sidecar_does_not_mutate_live_manifest(self):
        frozen = manifest()
        frozen['submission_parent'] = manifest()
        before = copy.deepcopy(frozen)
        with tempfile.TemporaryDirectory() as directory:
            path = schema.write_sidecar(directory, frozen)
            saved = schema.read_manifest(Path(path).read_text())
            self.assertNotIn('submission_parent', saved)
            self.assertFalse(Path(path + '.tmp').exists())
        self.assertEqual(frozen, before)

    def test_convergence_subset_and_reuse_metadata_survive_frozen_job_recovery(self):
        frozen = manifest()
        frozen['scan_axes'][0]['values'] = [16, 32, 48]
        frozen['point_table']['p000002']['values']['N_THETA'] = 48
        frozen['point_table']['p000002']['result_path'][1] = '48.00000'
        frozen['convergence_group'] = dict(parameter='N_THETA', baseline={'N_THETA': 32},
            requested=[16, 32, 48], shared=[dict(value=32, group='N_ENERGY')], fixed={},
            submit_coordinates=[[16, .1], [48, .2]], reused_points=4,
            reused_scope=dict(coordinates=[], unknown=[], issues=[]))
        with tempfile.TemporaryDirectory() as directory:
            path = schema.write_sidecar(directory, frozen)
            recovered = schema.validate_manifest(schema.read_manifest(Path(path).read_text()), WORKDIR, SCRIPT)
        self.assertEqual(recovered['point_table'], frozen['point_table'])
        self.assertEqual(recovered['convergence_group'], frozen['convergence_group'])
        self.assertEqual(recovered['points'], ['p000001', 'p000002'])

    def test_base64_preserves_newlines_despite_transport_chunking(self):
        text = base64.b64encode(SCRIPT.encode()).decode()
        self.assertEqual(probe.script_content(framed('SCRIPT', '\n\n'.join(text[i:i+8] for i in range(0,len(text),8)))), SCRIPT)


class IdentityTests(unittest.TestCase):
    @unittest.skipIf(sys.platform == 'win32', 'The recovery probe executes on a Bash server')
    def test_pending_array_accounting_is_expanded_before_identity_validation(self):
        # Model Slurm's actual pending-array response: without --array it
        # returns one compressed ID. Exercise the generated shell query so
        # the parser remains strict about ownership and exact child IDs.
        fake_scheduler = '''
id() { printf 'user\\n'; }
squeue() { return 0; }
sacct() {
  case " $* " in
    *" --array "*) printf '123_0|user|PENDING|WORKDIR\\n123_1|user|PENDING|WORKDIR\\n';;
    *) printf '123_[0-1]|user|PENDING|WORKDIR\\n';;
  esac
}
'''.replace('WORKDIR', WORKDIR)
        result = subprocess.run(['bash', '-c', fake_scheduler + probe.identity_command('123')],
                                capture_output=True, text=True, check=True)
        identity = probe.parse_identity(result.stdout, '123')
        self.assertEqual([row['job_id'] for row in identity['rows']], ['123_0', '123_1'])
        self.assertEqual(identity['workdir'], WORKDIR)

    def test_empty_live_queue_with_accounting_finds_old_job(self):
        self.assertEqual(probe.parse_identity(identity_text(), '123')['workdir'], WORKDIR)

    def test_wrong_owner_missing_accounting_and_conflicting_workdirs(self):
        replies = [identity_text(user='someone_else'), identity_text(directory='/'),
            identity_text(queue='123_0|user|RUNNING|/work/user/' + 'b' * 32 + '\n'),
            framed('USER', 'user') + framed('QUEUE', '') + framed('ACCOUNT', '')]
        for text in replies:
            with self.subTest(text=text[:80]), self.assertRaises(ValueError):
                probe.parse_identity(text, '123')

    def test_controller_error_is_not_a_missing_job(self):
        def broken(*args, **kwargs):
            kwargs['std_err'].append('controller connection failed')
            return 1
        with self.assertRaisesRegex(RuntimeError, 'controller connection failed'):
            probe.remote_text(SimpleNamespace(remote_execute=broken), ENDPOINT, probe.identity_command('123'))


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.remote = Remote(self.path / 'remote')
        self.root = dict(SETTINGS={'REMOTE_SETUP': {}}, RUN_DB={'Jet': {'old_scan': 'preserve'}})
        self.counter = 0

    def recover(self, root=None, factory=dict, remote=None):
        return recovery.recover_job(self.root if root is None else root, remote or self.remote,
            '123', ENDPOINT, str(self.path / 'local'), factory, FileOwner, FileOwner)

    def test_completed_job_import_is_idempotent_and_keeps_public_scans(self):
        for factory in (dict, OMFITMapping):
            root = treeify(copy.deepcopy(self.root), factory)
            first = self.recover(root, factory)
            count = self.remote.downloads
            second = self.recover(root, factory)
            self.assertFalse(first['already_present'])
            self.assertTrue(second['already_present'])
            self.assertEqual(self.remote.downloads, count)
            self.assertEqual(root['RUN_DB']['Jet']['old_scan'], 'preserve')
            self.assertEqual(root['RUN_MANIFEST']['scheduler_sync']['outcome'], 'completed')
            self.assertEqual(set(root['RUN_DB']['__RUNS__'][TOKEN]['inputs']), {'scan.pbs','p000001','p000002'})
            self.assertNotIn('cases', root['RUN_HISTORY'][TOKEN])
            self.assertEqual(root['RUN_DB']['__RUNS__'][TOKEN]['cases'], {})

    def test_active_and_cancelled_jobs_attach_without_wait_submit_or_cancel(self):
        for state in ('active', 'cancelled'):
            remote = Remote(self.path / state, state=state)
            root = copy.deepcopy(self.root)
            self.recover(root, remote=remote)
            self.assertEqual(root['RUN_MANIFEST']['scheduler_sync']['outcome'], state)
            self.assertEqual(len(remote.calls), 5)
            self.assertTrue(all('scancel' not in cmd and 'sbatch ' not in cmd for cmd in remote.calls))

    def test_missing_input_zip_does_not_hide_collectable_output(self):
        (self.remote.directory / 'p000002.zip').unlink()
        report = self.recover()
        self.assertEqual(report['missing_inputs'], ['p000002'])
        self.assertEqual(len(self.root['RUN_MANIFEST']['points']), 2)

    def test_reopened_unstarted_point_uses_run_db_input_owner(self):
        self.recover()
        frozen = copy.deepcopy(self.root['RUN_MANIFEST'])
        frozen.update(source_local_workDir='/missing/old-session', skipped_reasons={'p000001': 'No time samples'})
        self.root['RUN_DB']['__RUNS__'][TOKEN]['manifest'] = frozen
        original = self.root['RUN_DB']['__RUNS__'][TOKEN]['inputs']['p000001']['zip']
        saved = self.path / 'saved-project-input.zip'
        shutil.copyfile(original.filename, saved)
        self.root['RUN_DB']['__RUNS__'][TOKEN]['inputs']['p000001']['zip'] = FileOwner(saved)
        source = continuation.resume_source(self.root, TOKEN, 'p000001',
            context=dict(results={}, sources={'p000001': (frozen, {})}))
        self.assertEqual(source['mode'], 'fresh')
        self.assertEqual(source['zip'], str(saved))

    def test_corrupt_input_or_failed_download_never_changes_project(self):
        before = copy.deepcopy(self.root)
        with zipfile.ZipFile(self.remote.directory/'p000001.zip', 'w') as packed:
            packed.writestr('input.cgyro', b'wrong original input')
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            self.recover()
        self.assertEqual(self.root, before)
        self.assertEqual(list((self.path/'local').iterdir()), [])
        with patch.object(self.remote, 'remote_downsync', return_value=1), self.assertRaises(RuntimeError):
            self.recover()
        self.assertEqual(self.root, before)

    def test_valid_hash_with_wrong_frozen_coordinates_is_rejected(self):
        self.remote.frozen['point_table']['p000001']['values']['KY'] = .3
        # Use a canonical path so the byte/input check, rather than key syntax,
        # is the independent evidence that catches an incorrect old manifest.
        self.remote.frozen['point_table']['p000001']['result_path'][-1] = '0.30000'
        with self.assertRaisesRegex(ValueError, 'disagrees with frozen coordinate'):
            self.recover()
        self.assertNotIn('__RUNS__', self.root['RUN_DB'])
        self.assertEqual(list((self.path/'local').iterdir()), [])

    def test_recovery_retains_other_pending_jobs_in_collection_queue(self):
        old = dict(run_token='other', case_id='different radius', job_id='122', status='submitted', batch_id='previous')
        self.root.update(RUN_HISTORY={'other': {'manifest': old}}, RUN_MANIFEST=copy.deepcopy(old),
                         RUN_BATCH={'batch_id': 'previous', 'tokens': ['other']})
        self.recover()
        self.assertEqual(self.root['RUN_BATCH']['tokens'], ['other', TOKEN])
        self.assertEqual(self.root['RUN_HISTORY']['other']['manifest']['job_id'], '122')
        self.assertEqual(self.root['RUN_HISTORY']['other']['manifest']['batch_id'], self.root['RUN_BATCH']['batch_id'])
        self.assertEqual([token for token, _ in queue.queue_records(self.root)], [TOKEN])
        self.assertEqual([token for token, _ in queue.queue_records(self.root, include_parked=True)], ['other', TOKEN])
        self.assertIn('本次恢复作业：完整 0 / 1', queue.queue_summary(self.root))

    def old_pending(self):
        old = dict(run_token='other', case_id='old radius', job_id='122', status='failed',
                   batch_id='previous', collection_status='pending')
        self.root.update(RUN_HISTORY={'other': {'manifest': old}}, RUN_MANIFEST=copy.deepcopy(old),
                         RUN_BATCH={'batch_id': 'previous', 'tokens': ['other']})
        self.root['SETTINGS']['SETUP'] = dict(irun=1, idownsync=0)

    def test_collection_only_reads_explicit_recovered_job_and_keeps_history(self):
        self.old_pending()
        self.recover()
        previous = copy.deepcopy(self.root['RUN_HISTORY']['other'])
        calls = []
        def run_script(title, name, **kwargs):
            calls.append((self.root['RUN_MANIFEST']['job_id'], name, kwargs))
            self.root['RUN_MANIFEST']['status'] = 'published'
        workflow.collect_batch(self.root, run_script)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0:2], ('123', 'CGYROScan.py'))
        self.assertFalse(calls[0][2]['allow_solver_retries'])
        self.assertEqual(self.root['RUN_HISTORY']['other'], previous)
        self.assertEqual(self.root['RUN_BATCH']['status'], 'published')
        self.assertIn('本次恢复作业：完整 1 / 1', queue.queue_summary(self.root))
        self.assertEqual(queue.pending_runs(self.root), [])
        self.assertEqual(self.root['SETTINGS']['SETUP'], dict(irun=1, idownsync=0))

    def test_synchronization_only_queries_explicit_recovered_job(self):
        self.old_pending()
        self.recover()
        previous = copy.deepcopy(self.root['RUN_HISTORY']['other'])
        calls = []
        def sync(view, ui):
            calls.append(view['RUN_MANIFEST']['job_id'])
            view['RUN_MANIFEST']['scheduler_sync'] = dict(outcome='completed')
        with patch.object(queue, 'refresh_run_state', sync):
            queue.refresh_queue(self.root, self.remote)
        self.assertEqual(calls, ['123'])
        self.assertEqual(self.root['RUN_HISTORY']['other'], previous)

    def test_recovery_again_narrows_previously_grouped_history_without_download(self):
        self.old_pending()
        self.recover()
        self.root['RUN_BATCH'].pop('focus_token')  # A pre-fix project snapshot.
        self.root['RUN_MANIFEST'] = copy.deepcopy(self.root['RUN_HISTORY']['other']['manifest'])
        downloads = self.remote.downloads
        owner = self.root['RUN_DB']['__RUNS__'][TOKEN]['inputs']['p000001']['zip']
        report = self.recover()
        self.assertTrue(report['already_present'])
        self.assertEqual(self.remote.downloads, downloads)
        self.assertEqual(self.root['RUN_MANIFEST']['job_id'], '123')
        self.assertEqual(report['manifest'], self.root['RUN_MANIFEST'])
        self.assertEqual([token for token, _ in queue.queue_records(self.root)], [TOKEN])
        self.assertIs(self.root['RUN_DB']['__RUNS__'][TOKEN]['inputs']['p000001']['zip'], owner)

    def test_invalid_recovery_focus_cannot_fall_back_to_collecting_history(self):
        self.old_pending()
        self.recover()
        for token in ('', 'not-in-the-batch'):
            self.root['RUN_BATCH']['focus_token'] = token
            previous = recovery._metadata_revision(self.root)
            setup = copy.deepcopy(self.root['SETTINGS']['SETUP'])
            owners = self.root['RUN_DB']['__RUNS__'][TOKEN]['inputs']
            calls = []
            with self.subTest(token=token), self.assertRaisesRegex(ValueError, 'selection is invalid'):
                workflow.collect_batch(self.root, lambda *args, **kwargs: calls.append(args))
            self.assertEqual(recovery._metadata_revision(self.root), previous)
            self.assertEqual(self.root['SETTINGS']['SETUP'], setup)
            self.assertIs(self.root['RUN_DB']['__RUNS__'][TOKEN]['inputs'], owners)
            self.assertEqual(calls, [])

    def test_existing_newer_attempt_and_retired_payload_not_overwritten(self):
        for saved in (dict(manifest=dict(manifest(), job_id='124')),
                      dict(manifest=dict(manifest(), job_id='123'), payload_retired=True)):
            root = copy.deepcopy(self.root)
            root['RUN_DB']['__RUNS__'] = {TOKEN: saved}
            before = copy.deepcopy(root)
            with self.assertRaises(ValueError):
                self.recover(root)
            self.assertEqual(root, before)

    def test_unconfirmed_saved_submission_keeps_existing_point_owners(self):
        frozen = dict(manifest(), job_id='', status='submission_unconfirmed')
        self.root['RUN_DB']['__RUNS__'] = {TOKEN: dict(manifest=frozen, cases={'retained': 'keep'})}
        self.recover()
        self.assertEqual(self.root['RUN_DB']['__RUNS__'][TOKEN]['cases']['retained'], 'keep')

    def test_stale_callback_and_reentrant_recovery_cannot_commit(self):
        download = self.remote.remote_downsync
        def changed(*args, **kwargs):
            self.root['RUN_MANIFEST'] = {'run_token': 'new_selection'}
            return download(*args, **kwargs)
        with patch.object(self.remote, 'remote_downsync', side_effect=changed), self.assertRaisesRegex(ValueError, '发生变化'):
            self.recover()
        self.assertNotIn('__RUNS__', self.root['RUN_DB'])
        recovery._RECOVERING.add(id(self.root))
        try:
            with self.assertRaisesRegex(ValueError, '正在恢复'):
                self.recover()
        finally:
            recovery._RECOVERING.discard(id(self.root))

    def test_sidecar_valid_nonce_and_missing_parent_checks(self):
        frozen = dict(manifest(), submission_nonce='d' * 32)
        remote = Remote(self.path / 'sidecar', frozen, sidecar=True)
        self.assertFalse(self.recover(remote=remote)['already_present'])
        frozen['continuation'] = {'source_token': 'missing_parent'}
        root = dict(SETTINGS={'REMOTE_SETUP': {}})
        with self.assertRaisesRegex(ValueError, '先恢复源运行'):
            self.recover(root, remote=remote)

    def test_native_assignment_abort_rolls_back_metadata_and_owners(self):
        class AbortRoot(OMFITMapping):
            armed = False
            def __setitem__(self, key, value):
                super().__setitem__(key, value)
                if key == 'RUN_MANIFEST' and self.armed:
                    self.armed = False
                    raise KeyboardInterrupt('Abort after mutation')
        root = treeify(self.root, OMFITMapping)
        root = AbortRoot(root)
        ensure_layout(root, OMFITMapping)
        before = copy.deepcopy(root)
        root.armed = True
        with self.assertRaises(KeyboardInterrupt):
            self.recover(root, OMFITMapping)
        self.assertEqual(root, before)
        self.assertNotIn(id(root), recovery._RECOVERING)

    def test_explicit_verified_recovery_can_reimport_a_deleted_task(self):
        ensure_layout(self.root)
        self.root['RUN_DB']['__STORAGE__']['deleted_tasks'] = {TOKEN: True}
        with patch.object(recovery, '_load_verified_manifest', side_effect=ValueError('bad identity')):
            with self.assertRaisesRegex(ValueError, 'bad identity'):
                self.recover()
        self.assertTrue(recovery.run_is_deleted(self.root, TOKEN))
        self.recover()
        self.assertFalse(recovery.run_is_deleted(self.root, TOKEN))
        self.assertIn(TOKEN, self.root['RUN_HISTORY'])

    def test_abort_after_clearing_deletion_marker_restores_marker_and_prior_records(self):
        class AbortState(OMFITMapping):
            armed = False
            def __setitem__(self, key, value):
                super().__setitem__(key, value)
                if key == 'deleted_tasks' and self.armed:
                    self.armed = False
                    raise KeyboardInterrupt('Abort after reimport marker')
        ensure_layout(self.root)
        state = AbortState(self.root['RUN_DB']['__STORAGE__'])
        state['deleted_tasks'] = {TOKEN: True}
        self.root['RUN_DB']['__STORAGE__'] = state
        before = copy.deepcopy(self.root)
        state.armed = True
        with self.assertRaisesRegex(KeyboardInterrupt, 'Abort after reimport marker'):
            self.recover()
        self.assertEqual(self.root, before)


class SubmissionSidecarTests(unittest.TestCase):
    def test_sidecar_is_uploaded_before_any_scheduler_command(self):
        with tempfile.TemporaryDirectory() as directory:
            root = dict(RUN_MANIFEST=manifest())
            inputs = []
            def upload(*args, **kwargs):
                inputs.extend(kwargs['inputs'])
                self.assertEqual(kwargs['executable'], ':')
                raise KeyboardInterrupt('stop after upload inspection')
            ui = SimpleNamespace(executable=upload)
            with patch.object(retry, 'save_current'), patch.object(retry, 'no_submission'), self.assertRaises(KeyboardInterrupt):
                retry._execute_submission(root, ui, dict, FileOwner, [], directory, 'sbatch scan.pbs')
            names = [Path(item.filename).name for item in inputs]
            self.assertEqual(names, ['.cgyro_submit.identity', schema.SIDECAR])
            saved = schema.read_manifest((Path(directory)/schema.SIDECAR).read_text())
            self.assertEqual(saved['submission_nonce'], root['RUN_MANIFEST']['submission_nonce'])


if __name__ == '__main__':
    unittest.main()
