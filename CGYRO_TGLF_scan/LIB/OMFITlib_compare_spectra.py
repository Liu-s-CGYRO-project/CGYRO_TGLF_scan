"""CGYRO/TGLF comparison: spectra.

Extracted from the reviewed project; data is read from the supplied OMFIT tree.
"""

# OMFIT libraries inherit a pylab namespace; keep Python scalar/iterator semantics.
from builtins import (
    Exception,
    ValueError,
    abs,
    all,
    any,
    float,
    int,
    len,
    list,
    max,
    min,
    range,
    set,
    sorted,
    str,
)

import numpy as np
from numpy import (
    argmax,
    argmin,
    argsort,
    array,
    isfinite,
    mean,
    nanmax,
    where,
)
from OMFITlib_compare_core import (
    _filter_curves_by_kind,
    _gamma_ratio_ky_bounds,
    _maybe_abs_ky,
    _to_float_scalar,
    apply_divide_by_ky,
    divide_title,
    mode_titles,
    parse_float_list_text,
    split_2d_param_name,
)
from OMFITlib_compare_series import (
    _parse_tglf_2d_value_pair,
    apply_cross_model_error_if_applicable,
)
from OMFITlib_compare_style import (
    DEFAULT_FIGSIZE_1X2,
    DEFAULT_FIGSIZE_2X2,
    DEFAULT_FIGSIZE_GAMMA_RATIO,
    _row_align_axes_limits,
    apply_color_order_to_axes,
    apply_figure_layout,
    finalize_axis_legend,
    style_2d_axes,
)


def _cgyro_error_mask_for_sorted_curve(curve, sort_idx, tol):
    """Build error-threshold mask for one sorted CGYRO curve."""
    try:
        omega_err = array(curve.get('omega_error', array([]))).ravel()
        gamma_err = array(curve.get('gamma_error', array([]))).ravel()
    except Exception:
        return None
    if len(omega_err) == 0 or len(gamma_err) == 0:
        return None
    if len(omega_err) <= max(sort_idx) or len(gamma_err) <= max(sort_idx):
        return None
    omega_err = omega_err[sort_idx]
    gamma_err = gamma_err[sort_idx]
    return (omega_err <= tol) & (gamma_err <= tol)


def _gamma_stat_for_curve(curve, ctx):
    """
    Compute one representative gamma statistic for gamma/gamma_ref ratio:
    - single ky: mean(gamma at nearest requested ky values)
    - all ky: max(gamma) within ky limits
    """
    ky = array(curve.get('ky', array([]))).ravel()
    omega = array(curve.get('omega', array([]))).ravel()
    gamma = array(curve.get('gamma', array([]))).ravel()
    n = min(len(ky), len(omega), len(gamma))
    if n <= 0:
        return None

    ky = ky[:n]
    omega = omega[:n]
    gamma = gamma[:n]
    sort_idx = argsort(ky)
    ky = ky[sort_idx]
    omega = omega[sort_idx]
    gamma = gamma[sort_idx]

    # Gamma ratios use the raw growth rate, not the hidden display scaling.
    y_gamma = gamma
    y_gamma = array(y_gamma).ravel()
    mask = isfinite(ky) & isfinite(y_gamma)

    if str(curve.get('kind', '')).upper() == 'CGYRO' and ctx.get('gamma_ref_error_filter', False):
        tol = float(ctx.get('error_tolerance', 0.01))
        err_mask = _cgyro_error_mask_for_sorted_curve(curve, sort_idx, tol)
        if err_mask is not None and len(err_mask) == len(mask):
            mask &= err_mask

    mode = str(ctx.get('gamma_ref_mode', 'all ky')).strip().lower()
    if mode == 'single ky':
        ky_targets = parse_float_list_text(ctx.get('gamma_ref_ky_values', ''))
        if len(ky_targets) == 0:
            return None
        cand_idx = where(mask)[0]
        if len(cand_idx) == 0:
            return None
        ky_cand = ky[cand_idx]
        gamma_cand = y_gamma[cand_idx]
        vals = []
        ky_targets = [_maybe_abs_ky(float(k), ctx) for k in ky_targets]
        for ky_req in ky_targets:
            idx_local = int(argmin(abs(ky_cand - float(ky_req))))
            vals.append(float(gamma_cand[idx_local]))
        if len(vals) == 0:
            return None
        return float(mean(array(vals)))

    ky_min, ky_max = _gamma_ratio_ky_bounds(ctx)
    if ky_min is not None:
        mask &= (ky >= ky_min)
    if ky_max is not None:
        mask &= (ky <= ky_max)
    if not any(mask):
        return None
    vals = y_gamma[mask]
    vals = vals[isfinite(vals)]
    if len(vals) == 0:
        return None
    return float(nanmax(vals))


