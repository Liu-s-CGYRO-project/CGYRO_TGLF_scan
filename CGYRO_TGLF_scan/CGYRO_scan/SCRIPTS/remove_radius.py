"""Preview or explicitly delete one run/radius from the current project."""
from builtins import ValueError, len, print
from OMFITlib_cgyro_radius_cleanup import preview_radius, remove_radius

defaultVars(runid='', rho=None, nr='', confirm=False, expected=None)
if confirm is not True and confirm is not False:
    raise ValueError('confirm must be a boolean; preview retained the original data.')
report = preview_radius(root, runid, rho, nr)
print('CGYRO radius selection: {} / nr={} / rho={}'.format(runid, nr or '*', rho))
print('Job records: {}; archive branches: {}'.format(report['jobs'], report['archives']))
if confirm is True:
    report = remove_radius(root, runid, rho, nr, OMFITtree, expected=report if expected is None else expected)
    print('Removed {} run records and {} archive branches. Save this project as a new ZIP.'.format(
        len(report['tokens']), len(report['archives'])))
else:
    print('Preview only. Set confirm=True to delete this radius from the current project.')
