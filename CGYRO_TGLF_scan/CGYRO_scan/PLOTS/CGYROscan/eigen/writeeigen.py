# Export the selected native ballooning eigenfunctions; do not invent missing fields.
import os
import tempfile
import numpy as np
from OMFITlib_cgyro_read import num2str_xj
settings = root['SETTINGS']
selection = settings['PLOTS']['1d']
effnum = settings['SETUP']['effnum']
destination = settings['DEPENDENCIES'].get('eigenout', None)
if not destination:
    destination = tempfile.mkdtemp(prefix='cgyro-eigen-export-', dir=str(OMFITworkDir(root, '')))
else:
    os.makedirs(destination, exist_ok=True)
for parameter in selection['para_eigen']:
    for ky in settings['PLOTS']['ky_eigen']:
        case = root['OUTPUTScan'][selection['Para']][num2str_xj(parameter, effnum)]['lin'][num2str_xj(ky, effnum)]
        balloon = case['balloon']
        theta_key = 'theta_b_over_pi'
        columns = [np.asarray(balloon[theta_key])]
        names = [theta_key]
        for field in ('balloon_phi', 'balloon_apar', 'balloon_bpar'):
            if field not in balloon:
                continue
            values = balloon[field]
            values = values.isel(t=-1) if hasattr(values, 'dims') else np.asarray(values)[:, -1]
            columns.extend([np.real(values), np.imag(values)])
            names.extend([field + '_real', field + '_imag'])
        if len(columns) == 1:
            raise ValueError('No balloon eigenfunctions in selected case')
        filename = selection['Para'] + '_' + num2str_xj(parameter, effnum) + '_ky_' + num2str_xj(ky, effnum) + '.csv'
        np.savetxt(os.path.join(destination, filename), np.column_stack(columns), delimiter=',', header=','.join(names), comments='')
print('Eigenfunctions exported to ' + destination)