def _gamma_ratio_curve_x_info(curve, ctx):
    """
    Decode x-value/x-label and fixed-parameter tag for gamma/gamma_ref plotting.

    For 2D TGLF value tuples, x-axis is selectable via `gamma_ref_tglf2d_x_axis`.
    """
    para = str(curve.get('para', '')).strip()
    value = curve.get('value', None)

    p1_val, p2_val = _parse_tglf_2d_value_pair(value)
    is_tglf_2d = (
        str(curve.get('kind', '')).upper() == 'TGLF'
        and p1_val is not None
        and p2_val is not None
        and len(para) > 0
    )
    if is_tglf_2d:
        p1_name, p2_name = split_2d_param_name(para)
        x_axis = str(ctx.get('gamma_ref_tglf2d_x_axis', p1_name)).strip()
        if x_axis in [p2_name, 'para2']:
            x_val = float(p2_val)
            x_name = p2_name
            fixed_name = p1_name
            fixed_val = float(p1_val)
        else:
            x_val = float(p1_val)
            x_name = p1_name
            fixed_name = p2_name
            fixed_val = float(p2_val)
        fixed_tag = f'{fixed_name}={fixed_val:g}'
        return x_val, x_name, fixed_tag

    x_val = _to_float_scalar(value)
    if x_val is None:
        return None, 'parameter value', ''
    x_name = para if len(para) > 0 else 'parameter value'
    return float(x_val), x_name, ''


def _gamma_ratio_group_key(curve, ctx):
    """Build grouping key for gamma/gamma_ref curves."""
    para = str(curve.get('para', '')).strip()
    if len(para) == 0:
        return None
    _, x_name, fixed_tag = _gamma_ratio_curve_x_info(curve, ctx)
    kind = str(curve.get('kind', '')).upper()
    if kind == 'CGYRO':
        return ('CGYRO', str(curve.get('nr', '')), para, str(x_name), str(fixed_tag))
    if kind == 'TGLF':
        return ('TGLF', str(curve.get('rho', '')), para, str(x_name), str(fixed_tag))
    return (kind, '', para, str(x_name), str(fixed_tag))


def _gamma_ratio_group_label(group_key, ref_value_used):
    """Format one legend label for a gamma-ratio grouped curve."""
    kind, scope, para, _x_name, fixed_tag = group_key
    ref_txt = f'{float(ref_value_used):g}'
    suffix = f', {fixed_tag}' if len(str(fixed_tag)) > 0 else ''
    if kind == 'CGYRO':
        return f'CGYRO({scope},{para}{suffix}), ref={ref_txt}'
    if kind == 'TGLF':
        return f'TGLF(rho={scope},{para}{suffix}), ref={ref_txt}'
    return f'{kind}({para}{suffix}), ref={ref_txt}'


def _compute_gamma_ratio_for_group(group_curves, ctx):
    """Compute x-value vs gamma/gamma_ref curve for one grouped scan."""
    ref_target = _to_float_scalar(ctx.get('gamma_ref_value', ''))
    if ref_target is None:
        return None

    gamma_map_raw = {}
    for curve in group_curves:
        x_val, _x_name, _fixed_tag = _gamma_ratio_curve_x_info(curve, ctx)
        if x_val is None:
            continue
        gamma_stat = _gamma_stat_for_curve(curve, ctx)
        if gamma_stat is None or (not isfinite(gamma_stat)):
            continue
        gamma_map_raw.setdefault(float(x_val), []).append(float(gamma_stat))

    if len(gamma_map_raw) == 0:
        return None

    gamma_map = {}
    for x_val, vals in gamma_map_raw.items():
        if len(vals) == 0:
            continue
        gamma_map[float(x_val)] = float(mean(array(vals)))
    if len(gamma_map) == 0:
        return None

    x_vals = array(sorted(gamma_map.keys()), dtype=float)
    ref_idx = int(argmin(abs(x_vals - float(ref_target))))
    ref_value_used = float(x_vals[ref_idx])
    gamma_ref = gamma_map.get(ref_value_used, None)
    if gamma_ref is None or (not isfinite(gamma_ref)) or abs(gamma_ref) <= 1e-12:
        return None

    y_vals = array([gamma_map[x] / gamma_ref for x in x_vals], dtype=float)
    return x_vals, y_vals, ref_value_used


