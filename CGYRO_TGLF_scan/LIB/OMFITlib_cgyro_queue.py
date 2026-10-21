"""Keep batch snapshots while one case occupies the live OMFIT branches.

RUN_MANIFEST is the active job view. RUN_HISTORY holds metadata only; point
payloads and frozen inputs belong to RUN_DB/__RUNS__/<token>/cases.
"""
from builtins import Exception, RuntimeError, ValueError, any, dict, len, list, print, range, str
from contextlib import nullcontext
from copy import deepcopy
import time
from OMFITlib_cgyro_storage import compact_storage
from OMFITlib_cgyro_db import ensure_layout, freeze_run_inputs, run_records
from OMFITlib_cgyro_run_state import (linked_kill_local, pbs_wait, quote as shell_quote,
                                    refresh_run_state, slurm_wait, stop_message, stop_run, submission_pending)


def collection_done(manifest):
    """Collection can finish after cancellation without a complete solver run."""
    return manifest.get('status', '') == 'published' or manifest.get('collection_status', '') in ('partial', 'empty')


def queue_records(root):
    """Return only this batch's known snapshots in submission order."""
    history = root.get('RUN_HISTORY', {})
    return [(token, history[token]) for token in root.get('RUN_BATCH', {}).get('tokens', [])
            if token in history and history[token].get('manifest', None)]


def save_current(root, factory=dict):
    """Save immutable result/input references before copying the active case."""
    manifest = root.get('RUN_MANIFEST', {})
    if (not manifest.get('run_token', '') or
            not any(key in root for key in ('RUN_DB', 'Cases', 'RUN_HISTORY'))):
        return  # Metadata-only scheduler views already refer to the saved entry.
    compact_storage(root, factory)
    batch = root.get('RUN_BATCH', {})
    token = manifest['run_token']
    if (batch.get('batch_id', '') and manifest.get('batch_id', '') == batch['batch_id']
            and token not in batch['tokens']):
        batch['tokens'] = list(batch['tokens']) + [token]
    entry = root.setdefault('RUN_HISTORY', factory()).setdefault(token, factory())
    saved = deepcopy(manifest)
    record = run_records(root, factory).setdefault(str(token), factory())
    record['manifest'] = deepcopy(manifest)
    if manifest.get('status', '') == 'published':
        saved.pop('point_table', None)
        record.pop('cases', None)  # Published scan paths now own these points.
        record.pop('inputs', None)
    else:
        freeze_run_inputs(root, manifest, factory)
    entry.pop('cases', None)
    entry['manifest'] = saved


def activate_run(root, token):
    """Restore a batch snapshot before waiting, retrying, or collecting it."""
    ensure_layout(root)
    entry = root['RUN_HISTORY'][token]
    if entry['manifest'].get('batch_id', '') != root['RUN_BATCH'].get('batch_id', ''):
        raise ValueError('The saved run belongs to another queue batch.')
    root['RUN_MANIFEST'] = deepcopy(entry['manifest'])


def pending_runs(root):
    """Finished but uncollected jobs still protect their results from replacement."""
    return [manifest for _, entry in queue_records(root) for manifest in [entry['manifest']]
            if manifest.get('submission_uncertain', False) or
            (not collection_done(manifest) and manifest.get('status', '') not in ('failed', 'cancelled'))]


def advancing_batch(root, batch_id):
    batch, manifest = root.get('RUN_BATCH', {}), root.get('RUN_MANIFEST', {})
    return (batch_id and batch.get('batch_id', '') == batch_id
            and batch.get('status', '') == 'submitting' and not batch.get('stop_requested', False)
            and manifest.get('batch_id', '') == batch_id
            and manifest.get('run_token', '') in batch.get('tokens', [])
            and manifest.get('run_token', '') in root.get('RUN_HISTORY', {}))


def queue_summary(root):
    rows = [entry['manifest'] for _, entry in queue_records(root)]
    batch = root.get('RUN_BATCH', {})
    done = len([row for row in rows if row.get('status', '') == 'published'])
    partial = len([row for row in rows if row.get('collection_status', '') == 'partial'])
    empty = len([row for row in rows if row.get('collection_status', '') == 'empty'])
    total = len(batch.get('case_ids', rows))
    return '批量案例：完整 {} / {}；部分结果 {}；无结果跳过 {}。'.format(done, total, partial, empty)


def refresh_queue(root, ui, factory=dict, recover=None):
    save_current(root, factory)
    current = root.get('RUN_MANIFEST', {}).get('run_token', '')
    errors = []
    for token, entry in queue_records(root):
        manifest = entry['manifest']
        if collection_done(manifest):
            continue
        try:
            record_root = dict(RUN_MANIFEST=manifest, SETTINGS=root['SETTINGS'])
            if submission_pending(manifest) and recover is not None:
                recover(record_root, ui, factory)
            if submission_pending(manifest):
                raise RuntimeError('Submission has no confirmed job ID; inspect its saved submit log: '
                                   + str(manifest.get('workDir', '')) + '/.cgyro_submit.out\n'
                                   + str(manifest.get('submission_probe_error', '')))
            if not manifest.get('job_id', '') and manifest.get('status', '') == 'failed':
                manifest.pop('sync_error', None)
                continue  # A definite rejection did not create a server job.
            if root.get('RUN_BATCH', {}).get('stop_requested', False) and manifest.get('scheduler', '') == 'slurm':
                # A submission-time Kill can precede the current receipt. Once
                # recovered, honor that same batch stop for all known jobs.
                if not manifest.get('batch_id', '') or manifest['batch_id'] != root['RUN_BATCH'].get('batch_id', ''):
                    raise ValueError('The saved job belongs to another batch; it was not cancelled.')
                stop_run(record_root, ui, manifest.get('job_id', ''), token)
            refresh_run_state(record_root, ui)
            manifest.pop('sync_error', None)
        except Exception as exc:
            manifest['sync_error'] = str(exc)
            errors.append(str(manifest.get('case_id', token)) + ': ' + str(exc))
        finally:
            if token == current:
                synchronized = deepcopy(manifest)
                root['RUN_MANIFEST'].clear()
                root['RUN_MANIFEST'].update(synchronized)
    if errors:
        raise RuntimeError('\n'.join(errors))
    return queue_summary(root)


