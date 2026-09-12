# -*-Python-*-
# Created by smithsp at 2013/06/03 14:20
#
# load_remote script loads TGYRO files after job is completed

defaultVars(
    server=root['SETTINGS']['REMOTE_SETUP']['server'],
    tunnel=root['SETTINGS']['REMOTE_SETUP']['tunnel'],
    remote_dir=root['SETTINGS']['REMOTE_SETUP']['workDir'],
    load_input_gacode=True,
)

runid = str(root['SETTINGS']['EXPERIMENT']['runid'])
print('Loading remote simulation for runid `%s` from %s on %s through %s' % (runid, remote_dir, server, tunnel))

local_dir = root['SETTINGS']['SETUP']['workDir']
OMFITx.initWorkdir(root, server=server, tunnel=tunnel, workdir=local_dir, remotedir=remote_dir, clean='local')

# take all outputs
outputs = remote_dir.rstrip('/') + '/*'

# dowsync remote results
OMFITx.remote_downsync(server, outputs, local_dir, tunnel=tunnel)

# check that everything would be loaded all right
try:
    tmp = OMFITtgyro(local_dir)
except Exception:
    for k in range(10):
        printe('Are you sure that pygacode tools is up-to-date with the version of GACODE that was run?')
    raise

# reset soft
root['SCRIPTS']['reset'].runNoGUI(soft=True)

# assign TGYRO output
root['OUTPUTS']['output'] = tmp

# load input files
root['INPUTS']['input.tgyro'] = OMFITgacode(local_dir + 'input.tgyro.gen')
tglf_dir = local_dir + '/' + list(root['INPUTS']['input.tgyro']['DIR'].keys())[0]
for k in ['tglf', 'glf23', 'gyro']:
    if os.path.exists(tglf_dir + '/input.' + k):
        root['INPUTS']['input.' + k] = OMFITgacode(tglf_dir + '/input.' + k)

# load PROFILES_GEN output files
input_gacode_location = parseLocation(root['SETTINGS']['DEPENDENCIES']['input_gacode'])

if load_input_gacode and os.path.exists(local_dir + 'input.gacode'):
    eval(buildLocation(input_gacode_location[:-1]))['input.gacode'] = OMFITinputgacode(local_dir + 'input.gacode')

# load TGYRO output input.gacode.new (or last one generated)
if os.path.exists(local_dir + 'input.gacode.new'):
    root['OUTPUTS']['input.gacode'] = OMFITinputgacode(local_dir + 'input.gacode.new')
else:
    ips = {}
    for item in glob.glob(local_dir + 'input.gacode.*'):
        if re.match('.*/input.gacode.[0-9]+$', item):
            ips[int(re.sub('.*/input.gacode.([0-9]+)$', r'\1', item))] = item
    if len(ips):
        root['OUTPUTS']['input.gacode'] = OMFITinputgacode(ips[sorted(ips.keys())[-1]])