def plot_gamma_ratio_compare_page(ax, ctx, curves, page_title=''):
    """Plot gamma/gamma_ref curves for CGYRO_vs_TGLF or TGLF_vs_CGYRO page."""
    if ax is None:
        return

    groups = {}
    for curve in curves:
        gkey = _gamma_ratio_group_key(curve, ctx)
        if gkey is None:
            continue
        groups.setdefault(gkey, []).append(curve)

    x_label_candidates = []
    has_any = False
    for gkey in sorted(groups.keys(), key=lambda x: (str(x[0]), str(x[1]), str(x[2]), str(x[4]))):
        result = _compute_gamma_ratio_for_group(groups[gkey], ctx)
        if result is None:
            continue
        x_vals, y_vals, ref_value_used = result
        if len(x_vals) == 0:
            continue
        x_label_candidates.append(str(gkey[3]))
        ax.plot(
            x_vals, y_vals, 'o-',
            linewidth=ctx.get('lw', 2),
            markersize=ctx.get('ms', 8),
            label=_gamma_ratio_group_label(gkey, ref_value_used),
        )
        has_any = True

    mode_txt = str(ctx.get('gamma_ref_mode', 'all ky'))
    title_txt = rf'$\gamma$/$\gamma_{{ref}}$ ({mode_txt})'
    if str(mode_txt).strip().lower() != 'single ky':
        ky_min, ky_max = _gamma_ratio_ky_bounds(ctx)
        if ky_min is not None or ky_max is not None:
            left = f'{ky_min:g}' if ky_min is not None else '-inf'
            right = f'{ky_max:g}' if ky_max is not None else 'inf'
            title_txt += f', ky in [{left}, {right}]'
    # if ctx.get('gamma_ref_error_filter', False):
    #     title_txt += f", CGYRO err<{ctx.get('error_tolerance', 0.01):g}>"
    if len(str(page_title).strip()) > 0:
        title_txt += f' - {page_title}'

    x_label_candidates = [x for x in x_label_candidates if len(str(x).strip()) > 0]
    if len(x_label_candidates) > 0 and len(set(x_label_candidates)) == 1:
        x_label = x_label_candidates[0]
    else:
        x_label = 'parameter value'
    ax.set_xlabel(str(x_label), fontdict={'family': 'DejaVu Sans', 'size': ctx.get('fs1', 16)})
    ax.set_ylabel(r'$\gamma$/$\gamma_{ref}$', fontdict={'family': 'DejaVu Sans', 'size': ctx.get('fs1', 16)})
    ax.set_title(title_txt, fontdict={'family': 'DejaVu Sans', 'size': ctx.get('fs1', 16)})
    ax.grid(True, alpha=0.3)

    if ctx.get('plot_log_x', False):
        try:
            x_all = []
            for ln in ax.get_lines():
                x_all.extend(list(array(ln.get_xdata()).ravel()))
            if len(x_all) > 0 and all(array(x_all, dtype=float) > 0):
                ax.set_xscale('log')
        except Exception:
            pass
    if ctx.get('plot_log_y', False):
        try:
            y_all = []
            for ln in ax.get_lines():
                y_all.extend(list(array(ln.get_ydata()).ravel()))
            if len(y_all) > 0 and all(array(y_all, dtype=float) > 0):
                ax.set_yscale('log')
        except Exception:
            pass

    for spine in ax.spines.values():
        spine.set_linewidth(ctx.get('bwith', 1.5))

    if has_any:
        finalize_axis_legend(ax, ctx, fontsize=ctx.get('fs2', 10))
        apply_color_order_to_axes(ax, ctx)
    else:
        ax.text(0.5, 0.5, 'No valid γ/γ_ref data', ha='center', va='center', transform=ax.transAxes)


