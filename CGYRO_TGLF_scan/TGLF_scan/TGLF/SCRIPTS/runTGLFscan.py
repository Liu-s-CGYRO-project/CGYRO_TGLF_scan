# -*-Python-*-
# Created by meneghini at 2013/03/08 18:01
"""Compute one scan axis and retain completed points if the batch fails."""
from OMFITlib_gui_api import task_action
from builtins import enumerate, float, isinstance, len, list, range, repr, sorted, str
import copy

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

result_branch = results + '_spectra' if isinstance(results, str) else None

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
if result_branch and not cache['matches'](cache_records.get(param, None), current):
    cache['forget_workbench'](root, (result_branch, param))
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

# A batch may fail after returning some good points (or be interrupted during a
# later wave). Archive those points before propagating the original exception.
# They remain available for inspection and, with proven provenance, resumption.
tmp = OMFITtree()
batch_error = None
try:
    task_action(root['SCRIPTS']['runTGLFbatch'],
        inputTGLF=scratch['input.tglf.scan'], results=tmp,
        enforce_constraints=True, continue_on_error=True)
except BaseException as exc:
    batch_error = exc

failures = []
for k, value in enumerate(valuesToRun):
    try:
        point = tmp.get(k, None)
        data = cache['flux_data'](point)
        results[param][value] = data
        results_spectra[param][value] = point
        if result_branch:
            cache['forget_workbench'](root, (result_branch, param, value))
    except Exception as _excp:
        failures.append(value)
        printe('TGLF scan failed for %s=%f : %s' % (param, value, repr(_excp)))
results[param].sort(key=float)
results_spectra[param].sort(key=float)
if batch_error is not None:
    raise batch_error
if failures:
    raise RuntimeError('TGLF scan {}: {} / {} points failed; completed results were retained'.format(
        param, len(failures), len(valuesToRun)))
