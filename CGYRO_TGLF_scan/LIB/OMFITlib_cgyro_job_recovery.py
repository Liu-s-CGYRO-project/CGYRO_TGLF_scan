"""Reconnect a verified Slurm allocation to the native CGYRO workflow.

Recovery is metadata + immutable input import, not submission or collection.
The public RUN_DB scans are untouched until the existing collector publishes
verified outputs. No result is copied into RUN_HISTORY or the active manifest.
"""
from builtins import (BaseException, Exception, OSError, RuntimeError, ValueError, any, dict, getattr,
                      id, len, list, object, reversed, set, sorted, str, sum)
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import os
import posixpath
import shutil
import sys
import tempfile
import uuid
from OMFITlib_cgyro_db import ensure_layout, rollback_actions, run_records
from OMFITlib_cgyro_job_probe import (files_command, identity_command, input_inventory_command,
    parse_identity, parse_inventory, read_remote_manifest, remote_text, script_content, section)
from OMFITlib_cgyro_recovery_manifest import (SIDECAR, job_number, read_manifest,
                                            validate_manifest, verify_input_zip)
from OMFITlib_cgyro_run_state import refresh_run_state, submitted_job_id, uncollected_job, submission_pending
from OMFITlib_cgyro_scratch import ensure_capacity

# Tk may re-enter callbacks while SSH pumps events. This is transient process
# state, never saved in an OMFIT project and always released after Abort.
_RECOVERING = set()


def _load_verified_manifest(ui, endpoint, identity, path):
    response = remote_text(ui, endpoint, files_command(identity, path))
    if submitted_job_id(section(response, 'RECEIPT'), 'slurm') != identity['job_id']:
        raise ValueError('The saved submission receipt does not match this job ID.')
    script = script_content(response)
    candidates = list(dict.fromkeys(section(response, 'CANDIDATES').splitlines()))
    candidates = [candidate for candidate in candidates if candidate]
    if not candidates:
        raise ValueError('未找到原始扫描清单。服务器输出仍保留；请在高级选项填写原 OMFIT 暂存目录中的 manifest.json。'
                         '不能用当前界面参数代替原扫描坐标。')
    # Prefer the pre-submit sidecar. Its nonce binds it to this exact gate;
    # malformed modern data must not silently fall back to an older snapshot.
    if candidates[0].endswith('/' + SIDECAR):
        candidates = candidates[:1]
    if len(candidates) > 12:
        raise ValueError('Multiple old OMFIT sessions match this run; specify the original manifest path.')
    verified = []
    for candidate in candidates:
        manifest = read_manifest(read_remote_manifest(ui, endpoint, candidate))
        manifest = validate_manifest(manifest, identity['workdir'], script)
        nonce = manifest.get('submission_nonce', '')
        if nonce and nonce != section(response, 'NONCE').strip():
            raise ValueError('The recovery sidecar belongs to another submission gate.')
        if manifest.get('job_id', '') and str(manifest['job_id']) != identity['job_id']:
            raise ValueError('The manifest belongs to another scheduler allocation.')
        verified.append((manifest, candidate))
    # Different saved scan coordinates must be resolved explicitly, never by
    # filesystem iteration order. Identical duplicate staging snapshots are OK.
    first, source = verified[0]
    identity_fields = ('run_token', 'runid', 'case_id', 'points', 'scan_axes', 'point_table',
                       'input_sha256', 'submit_script_sha256', 'point_workdirs', 'continuation')
    for other, _ in verified[1:]:
        if any(other.get(key, None) != first.get(key, None) for key in identity_fields):
            raise ValueError('Conflicting original manifests; specify which staging manifest belongs to this run.')
    return first, source


def _existing_run(root, manifest, endpoint, job_id):
    token = manifest['run_token']
    record = run_records(root).get(token, {})
    existing = record.get('manifest', root.get('RUN_HISTORY', {}).get(token, {}).get('manifest', {}))
    if record.get('payload_retired', False):
        raise ValueError('该历史运行已被较新结果替代；不会重新导入旧输出覆盖现有结果。')
    if existing:
        if (str(existing.get('job_id', '')) not in ('', job_id) or existing.get('workDir', '') != manifest['workDir']
                or existing.get('server', '') != endpoint['server']):
            raise ValueError('工程已保留此运行的另一提交记录；恢复已停止，避免覆盖较新的重试。')
        if existing.get('point_table', manifest['point_table']) != manifest['point_table']:
            raise ValueError('Existing run coordinates disagree with the recovered manifest.')
        # An OMFIT save between upload and receipt is not a second job. The
        # verified scheduler identity can repair it while retaining its owners.
        return existing if existing.get('job_id', '') else None
    return None


