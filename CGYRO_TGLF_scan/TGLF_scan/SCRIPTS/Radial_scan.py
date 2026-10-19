# -*-Python-*-
# Created by thomek at 15 Jun 2016  09:47
"""Archive each successful radius even if a later radius fails or is stopped."""
from builtins import enumerate, len, str
import copy
flx = root.setdefault('Experimental_fluxes', OMFITcollection())
spec = root.setdefault('Experimental_spectra', OMFITcollection())
rho_scan = root['SETTINGS']['PHYSICS']['rho_scan']
recalculate = root['SETTINGS']['PHYSICS'].setdefault('recalculate', False)
cache = root['TGLF']['LIB']['OMFITlib_tglf_cache'].runNoGUI()
records = root.setdefault('_radial_cache_provenance', {})
current = {rho: cache['provenance'](root['TGLF'], root['input.tglf'][rho], 'radial', {'rho': rho}) for rho in rho_scan}
if not recalculate:
    rho_needed = []
    for rho in rho_scan:
        if rho in flx and rho in spec and cache['matches'](records.get(rho, None), current[rho]):
            printi('Experimental fluxes and spectra already calculated for %s' % rho)
            continue
        rho_needed.append(rho)
    rho_scan = rho_needed
# Remove stale pairs before submission; a failed new run cannot leave old data labelled current.
for rho in rho_scan:
    for collection in (flx, spec, records):
        collection.pop(rho, None)
input_tglf = [copy.deepcopy(root['input.tglf'][rho]) for rho in rho_scan]
if len(input_tglf) == 0:
    print('All results already calculated.')
    OMFITx.End()
results = OMFITtree()
batch_error = None
try:
    root['TGLF']['SCRIPTS']['runTGLFbatch'].run(
        inputTGLF=input_tglf, runIDs=rho_scan, results=results,
        enforce_constraints=False, continue_on_error=True)
except BaseException as exc:
    batch_error = exc
failures = []
# Collection is independent of submission status: a failed batch can still
# contain usable radii. Publish each result/provenance pair only after validation.
for k, rho in enumerate(rho_scan):
    try:
        point = results.get(rho, None)
        cache['flux_data'](point)
        flx[rho] = point['gbflux']
        spec[rho] = point
        records[rho] = current[rho]
    except Exception as _excp:
        failures.append(rho)
        printe('TGLF radial scan failed for radius=%s: %s' % (rho, str(_excp)))

flx.sort()
spec.sort()
if batch_error is not None:
    raise batch_error
if failures:
    raise RuntimeError('TGLF radial scan: {} / {} radii failed; completed results were retained'.format(
        len(failures), len(rho_scan)))
