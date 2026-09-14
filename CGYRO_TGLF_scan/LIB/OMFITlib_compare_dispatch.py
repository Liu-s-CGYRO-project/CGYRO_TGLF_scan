"""Validate, collect comparison pages, then render or export through OMFIT."""

# OMFIT libraries inherit a pylab namespace; keep Python scalar/iterator semantics.
from builtins import (
    RuntimeWarning,
    ValueError,
    any,
    dict,
    hasattr,
    len,
    list,
    map,
    print,
    str,
)
import csv
import json
from pathlib import (
    Path,
)
import tempfile
import warnings
import numpy as np
from OMFITlib_compare_core import (
    build_context,
)
from OMFITlib_compare_series import (
    collect_cgyro_curves,
    collect_tglf_curves,
    read_settings,
)
from OMFITlib_compare_spectra import (
    _plot_compare_page,
)
from OMFITlib_compare_status import (
    plot_cgyro_output_status,
)
from OMFITlib_compare_tglf import (
    plot_tglf_vs_tglf,
)
from OMFITlib_compare_state import (
    selection_check,
)


def collect_comparison_pages(root, ctx):
    """One collection path for plotting and CSV export; no figure creation."""
    mode = ctx['compare_mode']
    if mode == 'TGLF_vs_TGLF':
        state = ctx['tglf_state']
        key = 'selected_paras_2d' if state.get('spectra_mode', None) == '2D' else 'selected_paras'
        for rho in state.get('rho_selected', []):
            curves = []
            for number in (1, 2):
                curves.extend(collect_tglf_curves(rho, state.get(key, {}), root, ctx, mode_idx=number))
            yield 'rho={}'.format(rho), [], curves
        return
    pairs, selected_tg, selected_cg, runid = read_settings(root, ctx, mode)
    runs = root.get('CGYRO_scan', {}).get('RUN_DB', {})
    for anchor, paired in pairs.items():
        cgyro = []
        if mode == 'CGYRO_vs_TGLF':
            cgyro = collect_cgyro_curves(anchor, paired, runid, runs, selected_cg, root, ctx)
            tglf = collect_tglf_curves(paired, selected_tg, root, ctx)
            title = '{} / {} ↔ TGLF rho={}'.format(runid, anchor, ', '.join(map(str, paired)))
        else:
            for nr in paired:
                cgyro.extend(collect_cgyro_curves(nr, anchor, runid, runs, selected_cg, root, ctx))
            tglf = collect_tglf_curves(anchor, selected_tg, root, ctx)
            title = 'TGLF rho={} ↔ {} / {}'.format(anchor, runid, ', '.join(map(str, paired)))
        yield title, cgyro, tglf


def export_comparison(root, ctx, pages):
    """CSV plus settings in a new folder; existing exports cannot be overwritten."""
    parent = Path(ctx['mode_state'].get('linear_export_dir', '')).expanduser()
    if not str(ctx['mode_state'].get('linear_export_dir', '')).strip() or not parent.is_dir():
        raise ValueError('Choose an existing export folder.')
    if not any(cg or tg for _, cg, tg in pages):
        raise ValueError('No valid selected spectra to export.')
    directory = Path(tempfile.mkdtemp(prefix='comparison_spectra_', dir=str(parent)))
    with (directory/'spectra.csv').open('x', newline='', encoding='utf-8-sig') as stream:
        writer = csv.writer(stream)
        writer.writerow(['page', 'model', 'curve', 'nr', 'rho', 'parameter', 'scan_value',
                         'ky', 'omega', 'gamma', 'omega_relative_std', 'gamma_relative_std'])
        for title, cg, tg in pages:
            for curve in cg + tg:
                for i in np.argsort(curve['ky']):
                    error = [curve['omega_error'][i], curve['gamma_error'][i]] if curve['kind'] == 'CGYRO' else ['', '']
                    writer.writerow([title, curve['kind'], curve['label'], curve.get('nr', None), curve.get('rho', None),
                                     curve['para'], str(curve['value']), curve['ky'][i], curve['omega'][i], curve['gamma'][i], *error])
    def serial(value):
        return value.tolist() if hasattr(value, 'tolist') else str(value)
    metadata = {
        'format': 1, 'compare_mode': ctx['compare_mode'],
        'normalization': 'main-ion' if ctx.get('normalize_main_ion', None) else 'native saved units',
        'values': 'omega/gamma before display /ky or /ky² scaling; negative gamma is preserved',
        'std': 'CGYRO population standard deviation / absolute mean; blank for TGLF',
        'averaging_fraction': ctx.get('ave_window', None), 'plot_settings': ctx.get('plot_state', {}),
        'diagnostics': ctx.get('_diagnostics', []),
    }
    (directory/'metadata.json').write_text(json.dumps(metadata, indent=2, ensure_ascii=False, default=serial), encoding='utf-8')
    print('Exported spectra to {}'.format(directory))
    return str(directory)


def run_plot(root):
    ctx = build_context(root)
    if ctx.get('check_cgyro_output_now', None):
        return plot_cgyro_output_status(root, ctx)
    report = selection_check(root)
    if report['errors']:
        raise ValueError('\n'.join(report['errors']))
    mode = ctx['compare_mode']
    if mode == 'CGYRO_vs_CGYRO':
        return root['PLOTS']['CGYRO_vs_CGYRO'].plot()
    try:
        if mode == 'TGLF_vs_TGLF' and ctx.get('tglf_vs_tglf_mode', None) == 'Flux':
            return plot_tglf_vs_tglf(root, ctx)
        pages = list(collect_comparison_pages(root, ctx))
        if not pages or not any(cg or tg for _, cg, tg in pages):
            raise ValueError('No valid selected spectra. Check the source, radii and parameter values.')
        if ctx['mode_state'].get('comparison_export_now', None):
            return export_comparison(root, ctx, pages)
        if mode == 'TGLF_vs_TGLF':
            return plot_tglf_vs_tglf(root, ctx)
        # Validate every page before creating any figure, avoiding partial comparisons.
        for title, cg, tg in pages:
            if not cg or not tg:
                raise ValueError('Missing valid curves in one model: '+title)
            if ctx.get('error_flag', None) == 'CGYRO-TGLF' and not ctx.get('plot_gamma_ratio', None):
                if len(cg) != 1 and len(tg) != 1:
                    raise ValueError('Choose exactly one reference curve in at least one model: '+title)
        notebook = FigureNotebook(0, 'CGYRO / TGLF comparison')
        for title, cgyro, tglf in pages:
            _plot_compare_page(notebook, ctx, title, title, cgyro, tglf)
    finally:
        diagnostics = list(dict.fromkeys(ctx.get('_diagnostics', [])))
        if diagnostics:
            warnings.warn('Skipped {} unavailable/invalid selections:\n{}'.format(len(diagnostics), '\n'.join(diagnostics[:10])), RuntimeWarning)
