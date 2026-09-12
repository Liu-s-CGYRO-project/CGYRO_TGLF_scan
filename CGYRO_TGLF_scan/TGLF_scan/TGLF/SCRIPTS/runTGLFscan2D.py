# -*-Python-*-
# Created by meneghini at 2015/03/28 13:56

defaultVars(
    param=root['SETTINGS']['PHYSICS']['scanParameter'],
    param2=root['SETTINGS']['PHYSICS']['scanParameter2D'],
    parameterRange2=root['SETTINGS']['PHYSICS']['scanParameter2DRange'],
    parameterRange=root['SETTINGS']['PHYSICS']['scanParameterRange'],
    inputTGLF=root['FILES']['input.tglf'],
    results='scanResults2D',
    results_spectra='scanResults2D_spectra',
    include_starting_param=True,
    cache_records=None,
)

if param2 == param:
    printe('Param1 = param2 -> change one of them')
    OMFITx.End()

cache = root['LIB']['OMFITlib_tglf_cache'].runNoGUI()
if cache_records is None:
    cache_records = root.setdefault('_scan_cache_provenance', {}).setdefault(results, {}) if isinstance(results, str) else {}

if isinstance(results, str):
    results_spectra = results + '_spectra'
    results = root.setdefault(results, OMFITtree())
if isinstance(results_spectra, str):
    results_spectra = root.setdefault(results_spectra, OMFITtree())

results.setdefault(param2 + '+' + param, OMFITtree())
results_spectra.setdefault(param2 + '+' + param, OMFITtree())
if include_starting_param:
    val2 = inputTGLF[param2]
    if val2 not in parameterRange2:
        parameterRange2 = sorted(list(parameterRange2) + [val2])
    val1 = inputTGLF[param]
    if val1 not in parameterRange:
        parameterRange = sorted(list(parameterRange) + [val1])
cache_key = param2 + '+' + param
current = cache['provenance'](root, inputTGLF, '2D', {'param': param, 'param2': param2, 'range': parameterRange, 'range2': parameterRange2})
if not cache['matches'](cache_records.get(cache_key), current):
    cache_records[cache_key + '_rows'] = {}
cache['prepare'](results, results_spectra, cache_key, cache_records, current, OMFITtree)
row_records = cache_records.setdefault(cache_key + '_rows', {})
tmpTGLF = copy.deepcopy(inputTGLF)
key2 = list(results[param2 + '+' + param].keys())
parameterRange2 = sorted(list(set(list(parameterRange2) + key2)))
if key2:
    parameterRange = sorted(list(set(list(parameterRange) + list(results[param2 + '+' + param][key2[0]].keys()))))


for i, value in enumerate(parameterRange2):
    tmpTGLF[param2] = value

    print('Scan %d of %d,  %s = %.3g' % (i + 1, len(parameterRange2), param2, value))
    if (param2.startswith('RLTS_') or param2.startswith('TAUS_')) and root['SETTINGS']['PHYSICS']['single_Ti']:
        for spec in range(1, inputTGLF['NS'] + 1):
            key = '%s%d' % (param2[:5], spec)
            if tmpTGLF['ZS_%d' % spec] != -1 and inputTGLF[key] == inputTGLF[param2] and key != param2:
                print('Modifying %s to be %g, was %g' % (key, value, tmpTGLF[key]))
                tmpTGLF[key] = value
    scratch['tmp1Dscan'] = OMFITtree()
    scratch['tmp1Dscan_spectra'] = OMFITtree()
    if value in results['%s+%s' % (param2, param)]:
        scratch['tmp1Dscan'][param] = copy.deepcopy(results[param2 + '+' + param][value])
        scratch['tmp1Dscan_spectra'][param] = copy.deepcopy(results_spectra[param2 + '+' + param][value])
    root['SCRIPTS']['runTGLFscan'].run(
        inputTGLF=tmpTGLF,
        results=scratch['tmp1Dscan'],
        results_spectra=scratch['tmp1Dscan_spectra'],
        include_starting_param=include_starting_param,
        param=param,
        parameterRange=parameterRange,
        cache_records=row_records.setdefault(value, {}),
    )
    print(param2 + '+' + param, param in scratch['tmp1Dscan'])
    results[param2 + '+' + param][value] = scratch['tmp1Dscan'].pop(param)
    results_spectra[param2 + '+' + param][value] = scratch['tmp1Dscan_spectra'].pop(param)
results[param2 + '+' + param].sort(key=float)
results_spectra[param2 + '+' + param].sort(key=float)
