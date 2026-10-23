"""CGYRO/TGLF comparison: tglf.

Extracted from the reviewed project; data is read from the supplied OMFIT tree.
"""
from OMFITlib_plot_sources import context_results
# OMFIT libraries inherit a pylab namespace; keep Python scalar/iterator semantics.
from builtins import (
    Exception,
    any,
    bool,
    dict,
    ValueError,
    TypeError,
    float,
    hasattr,
    len,
    max,
    min,
    object,
    range,
    sorted,
    str,
)

from numpy import (
    array,
    meshgrid,
)
from OMFITlib_compare_core import (
    _flux_species_rank,
    _fmt_curve_value,
    apply_3d_log_ticks,
    available_numeric_keys,
    build_3d_x_axis,
    build_labeled_mode_curves,
    build_surface_from_curves,
    collect_tglf2d_mode_curves,
    get_2d_scan_values,
    mode_titles,
    prepare_spectrum_for_plot,
    resolve_2d_param_node,
    resolve_key,
    split_2d_param_name,
    to_float_list,
)
from OMFITlib_compare_flux import (
    collect_tglf2d_flux_spectrum_curves,
    collect_tglf_flux_spectrum_curves,
    extract_flux_components,
)
from OMFITlib_compare_series import (
    collect_tglf_curves,
)
from OMFITlib_compare_spectra import (
    plot_curves_no_error_2x2,
)
from OMFITlib_compare_style import (
    DEFAULT_FIGSIZE_1X2,
    DEFAULT_FIGSIZE_2X2,
    DEFAULT_FIGSIZE_3D_GRID,
    apply_figure_layout,
    finalize_axis_legend,
    style_two_panel_xy_axes,
)


def plot_tglf_flux_1d(fn, root, ctx):
    """
    Plot TGLF 1D scan flux-vs-parameter pages.

    For each selected `(rho, parameter)`, creates a 1x2 page:
    left=`Gam/Gam_GB`, right=`Q/Q_GB`.
    """
    tglf_state = ctx['tglf_state']
    rho_selected = tglf_state.get('rho_selected', [])
    selected_paras = tglf_state.get('selected_paras', {})
    flux_species = ctx.get('tglf_flux_species', 'Both')
    merge_ions = bool(ctx.get('tglf_flux_merge_ions', True))
    scan1d = context_results(root, ctx, 'Flux')

    for rho in rho_selected:
        rho_key = resolve_key(scan1d, rho)
        if rho_key is None:
            continue
        rho_data = scan1d[rho_key]

        for para, values in selected_paras.items():
            para_key = resolve_key(rho_data, para)
            if para_key is None:
                continue

            para_node = rho_data[para_key]
            x_values = to_float_list(values)
            if len(x_values) == 0:
                x_values = available_numeric_keys(para_node)
            if len(x_values) == 0:
                continue

            gam_series = {}
            q_series = {}
            for xv in x_values:
                x_key = resolve_key(para_node, xv)
                if x_key is None:
                    continue
                gam_comp, q_comp = extract_flux_components(
                    para_node[x_key], flux_species=flux_species, merge_ions=merge_ions
                )
                try:
                    x_plot = float(x_key)
                except Exception:
                    x_plot = float(xv)
                for sp, val in gam_comp.items():
                    gam_series.setdefault(sp, []).append((x_plot, val))
                for sp, val in q_comp.items():
                    q_series.setdefault(sp, []).append((x_plot, val))

            if len(gam_series) == 0 and len(q_series) == 0:
                continue

            fig, ax = fn.subplots(
                nrows=1, ncols=2, figsize=DEFAULT_FIGSIZE_1X2,
                label=f'rho={rho}, {para_key}', sharex=False, sharey=False, squeeze=False
            )
            apply_figure_layout(fig, ctx)
            for sp in sorted(gam_series.keys(), key=_flux_species_rank):
                pts = gam_series.get(sp, [])
                pts = sorted(pts, key=lambda t: t[0])
                ax[0, 0].plot([p[0] for p in pts], [p[1] for p in pts], 'o-', label=sp, linewidth=ctx['lw'])
            for sp in sorted(q_series.keys(), key=_flux_species_rank):
                pts = q_series.get(sp, [])
                pts = sorted(pts, key=lambda t: t[0])
                ax[0, 1].plot([p[0] for p in pts], [p[1] for p in pts], 'o-', label=sp, linewidth=ctx['lw'])

            style_two_panel_xy_axes(
                ax, ctx,
                title_left='Gam/Gam_GB',
                title_right='Q/Q_GB',
                xlabel_left=str(para_key),
            )


