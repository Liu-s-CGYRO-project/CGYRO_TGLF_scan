# -*-Python-*-
print('Resetting all TGLF variables scans')
for key in ('FILES', 'scanResults', 'scanResults_spectra', 'scanResults2D', 'scanResults2D_spectra',
            'scanResults3D', 'scanResults3D_spectra', 'UQResults', 'UQResults_spectra',
            '_scan_cache_provenance', '_workbench_index'):
    root.pop(key, None)
root['FILES'] = OMFITtree()