def _metadata_revision(root):
    """Do not touch lazy result/file owners in legacy history during SSH."""
    history = {str(token): deepcopy(entry.get('manifest', {}))
               for token, entry in root.get('RUN_HISTORY', {}).items()}
    return deepcopy(root.get('RUN_MANIFEST', {})), deepcopy(root.get('RUN_BATCH', {})), history


def _import_inputs(ui, endpoint, manifest, local, factory, path_reader, ascii_reader):
    inventory = parse_inventory(remote_text(ui, endpoint, input_inventory_command(manifest)), manifest)
    # Recovery needs real free space; the 100 GiB start limit applies only to
    # starting new computation and must not prevent recovering finished work.
    ensure_capacity(local, 2 * sum(inventory.values()))
    base = manifest.get('source_workDir', manifest['workDir'])
    paths = [posixpath.join(base, name) for name in inventory]
    code = ui.remote_downsync(endpoint['server'], paths, local + os.sep,
                             tunnel=endpoint.get('tunnel', ''), quiet=True, ignoreReturnCode=True)
    if code != 0:
        raise RuntimeError('Original CGYRO inputs could not be downloaded; existing records are unchanged.')
    for name, size in inventory.items():
        path = os.path.join(local, name)
        if os.path.islink(path) or not os.path.isfile(path) or os.path.getsize(path) != size:
            raise ValueError('Recovered input is missing or changed during transfer: ' + name)
    script = os.path.join(local, 'scan.pbs')
    with open(script, 'rb') as stream:
        if hashlib.sha256(stream.read()).hexdigest() != manifest['submit_script_sha256']:
            raise ValueError('The original submission script checksum changed during recovery.')
    inputs = factory()
    inputs['scan.pbs'] = ascii_reader(script)
    missing = []
    for point in manifest['points']:
        name = point + '.zip'
        if name not in inventory:
            missing.append(point)
            continue  # Readable solver output can still be collected.
        path = os.path.join(local, name)
        verify_input_zip(path, manifest['input_sha256'][point], manifest['point_table'][point])
        item = factory()
        item['zip'] = path_reader(path)
        inputs[point] = item
    return inputs, missing


def _recovered_manifest(original, identity, endpoint, source, local, missing):
    manifest = deepcopy(original)
    # A snapshot can have been taken inside an aborted callback. None of those
    # saved control flags grants a recovered job permission to cancel or retry.
    for name in ('submission_parent', 'stop_requested', 'submission_stop_requested', 'auto_collect_requested',
                 'cancellation', 'scheduler_sync', 'scheduler_status', 'load_errors', 'loaded_points',
                 'partial_points', 'failed_points', 'skipped_points', 'skipped_reasons', 'terminal_reason'):
        manifest.pop(name, None)
    manifest.update(dict(server=endpoint['server'], tunnel=endpoint.get('tunnel', ''),
        serverPicker=endpoint.get('serverPicker', ''), job_id=identity['job_id'], status='submitted',
        submission_uncertain=False, collection_status='pending', local_workDir=local, source_local_workDir=local))
    manifest['recovery'] = dict(job_id=identity['job_id'], user=identity['user'], manifest_path=source,
        original_batch_id=original.get('batch_id', ''), original_local_workDir=original.get('local_workDir', ''),
        missing_inputs=missing, at=datetime.now(timezone.utc).isoformat())
    return manifest


def _install(root, manifest, inputs, factory):
    """Publish only after every probe/download succeeds; journal native writes.

    Retain pending records without changing their physical run identity. Only
    the explicitly recovered token is in the action scope; retaining history
    must never grant synchronization, collection or cancellation of old jobs.
    """
    db = ensure_layout(root, factory)
    token = manifest['run_token']
    history = root.get('RUN_HISTORY', {})
    records = db.get('__RUNS__', {})
    snapshots = {}
    for old_token, entry in history.items():
        saved = entry.get('manifest', {})
        if uncollected_job(saved) or submission_pending(saved):
            snapshots[str(old_token)] = deepcopy(saved)
    current = root.get('RUN_MANIFEST', {})
    if (uncollected_job(current) or submission_pending(current)) and current.get('run_token', ''):
        snapshots[current['run_token']] = deepcopy(current)
    batch_id = uuid.uuid4().hex
    snapshots[token] = deepcopy(manifest)
    for saved in snapshots.values():
        saved['batch_id'] = batch_id
    batch = dict(batch_id=batch_id, tokens=list(snapshots), case_ids=[row.get('case_id', row['run_token']) for row in snapshots.values()],
                 completed=[], errors=[], status='recovered', focus_token=token)
    missing = object()
    changes = []
    def assign(mapping, key, value):
        changes.append((mapping, key, mapping.get(key, missing)))
        mapping[key] = value
    try:
        if 'RUN_HISTORY' not in root:
            assign(root, 'RUN_HISTORY', factory())
        if '__RUNS__' not in db:
            assign(db, '__RUNS__', factory())
        history, records = root['RUN_HISTORY'], db['__RUNS__']
        for old_token, saved in snapshots.items():
            if old_token not in history:
                assign(history, old_token, factory())
            assign(history[old_token], 'manifest', deepcopy(saved))
            if old_token not in records:
                assign(records, old_token, factory())
            assign(records[old_token], 'manifest', deepcopy(saved))
        if 'inputs' not in records[token]:
            assign(records[token], 'inputs', inputs)
        else:
            for name, value in inputs.items():
                if name not in records[token]['inputs']:
                    assign(records[token]['inputs'], name, value)
        if 'cases' not in records[token]:
            assign(records[token], 'cases', factory())
        assign(root, 'RUN_BATCH', batch)
        assign(root, 'RUN_MANIFEST', deepcopy(snapshots[token]))
    except BaseException as error:
        def restore(mapping, key, old):
            if old is missing:
                mapping.pop(key, None)
            else:
                mapping[key] = old
        rollback_actions(error, [('restore ' + str(k), lambda m=m, k=k, v=v: restore(m, k, v))
                                 for m, k, v in reversed(changes)])
        raise


