"""Recover submission acknowledgements and retry eligible failed points.

A transport retry only reads the existing submission/output. A solver retry
creates a new attempt directory, verifies the original inputs, and retains the
successful points' locations. These operations must never be interchanged.
"""
from builtins import BaseException, Exception, RuntimeError, ValueError, any, dict, enumerate, int, iter, len, list, print, range, str
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import os
import posixpath
import re
import time
import uuid
import zipfile
from OMFITlib_cgyro_queue import save_current, shell_quote, wait_current
from OMFITlib_cgyro_run_state import submitted_job_id, text_output


NON_RETRYABLE_STATES = {'CANCELLED', 'TIMEOUT', 'OUT_OF_MEMORY', 'DEADLINE'}


def retry_limit(root):
    value = root['SETTINGS']['SETUP'].get('failed_point_retries', 2)
    count = int(value)
    if str(count) != str(value).strip() or not 0 <= count <= 3:
        raise ValueError('Failed-point retries must be an integer from 0 to 3.')
    return count


def network_error(error):
    text = str(error).lower()
    return any(word in text for word in ('timed out', 'timeout', 'connection', 'ssh', 'sftp', 'rsync',
        'network', 'broken pipe', 'temporary', 'socket', 'transport', 'could not query', 'could not synchronize'))


def recover_submission(root, ui, factory=dict):
    """Read the transaction log before considering another scheduler submission."""
    manifest = root['RUN_MANIFEST']
    scheduler = manifest.get('scheduler', '')
    job_id = submitted_job_id(manifest.get('submit_output', ''), scheduler)
    if not job_id:
        # The executor has returned or explicit synchronization was requested.
        # A missing/empty log is not evidence that the scheduler rejected the job.
        manifest.update(dict(status='submission_unconfirmed', submission_uncertain=True))
        save_current(root, factory)
        for attempt in range(3):
            output, errors = [], []
            try:
                code = ui.remote_execute(manifest['server'], 'cat -- .cgyro_submit.out',
                    manifest['workDir'], manifest.get('tunnel', ''), quiet=True, ignoreReturnCode=True,
                    use_bang_command=False, std_out=output, std_err=errors)
                if code == 0:
                    manifest.pop('submission_probe_error', None)
                    # Retain a recovered rejection too, so a known refusal does
                    # not leave the run permanently marked "submission uncertain".
                    recovered = text_output(output)
                    captured = str(manifest.get('submit_output', ''))
                    if recovered and recovered not in captured:
                        manifest['submit_output'] = captured + '\n' + recovered
                    job_id = submitted_job_id(output, scheduler)
                    if job_id:
                        break
                else:
                    manifest['submission_probe_error'] = text_output(errors) or 'Submission log is not available.'
            except Exception as exc:
                manifest['submission_probe_error'] = str(exc)
            if attempt < 2:
                time.sleep(1)
    if not job_id:
        if re.search(r'(?mi)^(?:sbatch|qsub):.*(?:error|invalid|reject)', manifest.get('submit_output', '')):
            manifest.update(dict(status='failed', submission_uncertain=False))
        save_current(root, factory)
        return False
    manifest.update(dict(job_id=job_id, status='submitted', submission_uncertain=False))
    manifest.pop('submission_probe_error', None)
    save_current(root, factory)
    return True


def interrupt_submission(root, factory, output, errors, error):
    """Persist Abort without another remote operation, then let it propagate.

    OMFIT's Abort derives from KeyboardInterrupt, outside Exception. The server
    may already have accepted the job; only a captured acknowledgement proves it.
    """
    manifest = root['RUN_MANIFEST']
    manifest['submit_output'] = text_output([output, errors])
    job_id = submitted_job_id(manifest['submit_output'], manifest['scheduler'])
    manifest.update(dict(job_id=job_id, submission_uncertain=not job_id,
        status='submitted' if job_id else 'submission_unconfirmed',
        submit_error=str(error) or 'Local submission interrupted.',
        submission_interrupted_at=datetime.now(timezone.utc).isoformat()))
    save_current(root, factory)


