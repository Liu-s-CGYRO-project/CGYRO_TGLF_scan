# -*-Python-*-
# Created by smithsp at 2013/11/06 14:32

# create multi subwindow data subtree
root['MULTI'] = OMFITtree()

# set up variables for prun
prerun = '''
root['tgyro_output'].clear()
root['input.tglf'].clear()
root['TGYRO']['PROFILES_GEN']['OUTPUTS'] = copy.deepcopy(root['TGYRO']['PROFILES_GEN']['MULTI'][kkk])
'''
postrun = '''
tgyro_output = root['tgyro_output']
input_tglf = root['input.tglf']
'''
window_keys = list(root['TGYRO']['PROFILES_GEN']['MULTI'].keys())

nsimultaneous = 1
if is_server('iris', SERVER[root['SETTINGS']['REMOTE_SETUP']['serverPicker']]['server']):
    nsimultaneous = len(window_keys)
results = root['SCRIPTS']['setup_tglf'].prun(
    len(window_keys),
    nsimultaneous,
    ['tgyro_output', 'input_tglf'],
    result_type=OMFITcollection,
    prerun=prerun,
    postrun=postrun,
    kkk=window_keys,
    runIDs=window_keys,
)

# extract results from prun
root['MULTI']['tgyro_output'] = results['tgyro_output']
root['MULTI']['input.tglf'] = results['input_tglf']
root['tgyro_output'] = list(results['tgyro_output'].values())[0]
root['input.tglf'] = list(results['input_tglf'].values())[0]

# Set up initial input.tglf
rho = root['SETTINGS']['PHYSICS']['rho']
if rho in root['input.tglf'] and not root['TGLF'].get('FILES', None):
    root['TGLF']['FILES'] = OMFITtree({'input.tglf': copy.deepcopy(root['input.tglf'][rho])})
