"""Keep batch snapshots while one case occupies the live OMFIT branches.

RUN_MANIFEST is the active job view. RUN_HISTORY holds metadata only; point
payloads and frozen inputs belong to RUN_DB/__RUNS__/<token>/cases.
"""
from builtins import BaseException, Exception, RuntimeError, ValueError, any, dict, len, list, object, print, range, str
from contextlib import nullcontext
from copy import deepcopy
import time
from OMFITlib_cgyro_storage import compact_storage
from OMFITlib_cgyro_db import ensure_layout, freeze_run_inputs, rollback_actions, run_is_deleted, run_records
from OMFITlib_cgyro_run_state import (STOP_POLL_ATTEMPTS, STOP_POLL_SECONDS, STOP_QUERY_ERROR_LIMIT,
                                    collection_finished, linked_kill_local, native_remote_execute, pbs_wait, quote as shell_quote,
                                    refresh_run_state, slurm_wait, stop_message, stop_run, submission_pending,
                                    uncollected_job)


def collection_done(manifest):
    """Collection can finish after cancellation without a complete solver run."""
    return collection_finished(manifest)


def queue_records(root, *, include_parked=False):
    """Return the explicit action scope; retain other pending jobs separately.

    Recovery preserves old queue metadata, but a supplied job ID only grants
    collection/synchronization permission for that job. An invalid focus must
    fail closed instead of silently broadening an action to historical jobs.
    Metadata inspection can request include_parked=True; retaining a historical
    record does not make it part of the newly selected operation.
    """
    history = root.get('RUN_HISTORY', {})
    batch = root.get('RUN_BATCH', {})
    tokens = batch.get('tokens', [])
    if not include_parked and 'focus_token' in batch:
        focus = str(batch['focus_token'])
        if not focus or focus not in tokens or not history.get(focus, {}).get('manifest', None):
            raise ValueError('The recovered job selection is invalid; recover the intended job ID again.')
        tokens = [focus]
    return [(token, history[token]) for token in tokens
            if token in history and history[token].get('manifest', None)]


def run_is_retired(root, token):
    """A tombstone is authoritative even when an old GUI retains its manifest."""
    return run_is_deleted(root, token) or run_records(root).get(str(token), {}).get('payload_retired', False)


def require_retained_run(root, token):
    if run_is_deleted(root, token):
        raise ValueError('This task was explicitly deleted. Close the old result window. '
                         'Recover its job ID explicitly if you want to import it again.')
    if run_is_retired(root, token):
        raise ValueError('This historical result was superseded and its payload was retired. '
                         'Reopen the result table and select the latest retained scan.')
    if run_records(root).get(str(token), {}).get('retired_points', {}):
        raise ValueError('Some points of this collected job were superseded and retired. '
                         'Use the retained result table to continue remaining points; recollection of the old job is disabled.')


def save_current(root, factory=dict):
    """Save immutable result/input references before copying the active case."""
    manifest = root.get('RUN_MANIFEST', {})
    if (not manifest.get('run_token', '') or
            not any(key in root for key in ('RUN_DB', 'Cases', 'RUN_HISTORY'))):
        return  # Metadata-only scheduler views already refer to the saved entry.
    if (run_is_retired(root, manifest['run_token']) or
            run_records(root).get(str(manifest['run_token']), {}).get('retired_points', {})):
        # A finally handler may save an obsolete selection after cleanup. Its
        # historical metadata is already retained; never recreate input/case
        # branches or overwrite that record from the stale live manifest.
        return
    compact_storage(root, factory, run_token=manifest['run_token'])
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
        # Public coordinates are authoritative; a finished job keeps metadata
        # only. The active collector already installed the result references.
        record.pop('cases', None)
        record.pop('inputs', None)
    else:
        freeze_run_inputs(root, manifest, factory)
    entry.pop('cases', None)
    entry['manifest'] = saved


def activate_run(root, token):
    """Restore a batch snapshot before waiting, retrying, or collecting it."""
    ensure_layout(root)
    require_retained_run(root, token)
    entry = root['RUN_HISTORY'][token]
    if entry['manifest'].get('batch_id', '') != root['RUN_BATCH'].get('batch_id', ''):
        raise ValueError('The saved run belongs to another queue batch.')
    root['RUN_MANIFEST'] = deepcopy(entry['manifest'])


