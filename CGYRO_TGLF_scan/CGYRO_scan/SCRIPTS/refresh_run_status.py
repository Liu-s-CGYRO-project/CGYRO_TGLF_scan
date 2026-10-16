"""Synchronize bookkeeping only; never submit, cancel or delete a job."""
from OMFITlib_cgyro_run_state import refresh_run_state

result = refresh_run_state(root, OMFITx)
print('CGYRO scheduler state: ' + result['outcome'])
if result['outcome'] in ('cancelled', 'failed'):
    print('The terminated run and its files are preserved. A fresh run is allowed; collect partial outputs if needed.')
elif result['outcome'] == 'unknown':
    print('No terminal state was confirmed. The existing run remains protected.')
