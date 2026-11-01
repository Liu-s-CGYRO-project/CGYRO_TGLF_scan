"""Render prepared CGYRO data; finalize color, legends and layout once per page."""
from builtins import ImportError, RuntimeWarning, any, dict, enumerate, float, len, list, max, min, repr, str, zip
import math
import warnings
import numpy as np
from OMFITlib_compare_core import apply_divide_by_ky, divide_title
from OMFITlib_compare_cgyro_data import filter_single_ky, grid_scan_points
from OMFITlib_compare_cgyro_selection import _legend_nr_prefix
from OMFITlib_cgyro_scan_view import coordinate_label, slice_caption
from OMFITlib_compare_style import (
    _default_color_cycle, _sort_label_handle_pairs, apply_figure_layout, cgyro_case_caption,
    compact_scan_value, finalize_axis_legend)

FIGURE_SIZES = {'Plot 2D': (12.5, 6.5), 'Plot single ky': (13., 5.6),
                'Plot time traces': (13., 5.6),
                'Plot γ/γ_ref': (9., 5.4), 'Plot eigen ball': (12.5, 6.5),
                'Plot 3D': (14., 5.9)}


def _color_group_label(label):
    for suffix in (', Re', ', Im', ', |.|'):
        if label.endswith(suffix):
            return label[:-len(suffix)]
    return label


def apply_color_order_to_axes(axes_obj, ctx):
    """Match every panel's case colors, including Re/Im and error-panel lines."""
    axes = np.asarray(axes_obj, dtype=object).ravel()
    representatives = {}
    for axis in axes:
        for line in axis.get_lines():
            label = str(line.get_label())
            if not label.startswith('_'):
                representatives.setdefault(_color_group_label(label), label)
    if not representatives:
        return
    ordered = _sort_label_handle_pairs(list(representatives.values()), list(representatives), ctx)
    colors = _default_color_cycle()
    mapping = {group: colors[index % len(colors)] for index, (_, group) in enumerate(ordered)}
    for axis in axes:
        for line in axis.get_lines():
            group = _color_group_label(str(line.get_label()))
            if group in mapping:
                line.set_color(mapping[group])


def _adjust_labels(texts, axis):
    if not texts:
        return
    try:
        from adjustText import adjust_text
    except ImportError:
        warnings.warn('adjustText is unavailable; peak labels keep their default positions.', RuntimeWarning)
        return
    adjust_text(texts, ax=axis, only_move={'text': 'y'},
                arrowprops=dict(arrowstyle='->', color='red', lw=1.5))


def _item_prefix(item, ctx):
    source = item.get('source_label', '')
    return (source + ' · ' if source else '') + _legend_nr_prefix(ctx, item['nr'])


def _label(item, ctx):
    metadata = item.get('slice_meta', {})
    if metadata.get('convergence', False):
        label = '{}={}'.format(metadata['axis'], compact_scan_value(item['value']))
        if item['value'] == metadata['baseline_value']:
            label += ' · 基准'
        if 'trace' in item:
            label += ', ky={:.4g}'.format(item['trace']['ky'])
        source = item.get('source_label', '')
        return (source + ' · ' if source else '') + label
    if metadata:
        return _item_prefix(item, ctx) + coordinate_label(metadata, item['value'])
    return '{}{}={}'.format(_item_prefix(item, ctx), item['para'], compact_scan_value(item['value']))


