# -*-Python-*-
# Created by sciortinof at 05 Aug 2019  11:51

r"""
This script computes the various terms of the TGLF response matrix and checks Onsager symmetry.
It runs multiple times at the same radius to infer the various terms of the response matrix. Note that this
is expected to be faster than doing a single run per radius with multiple trace impurities since the computational
cost of TGLF goes as NS^2.

Transport coefficients follow the formulation
R \Gamma / n_z = D ( R/Lnz + cT * R / LTz + cR * vz' + cp)

"""

from OMFITlib_tglf import compute_STRAHL_correction
from scipy.constants import e as q_electron, m_p

defaultVars(
    frac_change=0.1,  # variable purely for debugging, it shouldn't matter
    runs_label=root['SETTINGS']['PHYSICS']['runs_label'],  # name of OMFIT Tree where results are stored
    thermodiffusion=root['SETTINGS']['PHYSICS']['compute_thermodiffusion'],
    rotodiffusion=root['SETTINGS']['PHYSICS']['compute_rotodiffusion'],
    rhoList=[0.6, 0.8],
)


# Setup OMFIT trees
root.setdefault('TGLF_SCAN_DB', OMFITtree())
root['TGLF_SCAN_DB'].setdefault(runs_label, OMFITtree())
run_root = root['TGLF_SCAN_DB'][runs_label]

# save settings used for the run, so that this can be reloaded later on
run_root['PHYSICS_SETTINGS'] = copy.deepcopy(root['SETTINGS']['PHYSICS'])

# Make sure that info of selected impurity are correctly copied
impElement = run_root['PHYSICS_SETTINGS']['impElement']
impZ = run_root['PHYSICS_SETTINGS']['impZ']
impM = run_root['PHYSICS_SETTINGS']['impM']

# Copy original input.gacode and create input.gacode_mod for our ions
run_root['input.gacode_orig'] = copy.deepcopy(root['TGYRO']['PROFILES_GEN']['OUTPUTS']['input.gacode'])
run_root['input.gacode_mod'] = copy.deepcopy(root['TGYRO']['PROFILES_GEN']['OUTPUTS']['input.gacode'])

# floating-point-precision seems to give trouble with input.tglf keys... Here's a little hack:
kkeys = np.array(root['input.tglf'].keys())
rhoList = [kkeys[np.argmin(np.abs(kkeys - rho))] for rho in rhoList]
run_root['rhoList'] = rhoList

# Store inputs (radial coord conversion isn't needed, but can be useful)
rho = np.array(rhoList)
input_rho = root['TGYRO']['PROFILES_GEN']['OUTPUTS']['input.gacode']['rho']
input_polflux = root['TGYRO']['PROFILES_GEN']['OUTPUTS']['input.gacode']['polflux']
input_psiN = (input_polflux - input_polflux[0]) / (input_polflux[-1] - input_polflux[0])
psiN = (interpolate.interp1d(input_rho, input_psiN))(rho)
run_root['rho'] = rho
run_root['psin'] = psiN


# Add trace impurity at the end of input.gacode_mod list (note the +1!)
impLoc = run_root['impLoc'] = len([run_root['input.gacode_mod']['IONS'][k][0] for k in run_root['input.gacode_mod']['IONS'].keys()]) + 1

# Add a single trace impurity
ion_names = run_root['input.gacode_mod'].ion_names()
print("ion_names: ", ion_names)

run_root['input.gacode_mod'].add_ion(
    ion_num=impLoc,
    ion=impElement,
    Z=impZ,
    A=impM,
    ni=run_root['input.gacode_mod']['ne'] * 1e-6,
    thermal=True,
    remove_density_from_ion='D',  # remove density from main ion background
    temperature_and_velocities_from_ion='D',
)  # T and v from main ion background

# =================

# Set our input.gacode_mod in the PROFILES_GEN module
root['TGYRO']['PROFILES_GEN']['OUTPUTS']['input.gacode'] = copy.deepcopy(run_root['input.gacode_mod'])

# Include all ions in TGYRO setup of TGLF inputs
root['TGYRO']['INPUTS']['input.tgyro']['LOC_N_ION'] = run_root['input.gacode_mod']['N_ION']
root['TGYRO']['SETTINGS']['PHYSICS']['LOC_N_ION_USER'] = run_root['input.gacode_mod']['N_ION']

# ==========
# when ions are changed, TGLF inputs must be re-computed using TGYRO
if (
    len(root['input.tglf'])
    and 'input.gacode_mod' in run_root
    and run_root['input.gacode_mod']['N_ION'] + 1 == root['input.tglf'][0.5]['NS']
):
    # if number of ions has not changed, and input.gacode_mod is already set up, assume that we don't need to run setup_tglf again
    pass
