# -*-Python-*-
# Created by sciortinof at 16 Jul 2019  16:23

"""
This script scans TGLF inputs to obtain frequencies and growth rates for each set of parameters.
Use Main_GUI to orchestrate the scan.

Quantities to scan are indicated via the "variables_to_scan" dictionary, which by default is built through
the 'quantities_selection_GUI', used in 'DV_scans_gui'.

The NMODES argument sets the number of dominant/subdominant TGLF modes to be stored
for later plotting.
"""

defaultVars(variables_to_scan=root['TGLF_inputs_to_scan'], NMODES=2, SAT_RULE=1)

import OMFITlib_tglf

# Setup OMFIT trees
root.setdefault('TGLF_SCAN_DB', OMFITtree())
root['TGLF_SCAN_DB'].setdefault('scans', OMFITtree())
scans_root = root['TGLF_SCAN_DB']['scans']

# Get variables to scan and recognize 'groups' of TGLF inputs that should be scanned together

# Use variable-specific percent variation
percent_var = {}
for variable in variables_to_scan.keys():
    percent_var[variable] = root['SETTINGS']['PHYSICS']['RelativeChange_%s' % variable]

# If TGLF input is not available, use TGYRO to set up
if len(root['input.tglf']):
    # copy from the list of radial input files
    rho = root['SETTINGS']['PHYSICS']['Var_r']
    root['TGLF']['FILES']['input.tglf'] = copy.deepcopy(root['input.tglf'][rho])
else:
    # use TGYRO to set up input.gacode at all radii, and also in root['TGLF']['FILES']['input.tglf']
    root['SCRIPTS']['setup_tglf'].run()

# ----------------------------

var_group_dict = OMFITlib_tglf.TGLF_var_group_scan(variables_to_scan.keys(), root['TGLF']['FILES']['input.tglf'])

# set saturation rule and number of modes to be stored by TGLF directly in the original input.tglf
root['TGLF']['FILES']['input.tglf']['NMODES'] = NMODES
root['TGLF']['FILES']['input.tglf']['SAT_RULE'] = SAT_RULE

# store original input.tglf and modify a modified version over iterations
scans_root['input.tglf_orig'] = copy.deepcopy(root['TGLF']['FILES']['input.tglf'])

# --------------------------------

for var_cnt, var_name in enumerate(
    variables_to_scan.keys()
):  # loop over groups of variables to be scanned -- this could be done with prun, but it doesn't take long anyway

    # ==== go UP by given percentage: ====
    # modify variable and run TGLF
    for var in var_group_dict[var_name]:
        root['TGLF']['FILES']['input.tglf'][var] = root['TGLF']['FILES']['input.tglf'][var] * (1 + percent_var[var_name])
    root['TGLF']['SCRIPTS']['runTGLF'].run()

    # store result and reset TGLF FILES
    scans_root['TGLF_' + var_name + '_Up_FILES'] = copy.deepcopy(root['TGLF']['FILES'])
    root['TGLF']['FILES'].clear()

    # restore original input.tglf
    root['TGLF']['FILES']['input.tglf'] = copy.deepcopy(scans_root['input.tglf_orig'])

    # ==== go DOWN by given percentage: ====
    # modify variable and run TGLF
    for var in var_group_dict[var_name]:
        root['TGLF']['FILES']['input.tglf'][var] = root['TGLF']['FILES']['input.tglf'][var] * (1 - percent_var[var_name])
    root['TGLF']['SCRIPTS']['runTGLF'].run()

    # store result and reset TGLF FILES
    scans_root['TGLF_' + var_name + '_Down_FILES'] = copy.deepcopy(root['TGLF']['FILES'])
    root['TGLF']['FILES'].clear()

    # restore original input.tglf
    root['TGLF']['FILES']['input.tglf'] = copy.deepcopy(scans_root['input.tglf_orig'])


# Finally, run baseline
root['TGLF']['SCRIPTS']['runTGLF'].run()
scans_root['TGLF_baseline_FILES'] = copy.deepcopy(root['TGLF']['FILES'])