def pending_runs(root):
    """Finished but uncollected jobs still protect their results from replacement."""
    return [manifest for _, entry in queue_records(root) for manifest in [entry['manifest']]
            if submission_pending(manifest) or uncollected_job(manifest) or
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
    focused = 'focus_token' in batch
    total = len(rows) if focused else len(batch.get('case_ids', rows))
    caption = '本次恢复作业' if focused else '批量案例'
    return (caption + '：完整 {} / {}；部分结果 {}；无结果跳过 {}。').format(done, total, partial, empty)


def queue_sync_summary(root):
    """Describe scheduler evidence separately from result collection counts."""
    rows = [entry['manifest'] for _, entry in queue_records(root)]
    if not rows and root.get('RUN_MANIFEST', None):
        rows = [root['RUN_MANIFEST']]
    ended, active, unknown, lines = 0, 0, 0, []
    for manifest in rows:
        sync = manifest.get('scheduler_sync', {})
        outcome = sync.get('outcome', '')
        if manifest.get('status', '') == 'published':
            ended += 1
            state = '已归档'
        elif sync.get('terminal', False) and outcome in ('completed', 'cancelled', 'failed'):
            ended += 1
            state = {'completed': 'Slurm 已完成', 'cancelled': 'Slurm 已取消', 'failed': 'Slurm 已失败'}[outcome]
        elif sync.get('active', False):
            active += 1
            state = '仍有活动或未识别的队列记录'
        else:
            unknown += 1
            state = '未确认终态：' + str(manifest.get('sync_error', '') or sync.get('reason', '') or '缺少有效查询结果')
        lines.append('作业 {}：{}'.format(manifest.get('job_id', '') or '未确认', state))
    return '作业状态核对：已结束 {}，活动 {}，未确认 {}。\n'.format(ended, active, unknown) + '\n'.join(lines)


def _commit_synced_manifest(root, token, manifest, factory):
    """Commit one queried status to both metadata views, preserving payloads.

    RUN_HISTORY drives the queue while RUN_DB/__RUNS__ drives continuation and
    retention. Updating only the former leaves contradictory saved identities
    after recovery/requeue. Query a detached manifest, then commit all views;
    an Abort during native assignment must restore their preceding snapshots.
    """
    if str(manifest.get('run_token', '')) != str(token):
        raise ValueError('Synchronized CGYRO manifest belongs to another run.')
    # Status synchronization must never migrate/compact payload trees. Legacy
    # owners stay where they are until an explicit collection/storage action.
    history = root.setdefault('RUN_HISTORY', factory()).setdefault(token, factory())
    records = root.setdefault('RUN_DB', factory()).setdefault('__RUNS__', factory())
    missing = object()
    record = records.get(str(token), missing)
    created = record is missing
    if created:
        record = factory()
    old_history, old_record = history.get('manifest', missing), record.get('manifest', missing)
    current = root.get('RUN_MANIFEST', {})
    current_matches = str(current.get('run_token', '')) == str(token)
    old_current = dict(current) if current_matches else None
    history_copy, record_copy, current_copy = deepcopy(manifest), deepcopy(manifest), deepcopy(manifest)
    try:
        if created:
            records[str(token)] = record
        history['manifest'], record['manifest'] = history_copy, record_copy
        if current_matches:
            current.clear()
            current.update(current_copy)
    except BaseException as original_error:
        def restore(mapping, key, value):
            if value is missing:
                mapping.pop(key, None)
            else:
                mapping[key] = value
        rollback = [('history', lambda: restore(history, 'manifest', old_history)),
                    ('record', lambda: records.pop(str(token), None) if created else restore(record, 'manifest', old_record))]
        if current_matches:
            # Even an interrupted clear can mutate before raising. Attempt the
            # update independently, and never skip the other saved view because
            # one native mapping rejects its rollback assignment.
            rollback.extend([('current clear', current.clear), ('current restore', lambda: current.update(old_current))])
        rollback_actions(original_error, rollback)
        raise


def _refresh_manifest(manifest, settings, batch, ui, factory, recover):
    """Query a detached metadata view, including a previously requested stop."""
    view = dict(RUN_MANIFEST=manifest, SETTINGS=settings)
    if submission_pending(manifest) and recover is not None:
        recover(view, ui, factory)
    if submission_pending(manifest):
        raise RuntimeError('Submission has no confirmed job ID; inspect its saved submit log: '
                           + str(manifest.get('workDir', '')) + '/.cgyro_submit.out\n'
                           + str(manifest.get('submission_probe_error', '')))
    if not manifest.get('job_id', '') and manifest.get('status', '') == 'failed':
        return  # A definite rejection did not create a server job.
    stop_batch = batch.get('stop_requested', False) and manifest.get('scheduler', '') == 'slurm'
    if stop_batch or manifest.get('submission_stop_requested', False):
        if stop_batch and (not manifest.get('batch_id', '') or manifest['batch_id'] != batch.get('batch_id', '')):
            raise ValueError('The saved job belongs to another batch; it was not cancelled.')
        # stop_run already queries the scheduler, also when cancellation was
        # accepted earlier. Repeating it here adds a second round trip per job.
        result = stop_run(view, ui, manifest.get('job_id', ''), manifest['run_token'])
        if result is None:
            raise RuntimeError(manifest.get('cancellation', {}).get('sync_error', '')
                               or 'Cancellation state could not be synchronized.')
        if manifest.get('submission_stop_requested', False):
            manifest['auto_collect_requested'] = True
    else:
        refresh_run_state(view, ui)


def refresh_queue(root, ui, factory=dict, recover=None):
    """Synchronize only selected job metadata, never save or hash result files."""
    errors = []
    current = root.get('RUN_MANIFEST', {})
    entries = queue_records(root)
    if not entries and current.get('run_token', ''):
        entries = [(current['run_token'], dict(manifest=current))]
    if not entries:
        raise ValueError('No CGYRO run record is available.')
    for token, entry in entries:
        # save_current used to freeze inputs and compact every active result
        # before a read-only status check. Use the live metadata directly when
        # it belongs to this job; other queued jobs use their frozen snapshot.
        source = current if str(current.get('run_token', '')) == str(token) else entry['manifest']
        if collection_done(source) or run_is_retired(root, token):
            continue
        before = deepcopy(source)
        manifest = deepcopy(before)
        try:
            _refresh_manifest(manifest, root['SETTINGS'], root.get('RUN_BATCH', {}), ui, factory, recover)
            sync = manifest.get('scheduler_sync', {})
            if sync.get('outcome', '') == 'unknown':
                detail = str(sync.get('errors', '')).strip()
                raise RuntimeError('作业 {} 未确认终态：{}{}'.format(
                    manifest.get('job_id', ''), sync.get('reason', '') or '请检查保存的调度查询输出。',
                    '\n' + detail[:1200] if detail else ''))
            manifest.pop('sync_error', None)
        except Exception as exc:
            manifest['sync_error'] = str(exc)
            errors.append(str(manifest.get('case_id', token)) + ': ' + str(exc))
        finally:
            # Native remote_execute pumps Tk events. Do not overwrite a job
            # replaced during the query. On Abort, retain any recovered job ID
            # or accepted cancellation before propagating the interruption.
            latest = (root.get('RUN_MANIFEST', {}) if source is current else
                      root.get('RUN_HISTORY', {}).get(token, {}).get('manifest', {}))
            if run_is_retired(root, token) or latest != before:
                errors.append(str(token) + ': Job record changed during synchronization; query again.')
            else:
                _commit_synced_manifest(root, token, manifest, factory)
    if errors:
        raise RuntimeError('\n'.join(errors))
    return queue_sync_summary(root)


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
    for attempt in range(STOP_POLL_ATTEMPTS):
        try:
            result = refresh_run_state(root, ui)
            errors = 0
            if result['terminal']:
                manifest.pop('stop_sync_error', None)
                return
        except Exception as exc:
            errors += 1
            manifest['stop_sync_error'] = str(exc)
            if errors >= STOP_QUERY_ERROR_LIMIT:
                raise
        if attempt + 1 < STOP_POLL_ATTEMPTS:
            time.sleep(STOP_POLL_SECONDS)
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
                code = native_remote_execute(ui, manifest['server'], '/bin/bash -c ' + shell_quote(command),
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
