"""Recover saved identities; a modern gate may seal an unstarted submission."""
from OMFITlib_cgyro_run_state import collection_finished
from OMFITlib_cgyro_queue import queue_records, refresh_queue
from OMFITlib_cgyro_retry import recover_submission

queued = bool(queue_records(root))
summary = refresh_queue(root, OMFITx, OMFITtree, recover=recover_submission)
if queued:
    print(summary)
else:
    manifest = root.get('RUN_MANIFEST', {})
    if not manifest.get('job_id', '') and manifest.get('status', '') == 'failed':
        print('No job was accepted by this attempt. A fresh run is allowed.')
    else:
        result = manifest.get('scheduler_sync', {'outcome': manifest.get('status', 'unknown')})
        print('CGYRO scheduler state: ' + result['outcome'])
        if result['outcome'] in ('cancelled', 'failed'):
            print('The terminated run and its files are preserved. ' +
                  ('Collection is finished; another run is allowed.' if collection_finished(root['RUN_MANIFEST']) else
                   'Collect and archive its outputs before starting another run.'))
        elif result['outcome'] == 'unknown':
            print('No terminal state was confirmed. The existing run remains protected.')
