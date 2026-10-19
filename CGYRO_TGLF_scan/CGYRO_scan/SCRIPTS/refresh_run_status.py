"""Synchronize bookkeeping only; never submit, cancel or delete a job."""
from OMFITlib_cgyro_run_state import refresh_run_state
from OMFITlib_cgyro_queue import queue_records, refresh_queue
from OMFITlib_cgyro_retry import recover_submission

if queue_records(root):
    print(refresh_queue(root, OMFITx, OMFITtree, recover=recover_submission))
else:
    if root.get('RUN_MANIFEST', {}).get('submission_uncertain', False) and not recover_submission(root, OMFITx, OMFITtree):
        raise RuntimeError('Submission remains unconfirmed; inspect the saved .cgyro_submit.out before resubmitting.')
    result = refresh_run_state(root, OMFITx)
    print('CGYRO scheduler state: ' + result['outcome'])
    if result['outcome'] in ('cancelled', 'failed'):
        print('The terminated run and its files are preserved. A fresh run is allowed; collect partial outputs if needed.')
    elif result['outcome'] == 'unknown':
        print('No terminal state was confirmed. The existing run remains protected.')
