# this script is used to do the overall call for the 1D and 2D scan
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

idimrun=setup['idimrun']
if idimrun==1:
    root['SCRIPTS']['CGYROScan.py'].run()
else:
    root['SCRIPTS']['CGYROScan_2d.py'].run()
