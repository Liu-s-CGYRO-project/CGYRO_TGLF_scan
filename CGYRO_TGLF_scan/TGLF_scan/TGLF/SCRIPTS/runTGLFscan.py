# -*-Python-*-
# Created by meneghini at 2013/03/08 18:01

defaultVars(
    param=root['SETTINGS']['PHYSICS']['scanParameter'],
    parameterRange=root['SETTINGS']['PHYSICS']['scanParameterRange'],
    inputTGLF=root.get('FILES', {}).get('input.tglf', None),
    results='scanResults',
    results_spectra='scanResults_spectra',
    include_starting_param=True,
    cache_records=None,
)

if inputTGLF is None:
    raise ValueError('Need an input.tglf file to run a TGLF scan')

# Provenance is kept outside numeric result keys used by plotting code.
cache = root['LIB']['OMFITlib_tglf_cache'].runNoGUI()
if cache_records is None:
    cache_records = root.setdefault('_scan_cache_provenance', {}).setdefault(results, {}) if isinstance(results, str) else {}

# setup the directory structure
if isinstance(results, str):
    results_spectra = results + '_spectra'
    if results not in root:
        root[results] = OMFITtree()
    results = root[results]
if param not in results:
    results[param] = OMFITtree()

if include_starting_param:
    val = inputTGLF[param]
    if val not in parameterRange:
        parameterRange = sorted(list(parameterRange) + [val])

# setup the directory structure
if isinstance(results_spectra, str):
    if results_spectra not in root:
        root[results_spectra] = OMFITtree()
    results_spectra = root[results_spectra]
if param not in results_spectra:
    results_spectra[param] = OMFITtree()

current = cache['provenance'](root, inputTGLF, '1D', {'param': param, 'range': parameterRange})
cache['prepare'](results, results_spectra, param, cache_records, current, OMFITtree)

# generate list of inputs
scratch['input.tglf.scan'] = []
valuesToRun = []
for k, value in enumerate(parameterRange):
    if value in results[param] and value in results_spectra[param]:
        print('Skipping %s=%s, because it was already computed' % (param, value))
        continue
    valuesToRun.append(value)
    tmpTGLF = copy.deepcopy(inputTGLF)
    tmpTGLF[param] = value
    if (param.startswith('RLTS_') or param.startswith('TAUS_')) and root['SETTINGS']['PHYSICS']['single_Ti']:
        for spec in range(1, inputTGLF['NS'] + 1):
            if tmpTGLF['ZS_%d' % spec] != -1 and inputTGLF['%s%d' % (param[:5], spec)] == inputTGLF[param]:
                tmpTGLF['%s%d' % (param[:5], spec)] = value
    scratch['input.tglf.scan'].append(tmpTGLF)

if len(scratch['input.tglf.scan']) == 0:
    print('All TGLF results already exist')
    OMFITx.End()

# parallel run
tmp = OMFITtree()
root['SCRIPTS']['runTGLFbatch'].run(inputTGLF=scratch['input.tglf.scan'], results=tmp, enforce_constraints=True)

# assemble results
for k, value in enumerate(valuesToRun):
    try:
        if tmp[k]['gbflux']['data'][0][0] == 'elec':
            results[param][value] = tmp[k]['gbflux']['data']
            results_spectra[param][value] = tmp[k]
    except Exception as _excp:
        printe('TGLF scan failed for %s=%f : %s' % (param, value, repr(_excp)))
results[param].sort(key=float)
