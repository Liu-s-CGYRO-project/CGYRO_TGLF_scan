# -*-Python-*-
# Modified by pvaezi at 2018/01/11 10:01
# Original script by meneghini

import chaospy as cp

defaultVars(
    param=root['SETTINGS']['PHYSICS']['scanParameters'],
    rv=root['INPUTS'].get('rv', None),
    nosamples=root['SETTINGS']['PHYSICS']['scanParameterSamples'],
    samplingmethod=root['SETTINGS']['PHYSICS']['inputParameterSamplingMethod'],
    inputTGLF=root.get('FILES', {}).get('input.tglf', None),
    results='UQResults',
    results_spectra='UQResults_spectra',
    include_starting_param=True,
)

if inputTGLF is None:
    raise ValueError('Need an input.tglf file to run a TGLF scan')

# setup simple distributions
if rv is None:
    if root['SETTINGS']['PHYSICS'].get('multiWindowDist', False):
        raise OMFITexception('Must provide rv before calling runTGLFUQscan')
    input_dist = []
    input_dist_norm = []
    for parami, p in enumerate(param, 1):
        input_dist.append(
            cp.Normal(
                mu=root['SETTINGS']['PHYSICS'].get('scanParameter' + str(parami) + 'Mean', inputTGLF[p]),
                sigma=root['SETTINGS']['PHYSICS'].get('scanParameter' + str(parami) + 'Std', inputTGLF[p] * 0.1),
            )
        )
        input_dist_norm.append(cp.Normal(mu=0.0, sigma=1.0))
    rv = cp.J(*input_dist)  # Joint distribution
    rv_proxy = cp.J(*input_dist_norm)  # Normalized joint distribution (used for forward propagation of probs)


# sampling from joint input distribution
parameterRange = rv.sample(nosamples, samplingmethod)
if parameterRange.ndim == 1:
    parameterRange = np.array([np.unique(np.concatenate((parameterRange, np.array([cp.E(rv)])), axis=0))])
else:
    parameterRange = np.concatenate((parameterRange, np.transpose(np.array([cp.E(rv)]))), axis=1)
parameterRange = parameterRange[:, parameterRange[0, :].argsort()]
root['SETTINGS']['PHYSICS']['UQInputSamples'] = parameterRange

# setup the directory structure
if isinstance(results, str):
    results_spectra = results + '_spectra'
    if results not in root:
        root[results] = OMFITtree()
    results = root[results]
if '_'.join(param) not in results:
    results['_'.join(param)] = OMFITtree()
print('_'.join(param))

# setup the directory structure
if isinstance(results_spectra, str):
    if results_spectra not in root:
        root[results_spectra] = OMFITtree()
    results_spectra = root[results_spectra]
if '_'.join(param) not in results_spectra:
    results_spectra['_'.join(param)] = OMFITtree()

# A new sample set/distribution must never mix with an earlier UQ result.
results['_'.join(param)] = OMFITtree()
results_spectra['_'.join(param)] = OMFITtree()
cache = root['LIB']['OMFITlib_tglf_cache'].runNoGUI()
root.setdefault('_scan_cache_provenance', {})['UQResults'] = cache['provenance'](
    root, inputTGLF, 'UQ', {'parameters': param, 'samples': parameterRange})

# generate list of inputs
scratch['input.tglf.scan'] = []
valuesToRun = []
for k in range(len(parameterRange[0])):
    valuesToRun.append('_'.join(parameterRange[:, k].astype(str)))
    tmpTGLF = copy.deepcopy(inputTGLF)
    for i in range(len(param)):
        tmpTGLF[param[i]] = parameterRange[i][k]
        if (param[i].startswith('RLTS_') or param[i].startswith('TAUS_')) and root['SETTINGS']['PHYSICS']['single_Ti']:
            for spec in range(1, inputTGLF['NS'] + 1):
                if tmpTGLF['ZS_%d' % spec] != -1 and inputTGLF['%s%d' % (param[i][:5], spec)] == inputTGLF[param[i]]:
                    tmpTGLF['%s%d' % (param[i][:5], spec)] = parameterRange[i][k]
    scratch['input.tglf.scan'].append(tmpTGLF)

# parallel run
tmp = root['SCRIPTS']['runTGLF'].prun(
    len(scratch['input.tglf.scan']), root['SETTINGS']['PHYSICS']['parallelScan'], 'result', inputTGLF=scratch['input.tglf.scan']
)
# assemble results
for k, value in enumerate(valuesToRun):
    try:
        if tmp[k]['gbflux']['data'][0][0] == 'elec':
            results['_'.join(param)]['_'.join(parameterRange[:, k].astype(str))] = tmp[k]['gbflux']['data']
            results_spectra['_'.join(param)]['_'.join(parameterRange[:, k].astype(str))] = tmp[k]
    except Exception as _excp:
        printe('TGLF scan failed for ' + ('_'.join(param)) + '=' + ('_'.join(parameterRange[:, k].astype(str))) + ' : ' + repr(_excp))
results['_'.join(param)].sort(key=str)