def confirm_submission(root, ui, factory, return_code, output, errors):
    """Finish one attempted submission without ever issuing another one.

    The caller records submitting/uncertain before entering the executor. Captured
    stdout remains usable even when the executor raises after the server accepted
    the job. A missing reply stays protected until its saved log confirms it.
    """
    manifest = root['RUN_MANIFEST']
    manifest['submit_output'] = text_output([output, errors])
    if recover_submission(root, ui, factory):
        return manifest['job_id']
    save_current(root, factory)
    reason = ('CGYRO submission was rejected; inspect ' if not manifest.get('submission_uncertain', True)
              else 'CGYRO submission is unconfirmed; inspect ')
    raise RuntimeError(reason + manifest['workDir']
                       + '/.cgyro_submit.out before submitting again (return code '
                       + str(return_code) + ').\n' + manifest.get('submit_output', '')
                       + '\n' + manifest.get('submit_error', ''))


def point_scheduler_states(manifest):
    """Keep each point's latest known state across partial retry attempts."""
    states = {}
    for attempt in manifest.get('attempts', []):
        states.update(attempt.get('scheduler_sync', {}).get('point_states', {}))
    states.update(manifest.get('scheduler_sync', {}).get('point_states', {}))
    return states


def retryable_points(root):
    manifest = root['RUN_MANIFEST']
    if (manifest.get('scheduler', '') not in ('slurm', 'pbs') or manifest.get('stop_requested', False)
            or root.get('RUN_BATCH', {}).get('stop_requested', False)
            or manifest.get('status', '') == 'cancelled' or manifest.get('submission_uncertain', False)
            or int(manifest.get('retry_count', 0)) >= retry_limit(root)):
        return []
    sync = manifest.get('scheduler_sync', {})
    if manifest.get('scheduler', '') == 'slurm' and not sync.get('terminal', False):
        return []  # Never duplicate a job with an unconfirmed terminal state.
    if manifest.get('scheduler', '') == 'pbs' and not manifest.get('wait_completed', False):
        return []
    if not manifest.get('input_sha256', {}) or any(re.fullmatch(r'p[0-9]{6,}', str(point)) is None for point in manifest['points']):
        return []  # Old unindexed/imported runs cannot be reconstructed safely.
    solver = manifest.get('solver_errors', {})
    # Current probes attribute fatal errors to individual points. Keep the
    # conservative whole-run guard only for older records lacking that map;
    # one invalid point must not suppress recovery of an unrelated NODE_FAIL.
    if not solver and any(text in str(manifest.get('failure_log', '')).lower() for text in (
            'integration error exceeded limit', 'bogus parameter', 'unknown parameter', 'invalid input', 'error reading input')):
        return []
    # The latest scheduler record contains only active_points. Without the
    # earlier attempts, an excluded TIMEOUT could appear eligible after a
    # different NODE_FAIL point has been retried.
    states = point_scheduler_states(manifest)
    failed = manifest.get('probe_failed_points', [])
    return [point for point in manifest['points'] if point in failed and not solver.get(point, [])
            and states.get(point, '') not in NON_RETRYABLE_STATES]


