# -*-Python-*-
# Created by smithsp at 07 May 2018  23:55

"""
This script calculates the inputs needed for the TGLF UQ scan at each radius
"""

import chaospy as cp

defaultVars(rho=root['SETTINGS']['PHYSICS']['rho'], params=None)

if rho is None:
    printe('Need value for rho, not None')
    OMFITx.End()

if params is None:
    if root['TGLF']['SETTINGS']['PHYSICS']['scanParameters'] is None:
        printe('Need list of scan parameters')
        OMFITx.End()
    params = root['TGLF']['SETTINGS']['PHYSICS']['scanParameters']

inputs = root.setdefault('UQ_inputs', OMFITcollection())
multi_win = root['SETTINGS']['PHYSICS']['multi_window_dist']

if multi_win:
    if 'MULTI' not in root or 'input.tglf' not in root['MULTI']:
        printe('Need MULTI and MULTI/input.tglf to run setup_UQ_inputs for multiwindow')
        OMFITx.End()
    input_win_data = []
else:
    input_dist = []
    input_dist_norm = []

print(
    'setup_UQ_inputs.py: type(params) = {}, isinstance(params, str) = {}, params = {}, tolist(params) = {}'.format(
        type(params), isinstance(params, str), params, tolist(params)
    )
)

params = tolist(params)
for paramN, param in enumerate(params):
    print('    paramN = {}, param = {}, multi_win = {}'.format(paramN, param, multi_win))
    if multi_win:
        tmp_var_list = []
        for k, in1 in root['MULTI']['input.tglf'].items():
            print('        k = {}, "mean" not in k = {}'.format(k, 'mean' not in k))
            if 'mean' not in k:
                tmp_var_list.append(in1[rho][param])
            else:
                mean_key = k
                print('        mean_key has been defined! mean_key = {}'.format(mean_key))
        input_win_data.append(tmp_var_list)
    else:
        input_dist.append(
            cp.Normal(
                mu=root['SETTINGS']['PHYSICS'][f'scanParameter{paramN}Mean'], sigma=root['SETTINGS']['PHYSICS'][f'scanParameter{paramN}Std']
            )
        )
        input_dist_norm.append(cp.Normal(mu=0.0, sigma=1.0))

pk = '_'.join(params) + ['', 'multi_win'][multi_win]

if pk in inputs and rho in inputs[pk] and 'rv' in inputs[pk][rho] and 'rv_proxy' in inputs[pk][rho]:
    rv = inputs[pk][rho]['rv']
    rv_proxy = inputs[pk][rho]['rv_proxy']

else:
    if multi_win:
        root['input.tglf'] = root['MULTI']['input.tglf'][mean_key]
        root['tgyro_output'] = root['MULTI']['tgyro_output'][mean_key]
        var_mean = np.mean(input_win_data, axis=1)
        if root['TGLF']['SETTINGS']['PHYSICS']['scanDimensions'] == 1:
            var_std = np.std(input_win_data, axis=1)
            rv = cp.Normal(mu=var_mean, sigma=var_std)
            rv_proxy = cp.Normal(mu=0, sigma=1)
        else:
            var_cov = np.cov(input_win_data, rowvar=1)
            if not np.all(np.linalg.eigvals(var_cov) > 0):
                printe('Not valid covariances; Turning off multi-window')
                root['SETTINGS']['PHYSICS']['multiWindowDist'] = False
                OMFITx.End()
            else:
                rv = cp.MvNormal(loc=var_mean, scale=var_cov)
                rv_proxy = cp.MvNormal(loc=var_mean * 0.0, scale=np.identity(len(var_mean)))

    else:
        rv = cp.J(*input_dist)  # Joint distribution
        rv_proxy = cp.J(*input_dist_norm)  # Normalized joint distribution (used for forward propagation of probs)

inputs.setdefault(pk, OMFITtree())
inputs[pk][rho] = root['TGLF']['INPUTS'] = OMFITtree()
root['TGLF']['INPUTS'].update({'rv': rv, 'rvprox': rv_proxy})