def plot_tglf_flux_2d(fn, root, ctx):
    """
    Plot TGLF 2D scan flux-vs-parameter pages.

    One parameter axis is used as x-axis, the other as grouping key, then
    curves are split by species channel.
    """
    tglf_state = ctx['tglf_state']
    rho_selected = tglf_state.get('rho_selected', [])
    selected_paras_2d = tglf_state.get('selected_paras_2d', {})
    flux_species = ctx.get('tglf_flux_species', 'Both')
    merge_ions = bool(ctx.get('tglf_flux_merge_ions', True))
    x_axis = ctx.get('tglf2d_x_axis', 'para1')
    scan2d = context_results(root, ctx, 'Flux')

    for rho in rho_selected:
        rho_key = resolve_key(scan2d, rho)
        if rho_key is None:
            continue
        rho_data = scan2d[rho_key]

        for pname, cfg in selected_paras_2d.items():
            if not hasattr(cfg, 'get'):
                continue
            pname_key = resolve_key(rho_data, pname)
            if pname_key is None:
                continue
            param_node = rho_data[pname_key]

            para1_values, para2_values = get_2d_scan_values(param_node, cfg)
            if len(para1_values) == 0 or len(para2_values) == 0:
                continue

            p1_name, p2_name = split_2d_param_name(str(pname_key))
            x_is_para1 = (str(x_axis) == str(p1_name)) or (x_axis == 'para1')
            if x_is_para1:
                x_name, x_values = p1_name, para1_values
                group_name, group_values = p2_name, para2_values
                group_is_para2 = True
            else:
                x_name, x_values = p2_name, para2_values
                group_name, group_values = p1_name, para1_values
                group_is_para2 = False

            gam_series = {}
            q_series = {}
            for gv in group_values:
                for xv in x_values:
                    if group_is_para2:
                        p1_val, p2_val = xv, gv
                    else:
                        p1_val, p2_val = gv, xv

                    node = resolve_2d_param_node(param_node, p1_val, p2_val)
                    if node is None:
                        continue

                    gam_comp, q_comp = extract_flux_components(
                        node, flux_species=flux_species, merge_ions=merge_ions
                    )
                    for sp, val in gam_comp.items():
                        key = (float(gv), sp)
                        gam_series.setdefault(key, []).append((float(xv), val))
                    for sp, val in q_comp.items():
                        key = (float(gv), sp)
                        q_series.setdefault(key, []).append((float(xv), val))

            if len(gam_series) == 0 and len(q_series) == 0:
                continue

            fig, ax = fn.subplots(
                nrows=1, ncols=2, figsize=DEFAULT_FIGSIZE_1X2,
                label=f'rho={rho}, {pname_key}, x={x_name}', sharex=False, sharey=False, squeeze=False
            )
            apply_figure_layout(fig, ctx)
            for (gv, sp) in sorted(gam_series.keys(), key=lambda x: (_flux_species_rank(x[1]), float(x[0]))):
                pts = gam_series.get((gv, sp), [])
                pts = sorted(pts, key=lambda t: t[0])
                label = f'{group_name}={gv:g}, {sp}'
                ax[0, 0].plot([p[0] for p in pts], [p[1] for p in pts], 'o-', label=label, linewidth=ctx['lw'])
            for (gv, sp) in sorted(q_series.keys(), key=lambda x: (_flux_species_rank(x[1]), float(x[0]))):
                pts = q_series.get((gv, sp), [])
                pts = sorted(pts, key=lambda t: t[0])
                label = f'{group_name}={gv:g}, {sp}'
                ax[0, 1].plot([p[0] for p in pts], [p[1] for p in pts], 'o-', label=label, linewidth=ctx['lw'])

            style_two_panel_xy_axes(
                ax, ctx,
                title_left='Gam/Gam_GB',
                title_right='Q/Q_GB',
                xlabel_left=str(x_name),
            )


