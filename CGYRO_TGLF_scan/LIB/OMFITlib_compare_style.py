"""CGYRO/TGLF comparison: style.

Extracted from the reviewed project; data is read from the supplied OMFIT tree.
"""
from matplotlib import rcParams
from OMFITlib_cgyro_archive import canonical_case_key, case_constants, case_parts
from OMFITlib_plot_window import fit_figure_window
# OMFIT libraries inherit a pylab namespace; keep Python scalar/iterator semantics.
from builtins import (
    Exception,
    TypeError,
    ValueError,
    abs,
    any,
    bool,
    enumerate,
    float,
    getattr,
    iter,
    len,
    list,
    max,
    min,
    next,
    object,
    range,
    repr,
    set,
    sorted,
    str,
    zip,
)

import re
from numpy import (
    array,
)


def apply_figure_layout(fig, ctx=None):
    """Compact, configurable figure size without process-wide rcParams changes."""
    if fig is None:
        return
    style = (ctx or {}).get('style', {})
    current = fig.get_size_inches()
    width = float(style.get('figure_width', 0)) or current[0]
    height = float(style.get('figure_height', 0)) or current[1]
    fig.set_size_inches(width, height, forward=True)
    if getattr(fig, 'set_layout_engine', None) is not None:
        fig.set_layout_engine('constrained', w_pad=.08, h_pad=.08, wspace=.08, hspace=.08)
    else:
        fig.set_constrained_layout(True)
        fig.set_constrained_layout_pads(w_pad=.08, h_pad=.08, wspace=.08, hspace=.08)
    for ax in fig.axes:
        ax.tick_params(labelsize=max(7, float(style.get('font_size', 12)) - 2))
        if style.get('show_grid', True):
            ax.grid(True, alpha=.18)
        else:
            ax.grid(False)
    fit_figure_window(fig)


def enable_legend_picking(ax):
    """Toggle true visibility across a figure, including legends outside the axes.

    Replacing/reordering a legend replaces its callback; repeated plotting never
    accumulates old callbacks or stale legend instances.
    """
    figure = ax.figure
    old = getattr(ax, '_compare_legend_cid', None)
    if old is not None:
        figure.canvas.mpl_disconnect(old)
    legend = ax.get_legend()
    if legend is None:
        return

    def identity(line):
        return str(getattr(line, '_comparison_identity', line.get_label()))

    def entries(current):
        # Legend texts, proxy handles and original artists share legend order,
        # including column-major packing and custom sorting. Retain artists
        # rather than looking them up by a possibly duplicated display label.
        proxies = getattr(current, 'legend_handles', None)
        if proxies is None:  # Matplotlib before 3.7.
            proxies = getattr(current, 'legendHandles', [])
        return zip(current.get_texts(), proxies, getattr(current, '_compare_sources', []))

    def refresh():
        for axes in figure.axes:
            current = axes.get_legend()
            if current is None:
                continue
            for text, proxy, source in entries(current):
                visible = source.get_visible()
                text.set_alpha(1. if visible else .25)
                proxy.set_alpha(1. if visible else .25)

    def click(event):
        if ax.get_legend() is not legend or event.button != 1 or event.x is None or event.y is None:
            return
        # An outside legend has event.inaxes == None; use its displayed bounds.
        renderer = figure.canvas.get_renderer()
        if not legend.get_window_extent(renderer).contains(event.x, event.y):
            return
        for text, proxy, source in entries(legend):
            bounds = text.get_window_extent(renderer)
            handle = proxy.get_window_extent(renderer)
            # Include the handle-to-text gap, but not another column or empty
            # legend space. Re-measure on each click after dragging/resizing.
            left, right = min(bounds.x0, handle.x0), max(bounds.x1, handle.x1)
            if not (left - 2 <= event.x <= right + 2 and bounds.y0 - 2 <= event.y <= bounds.y1 + 2):
                continue
            key, visible = identity(source), not source.get_visible()
            for axes in figure.axes:
                for line in axes.get_lines():
                    if identity(line) == key:
                        line.set_visible(visible)
            refresh()
            figure.canvas.draw_idle()
            return

    ax._compare_legend_cid = figure.canvas.mpl_connect('button_press_event', click)
    refresh()


def _legend_fontsize_from_existing(legend, fallback):
    """Prefer existing legend text size so reordering does not unexpectedly resize."""
    if legend is None:
        return fallback
    try:
        texts = legend.get_texts()
        if len(texts) > 0:
            return float(texts[0].get_fontsize())
    except Exception:
        pass
    return fallback


