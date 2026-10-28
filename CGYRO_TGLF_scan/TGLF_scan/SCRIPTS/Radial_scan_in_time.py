# -*-Python-*-
# Created by grierson at 08 Sep 2017  10:20

"""
This script runs TGLF and produces an eigenvalue spectrum radial
profile for multiple time points

"""

# Times are intentionally explicit; this entry must never start a different
# shot's demonstration calculations just because it was opened from a project.
from OMFITlib_gui_api import task_action
defaultVars(shot=root['SETTINGS']['EXPERIMENT']['shot'],
            runid=root['SETTINGS']['EXPERIMENT']['runid'], times=None, avgtim=0.0,
            rhos=root['SETTINGS']['PHYSICS']['rho_scan'])
if times is None or len(np.atleast_1d(times)) == 0:
    raise OMFITexception('Provide explicit times in milliseconds for the radial time scan')
times = np.atleast_1d(times)
rhos = list(rhos)
if not np.all(np.isfinite(times)) or not rhos:
    raise OMFITexception('Times must be finite and at least one radius is required')

root['SETTINGS']['EXPERIMENT']['shot'] = shot
root['SETTINGS']['EXPERIMENT']['runid'] = runid
root['SETTINGS']['PHYSICS']['rho_scan'] = rhos

TGYRO = root['TGYRO']
PROFILES_GEN = root['TGYRO']['PROFILES_GEN']
TRXPL = PROFILES_GEN['TRXPL']

# Set up PROFILES_GEN to run TRXPL
PROFILES_GEN['SETTINGS']['PHYSICS']['start_from'] = 'statefile'
PROFILES_GEN['SETTINGS']['PHYSICS']['use_trxpl'] = True

# Set up static TRXPL settings
TRXPL['SETTINGS']['EXPERIMENT']['shot'] = shot
TRXPL['SETTINGS']['EXPERIMENT']['runid'] = runid
TRXPL['SETTINGS']['EXPERIMENT']['avgtim'] = avgtim

# Set up ouptut structure
root['Experimental_spectra_in_time'] = OMFITtree()
for rho in rhos:
    root['Experimental_spectra_in_time'][rho] = {}
    for time in times:
        root['Experimental_spectra_in_time'][rho][time] = {}

for time in times:
    TRXPL['SETTINGS']['EXPERIMENT']['time'] = time

    # Run TRXPL
    task_action(TRXPL['SCRIPTS']['trxpl'])

    PROFILES_GEN['SETTINGS']['DEPENDENCIES']['profpowbal'] = "root['TRXPL']['OUTPUTS']['statefile']"
    PROFILES_GEN['SETTINGS']['DEPENDENCIES']['gEQDSK'] = "root['TRXPL']['OUTPUTS']['gEQDSK']"
    if 'reorder_ion_names' in PROFILES_GEN['SETTINGS']['PHYSICS']:
        PROFILES_GEN['SETTINGS']['PHYSICS']['reorder_ion_names'] = None
    task_action(PROFILES_GEN['SCRIPTS']['run_profiles_gen'])
    names = PROFILES_GEN['OUTPUTS']['input.gacode'].ion_names()
    printw('ION names:{}'.format(names))
    PROFILES_GEN['SETTINGS']['PHYSICS']['reorder_ion_names'] = names
    task_action(PROFILES_GEN['SCRIPTS']['reorder_ions'])

    # Ion inclusion/order follows the current PROFILES_GEN/TGYRO settings.
    # No implicit deletion of B, N, LUMPED ions or forced NS=3.

    root['tgyro_output'].clear()
    root['input.tglf'].clear()
    task_action(root['SCRIPTS']['setup_tglf'])
    root['SETTINGS']['PHYSICS']['rho_scan'] = rhos
    task_action(root['SCRIPTS']['Radial_scan'])

    for rho in rhos:
        root['Experimental_spectra_in_time'][rho][time] = copy.deepcopy(root['Experimental_spectra'][rho])

    # Clear outputs
    root['Experimental_fluxes'].clear()
    root['Experimental_spectra'].clear()
