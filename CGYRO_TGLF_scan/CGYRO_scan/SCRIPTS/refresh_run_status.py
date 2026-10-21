"""Recover saved identities; a modern gate may seal an unstarted submission."""
from OMFITlib_cgyro_run_state import refresh_run_state, submission_pending
from OMFITlib_cgyro_queue import queue_records, refresh_queue
from OMFITlib_cgyro_retry import recover_submission, stop_submitted

if queue_records(root):
    print(refresh_queue(root, OMFITx, OMFITtree, recover=recover_submission))
else:
    manifest = root.get('RUN_MANIFEST', {})
    if submission_pending(manifest):
        recover_submission(root, OMFITx, OMFITtree)
    if submission_pending(manifest):
        raise RuntimeError('Submission remains unconfirmed; inspect ' + str(manifest.get('workDir', ''))
                           + '/.cgyro_submit.out before resubmitting.\n'
                           + str(manifest.get('submission_probe_error', '')))
    if not manifest.get('job_id', '') and manifest.get('status', '') == 'failed':
        print('No job was accepted by this attempt. A fresh run is allowed.')
    else:
        stop_submitted(root, OMFITx, OMFITtree)
        result = refresh_run_state(root, OMFITx)
        print('CGYRO scheduler state: ' + result['outcome'])
        if result['outcome'] in ('cancelled', 'failed'):
            print('The terminated run and its files are preserved. A fresh run is allowed; collect partial outputs if needed.')
        elif result['outcome'] == 'unknown':
            print('No terminal state was confirmed. The existing run remains protected.')
