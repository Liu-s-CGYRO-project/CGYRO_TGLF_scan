# Validate the selected endpoint, then run the unified 1D/2D/3D collector.
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
if idimrun not in (1, 2, 3):
    config_error('CGYRO parameter-axis count must be 1, 2, or 3')
root['SCRIPTS']['CGYROScan.py'].run()
