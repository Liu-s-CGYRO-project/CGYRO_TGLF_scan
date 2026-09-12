# -*-Python-*-
# Created by sciortinof at 16 Jul 2019  16:33

"""
This script is used to launch scans of TGLF inputs to test sensitivity of D,V and V/D radial profiles.

Quantities to scan are indicated via the "variables_to_scan" dictionary, which by default is built through
the 'quantities_selection_GUI', used in 'DV_scans_gui'.
"""
defaultVars(
    variables_to_scan=root['TGLF_inputs_to_scan'],
    runs_label=root['SETTINGS']['PHYSICS']['runs_label'],
    frac_change=0.1,  # fractional change, only for debugging, it shouldn't make any difference!
)


from scipy.constants import e, m_p
import OMFITlib_tglf

# Set up results tree within the database structure
data_label = 'D_and_v_' + runs_label
root.setdefault('TGLF_SCAN_DB', OMFITtree())
root['TGLF_SCAN_DB'].setdefault(data_label, OMFITtree())

data_root = root['TGLF_SCAN_DB'][data_label]
run_root = root['TGLF_SCAN_DB'][runs_label]

# deal with possible floating-point precision issues...
kkeys = np.array(root['input.tglf'].keys())
rhoList = [kkeys[np.argmin(np.abs(kkeys - rho))] for rho in run_root['rhoList']]
run_root['rhoList'] = rhoList

# correct possible rounding issues of Python lists-to-array conversions
# run_root['rhoList'] = [round(r,3) for r in  run_root['rhoList']]
# rhoList = run_root['rhoList']

# save settings used for the run, so that this can be reloaded later on
data_root['PHYSICS_SETTINGS'] = copy.deepcopy(root['SETTINGS']['PHYSICS'])

# Get variables to scan and recognize 'groups' of TGLF inputs that should be scanned together
var_group_dict = OMFITlib_tglf.TGLF_var_group_scan(variables_to_scan.keys(), root['input.tglf'][rhoList[0]])
data_root['scan_vars'] = variables_to_scan.keys()

# Get original copy
root['input.tglf.original'] = copy.deepcopy(root['input.tglf'])

# Reset scans first
root['scanResults'].clear()

# ==== Run ====
# Run baseline
tmp_name = 'DVscan_baseline'  # name of OMFIT Tree where results are stored

if root['SETTINGS']['PHYSICS']['transport_matrix_method']:
    # use matrix inversion method
    root['SCRIPTS']['resp_matrix'].run(frac_change=frac_change, runs_label=tmp_name, rhoList=rhoList)
    # Obtain and store results using the plot_resp_matrix.py script (but don't plot now)
    root['PLOTS']['plot_resp_matrix'].run(runs_label=tmp_name, plot_results=False)
else:
    # scan gradients with separate TGLF runs
    root['SCRIPTS']['particleDandVscan'].run(runs_label=tmp_name)
    root['SCRIPTS']['particleDandVprofile'].run(runs_label=tmp_name)

# ============
# save sensitivity results in tmp_name dictionary and delete temporary tree. No need to save settings from temporary runs
fields_to_copy = {x: root['TGLF_SCAN_DB'][tmp_name][x] for x in root['TGLF_SCAN_DB'][tmp_name] if x not in ['PHYSICS_SETTINGS']}
for field in fields_to_copy.keys():
    data_root[field] = OrderedDict()
    data_root[field]['baseline'] = root['TGLF_SCAN_DB'][tmp_name][field]
del root['TGLF_SCAN_DB'][tmp_name]

# ============


for var_cnt, var_name in enumerate(variables_to_scan.keys()):
    for scan_dir in ['up', 'down']:

        rel_ch = np.abs(root['SETTINGS']['PHYSICS']['RelativeChange_%s_list' % var_name])
        percent_list = -rel_ch if scan_dir == 'down' else rel_ch

        # Reset scan results first
        root['scanResults'].clear()

        for ii, rad in enumerate(rhoList):  # change variable at every requested radius
            local_group = OMFITlib_tglf.TGLF_var_group_scan([var_name], root['input.tglf'][rad])
            for single_var in local_group[var_name]:

                root['input.tglf'][rad][single_var] = root['input.tglf'][rad][single_var] * (1 + percent_list[ii])

        # ==== Run ====
        tmp_name = 'DVscan_%s_%s' % (var_name, scan_dir)  # name of OMFIT Tree where results are temporarily stored

        if root['SETTINGS']['PHYSICS']['transport_matrix_method']:
            # use matrix inversion method
            root['SCRIPTS']['resp_matrix'].run(frac_change=frac_change, runs_label=tmp_name, rhoList=rhoList)
            # Obtain and store results using the plot_resp_matrix.py script (but don't plot yet)
            root['PLOTS']['plot_resp_matrix'].run(runs_label=tmp_name, plot_results=False)
        else:
            # scan gradients with separate TGLF runs
            root['SCRIPTS']['particleDandVscan'].run(runs_label=tmp_name)
            root['SCRIPTS']['particleDandVprofile'].run(runs_label=tmp_name)

        # ===========

        # save sensitivity results in tmp_name dictionary and delete temporary tree
        for field in fields_to_copy.keys():
            data_root[field]['{}_{}'.format(var_name, scan_dir)] = root['TGLF_SCAN_DB'][tmp_name][field]
        del root['TGLF_SCAN_DB'][tmp_name]

        # ============

        # set input.tglf back to its original values
        del root['input.tglf']
        root['input.tglf'] = copy.deepcopy(root['input.tglf.original'])