def _spectra(axes, items, ctx):
    annotations = []
    for item in items:
        ky, omega, gamma, omega_error, gamma_error, _, _ = item['series']
        y_omega, y_gamma, title_omega, title_gamma = apply_divide_by_ky(
            ky, omega, gamma, ctx['divide_by_ky'], ctx['divide_by_ky2'])
        label = _label(item, ctx)
        axes[0, 0].plot(ky, y_omega, label=label, linewidth=ctx['lw'])
        axes[1, 0].plot(ky, y_gamma, label=label, linewidth=ctx['lw'])
        if axes.shape[1] == 2:
            axes[0, 1].plot(ky, omega_error, label=label, linewidth=ctx['lw'])
            axes[1, 1].plot(ky, gamma_error, label=label, linewidth=ctx['lw'])
        if ctx['highlight_max_gamma']:
            valid = np.isfinite(y_gamma) & np.isfinite(ky)
            if ctx.get('plot_log_x', None):
                valid &= ky > 0
            if ctx.get('plot_log_y', None):
                valid &= y_gamma > 0
            indices = np.flatnonzero(valid)
            if len(indices):
                index = indices[np.argmax(y_gamma[indices])]
                x, y = ky[index], y_gamma[index]
                axes[1, 0].plot(x, y, 'ro', markersize=ctx['ms'])
                annotations.append(axes[1, 0].annotate('({:.3g}, {:.3g})'.format(x, y), (x, y)))
    axes[0, 0].set_title(title_omega)
    axes[1, 0].set_title(title_gamma)
    if axes.shape[1] == 2:
        axes[0, 1].set_title('Relative time fluctuation of omega')
        axes[1, 1].set_title('Relative time fluctuation of gamma')
    for axis in axes[-1, :]:
        axis.set_xlabel(r'$k_y\rho_s$')
    return annotations


def _time_traces(axes, items, ctx):
    """A page owns one actual ky; both panels use identical curve identities."""
    for item in items:
        trace = item['trace']
        for axis, field in zip(axes.ravel(), ('omega', 'gamma')):
            values = np.asarray(trace[field], dtype=float)
            axis.plot(trace['time'], np.where(np.isfinite(values), values, np.nan),
                      label=_label(item, ctx), linewidth=ctx['lw'],
                      marker='o' if len(trace['time']) == 1 else None, markersize=ctx['ms'])
    for axis, symbol in zip(axes.ravel(), (r'$\omega$', r'$\gamma$')):
        axis.set_xlabel(r'Time ($a/c_s$)')
        axis.set_ylabel(symbol + r' ($c_s/a$)')
        axis.set_title(symbol + ' vs time')


def _single_ky(axes, items, ctx):
    for item in items:
        x, y, omega, gamma = grid_scan_points(*item['cloud'], parameter_values=item.get('scan_values', None))
        selected = filter_single_ky(x, ctx['selected_single_ky'])
        for ky in selected:
            column = np.flatnonzero(x == ky)[0]
            # A missing scan value stays NaN, leaving a visible gap in the curve.
            label = '{}{}, ky={:.4g}'.format(_item_prefix(item, ctx), slice_caption(item.get('slice_meta', {}), item['para']), ky)
            for axis, values in zip(axes.ravel(), (omega[:, column], gamma[:, column])):
                axis.plot(y, values, 'o-', label=label, linewidth=ctx['lw'], markersize=ctx['ms'])
    parameters = list(dict.fromkeys(item.get('axis_name', item['para']) for item in items))
    for axis, field in zip(axes.ravel(), ('omega', 'gamma')):
        axis.set_xlabel(str(parameters[0]) if len(parameters) == 1 else 'parameter value')
        axis.set_ylabel(divide_title(ctx, field))
        axis.set_title(divide_title(ctx, field) + ' vs scan parameter')


def _ratio(axes, items, ctx):
    axis = axes[0, 0]
    for item in items:
        x, y, reference = item['ratio']
        axis.plot(x, y, 'o-', linewidth=ctx['lw'], markersize=ctx['ms'],
                  label='{}{}, ref={:g}'.format(_item_prefix(item, ctx), slice_caption(item.get('slice_meta', {}), item['para']), reference))
    parameters = list(dict.fromkeys(item.get('axis_name', item['para']) for item in items))
    axis.set_xlabel(str(parameters[0]) if len(parameters) == 1 else 'parameter value')
    axis.set_ylabel(r'$\gamma/\gamma_{\mathrm{ref}}$')
    axis.set_title('Growth-rate ratio')
    axis.axhline(1., color='.6', linewidth=.8, linestyle=':', label='_reference')