def plot_on_axes(
    ax, ctx, label_str, ky, omega, gamma, omega_error, gamma_error,
    error_label=None, show_error=True
):
    """Plot one curve group onto the shared 2x2 layout."""
    if len(ky) == 0:
        return
    if error_label is None:
        error_label = label_str

    # Defensive fallback: keep error arrays aligned to ky length.
    if len(omega_error) != len(ky):
        omega_error = np.full(len(ky), np.nan)
    if len(gamma_error) != len(ky):
        gamma_error = np.full(len(ky), np.nan)

    sort_idx = argsort(ky)
    ky = ky[sort_idx]
    omega = omega[sort_idx]
    gamma = gamma[sort_idx]
    omega_error = omega_error[sort_idx]
    gamma_error = gamma_error[sort_idx]

    y_omega, y_gamma, title_omega, title_gamma = apply_divide_by_ky(
        ky, omega, gamma, ctx['divide_by_ky'], ctx.get('divide_by_ky2', False)
    )

    style_2d_axes(ax, ctx['bwith'])

    ax[0, 0].set_title(title_omega, fontdict={'family': 'DejaVu Sans', 'size': ctx['fs1']})
    ax[0, 0].plot(ky, y_omega, label=label_str, linewidth=ctx['lw'])
    if ctx['plot_log_x']:
        ax[0, 0].set_xscale('log')
    if ctx['plot_log_y']:
        ax[0, 0].set_yscale('log')
        ax[1, 0].set_yscale('log')

    ax[0, 1].set_title('Relative model difference' if ctx.get('error_flag') == 'CGYRO-TGLF' else 'Relative time fluctuation', fontdict={'family': 'DejaVu Sans', 'size': ctx['fs1']})
    ax[1, 1].set_title('Relative model difference' if ctx.get('error_flag') == 'CGYRO-TGLF' else 'Relative time fluctuation', fontdict={'family': 'DejaVu Sans', 'size': ctx['fs1']})
    if show_error:
        error_line, = ax[0, 1].plot(ky, omega_error, linewidth=ctx['lw'], label=error_label)
        error_line._comparison_identity = label_str

        error_line, = ax[1, 1].plot(ky, gamma_error, linewidth=ctx['lw'], label=error_label)
        error_line._comparison_identity = label_str

    ax[1, 0].set_title(title_gamma, fontdict={'family': 'DejaVu Sans', 'size': ctx['fs1']})
    ax[1, 0].plot(ky, y_gamma, label=label_str, linewidth=ctx['lw'])

    ax[1, 0].set_xlabel('$k_y$*$\\rho_s$', fontdict={'family': 'DejaVu Sans', 'size': ctx['fs1']}, labelpad=5)
    ax[1, 1].set_xlabel('$k_y$*$\\rho_s$', fontdict={'family': 'DejaVu Sans', 'size': ctx['fs1']}, labelpad=5)

    if ctx.get('highlight_max_gamma', False):
        max_gamma_idx = argmax(y_gamma)
        x_val = ky[max_gamma_idx]
        y_val = y_gamma[max_gamma_idx]
        ax[1, 0].plot(x_val, y_val, 'ro', markersize=ctx['ms'] * 1.5)
        ax[1, 0].annotate(f'({x_val:.3f}, {y_val:.3f})', xy=(x_val, y_val))

    # Keep legend behavior synchronized after each curve append.
    finalize_axis_legend(ax[0, 0], ctx)
    finalize_axis_legend(ax[1, 0], ctx)
    finalize_axis_legend(ax[0, 1], ctx)
    finalize_axis_legend(ax[1, 1], ctx)


def _plot_model_curves_one_column(ax, col_idx, ctx, curves, model_name):
    """
    Plot omega/gamma curves for one model into one column of a 2x2 layout.

    Row 0: omega(/ky)
    Row 1: gamma(/ky)
    """
    for r in range(2):
        ax[r, col_idx].spines['bottom'].set_linewidth(ctx['bwith'])
        ax[r, col_idx].spines['left'].set_linewidth(ctx['bwith'])
        ax[r, col_idx].spines['top'].set_linewidth(ctx['bwith'])
        ax[r, col_idx].spines['right'].set_linewidth(ctx['bwith'])

    base_omega = divide_title(ctx, 'omega')
    base_gamma = divide_title(ctx, 'gamma')

    for curve in curves:
        ky = curve.get('ky', array([]))
        omega = curve.get('omega', array([]))
        gamma = curve.get('gamma', array([]))
        label_str = curve.get('label', '')
        if len(ky) == 0:
            continue

        sort_idx = argsort(ky)
        ky = ky[sort_idx]
        omega = omega[sort_idx]
        gamma = gamma[sort_idx]

        y_omega, y_gamma, _, _ = apply_divide_by_ky(
            ky, omega, gamma,
            ctx.get('divide_by_ky', True), ctx.get('divide_by_ky2', False)
        )
        ax[0, col_idx].plot(ky, y_omega, linewidth=ctx['lw'], label=label_str)
        ax[1, col_idx].plot(ky, y_gamma, linewidth=ctx['lw'], label=label_str)

    ax[0, col_idx].set_title(
        f'{model_name} {base_omega}', fontdict={'family': 'DejaVu Sans', 'size': ctx['fs1']}
    )
    ax[1, col_idx].set_title(
        f'{model_name} {base_gamma}', fontdict={'family': 'DejaVu Sans', 'size': ctx['fs1']}
    )
    ax[0, col_idx].set_xlabel('$k_y$*$\\rho_s$', fontdict={'family': 'DejaVu Sans', 'size': ctx['fs1']}, labelpad=5)
    ax[1, col_idx].set_xlabel('$k_y$*$\\rho_s$', fontdict={'family': 'DejaVu Sans', 'size': ctx['fs1']}, labelpad=5)

    if ctx.get('plot_log_x', False):
        ax[0, col_idx].set_xscale('log')
        ax[1, col_idx].set_xscale('log')
    if ctx.get('plot_log_y', False):
        ax[0, col_idx].set_yscale('log')
        ax[1, col_idx].set_yscale('log')

    finalize_axis_legend(ax[0, col_idx], ctx)
    finalize_axis_legend(ax[1, col_idx], ctx)


