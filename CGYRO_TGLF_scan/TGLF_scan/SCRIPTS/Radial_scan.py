# -*-Python-*-
# Created by thomek at 15 Jun 2016  09:47
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
        if rho in flx and rho in spec and cache['matches'](records.get(rho), current[rho]):
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
root['TGLF']['SCRIPTS']['runTGLFbatch'].run(inputTGLF=input_tglf, runIDs=rho_scan, results=results, enforce_constraints=False)
for k, rho in enumerate(rho_scan):
    try:
        if results[rho]['gbflux']['data'][0][0] == 'elec':
            flx[rho] = results[rho]['gbflux']
            spec[rho] = results[rho]
            records[rho] = current[rho]
    except Exception as _excp:
        printe('TGLF radial scan failed for radius=%s' % rho)

flx.sort()
spec.sort()
