"""OMFIT entry point for CGYRO self-comparison: validate, collect, then render.

Selection, numerical data, eigenfields, figure rendering and export live in
separate libraries. Only this adapter depends on OMFIT's FigureNotebook global.
The frequently used data helpers remain importable from this original module.
"""
from builtins import (IndexError, KeyError, RuntimeWarning, TypeError, ValueError,
                      dict, len, list, str)
import warnings
from OMFITlib_compare_cgyro_selection import (
    build_context, _combine_nr_on_single_page, _iter_selected_parameter_items,
    _has_any_selected_parameters, parse_float_list_text)
from OMFITlib_compare_cgyro_data import (
    collect_value_series, build_param_cloud, get_gamma_ratio_curve, diagnostic,
    compute_freq_stats, filter_single_ky, normalize_if_needed)
from OMFITlib_compare_cgyro_eigen import (
    collect_eigen_entries_for_value, extract_eigen_curve, flatten_balloon_field,
    interpolate_field, select_eigen_entries)
from OMFITlib_compare_cgyro_export import export_selected_linear_spectra
from OMFITlib_compare_cgyro_render import render_page
from OMFITlib_compare_state import selection_check


def collect_plot_items(root, ctx):
    """Finish data validation before creating a notebook or any figure."""
    items = []
    for nr in ctx['nr_CGYRO']:
        for para, values in _iter_selected_parameter_items(ctx, nr):
            identity = {'nr': nr, 'para': para}
            if ctx['plot_gamma_ratio']:
                ratio = get_gamma_ratio_curve(root, ctx, nr, para, values)
                if ratio is not None:
                    items.append(dict(identity, ratio=ratio))
            elif ctx['single_ky'] or ctx['plot_3d']:
                cloud = build_param_cloud(root, ctx, nr, para, values)
                if len(cloud[0]):
                    items.append(dict(identity, cloud=cloud))
            else:
                for value in values:
                    if ctx['plot_eigen_ball']:
                        entries = collect_eigen_entries_for_value(root, ctx, nr, para, value)
                        for entry in entries:
                            try:
                                curve = extract_eigen_curve(entry['datadir'])
                            except (KeyError, IndexError, TypeError, ValueError) as exc:
                                diagnostic(ctx, nr, para, value, exc, ky=entry['ky'])
                                continue
                            if curve is None:
                                diagnostic(ctx, nr, para, value, 'Missing or invalid saved balloon/phi data', ky=entry['ky'])
                            else:
                                items.append(dict(identity, value=value, ky=entry['ky'], eigen=curve))
                    else:
                        series = collect_value_series(root, ctx, nr, para, value)
                        if len(series[0]):
                            items.append(dict(identity, value=value, series=series))
    return items


def group_plot_pages(items, ctx):
    pages = {}
    for item in items:
        if ctx['plot_3d']:
            key = (str(item['nr']), str(item['para']))
        else:
            key = ('All selected radii',) if _combine_nr_on_single_page(ctx) else (str(item['nr']),)
        pages.setdefault(key, []).append(item)
    return [(' / '.join(key), values) for key, values in pages.items()]


def run_plot(root):
    report = selection_check(root, mode='CGYRO_vs_CGYRO')
    if report['errors']:
        raise ValueError('\n'.join(report['errors']))
    ctx = build_context(root)
    if not ctx['plotcgyro']:
        return []
    if not _has_any_selected_parameters(ctx):
        raise ValueError('No CGYRO parameter remains selected; check the current radius/parameter checkboxes')
    if ctx.get('export_linear_now', False):
        return export_selected_linear_spectra(root, ctx)
    items = collect_plot_items(root, ctx)
    if not items:
        detail = '\n'.join(ctx['_diagnostics'][:5])
        raise ValueError('No valid selected CGYRO data for this plot.\n' + detail)
    if ctx['_diagnostics']:
        warnings.warn('CGYRO selections skipped or filtered:\n' + '\n'.join(ctx['_diagnostics'][:10]), RuntimeWarning)
    notebook = FigureNotebook(0, 'CGYRO scan comparison')
    return [render_page(notebook, ctx, label, values) for label, values in group_plot_pages(items, ctx)]
