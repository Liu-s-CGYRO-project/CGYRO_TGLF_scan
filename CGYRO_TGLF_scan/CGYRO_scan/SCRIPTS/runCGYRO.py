# Validate the selected endpoint, then run the unified 1D/2D/3D collector.
from OMFITlib_gui_api import task_action
from builtins import print
print('[CGYRO] Run entry started; validating endpoint and scan settings.', flush=True)
defaultVars(wait_for_completion=True, batch_id='', continuation=None, check_temp_start=True)
rmt_setup=root['SETTINGS']['REMOTE_SETUP']
setup=root['SETTINGS']['SETUP']


def cfg_missing(node, key):
    try:
        return key not in node.keys() or node[key] in [None, '']
    except Exception:
        return True


def config_error(message):
    try:
        raise OMFITexception(message)
    except NameError:
        raise ValueError(message)


if 'submit_backend' in rmt_setup.keys():
    del rmt_setup['submit_backend']

if cfg_missing(rmt_setup, 'serverPicker'):
    config_error("SETTINGS['REMOTE_SETUP']['serverPicker'] must be set")

server_picker = str(rmt_setup['serverPicker'])
if server_picker not in rmt_setup:
    config_error('Missing selected server configuration: ' + server_picker)
selected = rmt_setup[server_picker]
for field in ('server', 'workDir', 'tunnel'):
    if field in selected and selected[field] is not None:
        rmt_setup[field] = selected[field]
if server_picker == 'localhost':
    rmt_setup['server'] = 'localhost'
    rmt_setup['tunnel'] = ''
elif cfg_missing(rmt_setup, 'server') or cfg_missing(rmt_setup, 'workDir'):
    config_error('Selected remote endpoint needs server and workDir')
if setup['icgyro'] == 0 and 'input.gyro' not in root['INPUTS']:
    config_error('GYRO mode requires a validated input.gyro; this example supplies CGYRO input only')

idimrun = int(setup['idimrun'])
if idimrun not in (0, 1, 2, 3):
    config_error('CGYRO parameter-axis count must be 0, 1, 2, or 3')
print('[CGYRO] Loading scan preparation workflow.', flush=True)
task_action(root['SCRIPTS']['CGYROScan.py'], wait_for_completion=wait_for_completion,
    batch_id=batch_id, continuation=continuation, check_temp_start=check_temp_start)
