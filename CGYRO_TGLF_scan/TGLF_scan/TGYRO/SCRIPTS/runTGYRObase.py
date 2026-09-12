# -*-Python-*-
# Created by meneghini at 2013/08/07 17:34

defaultVars(waitBatchJob=True, radial_distribution=root['SETTINGS']['PHYSICS']['radial_distribution'], load_input_gacode=True,remote_dir=root['SETTINGS']['REMOTE_SETUP']['workDir'])

if input_gacode is None:
    raise OMFITexception('input.gacode is missing')

# define inputs
inputs = [(root['INPUTS']['input.tgyro'], 'input.tgyro'), (input_gacode, 'input.gacode')]

if root['SETTINGS']['PHYSICS']['Turb_Model'] == 'MMM':
    inputs.append((root['INPUTS']['input.mmm'], 'input.mmm'))

# Force dumping of TGLF input that are actually used by TGYRO
root['INPUTS']['input.tgyro']['TGYRO_TGLF_DUMP_FLAG'] = 1

# Force writing of new, smooth output profiles
# If running pedestal model, then the -1 option is used to generate an
# input.gacode file for each iteration. This is necessary, because the
# edge boundary condition changes at each iteration.
if root['INPUTS']['input.tgyro'].get('TGYRO_PED_MODEL', 0) == 0:
    root['INPUTS']['input.tgyro']['TGYRO_WRITE_PROFILES_FLAG'] = 1
else:
    root['INPUTS']['input.tgyro']['TGYRO_WRITE_PROFILES_FLAG'] = -1

# Fit edge density and zeff profiles if runnin pedestal and those were not set by the user
if root['INPUTS']['input.tgyro']['TGYRO_PED_MODEL'] == 2 and (
    root['INPUTS']['input.tgyro']['TGYRO_NEPED'] == 0 or root['INPUTS']['input.tgyro']['TGYRO_ZEFFPED'] == 0
):
    printi('Fit input.gacode pedestal electron density')
    from OMFITlib_general import fit_ne_EPED1

    data = fit_ne_EPED1()
    if root['INPUTS']['input.tgyro']['TGYRO_NEPED'] == 0:
        root['INPUTS']['input.tgyro']['TGYRO_NEPED'] = data['ne_ped']
    if root['INPUTS']['input.tgyro']['TGYRO_ZEFFPED'] == 0:
        root['INPUTS']['input.tgyro']['TGYRO_ZEFFPED'] = data['zeff_ped']

# set number of ions
root['INPUTS']['input.tgyro']['LOC_N_ION'] = len(input_gacode['IONS'])
# do not include in TGLF and NEO ions that are not there
for k in range(root['INPUTS']['input.tgyro']['LOC_N_ION'] + 1, 10):
    root['INPUTS']['input.tgyro']['TGYRO_CALC_FLAG' + str(k)] = 0

# set run DIR according to number of processors required
root['INPUTS']['input.tgyro']['DIR'] = SortedDict()
turb_model = root['SETTINGS']['PHYSICS']['Turb_Model']
if turb_model == 'OMFIT QLGYRO':
    turb_model = 'TGLF'
inputfile = 'input.' + turb_model.lower()
cp_script = ''


from OMFITlib_general import setup_radii

setup_radii(radial_distribution)

for i in range(1, 1 + root['SETTINGS']['PHYSICS']['n_rad']):
    if i == 1:
        # sorting done to handle `Begin overlay [Add parameters above this line]` comment
        root['INPUTS'][inputfile].sort(reverse=True)
        inputs.append((root['INPUTS'][inputfile], f'{turb_model}{i}' + os.sep + inputfile))
    else:
        cp_script = f'''
#!/bin/bash
for i in `seq 2 {i}`;
do
    mkdir {turb_model}$i
    cp {turb_model}1/{inputfile} {turb_model}$i/{inputfile}
done
chmod +x qprint

'''

# if restarting upload
if root['INPUTS']['input.tgyro']['LOC_RESTART_FLAG'] == 1:
    inputs.insert(0, (root['OUTPUTS']['output'], '../'))

# upload inputs and replicate `DIR`
OMFITx.executable(root, inputs, [], executable='sh %s', script=(cp_script, 'cp_script.sh'), remotedir=remote_dir)

# execute TGYRO
std_out = []
OMFITx.executable(root, [], [], clean=False, std_out=std_out,remotedir=remote_dir)

if waitBatchJob:
    # wait for batch job to finish
    if 'gacode_qsub' in str(root['SETTINGS']['SETUP']['executable']):
        root.setdefault('RUN_DB', OMFITtree())
        runid = evalExpr(root['SETTINGS']['EXPERIMENT']['runid'])
        root['RUN_DB'].setdefault(runid, OMFITtree())
        root['RUN_DB'][runid]['job_run'] = OMFITx.manage_job(root, std_out)
        try:
            root['RUN_DB'][runid]['job_run'].wait_print('batch.out', 'batch.err')
        except OMFITexception as _excp:
            if 'qprint detached' not in str(_excp):
                raise
        del root['RUN_DB'][runid]['job_run']

    # fetch the results
    root['SCRIPTS']['load_remote'].run(load_input_gacode=load_input_gacode)
