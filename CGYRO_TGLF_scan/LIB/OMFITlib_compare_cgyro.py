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
    collect_value_series, collect_time_series, build_param_cloud, get_gamma_ratio_curve, diagnostic,
    compute_freq_stats, filter_single_ky, normalize_if_needed)
from OMFITlib_compare_cgyro_eigen import (
    collect_eigen_entries_for_value, extract_eigen_curve, flatten_balloon_field,
    interpolate_field, select_eigen_entries)
from OMFITlib_compare_cgyro_export import export_selected_linear_spectra
from OMFITlib_compare_cgyro_render import render_page
from OMFITlib_compare_state import selection_check, selected_cgyro_runs
from OMFITlib_compare_style import cgyro_case_caption
from OMFITlib_cgyro_scan_view import slice_caption


def collect_plot_items(root, ctx):
    """Finish data validation before creating a notebook or any figure."""
    items = []
    for nr in ctx['nr_CGYRO']:
        for para, values in _iter_selected_parameter_items(ctx, nr):
            metadata = ctx.get('_cgyro_slices', {}).get((str(nr), str(para)), {})
            identity = dict(nr=nr, para=para, slice_meta=metadata,
                            axis_name=metadata.get('axis', para), scan_values=values)
            if ctx.get('plot_time_traces', False):
                for value in values:
                    for trace in collect_time_series(root, ctx, nr, para, value):
                        items.append(dict(identity, value=value, trace=trace))
            elif ctx['plot_gamma_ratio']:
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
            if item.get('source_label', ''):
                key += (item['source_label'],)
        else:
            key = ('All selected radii',) if _combine_nr_on_single_page(ctx) else (str(item['nr']),)
            if ctx.get('plot_time_traces', False):
                key += ('ky={:.10g}'.format(item['trace']['ky']),)
        pages.setdefault(key, []).append(item)
    labeled = []
    for key, values in pages.items():
        if ctx['plot_3d']:
            key = (key[0], slice_caption(values[0]['slice_meta'], key[1])) + key[2:]
        if not _combine_nr_on_single_page(ctx):
            key = (cgyro_case_caption(key[0], include_radius=True),) + key[1:]
        labeled.append((' / '.join(key), values))
    return labeled


def run_plot(root):
    report = selection_check(root, mode='CGYRO_vs_CGYRO')
    if report['errors']:
        raise ValueError('\n'.join(report['errors']))
    state = root['SETTINGS']['PHYSICS']['CGYRO_vs_CGYRO']
    contexts = [build_context(root, selected) for selected in selected_cgyro_runs(state)]
    ctx = dict(contexts[0])
    if not ctx['plotcgyro']:
        return []
    for selected in contexts:
        if not _has_any_selected_parameters(selected):
            raise ValueError(str(selected['runid']) + ': No CGYRO parameter remains selected; check the current radius/parameter checkboxes')
    if ctx.get('export_linear_now', False):
        exports = [export_selected_linear_spectra(root, selected) for selected in contexts]
        return exports if state.get('compare_multiple_runs', False) else exports[0]
    items, diagnostics = [], []
    for selected in contexts:
        values = collect_plot_items(root, selected)
        if state.get('compare_multiple_runs', False):
            for item in values:
                item['source_label'] = str(selected['runid'])
        items.extend(values)
        diagnostics.extend(selected['_diagnostics'])
    ctx['_diagnostics'] = diagnostics
    ctx['nr_CGYRO'] = list(dict.fromkeys(nr for selected in contexts for nr in selected['nr_CGYRO']))
    if not items:
        detail = '\n'.join(ctx['_diagnostics'][:5])
        raise ValueError('No valid selected CGYRO data for this plot.\n' + detail)
    if ctx['_diagnostics']:
        warnings.warn('CGYRO selections skipped or filtered:\n' + '\n'.join(ctx['_diagnostics'][:10]), RuntimeWarning)
    notebook = FigureNotebook(0, 'CGYRO scan comparison')
    return [render_page(notebook, ctx, label, values) for label, values in group_plot_pages(items, ctx)]