else:
    # Setup the inputs for TGLF (all trace ions still being the same)
    root.setdefault('input.tglf', OMFITtree()).clear()
    root['SCRIPTS']['setup_tglf'].run()

# ==========

# Reset the input.gacode file without the trace impurities
root['TGYRO']['PROFILES_GEN']['OUTPUTS']['input.gacode'] = copy.deepcopy(run_root['input.gacode_orig'])

# allocate arrays
run_root['M'] = []
run_root['M_inv'] = []
run_root['gamma_z'] = []
run_root['nz'] = []

# compute also heat diffusivities:
run_root['chi_i'] = np.zeros_like(rhoList)
run_root['chi_e'] = np.zeros_like(rhoList)
run_root['chi_i_exp'] = np.zeros_like(rhoList)
run_root['chi_e_exp'] = np.zeros_like(rhoList)

keys = list(root['input.tglf'])
for imp in range(2, root['input.tglf'][keys[0]]['NS']):  # get number of ions from one of the created input.tglf
    run_root['chi_imp%d' % imp] = np.zeros_like(rhoList)

dTedr_exp = -np.array(np.gradient(root['tgyro_output']['te'][0, :])) / np.gradient(root['tgyro_output']['rmin'][0, :])  # eV / m
dTidr_exp = -np.array(np.gradient(root['tgyro_output']['ti1'][0, :])) / np.gradient(root['tgyro_output']['rmin'][0, :])  # eV / m

# ========================

# create a new list of tglf inputs at each radius --> this will be modified for the scan
run_root['input.tglf.modified'] = copy.deepcopy(root['input.tglf'])

tglf_inputs = []
batch_lines = []
outputs = ['./']

server = SERVER[root['TGLF']['SETTINGS']['REMOTE_SETUP']['serverPicker']]['server']
if is_server(server, 'iris'):
    partition = 'short,medium,long'
else:
    partition = None


# allocate space for matrix elements at each radius
num_runs_per_rad = 2
if thermodiffusion:
    num_runs_per_rad += 1
if rotodiffusion:
    num_runs_per_rad += 1


RLnz = np.zeros((num_runs_per_rad, len(rhoList)))
nz = np.zeros((num_runs_per_rad, len(rhoList)))
gamma_z = np.zeros((num_runs_per_rad, len(rhoList)))
Q_z = np.zeros((num_runs_per_rad, len(rhoList)))
Q_e = np.zeros(len(rhoList))
Q_i = np.zeros(len(rhoList))
if thermodiffusion:
    RLTz = np.zeros((num_runs_per_rad, len(rhoList)))
if rotodiffusion:
    grad_vz = np.zeros((num_runs_per_rad, len(rhoList)))

RLTe = np.zeros(len(rhoList))
RLTi = np.zeros(len(rhoList))
rmin = np.zeros_like(rhoList)
cs = np.zeros_like(rhoList)
vthz = np.zeros_like(rhoList)


