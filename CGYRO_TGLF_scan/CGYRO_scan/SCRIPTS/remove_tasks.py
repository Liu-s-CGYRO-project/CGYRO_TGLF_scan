"""Preview selected CGYRO tasks; deleting requires two explicit confirmations."""
from builtins import ValueError, len, print
from OMFITlib_cgyro_task_cleanup import preview_tasks, remove_tasks

defaultVars(tokens=None, confirm=False, expected=None, confirmation='')
if confirm is not True and confirm is not False:
    raise ValueError('confirm must be a boolean; no tasks were deleted.')
report = preview_tasks(root, tokens)
print('CGYRO task deletion preview: {} tasks, {} archived points.'.format(
    len(report['tokens']), report['archived_points']))
for task in report['tasks']:
    print('Task {}: servers={}, jobs={}'.format(task['token'], task['servers'], task['jobs']))
if confirm is True:
    remove_tasks(root, tokens, expected, confirmation, OMFITtree)
    print('Selected tasks removed from this project. Save as a new ZIP. Remote jobs/files were not changed.')
else:
    print('Preview only. Confirmation challenge: ' + report['confirmation'])
