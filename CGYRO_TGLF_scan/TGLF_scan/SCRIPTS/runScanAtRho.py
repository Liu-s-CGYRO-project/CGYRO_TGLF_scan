# -*-Python-*-
# Created by lugaimin at 2014/06/12 15:01

from OMFITlib_gui_api import task_action
from builtins import list
import copy

rho = root['SETTINGS']['PHYSICS']['rho']
dimension = root['SETTINGS']['PHYSICS']['scanDimensions']
scanResults, script = {
    1: ('scanResults', 'runTGLFscan'),
    2: ('scanResults2D', 'runTGLFscan2D'),
    'UQ': ('UQResults', 'runTGLFUQscan'),
}[dimension]
if dimension == 'UQ':
    task_action(root['SCRIPTS']['setup_UQ_inputs'])
scanResults_spectra = scanResults + '_spectra'

# The child module's FILES, result branches and provenance belong to its
# single-file calculation. Pass this radius's own mappings directly so partial
# successes are retained even when a later scan point raises an exception.
radial_input = copy.deepcopy(root['input.tglf'][rho])
results = root.setdefault(scanResults, OMFITtree()).setdefault(rho, OMFITtree())
spectra = root.setdefault(scanResults_spectra, OMFITtree()).setdefault(rho, OMFITtree())
radial_provenance = root.setdefault('_scan_cache_provenance', {}).setdefault(rho, {})
cache_records = radial_provenance if dimension == 'UQ' else radial_provenance.setdefault(scanResults, {})
physics = root['TGLF']['SETTINGS']['PHYSICS']
group = ('_'.join(physics['scanParameters']) if dimension == 'UQ' else
         physics['scanParameter2D'] + '+' + physics['scanParameter'] if dimension == 2 else
         physics['scanParameter'])
previous = (results.get(group, None), spectra.get(group, None))

try:
    task_action(root['TGLF']['SCRIPTS'][script],
        inputTGLF=radial_input, results=results, results_spectra=spectra, cache_records=cache_records)
finally:
    if results.get(group, None) is not previous[0] or spectra.get(group, None) is not previous[1]:
        index = root.get('_workbench_index', {})
        for path in list(index):
            if path[:3] == (scanResults_spectra, rho, group):
                del index[path]
printi('Scan is finished')