def recover_job(root, ui, job_id, endpoint, local_base, factory=dict, path_reader=None,
                ascii_reader=None, manifest_path=''):
    """Public injected-I/O API; requires an explicit server and parent job ID."""
    job_id = job_number(job_id)
    if not endpoint.get('server', '') or path_reader is None or ascii_reader is None:
        raise ValueError('Recovery needs a server connection and native input readers.')
    key = id(root)
    if key in _RECOVERING:
        raise ValueError('此工程正在恢复作业，请等待当前查询完成。')
    _RECOVERING.add(key)
    local, committing = None, False
    try:
        # Compare metadata only. Query callbacks must not commit over a newer
        # selection/submission made while the native SSH dialog pumps events.
        before = _metadata_revision(root)
        identity = parse_identity(remote_text(ui, endpoint, identity_command(job_id)), job_id)
        original, source = _load_verified_manifest(ui, endpoint, identity, manifest_path)
        existing = _existing_run(root, original, endpoint, job_id)
        if existing is not None:
            # Re-select an already retained job without downloading inputs.
            # This also narrows batches created by versions that grouped every
            # uncollected historical job into the recovery action.
            if before != _metadata_revision(root):
                raise ValueError('恢复期间运行记录发生变化，请重新执行恢复。')
            if (root.get('RUN_BATCH', {}).get('focus_token', '') != original['run_token']
                    or root.get('RUN_MANIFEST', {}).get('run_token', '') != original['run_token']):
                _install(root, deepcopy(existing), factory(), factory)
            return dict(already_present=True, manifest=deepcopy(root['RUN_MANIFEST']), missing_inputs=[])
        parent = original.get('continuation', {}).get('source_token', '')
        if parent and not run_records(root).get(parent, {}).get('manifest', {}):
            raise ValueError('这是续算作业，原扫描记录尚未恢复。请先恢复源运行 ' + str(parent)
                             + '，再恢复本次续算；服务器文件未改变。')
        os.makedirs(local_base, exist_ok=True)
        local = tempfile.mkdtemp(prefix='recover_' + job_id + '_', dir=local_base)
        inputs, missing = _import_inputs(ui, endpoint, original, local, factory, path_reader, ascii_reader)
        manifest = _recovered_manifest(original, identity, endpoint, source, local, missing)
        refresh_run_state(dict(RUN_MANIFEST=manifest, SETTINGS=root['SETTINGS']), ui)
        if before != _metadata_revision(root):
            raise ValueError('恢复期间运行记录发生变化，请重新执行恢复；已下载输入仍保留。')
        committing = True
        _install(root, manifest, inputs, factory)
        return dict(already_present=False, manifest=deepcopy(root['RUN_MANIFEST']), missing_inputs=missing)
    finally:
        # Only pre-commit staging is disposable. Once native assignment starts,
        # even an unsuccessful rollback may leave a live file owner behind.
        original_error = sys.exc_info()[1]
        try:
            if local is not None and not committing:
                parent, target = os.path.realpath(local_base), os.path.realpath(local)
                if os.path.dirname(target) == parent and os.path.basename(target).startswith('recover_' + job_id + '_'):
                    try:
                        shutil.rmtree(target)
                    except OSError as cleanup_error:
                        if original_error is not None:
                            original_error.recovery_cleanup_error = str(cleanup_error)
                        else:
                            raise
        finally:
            _RECOVERING.discard(key)