def plot_curves_split_no_error_2x2(ax, ctx, tglf_curves, cgyro_curves):
    """
    No_error mode:
    - left column: TGLF omega/gamma
    - right column: CGYRO omega/gamma
    with row-wise aligned x/y ranges.
    Colors are assigned with independent cycles per model column.
    """
    if ax is None:
        return

    _plot_model_curves_one_column(ax, 0, ctx, tglf_curves, 'TGLF')
    _plot_model_curves_one_column(ax, 1, ctx, cgyro_curves, 'CGYRO')
    _row_align_axes_limits(ax)
    apply_color_order_to_axes([ax[0, 0], ax[1, 0]], ctx)
    apply_color_order_to_axes([ax[0, 1], ax[1, 1]], ctx)


def _plot_no_error_column(ax, col_idx, ctx, curves, mode_idx):
    """Plot one eigen-mode on one column: [omega(mode); gamma(mode)]."""
    if not curves:
        for r in range(2):
            ax[r, col_idx].text(.5, .5, 'Mode {} not available'.format(mode_idx), transform=ax[r, col_idx].transAxes, ha='center')
    for r in range(2):
        ax[r, col_idx].spines['bottom'].set_linewidth(ctx['bwith'])
        ax[r, col_idx].spines['left'].set_linewidth(ctx['bwith'])
        ax[r, col_idx].spines['top'].set_linewidth(ctx['bwith'])
        ax[r, col_idx].spines['right'].set_linewidth(ctx['bwith'])

    for curve in curves:
        ky = curve.get('ky', array([]))
        omega = curve.get('omega', array([]))
        gamma = curve.get('gamma', array([]))
        label_str = curve.get('label', '')

        if len(ky) == 0:
            continue

        sort_idx = argsort(ky)
        ky = ky[sort_idx]
        omega = omega[sort_idx]
        gamma = gamma[sort_idx]

        y_omega, y_gamma, _, _ = apply_divide_by_ky(
            ky, omega, gamma, ctx['divide_by_ky'], ctx.get('divide_by_ky2', False)
        )
        ax[0, col_idx].plot(ky, y_omega, label=label_str, linewidth=ctx['lw'])
        ax[1, col_idx].plot(ky, y_gamma, label=label_str, linewidth=ctx['lw'])

    title_omega, title_gamma = mode_titles(ctx, mode_idx)
    ax[0, col_idx].set_title(title_omega, fontdict={'family': 'DejaVu Sans', 'size': ctx['fs1']})
    ax[1, col_idx].set_title(title_gamma, fontdict={'family': 'DejaVu Sans', 'size': ctx['fs1']})
    ax[0, col_idx].set_xlabel('$k_y$*$\\rho_s$', fontdict={'family': 'DejaVu Sans', 'size': ctx['fs1']}, labelpad=5)
    ax[1, col_idx].set_xlabel('$k_y$*$\\rho_s$', fontdict={'family': 'DejaVu Sans', 'size': ctx['fs1']}, labelpad=5)

    if ctx.get('plot_log_x', False):
        ax[0, col_idx].set_xscale('log')
        ax[1, col_idx].set_xscale('log')
    if ctx.get('plot_log_y', False):
        ax[0, col_idx].set_yscale('log')
        ax[1, col_idx].set_yscale('log')

    finalize_axis_legend(ax[0, col_idx], ctx)
    finalize_axis_legend(ax[1, col_idx], ctx)


