"""CGYRO/TGLF comparison: style.

Extracted from the reviewed project; data is read from the supplied OMFIT tree.
"""

# OMFIT libraries inherit a pylab namespace; keep Python scalar/iterator semantics.
from builtins import (
    Exception,
    abs,
    bool,
    enumerate,
    float,
    getattr,
    len,
    list,
    max,
    min,
    object,
    range,
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

    def refresh():
        for axes in figure.axes:
            current = axes.get_legend()
            if current is None:
                continue
            by_label = {str(line.get_label()): line for line in axes.get_lines()}
            handles = current.get_lines()
            for idx, text in enumerate(current.get_texts()):
                line = by_label.get(text.get_text())
                visible = line is None or line.get_visible()
                text.set_alpha(1. if visible else .25)
                if idx < len(handles):
                    handles[idx].set_alpha(1. if visible else .25)

    def click(event):
        if event.button != 1 or event.x is None or event.y is None:
            return
        # An outside legend has event.inaxes == None; use its displayed bounds.
        renderer = figure.canvas.get_renderer()
        if not legend.get_window_extent(renderer).contains(event.x, event.y):
            return
        texts = legend.get_texts()
        if not texts:
            return
        text = min(texts, key=lambda item: abs(event.y - item.get_window_extent(renderer).y0
                                              - item.get_window_extent(renderer).height / 2))
        targets = [line for line in ax.get_lines() if str(line.get_label()) == text.get_text()]
        if not targets:
            return
        key, visible = identity(targets[0]), not targets[0].get_visible()
        for axes in figure.axes:
            for line in axes.get_lines():
                if identity(line) == key:
                    line.set_visible(visible)
        refresh()
        figure.canvas.draw_idle()

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
    return list(CGYRO_COMPARISON_LINE_COLOR_PALETTE)


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

    ax[0, 0].set_title(title_left, fontdict={'family': 'DejaVu Sans', 'size': ctx['fs1']})
    ax[0, 1].set_title(title_right, fontdict={'family': 'DejaVu Sans', 'size': ctx['fs1']})
    ax[0, 0].set_xlabel(str(xlabel_left), fontdict={'family': 'DejaVu Sans', 'size': ctx['fs1']}, labelpad=5)
    ax[0, 1].set_xlabel(str(xlabel_right), fontdict={'family': 'DejaVu Sans', 'size': ctx['fs1']}, labelpad=5)

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
