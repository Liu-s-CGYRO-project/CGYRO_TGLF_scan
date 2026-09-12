"""CGYRO/TGLF comparison: tglf.

Extracted from the reviewed project; data is read from the supplied OMFIT tree.
"""

# OMFIT libraries inherit a pylab namespace; keep Python scalar/iterator semantics.
from builtins import (
    Exception,
    any,
    bool,
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
    scan1d = root['TGLF_scan'].get('scanResults', {})

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
    scan2d = root['TGLF_scan'].get('scanResults2D', {})

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
    if not ctx.get('show_flux_spectra', True):
        return
    """Create one standalone page for particle/energy flux-vs-ky."""
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
        ax0.set_title(f'{title_text} flux spectrum', fontdict={'family': 'DejaVu Sans', 'size': ctx['fs1']})
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
                axi.set_title(str(field_labels[i_fd]), fontdict={'family': 'DejaVu Sans', 'size': ctx['fs2']})
            if i_fd == 0:
                axi.set_ylabel(str(species_labels[i_sp]), fontdict={'family': 'DejaVu Sans', 'size': ctx['fs2']})
            if i_sp == n_sp - 1:
                axi.set_xlabel('$k_y$*$\\rho_s$', fontdict={'family': 'DejaVu Sans', 'size': ctx['fs2']})
            else:
                axi.set_xticklabels([])

            if i_sp == 0 and i_fd == 0 and len(curve_list) > 0:
                finalize_axis_legend(axi, ctx, fontsize=max(8, ctx['fs2'] - 1))

    fig.suptitle(str(title_text), fontsize=ctx['fs1'] + 1)


def plot_tglf_vs_tglf(root, ctx):
    """
    Entry for `TGLF_vs_TGLF` mode.

    Dispatches between:
    - Flux mode (`plot_tglf_flux_1d/2d`)
    - Spectra mode (1D/2D omega-gamma and flux-spectrum pages)
    """
    tglf_state = ctx['tglf_state']
    spectra_mode = tglf_state.get('spectra_mode', '1D')
    tglf_mode = ctx.get('tglf_vs_tglf_mode', 'Spectra')

    # New TGLF_vs_TGLF mode: flux-vs-parameter plotting (2D figures only).
    if tglf_mode == 'Flux':
        fn = FigureNotebook(0, 'TGLF_vs_TGLF')
        if spectra_mode == '2D':
            plot_tglf_flux_2d(fn, root, ctx)
        else:
            plot_tglf_flux_1d(fn, root, ctx)
        return

    if spectra_mode != '2D':
        rho_selected = tglf_state.get('rho_selected', [])
        tglf_selected_paras = tglf_state.get('selected_paras', {})
        for rho in rho_selected:
            curves_mode1 = collect_tglf_curves(
                rho, tglf_selected_paras, root, ctx, mode_idx=1, include_rho_in_label=False
            )
            curves_mode2 = collect_tglf_curves(
                rho, tglf_selected_paras, root, ctx, mode_idx=2, include_rho_in_label=False
            )
            if len(curves_mode1) == 0 and len(curves_mode2) == 0:
                continue

            # One notebook per rho; notebook title is exactly "rho=...".
            fn_rho = FigureNotebook(0, f'rho={rho}')

            # Page 1: omega/gamma
            fig2d, ax_2d = fn_rho.subplots(
                nrows=2,
                ncols=2,
                figsize=DEFAULT_FIGSIZE_2X2,
                label='omega-gamma',
                sharex=True,
                sharey=False,
                squeeze=False,
            )
            apply_figure_layout(fig2d, ctx)
            plot_curves_no_error_2x2(ax_2d, ctx, curves_mode1, curves_mode2)

            # Page 2/3: particle and energy flux-vs-ky.
            particle_panel = collect_tglf_flux_spectrum_curves(
                rho, tglf_selected_paras, root, quantity_name='particle', ctx=ctx
            )
            energy_panel = collect_tglf_flux_spectrum_curves(
                rho, tglf_selected_paras, root, quantity_name='energy', ctx=ctx
            )
            _plot_flux_spectrum_page(fn_rho, particle_panel, 'particle', ctx)
            _plot_flux_spectrum_page(fn_rho, energy_panel, 'energy', ctx)
        return

    # 2D spectra plotting
    scan2d = root['TGLF_scan'].get('scanResults2D_spectra', {})
    rho_selected = tglf_state.get('rho_selected', [])
    selected_paras_2d = tglf_state.get('selected_paras_2d', {})
    plot_mode_2d = ctx.get('tglf2d_plot_mode', '2D')
    x_axis = ctx.get('tglf2d_x_axis', 'para1')

    for rho in rho_selected:
        rho_key = resolve_key(scan2d, rho)
        if rho_key is None:
            continue
        # One notebook per rho for consistent grouping with 1D spectra mode.
        fn_rho = FigureNotebook(0, f'rho={rho}')
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
            page_label = f'rho={rho}, {pname_key}'
            use_para2 = (x_axis == 'para2') or (str(x_axis) == str(p2_name))
            if not use_para2:
                # outer loop = para2: fixed para2, loop para1
                fixed_name = p2_name
                fixed_values = para2_values
                varying_name = p1_name
                varying_values = para1_values
                fixed_is_para2 = True
            else:
                # outer loop = para1: fixed para1, loop para2
                fixed_name = p1_name
                fixed_values = para1_values
                varying_name = p2_name
                varying_values = para2_values
                fixed_is_para2 = False

            if plot_mode_2d == '2D':
                curves_raw_by_mode = collect_tglf2d_mode_curves(
                    param_node,
                    fixed_values,
                    varying_values,
                    fixed_is_para2,
                    # Keep raw omega/gamma here; _plot_no_error_column will apply
                    # divide_by_ky exactly once for 2D line plots.
                    divide_by_ky=False,
                    divide_by_ky2=False,
                    normalize_main_ion=ctx.get('normalize_main_ion', False),
                    ctx=ctx,
                )
                curves_mode1 = build_labeled_mode_curves(curves_raw_by_mode[1], varying_name, fixed_name)
                curves_mode2 = build_labeled_mode_curves(curves_raw_by_mode[2], varying_name, fixed_name)
                if len(curves_mode1) == 0 and len(curves_mode2) == 0:
                    continue

                fig2d, ax_2d = fn_rho.subplots(
                    nrows=2,
                    ncols=2,
                    figsize=DEFAULT_FIGSIZE_2X2,
                    label=f'omega-gamma ({pname_key})',
                    sharex=True,
                    sharey=False,
                    squeeze=False,
                )
                apply_figure_layout(fig2d, ctx)
                plot_curves_no_error_2x2(ax_2d, ctx, curves_mode1, curves_mode2)

                particle_panel = collect_tglf2d_flux_spectrum_curves(
                    param_node,
                    fixed_values,
                    varying_values,
                    fixed_is_para2,
                    quantity_name='particle',
                    varying_name=varying_name,
                    fixed_name=fixed_name,
                    ctx=ctx,
                )
                energy_panel = collect_tglf2d_flux_spectrum_curves(
                    param_node,
                    fixed_values,
                    varying_values,
                    fixed_is_para2,
                    quantity_name='energy',
                    varying_name=varying_name,
                    fixed_name=fixed_name,
                    ctx=ctx,
                )
                _plot_flux_spectrum_page(
                    fn_rho, particle_panel, 'particle', ctx,
                    page_label=f'particle ({pname_key})',
                    title_text=f'particle ({pname_key})',
                )
                _plot_flux_spectrum_page(
                    fn_rho, energy_panel, 'energy', ctx,
                    page_label=f'energy ({pname_key})',
                    title_text=f'energy ({pname_key})',
                )
                continue

            # 3D mode: one surface per fixed outer-loop value.
            for fixed_val in fixed_values:
                spectra_curves_by_mode = collect_tglf2d_mode_curves(
                    param_node,
                    [fixed_val],
                    varying_values,
                    fixed_is_para2,
                    divide_by_ky=ctx.get('divide_by_ky', True),
                    divide_by_ky2=ctx.get('divide_by_ky2', False),
                    normalize_main_ion=ctx.get('normalize_main_ion', False),
                    ctx=ctx,
                )

                if len(spectra_curves_by_mode[1]) == 0 and len(spectra_curves_by_mode[2]) == 0:
                    continue

                try:
                    fig, ax = fn_rho.subplots(
                        nrows=2, ncols=2, figsize=DEFAULT_FIGSIZE_3D_GRID,
                        label=f'omega-gamma ({pname_key}, {fixed_name}={_fmt_curve_value(fixed_val)})',
                        squeeze=False, subplot_kw={'projection': '3d'}
                    )
                except Exception:
                    fig, ax2d = fn_rho.subplots(
                        nrows=2, ncols=2, figsize=DEFAULT_FIGSIZE_3D_GRID,
                        label=f'omega-gamma ({pname_key}, {fixed_name}={_fmt_curve_value(fixed_val)})',
                        squeeze=False
                    )
                    try:
                        for rr in range(2):
                            for cc in range(2):
                                ax2d[rr, cc].remove()
                    except Exception:
                        pass
                    ax = array([
                        [fig.add_subplot(2, 2, 1, projection='3d'), fig.add_subplot(2, 2, 2, projection='3d')],
                        [fig.add_subplot(2, 2, 3, projection='3d'), fig.add_subplot(2, 2, 4, projection='3d')],
                    ], dtype=object)
                apply_figure_layout(fig, ctx)

                for mode_idx, col_idx in [(1, 0), (2, 1)]:
                    spectra_curves = spectra_curves_by_mode[mode_idx]
                    if len(spectra_curves) == 0:
                        continue

                    title_omega, title_gamma = mode_titles(ctx, mode_idx)

                    ky_base, var_axis, z_omega, z_gamma = build_surface_from_curves(spectra_curves)
                    if ky_base is None:
                        continue

                    x_vals_plot, x_label_3d, use_log_x_3d = build_3d_x_axis(
                        ky_base, ctx.get('plot_log_x', False)
                    )
                    x_mesh, y_mesh = meshgrid(x_vals_plot, var_axis)

                    ax[0, col_idx].plot_surface(x_mesh, y_mesh, z_omega, cmap='viridis', linewidth=0, antialiased=True)
                    ax[1, col_idx].plot_surface(x_mesh, y_mesh, z_gamma, cmap='plasma', linewidth=0, antialiased=True)

                    ax[0, col_idx].set_title(title_omega)
                    ax[1, col_idx].set_title(title_gamma)
                    ax[0, col_idx].set_xlabel(x_label_3d)
                    ax[1, col_idx].set_xlabel(x_label_3d)
                    ax[0, col_idx].set_ylabel(varying_name)
                    ax[1, col_idx].set_ylabel(varying_name)
                    if use_log_x_3d:
                        apply_3d_log_ticks(ax[0, col_idx], ax[1, col_idx], x_vals_plot, ky_base)

                particle_panel = collect_tglf2d_flux_spectrum_curves(
                    param_node,
                    [fixed_val],
                    varying_values,
                    fixed_is_para2,
                    quantity_name='particle',
                    varying_name=varying_name,
                    fixed_name=fixed_name,
                    ctx=ctx,
                )
                energy_panel = collect_tglf2d_flux_spectrum_curves(
                    param_node,
                    [fixed_val],
                    varying_values,
                    fixed_is_para2,
                    quantity_name='energy',
                    varying_name=varying_name,
                    fixed_name=fixed_name,
                    ctx=ctx,
                )
                page_suffix = f'{pname_key}, {fixed_name}={_fmt_curve_value(fixed_val)}'
                _plot_flux_spectrum_page(
                    fn_rho, particle_panel, 'particle', ctx,
                    page_label=f'particle ({page_suffix})',
                    title_text=f'particle ({page_suffix})',
                )
                _plot_flux_spectrum_page(
                    fn_rho, energy_panel, 'energy', ctx,
                    page_label=f'energy ({page_suffix})',
                    title_text=f'energy ({page_suffix})',
                )