def plot_curves_no_error_2x2(ax, ctx, curves_mode1, curves_mode2):
    """Plot two eigen-modes in one 2x2 page, left-right by mode."""
    if ax is None:
        return
    _plot_no_error_column(ax, 0, ctx, curves_mode1, 1)
    _plot_no_error_column(ax, 1, ctx, curves_mode2, 2)
    apply_color_order_to_axes(ax, ctx)


def plot_curve_group(ax_2d, ctx, curves):
    """Render a list of prepared curves to axes."""
    for curve in curves:
        plot_on_axes(
            ax_2d, ctx,
            curve['label'],
            curve['ky'], curve['omega'], curve['gamma'],
            curve['omega_error'], curve['gamma_error'],
            error_label=curve.get('error_label', curve['label']),
            show_error=curve.get('show_error', True),
        )
    apply_color_order_to_axes(ax_2d, ctx)


def _plot_compare_page(fn, ctx, page_id, page_title, cgyro_curves, tglf_curves):
    """
    Render one compare page for CGYRO_vs_TGLF-like modes.

    Handles both:
    - standard 2x2 omega/gamma(+error) pages
    - γ/γ_ref pages (single or split panel mode)
    """
    page_id = str(page_id)
    page_title = str(page_title)
    all_curves = cgyro_curves + tglf_curves
    if not cgyro_curves or not tglf_curves:
        raise ValueError('No valid curves in one model for page {}. Check the selected source and values.'.format(page_id))
    if not ctx.get('plot_gamma_ratio'):
        apply_cross_model_error_if_applicable(ctx, cgyro_curves, tglf_curves)

    if ctx.get('plot_gamma_ratio', False):
        if ctx.get('gamma_ref_split_panels', False):
            fig_ratio, ax_ratio = fn.subplots(
                nrows=1,
                ncols=2,
                figsize=DEFAULT_FIGSIZE_1X2,
                label=f'{page_id}_gamma_ratio_split',
                sharex=False,
                sharey=True,
                squeeze=False,
            )
            apply_figure_layout(fig_ratio, ctx)
            plot_gamma_ratio_compare_page(
                ax_ratio[0, 0], ctx, _filter_curves_by_kind(all_curves, 'TGLF'),
                page_title=f'{page_title} [TGLF]'
            )
            plot_gamma_ratio_compare_page(
                ax_ratio[0, 1], ctx, _filter_curves_by_kind(all_curves, 'CGYRO'),
                page_title=f'{page_title} [CGYRO]'
            )
        else:
            fig_ratio, ax_ratio = fn.subplots(
                nrows=1,
                ncols=1,
                figsize=DEFAULT_FIGSIZE_GAMMA_RATIO,
                label=f'{page_id}_gamma_ratio',
                sharex=False,
                sharey=False,
                squeeze=False,
            )
            apply_figure_layout(fig_ratio, ctx)
            plot_gamma_ratio_compare_page(
                ax_ratio[0, 0], ctx, all_curves, page_title=page_title
            )
        return

    if ctx.get('error_flag') == 'No_error' and ctx.get('comparison_layout', 'Overlay') == 'Overlay':
        fig, axes = fn.subplots(nrows=2, ncols=1, figsize=(10., 6.5), label=page_id,
                                sharex=True, sharey=False, squeeze=False)
        apply_figure_layout(fig, ctx)
        _plot_model_curves_one_column(axes, 0, ctx, all_curves, '')
        apply_color_order_to_axes(axes, ctx)
        fig.suptitle(page_title, fontsize=ctx['fs1'])
        return

    fig2d, ax_2d = fn.subplots(
        nrows=2,
        ncols=2,
        figsize=DEFAULT_FIGSIZE_2X2,
        label=page_id,
        sharex=True,
        sharey=False,
        squeeze=False,
    )
    apply_figure_layout(fig2d, ctx)
    fig2d.suptitle(page_title, fontsize=ctx['fs1'])

    if str(ctx.get('error_flag', 'CGYRO')) == 'No_error':
        plot_curves_split_no_error_2x2(ax_2d, ctx, tglf_curves, cgyro_curves)
    else:
        plot_curve_group(ax_2d, ctx, all_curves)
