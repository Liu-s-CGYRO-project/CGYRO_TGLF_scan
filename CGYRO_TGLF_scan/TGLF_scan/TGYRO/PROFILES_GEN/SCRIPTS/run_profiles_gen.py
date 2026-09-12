# -*-Python-*-
# Created by holland at 2013/03/06 14:30

defaultVars(enforce_quasineutrality=False, gEQDSK=gEQDSK, profpowbal=profpowbal, calcEr=root['SETTINGS']['PHYSICS']['calcEr'], args='')

inputs = []

# input.gacode
if isinstance(profpowbal, OMFITinputgacode) and (gEQDSK is None):
    if 'input.gacode' in root['INPUTS']:
        root['OUTPUTS']['input.gacode'] = copy.deepcopy(root['INPUTS']['input.gacode'])

# power-balance
else:
    if profpowbal is None:
        print('Creating `null` input.gacode')
        args += ' -i null'
    # ODS
    elif isinstance(profpowbal, ODS):
        statefile = OMFITinputgacode('input.gacode').from_omas(profpowbal)
        args += ' -i ' + os.path.basename(statefile.filename)
        inputs.append(statefile)
        gEQDSK = OMFITgeqdsk('').from_omas(profpowbal)
    else:
        # if it is a list of statefiles, take the last one
        if isinstance(profpowbal, OMFITtree):
            profpowbal.sort(key=sortHuman)
            statefile = profpowbal[list(profpowbal.keys())[-1]]
        else:
            statefile = profpowbal
        args += ' -i ' + os.path.basename(statefile.filename)
        inputs.append(statefile)

    # equilibrium
    outputs = ['input.gacode']
    if gEQDSK is not None:
        args += ' -g ' + os.path.basename(gEQDSK.filename)
        inputs.append(gEQDSK)
        if isinstance(gEQDSK, dict):
            # gEQDSK is in COCOS 1, sign of Ip/Bt already postive for CCW
            args += ' -ipccw %d -btccw %d' % (sign(gEQDSK['CURRENT']), sign(gEQDSK['BCENTR']))

    # CER
    if CER is not None:
        args += ' -cer ' + os.path.basename(CER.filename)
        inputs.append(CER)

    # clear all existing previous outputs
    root['OUTPUTS'].clear()

    # run profiles_gen (serial)
    if 'pppl.gov' not in root['SETTINGS']['REMOTE_SETUP']['server']:
        server = root['SETTINGS']['REMOTE_SETUP']['server']
        serverPicker = str(SERVER(str(root['SETTINGS']['REMOTE_SETUP']['serverPicker'])))
    else:
        server = SERVER['pppl_sunfire']['server']
        serverPicker = 'portal'
    executable = 'profiles_gen '

    if serverPicker in root['SETTINGS']['REMOTE_SETUP']:
        executable = root['SETTINGS']['REMOTE_SETUP'][serverPicker]['environment'] + '\n' + executable

    OMFITx.executable(root, inputs, outputs, arguments=args, executable=executable, server=server)

    # load profiles files
    for item in outputs:
        if os.path.exists(item):
            root['OUTPUTS'][item] = OMFITinputgacode(item, GACODEtype='profiles')
        else:
            warnings.warn(rootName + ': no ' + item + '\nMake sure you are giving the right inputs to profiles_gen')

if profpowbal is None:
    root['OUTPUTS']['input.gacode']['rho'] = linspace(0, 1, root['OUTPUTS']['input.gacode']['N_EXP'])

# reorder ions as per request of the user
try:
    root['SCRIPTS']['reorder_ions'].run()
except Exception as _excp:
    root['SETTINGS']['PHYSICS']['reorder_ion_names'] = None
    printe(repr(_excp))

# make sure temperatures/densities are always >0
for item in ['Te', 'ne'] + ['Ti_%d' % i for i in range(1, 11)] + ['ni_%d' % i for i in range(1, 11)]:
    what = root['OUTPUTS']['input.gacode'][item]
    indexN = where(what <= 0)
    indexP = where(what > 0)
    if len(indexP[0]) and len(indexN[0]):
        printw(item + ' had some elements which were not positive (possibly 0)!!!')
        printw(item + ' non-positive elements changed to %g' % (min(what[indexP])))
        what[indexN] = min(what[indexP])

if 'input.gacode' in root['OUTPUTS']:
    root['OUTPUTS']['input.gacode_base'] = copy.deepcopy(root['OUTPUTS']['input.gacode'])

# blend eped profile
if EPED is not None and root['SETTINGS']['PHYSICS']['blendEPED']:
    root['SCRIPTS']['blendEPED'].run(test=False)
    root['SCRIPTS']['enforce_quasineutrality'].run()

# enforce quasineutrality
elif enforce_quasineutrality or root['SETTINGS']['PHYSICS']['calcEr']:
    root['SCRIPTS']['enforce_quasineutrality'].run()

# run a second time with -vgen option if need to calculate Er
if calcEr:
    root['SCRIPTS']['run_profiles_gen_vgen'].run()

# update ion names in root['SETTINGS']['PHYSICS']['reorder_ion_names']
import OMFITlib_profilesgen

numd_ion_names = OMFITlib_profilesgen.numd_ion_names()

# remove extra dummy ions
root['OUTPUTS']['input.gacode'].remove_dummy_ions()


# account for measured high-Z impurity radiation
if root['SETTINGS']['PHYSICS'].get('removeHighZimpRad', False):
    # measured total radiated power in W
    prad = profpowbal['prad']['data']
    # calculated lione radiatuion in W
    prad_li = profpowbal['prad_li']['data']
    # calculated bremsstrahlung in W
    prad_br = profpowbal['prad_br']['data']
    prad_highZ = np.maximum(prad - prad_li - prad_br, 0)
    vol = profpowbal['vol']['data']

    qrfe = root['OUTPUTS']['input.gacode'].setdefault('qrfe', vol * 0)
    qrfe[: len(prad_highZ)] -= prad_highZ / np.diff(vol) / 1e6  # MW/m^3
