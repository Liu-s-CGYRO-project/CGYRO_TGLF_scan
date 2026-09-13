# -*-Python-*-
# Created by lugaimin at 2014/06/12 15:01

rho = root['SETTINGS']['PHYSICS']['rho']
if root['SETTINGS']['PHYSICS']['scanDimensions'] == 1:
    scanResults = 'scanResults'
elif root['SETTINGS']['PHYSICS']['scanDimensions'] == 2:
    scanResults = 'scanResults2D'
elif root['SETTINGS']['PHYSICS']['scanDimensions'] == 'UQ':
    scanResults = 'UQResults'
    root['SCRIPTS']['setup_UQ_inputs'].run()
scanResults_spectra = scanResults + '_spectra'

# Pass a private radial input to the scan. FILES belongs to the single-file run.
radial_input = copy.deepcopy(root['input.tglf'][rho])

# initialize directory structure
root.setdefault(scanResults_spectra, OMFITtree())
if rho not in root.setdefault(scanResults, OMFITtree()):
    for scanName in [scanResults, scanResults_spectra]:
        root[scanName][rho] = OMFITtree()
        root['TGLF'][scanName] = OMFITtree()
else:
    for scanName in [scanResults, scanResults_spectra]:
        root['TGLF'][scanName] = copy.deepcopy(root[scanName][rho])

# Only the provenance saved with this radius may accompany its cached data.
radial_provenance = root.setdefault('_scan_cache_provenance', {})
root['TGLF']['_scan_cache_provenance'] = copy.deepcopy(radial_provenance.get(rho, {}))

# run 1D/2D/UQ TGLF scan
if root['SETTINGS']['PHYSICS']['scanDimensions'] == 1:
    root['TGLF']['SCRIPTS']['runTGLFscan'].run(inputTGLF=radial_input)
elif root['SETTINGS']['PHYSICS']['scanDimensions'] == 2:
    root['TGLF']['SCRIPTS']['runTGLFscan2D'].run(inputTGLF=radial_input)
elif root['SETTINGS']['PHYSICS']['scanDimensions'] == 'UQ':
    root['TGLF']['SCRIPTS']['runTGLFUQscan'].run(inputTGLF=radial_input)

# store solution at this radius
for scanName in [scanResults, scanResults_spectra]:
    root[scanName][rho] = root['TGLF'].pop(scanName)

radial_provenance[rho] = copy.deepcopy(root['TGLF'].get('_scan_cache_provenance', {}))
printi('Scan is finished')