def reorder_legend(ax, ctx=None, fontsize=None):
    """
    Apply configured legend ordering mode to current axes.

    Returns created legend object, or None when no labeled handles exist.
    """
    handles, labels = ax.get_legend_handles_labels()
    if len(handles) == 0:
        return None

    ctx = ctx or {}
    pairs = _sort_label_handle_pairs(labels, handles, ctx)
    labels_sorted = [p[0] for p in pairs]
    handles_sorted = [p[1] for p in pairs]

    if fontsize is None:
        fallback_fs = ctx.get('fs2', 10)
        fontsize = _legend_fontsize_from_existing(ax.get_legend(), fallback_fs)

    location = ctx.get('style', {}).get('legend_location', 'best')
    options = {'loc': location}
    if location == 'outside':
        options = {'loc': 'upper left', 'bbox_to_anchor': (1.02, 1.)}
    options['ncol'] = ctx.get('_legend_columns', 1)
    legend_new = ax.legend(handles_sorted, labels_sorted, fontsize=fontsize, framealpha=.85, **options)
    legend_new._compare_sources = handles_sorted
    try:
        legend_new.set_draggable(True)
    except Exception:
        pass
    return legend_new


def finalize_axis_legend(ax, ctx, fontsize=None):
    """
    Build/reorder one axis legend and enable click-to-hide behavior.

    Returns True when legend exists (i.e., at least one labeled line).
    """
    legend_obj = reorder_legend(ax, ctx, fontsize=fontsize)
    if legend_obj is None:
        return False
    enable_legend_picking(ax)
    return True


def _legend_natural_key(text):
    """Natural-sort key helper used by legend reordering."""
    parts = re.split(r'(\d+(?:\.\d+)?)', str(text))
    out = []
    for p in parts:
        if len(p) == 0:
            continue
        try:
            out.append((0, float(p)))
        except Exception:
            out.append((1, p.lower()))
    return out


def _legend_manual_tokens(text):
    """Split manual legend-order text into normalized non-empty tokens."""
    return [x.strip() for x in str(text).split(',') if len(x.strip()) > 0]


def compact_scan_value(value):
    """Trim numeric padding while retaining the float's round-trip precision."""
    try:
        text = repr(float(value))
        return text[:-2] if text.endswith('.0') else text
    except (TypeError, ValueError):
        return str(value)


def cgyro_case_caption(case, peers=None, include_radius=False):
    """Short English display name; case lookup always keeps the original key."""
    parts = case_parts(case)
    if parts is None:
        return canonical_case_key(case)
    nr, rho, ion = parts
    related = [case_parts(peer) for peer in (peers if peers is not None else [case])]
    caption = 'Original' if ion == 'BASE' else 'Unidentified' if ion == 'UNKNOWN' else ion
    show_radius = include_radius or any(part is None or part[1] != rho or
                                       (rho == 'unknown' and part[0] != nr) for part in related)
    if show_radius:
        scope = 'nr=' + nr if rho == 'unknown' else 'rho=' + compact_scan_value(rho)
        if rho == 'unknown' and nr.startswith('RMIN='):
            scope = nr
        elif rho == 'unknown' and nr.startswith('legacy-output-'):
            scope = 'Legacy ' + nr.rsplit('-', 1)[-1]
        caption = scope + ', ' + caption
    if any(part is not None and part[0] != nr and part[1:] == (rho, ion) for part in related):
        if not (show_radius and rho == 'unknown'):
            caption += ' [nr=' + nr + ']'
    for name, number in case_constants(case).items():
        caption += ', {}={}'.format(name, number)
    return caption


def _legend_mass_key(text):
    """H/D/T order, preferring explicit case identity over legacy name tokens."""
    text = str(text)
    order = {'H': 0, 'D': 1, 'T': 2}
    case = re.search(r'(?<![A-Za-z0-9])ion(?:_case)?\s*=\s*([A-Za-z]+)(?![A-Za-z0-9])', text, re.IGNORECASE)
    if case is not None:
        rank = order.get(case.group(1).upper(), 3)
    else:
        # Underscores delimit old parameter suffixes, but letters within
        # N_THETA / TGLF must never be mistaken for isotope names.
        header = text.split('·', 1)[0]
        ions = set(re.findall(r'(?<![A-Za-z0-9])([HDT])(?![A-Za-z0-9])', header))
        rank = order[next(iter(ions))] if len(ions) == 1 else 3
    return rank, _legend_natural_key(text)


def _sort_label_handle_pairs(labels, handles, ctx):
    """Sort (label, handle) pairs using the active legend ordering settings."""
    mode = ctx.get('legend_order_mode', 'Plot order')
    custom_text = ctx.get('legend_order_text', '')
    pairs = list(zip(labels, handles))

    if mode == 'Alphabetical':
        return sorted(pairs, key=lambda x: str(x[0]).lower())
    if mode == 'Reverse alphabetical':
        return sorted(pairs, key=lambda x: str(x[0]).lower(), reverse=True)
    if mode == 'Natural':
        return sorted(pairs, key=lambda x: _legend_natural_key(x[0]))
    if mode == 'Isotope mass':
        return sorted(pairs, key=lambda x: _legend_mass_key(getattr(x[1], '_comparison_identity', x[0])))
    if mode == 'Manual order':
        keys = _legend_manual_tokens(custom_text)

        def sort_key(item):
            label = str(item[0])
            low = label.lower()
            for i, key in enumerate(keys):
                if key.startswith('re:'):
                    pattern = key[3:].strip()
                    if len(pattern) > 0:
                        try:
                            if re.search(pattern, label):
                                return (0, i, _legend_natural_key(label))
                        except Exception:
                            pass
                if key.lower() in low:
                    return (0, i, _legend_natural_key(label))
            return (1, len(keys), _legend_natural_key(label))

        return sorted(pairs, key=sort_key)

    return pairs