# create list of input.tglf files to be run in parallel
for i, rho in enumerate(rhoList):

    # Some useful variables
    ind_rho = closestIndex(root['tgyro_output']['rho'][0, :], rho)
    rmin[i] = root['tgyro_output']['rmin'][0, ind_rho] * 1e-2
    cs[i] = root['tgyro_output']['c_s'][0, ind_rho]
    vthz[i] = np.sqrt(root['tgyro_output']['ti1'] * 1e3 * q_electron / (impM * m_p))[
        0, ind_rho
    ]  # note chosen definition without factor of sqrt(2)

    a = root['tgyro_output']['a'] * 1e-2
    Rmaj = root['tgyro_output']['rmaj/a'][0, 0] * a  # use Rmaj on given on axis
    RLTe[i] = run_root['input.tglf.modified'][rho]['RLTS_1'] * Rmaj / a  # 1st index is electrons in TGLF
    RLTi[i] = run_root['input.tglf.modified'][rho]['RLTS_2'] * Rmaj / a  # 2nd index is main ions in TGLF

    # get different TGLF runs with (1) standard inputs; (2) modified grad(nz); (3) modified grad(Tz); (4) modified grad(vz)
    # baseline:
    nz[0, i] = root['tgyro_output']['ni{}'.format(impLoc)][0, ind_rho] * 1e-13  # cm^-3 --> 10^19 m^-3
    RLnz[0, i] = run_root['input.tglf.modified'][rho]['RLNS_{}'.format(impLoc + 1)] * Rmaj / a  # convert aL -->RL normalization
    if thermodiffusion:
        RLTz[0, i] = run_root['input.tglf.modified'][rho]['RLTS_{}'.format(impLoc + 1)] * Rmaj / a
    if rotodiffusion:
        grad_vz[0, i] = run_root['input.tglf.modified'][rho]['VPAR_SHEAR_{}'.format(impLoc + 1)] * Rmaj / a * cs[i] / vthz[i]
    tglf_inputs.append(copy.deepcopy(run_root['input.tglf.modified'][rho]))

    # perturbed grad(nz)
    run_root['input.tglf.modified'][rho]['RLNS_{}'.format(impLoc + 1)] *= 1 + frac_change
    nz[1, i] = root['tgyro_output']['ni{}'.format(impLoc)][0, ind_rho] * 1e-13  # cm^-3 --> 10^19 m^-3
    RLnz[1, i] = run_root['input.tglf.modified'][rho]['RLNS_{}'.format(impLoc + 1)] * Rmaj / a  # convert aL -->RL normalization
    if thermodiffusion:
        RLTz[1, i] = run_root['input.tglf.modified'][rho]['RLTS_{}'.format(impLoc + 1)] * Rmaj / a
    if rotodiffusion:
        grad_vz[1, i] = run_root['input.tglf.modified'][rho]['VPAR_SHEAR_{}'.format(impLoc + 1)] * Rmaj / a * cs[i] / vthz[i]
    tglf_inputs.append(copy.deepcopy(run_root['input.tglf.modified'][rho]))

    if thermodiffusion:
        # perturbed grad(Tz)
        run_root['input.tglf.modified'][rho]['RLTS_{}'.format(impLoc + 1)] *= 1 + frac_change
        nz[2, i] = root['tgyro_output']['ni{}'.format(impLoc)][0, ind_rho] * 1e-13  # cm^-3 --> 10^19 m^-3
        RLnz[2, i] = run_root['input.tglf.modified'][rho]['RLNS_{}'.format(impLoc + 1)] * Rmaj / a  # convert aL -->RL normalization
        RLTz[2, i] = run_root['input.tglf.modified'][rho]['RLTS_{}'.format(impLoc + 1)] * Rmaj / a
        if rotodiffusion:
            grad_vz[2, i] = run_root['input.tglf.modified'][rho]['VPAR_SHEAR_{}'.format(impLoc + 1)] * Rmaj / a * cs[i] / vthz[i]
        tglf_inputs.append(copy.deepcopy(run_root['input.tglf.modified'][rho]))

    if rotodiffusion:
        # perturbed grad(vz)
        run_root['input.tglf.modified'][rho]['VPAR_SHEAR_{}'.format(impLoc + 1)] *= 1 + frac_change
        nz[-1, i] = root['tgyro_output']['ni{}'.format(impLoc)][0, ind_rho] * 1e-13  # cm^-3 --> 10^19 m^-3
        RLnz[-1, i] = run_root['input.tglf.modified'][rho]['RLNS_{}'.format(impLoc + 1)] * Rmaj / a  # convert aL -->RL normalization
        if thermodiffusion:
            RLTz[-1, i] = run_root['input.tglf.modified'][rho]['RLTS_{}'.format(impLoc + 1)] * Rmaj / a
        grad_vz[-1, i] = run_root['input.tglf.modified'][rho]['VPAR_SHEAR_{}'.format(impLoc + 1)] * Rmaj / a * cs[i] / vthz[i]
        tglf_inputs.append(copy.deepcopy(run_root['input.tglf.modified'][rho]))


# ===== set up batch job  =========
inputs = []
for i, input in enumerate(tglf_inputs):
    inputs.append((input, '%d/input.tglf' % i))
    batch_lines.append('tglf -e %d' % i)

# run job array for all radii
OMFITx.job_array(
    root,
    inputs=inputs,
    outputs=outputs,
    batch_lines=batch_lines,
    environment='\n'.join(str(root['TGLF']['SETTINGS']['SETUP']['executable']).splitlines()[:-1]),
    partition=partition,
    job_time='00:30:00',
)