def plot_complex_field(axis, x, y, label_base, ctx):
    if ctx['eigen_abs']:
        axis.plot(x, np.abs(y), label=label_base + ', |.|', linewidth=ctx['lw'])
    else:
        axis.plot(x, np.real(y), label=label_base + ', Re', linewidth=ctx['lw'])
        axis.plot(x, np.imag(y), '--', label=label_base + ', Im', linewidth=ctx['lw'])


def _eigen(axes, items, ctx):
    fields = (('phi_b', r'$\phi$'), ('epar_b', r'$E_{\parallel}$'),
              ('apar_b', r'$A_{\parallel}$'), ('bpar_b', r'$B_{\parallel}$'))
    for axis, (field, title) in zip(axes.ravel(), fields):
        available = False
        for item in items:
            curve = item['eigen']
            present = field == 'phi_b' or curve.get('has_' + field.split('_')[0], False)
            if present:
                available = True
                plot_complex_field(axis, curve['theta_over_pi'], curve[field],
                                   _label(item, ctx) + ', ky={:.4g}'.format(item['ky']), ctx)
        axis.set_title(('|' + title + '|') if ctx['eigen_abs'] else 'Re / Im (' + title + ')')
        if not available:
            axis.text(.5, .5, 'No valid saved ' + title + ' data',
                      ha='center', va='center', transform=axis.transAxes)
    for axis in axes[-1, :]:
        axis.set_xlabel(r'$\theta/\pi$')


def _surface(fig, axes, item, ctx):
    ky, parameter, omega, gamma = item['cloud']
    x, y, omega_grid, gamma_grid = grid_scan_points(ky, parameter, omega, gamma,
                                                  parameter_values=item.get('scan_values', None))
    xgrid, ygrid = np.meshgrid(x, y)
    for axis, field, values, grid, cmap in zip(axes.ravel(), ('omega', 'gamma'),
                                             (omega, gamma), (omega_grid, gamma_grid), ('viridis', 'plasma')):
        # Incomplete and one-dimensional scans cannot define a rectangular surface.
        if min(grid.shape) >= 2 and np.all(np.isfinite(grid)):
            artist = axis.plot_surface(xgrid, ygrid, grid, cmap=cmap, alpha=.85)
        else:
            artist = axis.scatter(ky, parameter, values, c=values, cmap=cmap, s=28)
        axis.set_xlabel(r'$k_y\rho_s$')
        axis.set_ylabel(str(item.get('axis_name', item['para'])))
        axis.set_zlabel(divide_title(ctx, field))
        axis.set_title('{} vs {} ({})'.format(divide_title(ctx, field), slice_caption(item.get('slice_meta', {}), item['para']),
                                            cgyro_case_caption(item['nr'], include_radius=True)))
        for name, coordinates in (('x', ky), ('y', parameter), ('z', values)):
            if ctx.get('plot_log_' + name, None):
                if np.all(coordinates > 0):
                    getattr(axis, 'set_' + name + 'scale')('log')
                else:
                    warnings.warn('3D log {} requires positive data; this axis remains linear.'.format(name), RuntimeWarning)
        # Keep each 3D axis in its original subplot cell on older Linux Matplotlib.
        fig.colorbar(artist, ax=axis, shrink=.55, pad=.12, use_gridspec=False)


