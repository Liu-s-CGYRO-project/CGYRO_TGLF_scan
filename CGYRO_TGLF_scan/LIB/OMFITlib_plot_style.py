"""Project-wide plotting API. Use plot_context(root) around new plot entry points.

Settings live once in the project SETTINGS/PLOT_STYLE. Nothing here changes
solver data or matplotlib's process-wide defaults outside a plotting call.
"""
from builtins import any, bool, dict, enumerate, float, getattr, hasattr, id, isinstance, len, list, max, set, str
from contextlib import contextmanager
from functools import partial
import math
import matplotlib as mpl
from matplotlib import colors, font_manager
from cycler import cycler

DEFAULTS = dict(font_family='DejaVu Sans', font_size=12., legend_font_size=9.,
                line_width=1.8, marker_size=5., axes_width=1., show_grid=True,
                palette='okabe_ito', custom_colors='', legend_location='best',
                figure_width=0., figure_height=0., dpi=120., export_dpi=300.)
PALETTES = {
    'okabe_ito': ['#0072B2', '#D55E00', '#009E73', '#CC79A7', '#E69F00', '#56B4E9', '#332288', '#666666'],
    'tableau': ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f'],
}


def project_root(node):
    """Find the owning project, including plots opened inside nested modules."""
    original, seen = node, set()
    while node is not None and id(node) not in seen:
        seen.add(id(node))
        if hasattr(node, 'get') and 'CGYRO_scan' in node and 'Transfer_tool' in node:
            return node
        node = getattr(node, '_OMFITparent', None)
    return original


def settings(root):
    owner = project_root(root)
    setup = owner.setdefault('SETTINGS', {})
    if 'PLOT_STYLE' not in setup:
        physics = setup.get('PHYSICS', {})
        old = physics.get(physics.get('compare_mode', ''), {}).get('style', {})
        setup['PLOT_STYLE'] = dict(DEFAULTS, **{k: old[k] for k in DEFAULTS if k in old})
    result = setup['PLOT_STYLE']
    for key, value in DEFAULTS.items():
        result.setdefault(key, value)
    return result


def palette(style):
    if style['palette'] == 'custom':
        values = str(style['custom_colors']).replace(';', ',').split(',')
        values = [value.strip() for value in values if value.strip()]
        if not values or any(not colors.is_color_like(value) for value in values):
            raise ValueError('自定义配色请填写颜色名称或 #RRGGBB，用逗号分隔')
        return values
    if style['palette'] not in PALETTES:
        raise ValueError('请选择有效的全局配色')
    return list(PALETTES[style['palette']])


def validated(root):
    style = dict(settings(root))
    for key in ('font_size', 'legend_font_size', 'line_width', 'marker_size', 'axes_width',
                'figure_width', 'figure_height', 'dpi', 'export_dpi'):
        number = float(style[key])
        optional = key in ('figure_width', 'figure_height', 'marker_size')
        if not math.isfinite(number) or (number < 0 if optional else number <= 0):
            raise ValueError('全局图形样式数值无效：' + key)
        style[key] = number
    if not str(style['font_family']).strip():
        raise ValueError('全局图形样式需要字体名称')
    if style['legend_location'] not in ('best', 'upper right', 'upper left', 'outside'):
        raise ValueError('请选择有效的图例位置')
    if not isinstance(style['show_grid'], bool):
        raise ValueError('显示网格必须为布尔值')
    palette(style)
    return style


def font_families(style):
    # Matplotlib resolves the first installed font containing each glyph.
    available = {font.name for font in font_manager.fontManager.ttflist}
    requested = str(style['font_family'])
    names = [requested, 'Noto Sans CJK SC', 'Microsoft YaHei', 'WenQuanYi Zen Hei', 'DejaVu Sans']
    return list(dict.fromkeys(name for name in names if name in available or name in ('sans-serif', 'serif', 'monospace')))


def apply_figure_style(figure, style):
    """Apply appearance to a finished figure; retain data, limits and reference lines."""
    from matplotlib.text import Text
    width, height = figure.get_size_inches()
    figure.set_size_inches(style['figure_width'] or width, style['figure_height'] or height, forward=True)
    figure.set_dpi(style['dpi'])
    # Native save dialogs run after this context ends. Keep the export default
    # on this figure, while respecting an explicit dpi passed by the caller.
    original_save = getattr(figure, '_project_savefig', figure.savefig)
    figure._project_savefig = original_save
    figure.savefig = partial(original_save, dpi=style['export_dpi'])
    family = font_families(style)
    for text in figure.findobj(match=Text):
        text.set_fontfamily(family)
        text.set_fontsize(style['font_size'])
    for axis in figure.axes:
        axis.tick_params(labelsize=max(6., style['font_size'] - 1), width=style['axes_width'])
        for spine in axis.spines.values():
            spine.set_linewidth(style['axes_width'])
        axis.grid(style['show_grid'], alpha=.18) if style['show_grid'] else axis.grid(False)
        for line in axis.lines:
            if line.get_transform() == axis.transData and line.get_gid() != 'reference':
                line.set_linewidth(style['line_width'])
                line.set_markersize(style['marker_size'])
        legend = axis.get_legend()
        if legend is not None:
            location = style['legend_location']
            # Preserve legend objects and their click-to-hide callbacks.
            setter = getattr(legend, 'set_loc', None)
            if setter is not None:
                if location == 'outside':
                    legend.set_bbox_to_anchor((1.02, 1.))
                    setter('upper left')
                else:
                    legend.set_bbox_to_anchor(None)
                    setter(location)
            for text in legend.get_texts():
                text.set_fontsize(style['legend_font_size'])
            for line in legend.get_lines():
                line.set_linewidth(style['line_width'])
                line.set_markersize(style['marker_size'])
    figure.canvas.draw_idle()


@contextmanager
def plot_context(root):
    """Scope rc defaults and finish only figures created by this plotting action."""
    import matplotlib.pyplot as plt
    style = validated(root)
    previous = set(plt.get_fignums())
    rc = {'font.family': font_families(style), 'font.size': style['font_size'],
          'legend.fontsize': style['legend_font_size'], 'lines.linewidth': style['line_width'],
          'lines.markersize': style['marker_size'], 'axes.linewidth': style['axes_width'],
          'axes.prop_cycle': cycler(color=palette(style)), 'axes.grid': style['show_grid'],
          'grid.alpha': .18, 'figure.dpi': style['dpi'], 'savefig.dpi': style['export_dpi'],
          'legend.loc': 'upper left' if style['legend_location'] == 'outside' else style['legend_location']}
    with mpl.rc_context(rc):
        yield style
        for number in set(plt.get_fignums()) - previous:
            apply_figure_style(plt.figure(number), style)