def _plot_flux_spectrum_page(fn, panel_data, quantity_name, ctx, page_label=None, title_text=None):
    """Create one standalone page for particle/energy flux-vs-ky."""
    if not ctx.get('show_flux_spectra', True):
        return
    species_labels = panel_data.get('species_labels', [])
    field_labels = panel_data.get('field_labels', [])
    curves = panel_data.get('curves', {})

    has_data = False
    for _key, items in curves.items():
        if len(items) > 0:
            has_data = True
            break

    if page_label is None:
        page_label = str(quantity_name)
    if title_text is None:
        title_text = str(quantity_name)

    if not has_data or len(species_labels) == 0 or len(field_labels) == 0:
        fig_empty, ax_empty = fn.subplots(
            nrows=1, ncols=1, figsize=(10, 4),
            label=page_label, squeeze=False
        )
        apply_figure_layout(fig_empty, ctx)
        ax0 = ax_empty[0, 0]
        ax0.set_title(f'{title_text} flux spectrum', fontdict={'size': ctx['fs1']})
        ax0.text(0.5, 0.5, 'No sum_flux_spectrum data', ha='center', va='center', transform=ax0.transAxes)
        ax0.set_axis_off()
        return

    n_sp = len(species_labels)
    n_fd = len(field_labels)
    fig_w = min(16.0, max(11.0, 3.6 * n_fd))
    fig_h = min(8.5, max(3.5, 2.0 * n_sp))

    fig, ax = fn.subplots(
        nrows=n_sp, ncols=n_fd, figsize=(fig_w, fig_h),
        label=page_label, sharex=True, sharey=False, squeeze=False
    )
    apply_figure_layout(fig, ctx)

    for i_sp in range(n_sp):
        for i_fd in range(n_fd):
            axi = ax[i_sp, i_fd]
            axi.spines['bottom'].set_linewidth(ctx['bwith'])
            axi.spines['left'].set_linewidth(ctx['bwith'])
            axi.spines['top'].set_linewidth(ctx['bwith'])
            axi.spines['right'].set_linewidth(ctx['bwith'])
            axi.axhline(0.0, color='0.4', linestyle='--', linewidth=0.8)

            curve_list = curves.get((i_sp, i_fd), [])
            curve_list = sorted(curve_list, key=lambda d: d.get('label', ''))
            for item in curve_list:
                ky = item.get('ky', array([]))
                y = item.get('y', array([]))
                if len(ky) == 0 or len(y) == 0:
                    continue
                axi.plot(ky, y, linewidth=ctx['lw'], label=item.get('label', ''))

            if ctx.get('plot_log_x', False):
                positive_x = True
                for item in curve_list:
                    ky_vals = item.get('ky', array([]))
                    if len(ky_vals) > 0 and any(array(ky_vals) <= 0):
                        positive_x = False
                        break
                if positive_x:
                    axi.set_xscale('log')

            if i_sp == 0:
                axi.set_title(str(field_labels[i_fd]), fontdict={'size': ctx['fs2']})
            if i_fd == 0:
                axi.set_ylabel(str(species_labels[i_sp]), fontdict={'size': ctx['fs2']})
            if i_sp == n_sp - 1:
                axi.set_xlabel('$k_y$*$\\rho_s$', fontdict={'size': ctx['fs2']})
            else:
                axi.set_xticklabels([])

            if i_sp == 0 and i_fd == 0 and len(curve_list) > 0:
                finalize_axis_legend(axi, ctx, fontsize=max(8, ctx['fs2'] - 1))

    fig.suptitle(str(title_text), fontsize=ctx['fs1'] + 1)