def stop_queue(root, ui, job_id, run_token, factory=dict):
    """The current wait stays alive if another job cannot yet be cancelled."""
    current, batch = root['RUN_MANIFEST'], root['RUN_BATCH']
    if (str(current.get('job_id', '')) != str(job_id) or current.get('run_token', '') != run_token
            or current.get('batch_id', '') != batch.get('batch_id', '')):
        raise ValueError('The batch changed; this old wait window cannot cancel it.')
    batch['stop_requested'] = True
    batch['status'] = 'cancel_requested'
    save_current(root, factory)
    errors = []
    # Cancel other cases first. Only wake this window after those requests succeed.
    for token, entry in queue_records(root):
        manifest = entry['manifest']
        if token == run_token or (manifest.get('status', '') in ('published', 'failed', 'cancelled')
                                 and not manifest.get('submission_uncertain', False)):
            continue
        try:
            if manifest.get('batch_id', '') != batch['batch_id']:
                raise ValueError('The saved job belongs to another batch.')
            stop_run(dict(RUN_MANIFEST=manifest, SETTINGS=root['SETTINGS']), ui,
                     manifest.get('job_id', ''), token)
        except Exception as exc:
            errors.append(str(manifest.get('case_id', token)) + ': ' + str(exc))
    if errors:
        raise RuntimeError('Some batch jobs could not be stopped. Retry Kill local.\n' + '\n'.join(errors))
    stop_run(root, ui, job_id, run_token)
    batch['auto_collect_requested'] = True
    save_current(root, factory)


def wait_for_stop(root, ui):
    """Wait briefly for Slurm cleanup/accounting; never infer a terminal state."""
    manifest = root['RUN_MANIFEST']
    manifest['auto_collect_requested'] = True
    errors = 0
    for attempt in range(20):
        try:
            result = refresh_run_state(root, ui)
            errors = 0
            if result['terminal']:
                manifest.pop('stop_sync_error', None)
                return
        except Exception as exc:
            errors += 1
            manifest['stop_sync_error'] = str(exc)
            if errors >= 3:
                raise
        if attempt < 19:
            time.sleep(2)
    raise RuntimeError('Slurm cancellation is still settling; automatic collection is pending. '
                       'The run is preserved. Synchronize and collect again after it reaches a terminal state.')


def wait_current(root, ui, factory=dict):
    manifest = root['RUN_MANIFEST']
    if collection_done(manifest):
        return
    batch = root.get('RUN_BATCH', {})
    if (batch.get('stop_requested', False) and manifest.get('batch_id', '') == batch.get('batch_id', '')
            and manifest.get('scheduler', '') == 'slurm'):
        try:
            stop_run(root, ui, manifest.get('job_id', ''), manifest['run_token'])
        finally:
            save_current(root, factory)
    if manifest.get('stop_requested', False):
        try:
            if manifest.get('scheduler', '') == 'slurm':
                wait_for_stop(root, ui)
            else:
                raise RuntimeError('Local stop recorded; confirm the remote job has ended before collecting.')
        finally:
            save_current(root, factory)
        return
    scheduler = manifest.get('scheduler', '')
    job_id, token = str(manifest.get('job_id', '') or ''), str(manifest['run_token'])
    if scheduler == 'slurm':
        command = slurm_wait(job_id, token)
    elif scheduler == 'pbs':
        command = pbs_wait(job_id)
    else:
        raise ValueError('A recorded Slurm/PBS job is required before waiting.')
    batch = root.get('RUN_BATCH', {})
    callback = ((lambda: stop_queue(root, ui, job_id, token, factory))
                if manifest.get('batch_id', '') and manifest.get('batch_id', '') == batch.get('batch_id', '') else None)
    scope = linked_kill_local(root, ui, job_id, token, stop_callback=callback) if scheduler == 'slurm' else nullcontext()
    errors = []
    with scope:
        for attempt in range(3):
            try:
                code = ui.remote_execute(manifest['server'], '/bin/bash -c ' + shell_quote(command),
                                         manifest['workDir'], manifest.get('tunnel', ''), quiet=False,
                                         ignoreReturnCode=True, use_bang_command=False, std_err=errors)
            except Exception as exc:
                code = -1
                errors.append(str(exc))
            if code == 0 or manifest.get('stop_requested', False):
                break
            if attempt < 2:
                time.sleep(attempt + 1)
    manifest['wait_completed'] = code == 0
    if code == 0:
        manifest.pop('wait_error', None)
    if manifest.get('stop_requested', False):
        try:
            wait_for_stop(root, ui)
        finally:
            save_current(root, factory)
        print(stop_message(manifest))
    elif code != 0:
        manifest['wait_error'] = str(errors)
        final = refresh_run_state(root, ui) if scheduler == 'slurm' else None
        if final is None or not final['terminal']:
            raise RuntimeError('Could not query CGYRO job ' + job_id + '; all submissions remain recorded. ' + str(errors))
    if not manifest.get('stop_requested', False) and manifest.get('status', '') not in ('cancelled', 'failed'):
        manifest['status'] = 'submitted_or_finished'
    save_current(root, factory)
