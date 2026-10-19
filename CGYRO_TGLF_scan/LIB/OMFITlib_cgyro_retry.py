"""Bounded failed-point retries in new directories, using the original inputs."""
from builtins import Exception, RuntimeError, ValueError, any, dict, enumerate, int, len, list, print, range, str
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
    rule = (r'(?i)submitted\s+batch\s+job\s+([0-9]+)' if manifest.get('scheduler', '') == 'slurm'
            else r'(?m)^\s*([0-9]+(?:\.[A-Za-z0-9._-]+)?)\s*$')
    match = re.search(rule, str(manifest.get('submit_output', '')))
    if match is not None:
        manifest.update(dict(job_id=match.group(1), status='submitted', submission_uncertain=False))
        save_current(root, factory)
        return True
    for attempt in range(3):
        output, errors = [], []
        try:
            code = ui.remote_execute(manifest['server'], 'cat -- .cgyro_submit.out',
                manifest['workDir'], manifest.get('tunnel', ''), quiet=True, ignoreReturnCode=True,
                use_bang_command=False, std_out=output, std_err=errors)
            match = re.search(rule, '\n'.join(str(item) for item in output)) if code == 0 else None
            if match is not None:
                manifest.update(dict(job_id=match.group(1), status='submitted', submission_uncertain=False))
                save_current(root, factory)
                return True
        except Exception as exc:
            manifest['submission_probe_error'] = str(exc)
        if attempt < 2:
            time.sleep(1)
    return False


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
    if any(text in str(manifest.get('failure_log', '')).lower() for text in (
            'integration error exceeded limit', 'bogus parameter', 'unknown parameter', 'invalid input', 'error reading input')):
        return []
    blocked = ('CANCELLED', 'TIMEOUT', 'OUT_OF_MEMORY', 'DEADLINE')
    states, solver = sync.get('point_states', {}), manifest.get('solver_errors', {})
    failed = manifest.get('probe_failed_points', [])
    return [point for point in manifest['points'] if point in failed and not solver.get(point, [])
            and states.get(point, '') not in blocked]


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
                if hashlib.sha256(archive.read(name)).hexdigest() != expected:
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
        manifest['submit_output'] = '\n'.join(str(item) for item in output + errors)
    except Exception as exc:
        manifest['submit_error'] = str(exc)
        code = -1
    # Even after a dropped SSH connection, the remote log can prove acceptance.
    if not recover_submission(root, ui, factory):
        if re.search(r'(?mi)^(?:sbatch|qsub):.*(?:error|invalid|reject)', manifest.get('submit_output', '')):
            manifest.update(dict(status='failed', submission_uncertain=False))
        save_current(root, factory)
        raise RuntimeError('Retry submission is unconfirmed; do not resubmit blindly. Inspect '
                           + remote + '/.cgyro_submit.out (return code ' + str(code) + ').')
    manifest['failed_points'], manifest['partial_points'] = [], []
    save_current(root, factory)


def collect_current(root, ui, factory, path_reader, ascii_reader):
    collection_retries = 0
    while True:
        try:
            root['SCRIPTS']['downsync.py'].run()
            return
        except Exception as exc:
            manifest = root['RUN_MANIFEST']
            if manifest.get('stop_requested', False) or root.get('RUN_BATCH', {}).get('stop_requested', False):
                raise
            # A download/query failure gets another read; it never launches a solver.
            if collection_retries < 2 and (network_error(exc) or manifest.get('load_errors', {})):
                collection_retries += 1
                time.sleep(collection_retries)
                continue
            points = retryable_points(root)
            if not points:
                raise
            print('CGYRO retry {} / {}: {} failed points; successful points are retained.'.format(
                int(manifest.get('retry_count', 0)) + 1, retry_limit(root), len(points)))
            submit_retry(root, ui, factory, path_reader, ascii_reader, points)
            wait_current(root, ui, factory)
            collection_retries = 0