def render_page(notebook, ctx, label, items):
    """Render one nonempty group in an OMFIT notebook, including 3D pages."""
    mode = 'Plot γ/γ_ref' if ctx['plot_gamma_ratio'] else ctx['plot_mode']
    rows, columns = {'Plot 2D': (2, 2 if ctx['error_flag'] == 'CGYRO' else 1),
                     'Plot single ky': (1, 2), 'Plot γ/γ_ref': (1, 1),
                     'Plot time traces': (1, 2),
                     'Plot eigen ball': (2, 2), 'Plot 3D': (1, 2)}[mode]
    options = {'subplot_kw': {'projection': '3d'}} if mode == 'Plot 3D' else {}
    fig, axes = notebook.subplots(nrows=rows, ncols=columns, label=label, squeeze=False,
                                  figsize=FIGURE_SIZES[mode], sharex=mode in ('Plot 2D', 'Plot eigen ball', 'Plot time traces'), **options)
    annotations = []
    if mode == 'Plot 3D':
        _surface(fig, axes, items[0], ctx)
    else:
        renderer = {'Plot 2D': _spectra, 'Plot single ky': _single_ky,
                    'Plot time traces': _time_traces,
                    'Plot γ/γ_ref': _ratio, 'Plot eigen ball': _eigen}[mode]
        annotations = renderer(axes, items, ctx) or []
        apply_color_order_to_axes(axes, ctx)
        legend_rows = 0
        for axis in axes.ravel():
            if ctx.get('plot_log_x', None):
                axis.set_xscale('log')
            if ctx.get('plot_log_y', None):
                axis.set_yscale('log')
            labels = axis.get_legend_handles_labels()[1]
            if labels:
                columns = 2 if len(labels) > 10 and ctx['style'].get('legend_location', None) != 'outside' else 1
                legend_rows = max(legend_rows, math.ceil(len(labels) / columns))
                finalize_axis_legend(axis, dict(ctx, _legend_columns=columns))
            for spine in axis.spines.values():
                spine.set_linewidth(ctx['bwith'])
        if not ctx['style'].get('figure_height', None):
            height = max(fig.get_figheight(), rows * (.8 + legend_rows * ctx['fs2'] * 1.5 / 72.))
            fig.set_size_inches(fig.get_figwidth(), height, forward=True)
    for axis in axes.ravel():
        axis.title.set_fontsize(ctx['fs1'])
        axis.xaxis.label.set_size(ctx['fs1'])
        axis.yaxis.label.set_size(ctx['fs1'])
    apply_figure_layout(fig, ctx)
    if annotations:
        _adjust_labels(annotations, axes[1, 0])
    return fig


def _convergence_colors(axes, items, ctx):
    """Keep colors and legend toggles local to an exact one-variable group."""
    apply_color_order_to_axes(axes, ctx)
    baseline_labels = [_label(item, ctx) for item in items if 'value' in item
                       and item['value'] == item['slice_meta']['baseline_value']]
    group = repr((items[0]['nr'], items[0]['para'], items[0].get('source_label', '')))
    for axis in axes.ravel():
        for line in axis.get_lines():
            label = str(line.get_label())
            if label.startswith('_'):
                continue
            # Eigenmode labels append ky and Re/Im after the same curve label.
            base = _color_group_label(label)
            line._comparison_identity = group + ':' + base
            if any(base == value or base.startswith(value + ', ky=') for value in baseline_labels):
                line.set_color('black')
                line.set_linestyle(':' if label.endswith(', Im') else '--')
                line.set_zorder(3)


def _convergence_reference(axes, items, ctx, mode):
    """Mark the actual baseline samples in scan-coordinate and surface views."""
    metadata = items[0]['slice_meta']
    baseline = metadata['baseline_value']
    label = '{}={} · 基准'.format(metadata['axis'], compact_scan_value(baseline))
    for item in items:
        if 'cloud' not in item:
            continue
        ky, parameter, omega, gamma = item['cloud']
        selected = (parameter == baseline) & np.isfinite(omega) & np.isfinite(gamma)
        if not np.any(selected):
            continue
        for axis, values in zip(axes.ravel(), (omega, gamma)):
            if mode == 'Plot 3D':
                line, = axis.plot(ky[selected], parameter[selected], values[selected],
                                  color='black', linestyle='--', linewidth=ctx['lw'], label=label)
            else:
                line = axis.axvline(baseline, color='black', linestyle='--', linewidth=ctx['lw'], label=label)
            line._comparison_identity = repr((item['nr'], item['para'], item.get('source_label', ''))) + ':baseline'
        return True
    if mode == 'Plot γ/γ_ref':
        for item in items:
            x, y, _ = item['ratio']
            if np.any((x == baseline) & np.isfinite(y)):
                line = axes[0, 0].axvline(baseline, color='black', linestyle='--', linewidth=ctx['lw'], label=label)
                line._comparison_identity = repr((item['nr'], item['para'], item.get('source_label', ''))) + ':baseline'
                return True
    return False