def _flux_panels(collector, ctx, *args, **kwargs):
    # Hidden flux controls must not force loading unrelated result files.
    if not ctx.get('show_flux_spectra', True):
        return {}
    return {quantity: collector(*args, quantity_name=quantity, ctx=ctx, **kwargs)
            for quantity in ('particle', 'energy')}


def _selected_2d_grids(root, ctx):
    """Resolve coordinates once; explicit empty axis selections stay empty."""
    state = ctx['tglf_state']
    saved = context_results(root, ctx, 'Spectra')
    for rho in state.get('rho_selected', []):
        rho_key = resolve_key(saved, rho)
        if rho_key is None:
            continue
        for parameter, config in state.get('selected_paras_2d', {}).items():
            if not hasattr(config, 'get'):
                continue
            key = resolve_key(saved[rho_key], parameter)
            if key is None:
                continue
            node = saved[rho_key][key]
            first, second = get_2d_scan_values(node, config)
            if not first or not second:
                continue
            first_name, second_name = split_2d_param_name(str(key))
            axis = ctx.get('tglf2d_x_axis', 'para1')
            if axis == 'para2' or str(axis) == str(second_name):
                yield rho, key, node, first, second, first_name, second_name, False
            else:
                yield rho, key, node, second, first, second_name, first_name, True


def collect_tglf_spectrum_pages(root, ctx):
    """Prepare all selected spectrum pages before any GUI window is created.

    Curves remain unscaled by ky here. Lines and surfaces each apply display
    scaling once while rendering; no renderer reopens a result or selection.
    """
    state = ctx['tglf_state']
    pages = []
    if state.get('spectra_mode', '1D') != '2D':
        selected = state.get('selected_paras', {})
        for rho in state.get('rho_selected', []):
            curves = {mode: collect_tglf_curves(rho, selected, root, ctx,
                      mode_idx=mode, include_rho_in_label=False) for mode in (1, 2)}
            if not any(curves.values()):
                continue
            panels = _flux_panels(collect_tglf_flux_spectrum_curves, ctx, rho, selected, root)
            pages.append(dict(rho=rho, kind='lines', label='omega-gamma',
                              curves=curves, panels=panels, suffix=''))
        return pages
    surface = ctx.get('tglf2d_plot_mode', '2D') != '2D'
    for rho, key, node, fixed, varying, fixed_name, varying_name, fixed_second in _selected_2d_grids(root, ctx):
        groups = [[value] for value in fixed] if surface else [fixed]
        for group in groups:
            curves = collect_tglf2d_mode_curves(node, group, varying, fixed_second,
                divide_by_ky=False, divide_by_ky2=False,
                normalize_main_ion=ctx.get('normalize_main_ion', False), ctx=ctx)
            if not any(curves.values()):
                continue
            suffix = str(key) + (', {}={}'.format(fixed_name, _fmt_curve_value(group[0])) if surface else '')
            if not surface:
                curves = {mode: build_labeled_mode_curves(curves[mode], varying_name, fixed_name) for mode in (1, 2)}
            panels = _flux_panels(collect_tglf2d_flux_spectrum_curves, ctx, node,
                                 group, varying, fixed_second, varying_name=varying_name, fixed_name=fixed_name)
            pages.append(dict(rho=rho, kind='surface' if surface else 'lines',
                              label='omega-gamma ({})'.format(suffix), curves=curves,
                              panels=panels, suffix=suffix, varying_name=varying_name))
    return pages