# ========================
# gather results
j = 0
baseline_heat_flux = []
for i in range(len(rhoList)):
    # baseline
    res = OMFITtglf(root['SETTINGS']['SETUP']['workDir'] + str(i + j * (num_runs_per_rad - 1)))
    gamma_z[0, i] = res['gbflux']['data']['Gam/Gam_GB'][impLoc]  # 0-index is electrons in TGLF gbflux
    Q_z[0, i] = res['gbflux']['data']['Q/Q_GB'][impLoc]
    baseline_heat_flux.append(np.asarray(res['gbflux']['data']['Q/Q_GB'], dtype=float))

    # perturbed grad(nz)
    res = OMFITtglf(root['SETTINGS']['SETUP']['workDir'] + str(i + j * (num_runs_per_rad - 1) + 1))
    gamma_z[1, i] = res['gbflux']['data']['Gam/Gam_GB'][impLoc]
    Q_z[1, i] = res['gbflux']['data']['Q/Q_GB'][impLoc]

    if thermodiffusion:
        # perturbed grad(Tz)
        res = OMFITtglf(root['SETTINGS']['SETUP']['workDir'] + str(i + j * (num_runs_per_rad - 1) + 2))
        gamma_z[2, i] = res['gbflux']['data']['Gam/Gam_GB'][impLoc]
        Q_z[2, i] = res['gbflux']['data']['Q/Q_GB'][impLoc]

    if rotodiffusion:
        # perturbed grad(vz)
        res = OMFITtglf(root['SETTINGS']['SETUP']['workDir'] + str(i + j * (num_runs_per_rad - 1) + num_runs_per_rad - 1))
        gamma_z[-1, i] = res['gbflux']['data']['Gam/Gam_GB'][impLoc]
        Q_z[-1, i] = res['gbflux']['data']['Q/Q_GB'][impLoc]

    # Qe and Qi should be the same for all runs at the same radius
    # Heat diffusivities describe the baseline, not the last trace perturbation.
    Q_e[i] = baseline_heat_flux[-1][0]
    Q_i[i] = baseline_heat_flux[-1][1]

    j += 1

# vectorized solution across all requested radii
inds = [closestIndex(root['tgyro_output']['rho'][0, :], rho) for rho in rhoList]
rmin = root['tgyro_output']['rmin'][0, inds] * 1e-2
a = root['tgyro_output']['a'] * 1e-2
gamma_GB = root['tgyro_output']['Gamma_GB'][0, inds]  # TGYRO Gamma_GB (10^19 m**-2 s^-1)
Q_GB = root['tgyro_output']['Q_GB'][0, inds] * 1e6

# Compute TGLF heat diffusivities for each species
ne = root['tgyro_output']['ne'][0, inds] * 1e-13  # cm^-3 --> 10^19 m^-3
ni = root['tgyro_output']['ni1'][0, inds] * 1e-13  # cm^-3 --> 10^19 m^-3
Te = root['tgyro_output']['te'][0, inds] * 1e3 * q_electron  # keV --> J
Ti = root['tgyro_output']['ti1'][0, inds] * 1e3 * q_electron  # keV --> J

# deal with annoying floating-point precision of keys....
kkeys = np.array(root['input.tglf'].keys())
rho = kkeys[np.argmin(np.abs(kkeys - rho))]

grad_Te = [root['input.tglf'][rho]['RLTS_1'] for rho in rhoList] / a * Te
grad_Ti = [root['input.tglf'][rho]['RLTS_2'] for rho in rhoList] / a * Ti

# expt chi's  ----- NB: root['tgyro_output']['p_e_tot'] is an interpolated version of root['tgyro_output']['profiles_evolution'][-1]['pow_e'], similarly for main ions
run_root['chi_e_exp'] = root['tgyro_output']['p_e_tot'][0, inds] / (dTedr_exp[inds] * (ne * 1e19) * q_electron)  # m^2 / s
run_root['chi_i_exp'] = root['tgyro_output']['p_i_tot'][0, inds] / (dTidr_exp[inds] * (ni * 1e19) * q_electron)  # m^2 / s

run_root['chi_e'] = Q_e * Q_GB / grad_Te / (ne * 1e19)
run_root['chi_i'] = Q_i * Q_GB / grad_Ti / (ni * 1e19)
# Q_i/Q_e are normalized; Q_GB is W/m^2, gradients are J/m and densities below are m^-3.
run_root['chi_eff'] = (Q_i + Q_e) * Q_GB / (grad_Ti * ni * 1e19 + grad_Te * ne * 1e19)

for imp in range(2, root['input.tglf'][rhoList[0]]['NS']):  # includes lumped impurity
    nimp = root['tgyro_output']['ni%d' % imp][0, inds] * 1e-13  # cm^-3 --> 10^19 m^-3
    Timp = root['tgyro_output']['ti%d' % imp][0, inds] * 1e3 * q_electron
    grad_Timp = [root['input.tglf'][rho]['RLTS_%d' % (imp + 1)] for rho in rhoList] / a * Timp
    # getting chi does not require scanning of nz'. Use only Q_z[0,:]
    run_root['chi_imp%d' % imp] = np.asarray(baseline_heat_flux)[:, imp] * Q_GB / grad_Timp / (nimp * 1e19)


# ===============
# Save inputs and outputs -- transport coefficients will be computed in a separate script
run_root['gamma_z'] = gamma_z
run_root['gamma_GB'] = gamma_GB
run_root['Q_z'] = Q_z
run_root['Q_GB'] = Q_GB
run_root['vthz'] = vthz
run_root['cs'] = cs

run_root['RLnz'] = RLnz
run_root['nz'] = nz
if thermodiffusion:
    run_root['RLTz'] = RLTz
if rotodiffusion:
    run_root['grad_vz'] = grad_vz
