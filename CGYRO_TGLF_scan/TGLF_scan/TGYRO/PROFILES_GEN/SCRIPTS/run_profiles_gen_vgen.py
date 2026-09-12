# -*-Python-*-
# Created by smithsp at 2013/07/22 11:04

root['SCRIPTS']['create_input.neo'].run()

input_gacode = root['OUTPUTS']['input.gacode']
inputs = [(input_gacode, 'input.gacode')]

input_neo = root['INPUTS']['input.neo']
inputs.append((input_neo, 'input.neo'))


input_neo['SIM_MODEL'] = root['SETTINGS']['PHYSICS']['sim_model']

outputs = ['vgen/input.gacode', 'vgen/out.vgen.jbs', 'vgen/out.vgen.vel']

nonzero_vel_ind = []
for i in range(1, input_neo['N_SPECIES']):
    if sum(abs(input_gacode['vtor_%d' % i])) > 0:
        nonzero_vel_ind.append(i)

if len(nonzero_vel_ind) > 1:
    printw(
        'More than one ion species has a non-zero toroidal velocity profile'
        'Therefore unable to tell vgen which ion velocity to match.\n'
        'Choosing the lowest index'
    )

# input.vgen
root['INPUTS']['input.vgen'] = input_vgen = OMFITgacode('input.vgen')
ordering_setting = root['SETTINGS']['PHYSICS']['rotation_ordering']
if len(nonzero_vel_ind) == 0:
    input_vgen['VEL_METHOD'] = 1
    input_vgen['ER_METHOD'] = 4
    input_vgen['ERSPECIES_INDX'] = 1
else:
    if CER is not None:
        # Default settings is strong rotation ordering (2) unless specified
        input_vgen['VEL_METHOD'] = 2 if ordering_setting is None else ordering_setting
        input_vgen['ER_METHOD'] = 4
    else:
        # Default settings is weak rotation ordering (1) unless specified
        input_vgen['VEL_METHOD'] = 1 if ordering_setting is None else ordering_setting
        input_vgen['ER_METHOD'] = 2
    input_vgen['ERSPECIES_INDX'] = nonzero_vel_ind[0]
input_vgen['NTHETA_MIN'] = min(tolist(root['SETTINGS']['PHYSICS']['vgen_N_THETA']))
input_vgen['NTHETA_MAX'] = max(tolist(root['SETTINGS']['PHYSICS']['vgen_N_THETA']))
input_vgen['TYPE'] = 'NULL'
inputs.append((input_vgen, 'input.vgen'))

# execute NEO
std_out = []
OMFITx.executable(root, inputs, [], std_out=std_out)

# wait for batch job to finish
if 'gacode_qsub' in str(root['SETTINGS']['SETUP']['executable']):
    root['job_run'] = OMFITx.manage_job(root, std_out)
    root['job_run'].wait_print('batch.out', 'batch.err')
    del root['job_run']

# collect NEO files
tmp = ''
for k in ['neoequil', 'neoexpnorm', 'neontheta']:
    tmp += 'cat vgen/out.vgen.%s[0-9][0-9]* | sort > vgen/out.vgen.%s\n' % (k, k)
    outputs.append('vgen/out.vgen.%s' % k)
OMFITx.executable(root, [], outputs, executable=tmp, clean=False)

# load profiles files in vgen/input.gacode
if os.path.exists('vgen/input.gacode'):
    root['OUTPUTS']['input.gacode'] = OMFITinputgacode('vgen/input.gacode')
else:
    printw(rootName + ': no vgen/input.gacode\nMake sure you are giving the right inputs to profiles_gen!')

# load bootstrap current saved in vgen/out.vgen.jbs
if os.path.exists('vgen/out.vgen.jbs'):
    root['OUTPUTS']['out.vgen.jbs'] = OMFITcsv('vgen/out.vgen.jbs')
else:
    printw(rootName + ': no vgen/out.vgen.jbs \nMake sure you are running the latest version of profiles_gen!')

# load vgen saved in vgen/out.vgen.vel
if os.path.exists('vgen/out.vgen.vel'):
    root['OUTPUTS']['out.vgen.vel'] = OMFITcsv('vgen/out.vgen.vel')
else:
    printw(rootName + ': no vgen/out.vgen.vel file\nMake sure you are running the latest version of profiles_gen!')

# load NEO extras
if 'neo_extra' in root['OUTPUTS']:
    del root['OUTPUTS']['neo_extra']
for file in ['neoequil', 'neoexpnorm', 'neontheta']:
    if os.path.exists('vgen/out.vgen.%s' % file):
        root['OUTPUTS'].setdefault('neo_extra', SortedDict())
        tmp = OMFITcsv('vgen/out.vgen.%s' % file)
        if file == 'neoequil':
            cols = ['rho_N', 'r/a_norm', 'q', 'rho_*', 'R_0/a_norm', 'NU_1/(v_norm/a)']
            nspecies = int((tmp['data'].shape[1] - len(cols)) // 4) - 1
            for k in list(range(1, nspecies + 1)) + ['e']:
                cols.append('n_%s/n_norm' % str(k))
                cols.append('T_%s/T_norm' % str(k))
                cols.append('dln n_%s/dr * a_norm' % str(k))
                cols.append('dln T_%s/dr * a_norm' % str(k))
        elif file == 'neoexpnorm':
            cols = ['rho_N', 'a_norm (m)', 'mass_norm (e-27 kg)', 'dens_norm (e19/m^3)', 'temp_norm (keV)', 'v_norm (m/s)', 'B_unit (T)']
        elif file == 'neontheta':
            cols = ['rho_N', 'ntheta']
        else:
            continue
        for k, c in enumerate(cols):
            root['OUTPUTS']['neo_extra'][c] = tmp['data'][:, k][argsort(tmp['data'][:, 0])]
    else:
        printw(rootName + ': no vgen/out.vgen.%s \nMake sure you are running the latest version of profiles_gen!' % file)

# postprocessing
root['SCRIPTS']['postprocess_vgen'].run()
