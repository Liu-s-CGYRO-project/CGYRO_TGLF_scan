"""Host-facing collection interface; scheduler and result readers remain separate.

The injected script runner keeps native OMFIT execution out of this coordinator.
No callable is saved in the data tree. Unknown submission states remain protected
by the existing entry scripts; GUI refresh must never call these functions.
"""
from builtins import dict, len, print, str
from OMFITlib_cgyro_queue import (activate_run, collection_done, pending_runs, queue_records,
                                 run_is_retired, save_current)
from OMFITlib_cgyro_run_state import submission_pending


def collect_run(node, run_script):
    """Read/archive current outputs only. Never grant solver retry permission."""
    setup = node['SETTINGS']['SETUP']
    old_run, old_download = setup.get('irun', None), setup.get('idownsync', None)
    try:
        setup['irun'], setup['idownsync'] = 0, 1
        return run_script('收集并归档 CGYRO 结果', 'CGYROScan.py',
                          collect_stopped=True, allow_solver_retries=False)
    finally:
        setup['irun'], setup['idownsync'] = old_run, old_download


def collect_batch(node, run_script, factory=dict, *, automatic=False):
    """Collect a batch, preserving partial results and each case's errors.

    node is CGYRO_scan, not the project root. run_script(title, name, **kw)
    must invoke an existing native SCRIPTS entry synchronously and propagate
    BaseException (OMFIT Abort). Only the explicit run action grants automatic
    waiting/retries; manually collecting must use the False default.
    """
    setup, batch = node['SETTINGS']['SETUP'], node['RUN_BATCH']
    previous = setup.get('irun', None), setup.get('idownsync', None)
    completed, errors = [], []
    try:
        setup['irun'], setup['idownsync'] = 0, 0
        for token, entry in queue_records(node):
            manifest = entry['manifest']
            if run_is_retired(node, token):
                # Retired snapshots have already been replaced at every full
                # coordinate. Batch recollection must not download them again.
                print('Skipping superseded CGYRO history: ' + str(manifest.get('case_id', token)))
                continue
            if manifest.get('status', '') == 'published':
                completed.append(manifest['case_id'])
                continue
            if automatic and collection_done(manifest):
                continue
            if not manifest.get('job_id', '') and manifest.get('status', '') == 'failed' and not submission_pending(manifest):
                continue  # A confirmed rejection has no results to collect.
            if not manifest.get('job_id', '') or submission_pending(manifest):
                errors.append(str(manifest.get('case_id', token)) + ': submission is not confirmed')
                continue
            activate_run(node, token)
            try:
                # Manual collection reads finished runs immediately. Active
                # jobs are reported by downsync; never wait or submit here.
                if automatic:
                    run_script('等待已提交的 CGYRO 案例', 'wait_current_run.py')
                setup['idownsync'] = 1
                run_script('收集并归档 CGYRO 批量结果', 'CGYROScan.py',
                          collect_stopped=True, allow_solver_retries=automatic)
                if node['RUN_MANIFEST'].get('status', '') == 'published':
                    completed.append(node['RUN_MANIFEST']['case_id'])
            except Exception as exc:
                errors.append(str(manifest.get('case_id', token)) + ': ' + str(exc))
            finally:
                save_current(node, factory)
    finally:
        setup['irun'], setup['idownsync'] = previous
        batch.update(dict(completed=completed, errors=errors,
            status='published' if len(completed) == len(batch['case_ids']) else
            'cancel_requested' if batch.get('stop_requested', False) and (pending_runs(node) or errors) else
            'cancelled' if batch.get('stop_requested', False) else 'partial'))
    if errors:
        # ASCII survives older OMFIT script serialization in error dialogs.
        raise ValueError('Some CGYRO cases were not archived; submitted jobs and successful results are preserved.\n'
                         + '\n'.join(errors))
    return completed