def _surface_axes(notebook, page):
    try:
        return notebook.subplots(nrows=2, ncols=2, figsize=DEFAULT_FIGSIZE_3D_GRID,
            label=page['label'], squeeze=False, subplot_kw={'projection': '3d'})
    except TypeError:
        # Older FigureNotebook adapters reject subplot_kw. Do not hide data or
        # rendering errors behind this compatibility branch.
        figure, old_axes = notebook.subplots(nrows=2, ncols=2, figsize=DEFAULT_FIGSIZE_3D_GRID,
                                            label=page['label'], squeeze=False)
        for row in old_axes:
            for axis in row:
                axis.remove()
        axes = array([[figure.add_subplot(2, 2, 1, projection='3d'), figure.add_subplot(2, 2, 2, projection='3d')],
                      [figure.add_subplot(2, 2, 3, projection='3d'), figure.add_subplot(2, 2, 4, projection='3d')]], dtype=object)
        return figure, axes


def _render_surface_page(notebook, ctx, page):
    figure, axes = _surface_axes(notebook, page)
    apply_figure_layout(figure, ctx)
    for mode, column in ((1, 0), (2, 1)):
        display_curves = []
        for curve in page['curves'][mode]:
            ky, omega, gamma = prepare_spectrum_for_plot(curve['ky'], curve['omega'], curve['gamma'],
                ctx.get('divide_by_ky', True), ctx.get('divide_by_ky2', False))
            display_curves.append(dict(curve, ky=ky, omega=omega, gamma=gamma))
        if not display_curves:
            continue
        ky, values, omega, gamma = build_surface_from_curves(display_curves)
        if ky is None:
            continue
        x_values, x_label, log_ticks = build_3d_x_axis(ky, ctx.get('plot_log_x', False))
        x_mesh, y_mesh = meshgrid(x_values, values)
        titles = mode_titles(ctx, mode)
        for row, field, color in ((0, omega, 'viridis'), (1, gamma, 'plasma')):
            axis = axes[row, column]
            axis.plot_surface(x_mesh, y_mesh, field, cmap=color, linewidth=0, antialiased=True)
            axis.set_title(titles[row])
            axis.set_xlabel(x_label)
            axis.set_ylabel(page['varying_name'])
        if log_ticks:
            apply_3d_log_ticks(axes[0, column], axes[1, column], x_values, ky)


def render_tglf_spectrum_pages(pages, ctx):
    """Render prepared pages; all result access belongs to the collector."""
    notebooks = {}
    for page in pages:
        rho = page['rho']
        if rho not in notebooks:
            notebooks[rho] = FigureNotebook(0, 'rho={}'.format(rho))
        notebook = notebooks[rho]
        if page['kind'] == 'surface':
            _render_surface_page(notebook, ctx, page)
        else:
            figure, axes = notebook.subplots(nrows=2, ncols=2, figsize=DEFAULT_FIGSIZE_2X2,
                label=page['label'], sharex=True, sharey=False, squeeze=False)
            apply_figure_layout(figure, ctx)
            plot_curves_no_error_2x2(axes, ctx, page['curves'][1], page['curves'][2])
        for quantity, panel in page['panels'].items():
            options = {}
            if page['suffix']:
                options = dict(page_label='{} ({})'.format(quantity, page['suffix']),
                               title_text='{} ({})'.format(quantity, page['suffix']))
            _plot_flux_spectrum_page(notebook, panel, quantity, ctx, **options)


def plot_tglf_vs_tglf(root, ctx):
    """Dispatch TGLF flux or collected spectrum pages through OMFIT."""
    if ctx.get('tglf_vs_tglf_mode', 'Spectra') == 'Flux':
        notebook = FigureNotebook(0, 'TGLF_vs_TGLF')
        render = plot_tglf_flux_2d if ctx['tglf_state'].get('spectra_mode', None) == '2D' else plot_tglf_flux_1d
        return render(notebook, root, ctx)
    pages = collect_tglf_spectrum_pages(root, ctx)
    if not pages:
        raise ValueError('No valid selected TGLF spectra. Check radii and parameter values.')
    return render_tglf_spectrum_pages(pages, ctx)
