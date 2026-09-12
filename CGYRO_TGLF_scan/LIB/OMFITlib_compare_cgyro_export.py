"""Export raw CGYRO spectra and provenance into a new directory for each action."""
from builtins import ValueError, len, print, repr, str
import hashlib
import json
from pathlib import Path
import re
import tempfile
import numpy as np
from OMFITlib_compare_cgyro_data import collect_value_series
from OMFITlib_compare_cgyro_selection import _iter_selected_parameter_items


def _safe_text_token(value):
    return re.sub(r'[^A-Za-z0-9_.-]+', '_', str(value))[:64]


def _export_linear_omega_gamma_vs_ky(ctx, nr, para, value, ky, omega, gamma,
                                     omega_error, gamma_error, omega_std, gamma_std, export_dir):
    arrays = [np.asarray(column).ravel() for column in
              (ky, omega, gamma, omega_error, gamma_error, omega_std, gamma_std)]
    if not len(ky):
        return None
    if len({len(column) for column in arrays}) != 1:
        raise ValueError('Spectrum columns have inconsistent lengths')
    identity = hashlib.sha256(repr((nr, para, value)).encode('utf-8')).hexdigest()[:12]
    filename = 'omega_gamma_vs_ky__{}__{}__{}_{}_{}.txt'.format(
        _safe_text_token(ctx.get('runid', '')), _safe_text_token(nr),
        _safe_text_token(para), _safe_text_token(value), identity)
    path = Path(export_dir) / filename
    matrix = np.column_stack(arrays)
    matrix = matrix[np.argsort(matrix[:, 0], kind='stable')]
    header = '\n'.join([
        'CGYRO_vs_CGYRO raw linear spectrum',
        'runid={!r}; nr={!r}; parameter={!r}; value={!r}'.format(ctx.get('runid'), nr, para, value),
        'normalize_main_ion={}; tail_fraction={}'.format(ctx.get('normalize_main_ion', False), ctx['ave_window']),
        'native units: ky=k_y*rho_s; omega/gamma=c_s/a',
        'main-ion option: ky *= sqrt(MASS)/Z; frequency/std *= sqrt(MASS), with the existing input species convention',
        'Raw signed means before display /ky or /ky^2; std is population std, not standard error',
        'ky omega gamma omega_rel_err gamma_rel_err omega_std gamma_std',
    ])
    with path.open('x', encoding='utf-8') as stream:
        np.savetxt(stream, matrix, fmt='%.12e', header=header)
    return str(path)


def export_selected_linear_spectra(root, ctx):
    target = str(ctx.get('export_linear_dir', '')).strip()
    if not target:
        raise ValueError('Choose an export directory')
    spectra = []
    for nr in ctx['nr_CGYRO']:
        for para, values in _iter_selected_parameter_items(ctx, nr):
            for value in values:
                series = collect_value_series(root, ctx, nr, para, value)
                if len(series[0]):
                    spectra.append((nr, para, value, series))
    if not spectra:
        raise ValueError('No valid selected CGYRO spectra to export. ' + '\n'.join(ctx['_diagnostics'][:5]))
    parent = Path(target).expanduser()
    parent.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix='cgyro_spectra_', dir=str(parent)))
    files = []
    for nr, para, value, series in spectra:
        output = _export_linear_omega_gamma_vs_ky(ctx, nr, para, value, *series, directory)
        files.append({'file': Path(output).name, 'nr': str(nr), 'parameter': str(para), 'value': str(value)})
    metadata = {
        'format': 1, 'workflow': 'CGYRO_vs_CGYRO', 'runid': str(ctx['runid']),
        'normalization': 'main-ion' if ctx['normalize_main_ion'] else 'native saved units',
        'values': 'signed omega/gamma before display /ky or /ky^2 scaling',
        'std': 'population standard deviation; relative std = std / absolute mean',
        'averaging_fraction': ctx['ave_window'], 'error_filter': ctx['error_filter'],
        'error_tolerance': ctx['error_tolerance'], 'abs_ky': ctx['abs_ky'],
        'diagnostics': ctx['_diagnostics'], 'spectra': files,
    }
    with (directory / 'metadata.json').open('x', encoding='utf-8') as stream:
        json.dump(metadata, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    with (directory / ('omega_gamma_vs_ky_manifest__runid_' + _safe_text_token(ctx['runid']) + '.txt')).open('x', encoding='utf-8') as stream:
        stream.write('# Exported omega/gamma vs ky files\n')
        stream.writelines(item['file'] + '\n' for item in files)
    print('Exported {} CGYRO spectra to {}'.format(len(files), directory))
    return str(directory)