def render_convergence_page(notebook, ctx, label, items):
    """One case page, one exact scan direction per column, using prepared data.

    The caller resolves common baselines from RUN_DB before rendering. Neither
    this function nor its helpers open a result or infer a missing baseline.
    Different fixed-coordinate groups remain separate even for the same axis.
    """
    mode = 'Plot γ/γ_ref' if ctx['plot_gamma_ratio'] else ctx['plot_mode']
    groups = {}
    for item in items:
        groups.setdefault((item['nr'], item['para']), []).append(item)
    if not groups:
        return None
    rows = {'Plot 2D': 4 if ctx['error_flag'] == 'CGYRO' else 2,
            'Plot single ky': 2, 'Plot time traces': 2, 'Plot γ/γ_ref': 1,
            'Plot eigen ball': 4, 'Plot 3D': 2}[mode]
    options = {'subplot_kw': {'projection': '3d'}} if mode == 'Plot 3D' else {}
    fig, axes = notebook.subplots(nrows=rows, ncols=len(groups), label=label, squeeze=False,
                                  figsize=(max(7., 4.5 * len(groups)), max(4., rows * 3.1)),
                                  sharex='col' if mode != 'Plot 3D' else False, **options)
    for column, group in enumerate(groups.values()):
        panels = axes[:, column:column + 1]
        metadata = group[0]['slice_meta']
        annotations = []
        if mode == 'Plot 2D':
            spectra_axes = (np.asarray([[panels[0, 0], panels[2, 0]],
                                       [panels[1, 0], panels[3, 0]]]) if rows == 4 else panels)
            annotations = _spectra(spectra_axes, group, ctx)
        elif mode == 'Plot 3D':
            _surface(fig, panels, group[0], ctx)
        else:
            {'Plot single ky': _single_ky, 'Plot time traces': _time_traces,
             'Plot γ/γ_ref': _ratio, 'Plot eigen ball': _eigen}[mode](panels, group, ctx)
        _convergence_colors(panels, group, ctx)
        if mode in ('Plot single ky', 'Plot 3D', 'Plot γ/γ_ref'):
            has_baseline = _convergence_reference(panels, group, ctx, mode)
        else:
            has_baseline = any(item['value'] == metadata['baseline_value'] for item in group)
        caption = metadata.get('label', metadata['axis'])
        caption += '\n基准 {}={}'.format(metadata['axis'], compact_scan_value(metadata['baseline_value']))
        if not has_baseline:
            caption += '（结果缺失）'
        panels[0, 0].set_title(caption + '\n' + panels[0, 0].get_title())
        for axis in panels.ravel():
            if mode != 'Plot 3D':
                if ctx.get('plot_log_x', False):
                    axis.set_xscale('log')
                if ctx.get('plot_log_y', False):
                    axis.set_yscale('log')
                for spine in axis.spines.values():
                    spine.set_linewidth(ctx['bwith'])
            if axis.get_legend_handles_labels()[1]:
                finalize_axis_legend(axis, dict(ctx, _legend_columns=1))
            axis.title.set_fontsize(ctx['fs1'])
            axis.xaxis.label.set_size(ctx['fs1'])
            axis.yaxis.label.set_size(ctx['fs1'])
        if annotations:
            _adjust_labels(annotations, panels[1, 0])
    title = label
    if mode not in ('Plot time traces', 'Plot eigen ball'):
        title += '\n统计窗口：末尾 {:.4g}% 样本（有足够样本时至少取 2 个）'.format(100 * ctx.get('ave_window', .02))
    fig.suptitle(title, fontsize=ctx['fs1'])
    apply_figure_layout(fig, ctx)
    return fig
