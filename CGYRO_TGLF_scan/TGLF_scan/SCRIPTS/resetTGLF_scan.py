# -*-Python-*-
# Created by meneghini at 2014/11/12 10:24

print('Resetting all TGLF_scan radial scans')

derived_keys = ('scanResults', 'scanResults_spectra', 'scanResults2D', 'scanResults2D_spectra',
                'UQResults', 'UQResults_spectra', 'Experimental_fluxes', 'Experimental_spectra', 'Experimental_spectra_in_time',
                '_scan_cache_provenance', '_radial_cache_provenance', '_input_cache_provenance')
for module in (root, root['TGLF']):
    for key in derived_keys:
        if key in module:
            del module[key]
root.setdefault('input.tglf', OMFITtree()).clear()
root.setdefault('tgyro_output', OMFITtree()).clear()

root['TGYRO']['SCRIPTS']['reset'].runNoGUI(soft=True)  # do not delete PROFILES_GEN