def submit_retry(root, ui, factory, path_reader, ascii_reader, points):
    manifest = root['RUN_MANIFEST']
    if not points or any(point not in retryable_points(root) for point in points):
        raise ValueError('Only eligible failed points may be retried.')
    if not os.environ.get('SHELL'):
        os.environ['SHELL'] = '/bin/bash'
    original_local = manifest.get('source_local_workDir', manifest['local_workDir'])
    original_remote = manifest.get('source_workDir', manifest['workDir'])
    number = int(manifest.get('retry_count', 0)) + 1
    suffix = 'retry_{}_{}'.format(number, uuid.uuid4().hex)
    local = os.path.join(original_local, suffix)
    remote = posixpath.join(original_remote, suffix)
    os.makedirs(local)
    with open(os.path.join(original_local, 'scan.pbs'), encoding='utf-8') as stream:
        script = stream.read()
    scheduler = manifest['scheduler']
    indices = [index for index, point in enumerate(manifest['points']) if point in points]
    if scheduler == 'slurm':
        cap = re.search(r'^#SBATCH --array=.*%([0-9]+)\s*$', script, re.MULTILINE)
        if cap is None:
            raise ValueError('Original Slurm array concurrency is missing.')
        command = 'sbatch --array=' + ','.join(str(index) for index in indices) + '%' + cap.group(1) + ' scan.pbs'
    elif scheduler == 'pbs':
        script, count = re.subn(r'^dir_list=\([^\n]*\)$', 'dir_list=(' + ' '.join(points) + ')', script, flags=re.MULTILINE)
        if count != 1:
            raise ValueError('Original PBS task list is ambiguous.')
        command = 'qsub scan.pbs'
    else:
        raise ValueError('Automatic failed-point retries require Slurm or PBS.')
    script_path = os.path.join(local, 'scan.pbs')
    with open(script_path, 'w', encoding='utf-8') as stream:
        stream.write(script)
    inputs = [ascii_reader(script_path)]
    for point in points:
        path = os.path.join(original_local, point + '.zip')
        with zipfile.ZipFile(path) as archive:
            for name, expected in manifest['input_sha256'][point].items():
                digest = hashlib.sha256()
                with archive.open(name) as member:
                    for chunk in iter(lambda: member.read(1024 * 1024), b''):
                        digest.update(chunk)
                if digest.hexdigest() != expected:
                    raise ValueError('Original retry input changed: ' + point + '/' + name)
        inputs.append(path_reader(path))
    attempts = list(manifest.get('attempts', []))
    attempts.append(dict(job_id=manifest.get('job_id', ''), workDir=manifest['workDir'],
        points=list(manifest.get('active_points', manifest['points'])), status=manifest.get('status', ''),
        failed_points=list(manifest.get('failed_points', [])), scheduler_sync=deepcopy(manifest.get('scheduler_sync', {}))))
    locations = dict(manifest.get('point_workdirs', {}))
    for point in manifest['points']:
        locations.setdefault(point, manifest['workDir'])
    for point in points:
        locations[point] = remote
    manifest.update(dict(attempts=attempts, source_workDir=original_remote, source_local_workDir=original_local,
        retry_count=number, active_points=list(points), point_workdirs=locations, workDir=remote,
        job_id='', status='submitting', submission_uncertain=True, wait_completed=False,
        scheduler_sync={}, scheduler_status='', submit_output='', submit_error='',
        retry_at=datetime.now(timezone.utc).isoformat()))
    save_current(root, factory)
    wrapper = command + ' > .cgyro_submit.out 2>&1; status=$?; cat .cgyro_submit.out; exit "$status"'
    output, errors = [], []
    try:
        code = ui.executable(root, inputs=inputs, outputs=[], server=manifest['server'],
            tunnel=manifest.get('tunnel', ''), workdir=local, remotedir=remote,
            executable='/bin/bash -lc ' + shell_quote(wrapper), clean=False,
            std_out=output, std_err=errors, ignoreReturnCode=True)
    except Exception as exc:
        manifest['submit_error'] = str(exc)
        code = -1
    except BaseException as exc:
        interrupt_submission(root, factory, output, errors, exc)
        raise
    confirm_submission(root, ui, factory, code, output, errors)
    manifest['failed_points'], manifest['partial_points'] = [], []
    save_current(root, factory)


def collect_current(root, ui, factory, path_reader, ascii_reader):
    collection_retries = 0
    while True:
        try:
            root['SCRIPTS']['downsync.py'].run()
        except Exception as exc:
            manifest = root['RUN_MANIFEST']
            # A download/query failure gets another read; it never launches a solver.
            if collection_retries < 2 and (network_error(exc) or manifest.get('load_errors', {})):
                collection_retries += 1
                time.sleep(collection_retries)
                continue
            raise
        manifest = root['RUN_MANIFEST']
        points = retryable_points(root)
        if not points:
            return
        print('CGYRO retry {} / {}: {} failed points; successful points are retained.'.format(
            int(manifest.get('retry_count', 0)) + 1, retry_limit(root), len(points)))
        submit_retry(root, ui, factory, path_reader, ascii_reader, points)
        wait_current(root, ui, factory)
        collection_retries = 0
