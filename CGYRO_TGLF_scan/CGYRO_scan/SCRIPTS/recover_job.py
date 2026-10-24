"""Recover an existing Slurm allocation; never execute or cancel the solver."""
from builtins import dict, len, print, str
import os
from OMFITlib_cgyro_job_recovery import recover_job

defaultVars(job_id='', manifest_path='')
remote = root['SETTINGS']['REMOTE_SETUP']
endpoint = dict(server=remote.get('server', ''), tunnel=remote.get('tunnel', ''),
                serverPicker=remote.get('serverPicker', ''))
base = os.path.join(str(OMFITworkDir(root, '')), 'recovered_jobs')
report = recover_job(root, OMFITx, job_id, endpoint, base, OMFITtree, OMFITpath, OMFITascii,
                     manifest_path=manifest_path)
manifest = report['manifest']
summary = ('Job {} already exists in this project.' if report['already_present'] else
           'Job {} recovered.').format(manifest['job_id'])
print(summary + ' {} / {} / {} points; status: {}'.format(
    manifest['runid'], manifest['case_id'], len(manifest['points']),
    manifest.get('scheduler_sync', {}).get('outcome', manifest.get('status', ''))))
if report['missing_inputs']:
    print('Original input ZIPs are missing for {} points. Existing output can still be collected; '
          'unstarted points need their original input before continuation.'.format(len(report['missing_inputs'])))
print('Use Synchronize job status while active; use Collect unarchived results after completion. '
      'Recovery did not submit, cancel, or recompute any job. Save this project to retain the restored record.')