def _default_color_cycle():
    """Return the line-color palette used by the cgyro_comparison GUI."""
    return list(rcParams['axes.prop_cycle'].by_key()['color'])


def apply_color_order_to_axes(axes_obj, ctx):
    """
    Re-assign colors by current legend order so color rank follows sorted label rank.

    This keeps same-label lines synchronized in one figure page.
    """
    try:
        axes_list = list(array(axes_obj, dtype=object).ravel())
    except Exception:
        axes_list = [axes_obj]

    labels_in_plot_order = []
    for axi in axes_list:
        for ln in axi.get_lines():
            label = str(getattr(ln, '_comparison_identity', ln.get_label()))
            if label.startswith('_'):
                continue
            if label not in labels_in_plot_order:
                labels_in_plot_order.append(label)

    if len(labels_in_plot_order) == 0:
        return

    sorted_pairs = _sort_label_handle_pairs(labels_in_plot_order, labels_in_plot_order, ctx)
    sorted_labels = [p[0] for p in sorted_pairs]
    colors = _default_color_cycle()
    label_to_color = {lb: colors[i % len(colors)] for i, lb in enumerate(sorted_labels)}

    for axi in axes_list:
        for ln in axi.get_lines():
            label = str(getattr(ln, '_comparison_identity', ln.get_label()))
            if label.startswith('_'):
                continue
            if label in label_to_color:
                ln.set_color(label_to_color[label])

        if axi.get_legend() is not None:
            finalize_axis_legend(axi, ctx)


def style_2d_axes(ax, bwith):
    """Set consistent axis border width for all 2x2 subplots."""
    for r in range(2):
        for c in range(2):
            ax[r, c].spines['bottom'].set_linewidth(bwith)
            ax[r, c].spines['left'].set_linewidth(bwith)
            ax[r, c].spines['top'].set_linewidth(bwith)
            ax[r, c].spines['right'].set_linewidth(bwith)


def _row_align_axes_limits(ax):
    """Force left/right panels in each row to share identical x/y limits."""
    for row_idx in [0, 1]:
        row_axes = [ax[row_idx, 0], ax[row_idx, 1]]
        active_axes = []
        for axi in row_axes:
            visible_lines = [
                ln for ln in axi.get_lines()
                if (not str(ln.get_label()).startswith('_')) and ln.get_visible()
            ]
            if len(visible_lines) > 0:
                active_axes.append(axi)

        if len(active_axes) == 0:
            continue

        xlims = [axi.get_xlim() for axi in active_axes]
        ylims = [axi.get_ylim() for axi in active_axes]
        x_min = min([x[0] for x in xlims])
        x_max = max([x[1] for x in xlims])
        y_min = min([y[0] for y in ylims])
        y_max = max([y[1] for y in ylims])

        if x_min >= x_max or y_min >= y_max:
            continue

        for axi in row_axes:
            axi.set_xlim((x_min, x_max))
            axi.set_ylim((y_min, y_max))


def style_two_panel_xy_axes(ax, ctx, title_left, title_right, xlabel_left, xlabel_right=None):
    """Apply consistent styling for 1x2 2D panels."""
    if xlabel_right is None:
        xlabel_right = xlabel_left

    ax[0, 0].set_title(title_left, fontdict={'size': ctx['fs1']})
    ax[0, 1].set_title(title_right, fontdict={'size': ctx['fs1']})
    ax[0, 0].set_xlabel(str(xlabel_left), fontdict={'size': ctx['fs1']}, labelpad=5)
    ax[0, 1].set_xlabel(str(xlabel_right), fontdict={'size': ctx['fs1']}, labelpad=5)

    if ctx.get('plot_log_x', False):
        ax[0, 0].set_xscale('log')
        ax[0, 1].set_xscale('log')
    if ctx.get('plot_log_y', False):
        ax[0, 0].set_yscale('log')
        ax[0, 1].set_yscale('log')

    finalize_axis_legend(ax[0, 0], ctx)
    finalize_axis_legend(ax[0, 1], ctx)


DEFAULT_FIGSIZE_2X2 = (12.5, 6.5)


DEFAULT_FIGSIZE_1X2 = (11.5, 5.5)


DEFAULT_FIGSIZE_3D_GRID = (12.0, 7.0)


DEFAULT_FIGSIZE_GAMMA_RATIO = (10.0, 6.5)


CGYRO_COMPARISON_LINE_COLOR_PALETTE = [
    "#F14040",
    "#1A6FDF",
    "#37AD6B",
    "#B177DE",
    "#CC9900",
    "#00CBCC",
    "#7D4E4E",
    "#8E8E00",
    "#FB6501",
    "#6699CC",
    "#6FB802",
]
