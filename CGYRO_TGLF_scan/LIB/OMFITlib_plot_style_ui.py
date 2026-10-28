"""One editor for project-wide appearance; scientific plot options stay local."""
from builtins import dict
from collections import OrderedDict
from OMFITlib_plot_style import DEFAULTS, settings
from OMFITlib_gui_layout import section_group, finish_gui_layout
from OMFITlib_gui_controls import checkbox
from OMFITlib_gui_api import adapt
from OMFITlib_gui_deferred import deferred_section
from OMFITlib_font_ui import open_font_manager


def render_style(root, ui):
    ui = adapt(ui).view_only()
    section = deferred_section(ui, lambda: _render_style(root, ui), local=True, container=True, action=True)
    if section is None:
        return _render_style(root, ui)
    section.show()


def _render_style(root, ui):
    state = settings(root)
    path = "root['SETTINGS']['PLOT_STYLE']"
    anchor = ui.Label('工程主界面的绘图入口共用此样式；修改后重新绘图生效。', align='left')

    def entry(key, label, help=''):
        ui.Entry(path + '[{!r}]'.format(key), label, default=DEFAULTS[key], width=10,
                 help=help, kwlabel={'width': 12, 'anchor': 'w'})

    with section_group(ui, '界面字体'):
        ui.Button('界面字体与字号', open_font_manager, refresh_tree=False)
    with section_group(ui, '字体与线条'):
        entry('font_family', '绘图字体', '输出图统一使用英文。默认 Liberation Sans，作为 Arial 的相近替代；用于英文、数字和常用数学符号。')
        entry('font_file', '字体文件', '可选：填写 .ttf、.otf 或 .ttc 文件路径，覆盖缓存的默认英文字体。不要求 Matplotlib 3.6，不读取旧的中文绘图字体设置。')
        with ui.same_row():
            entry('font_size', '字号 / pt')
            entry('legend_font_size', '图例字号 / pt')
        with ui.same_row():
            entry('line_width', '线宽 / pt')
            entry('marker_size', '标记大小 / pt')
        entry('axes_width', '轴线宽 / pt')
    with section_group(ui, '配色与图例'):
        ui.ComboBox(path + "['palette']", OrderedDict([
            ('清晰配色', 'okabe_ito'), ('常规配色', 'tableau'), ('自定义', 'custom')]),
            '曲线配色', default='okabe_ito', updateGUI=True)
        if state['palette'] == 'custom':
            entry('custom_colors', '颜色列表', '颜色按曲线依次使用，以逗号分隔，例如 #0072B2, #D55E00, #009E73。')
        ui.ComboBox(path + "['legend_location']", OrderedDict([
            ('自动', 'best'), ('右上', 'upper right'), ('左上', 'upper left'), ('图外', 'outside')]),
            '图例位置', default='best')
        checkbox(ui, path + "['show_grid']", state, 'show_grid', '显示浅色网格', default=True)
    with section_group(ui, '画布与导出'):
        with ui.same_row():
            entry('figure_width', '宽度 / in', '0 表示按各图的布局自动设置。')
            entry('figure_height', '高度 / in', '0 表示按各图的布局自动设置。')
        with ui.same_row():
            entry('dpi', '显示 DPI')
            entry('export_dpi', '导出 DPI', '用于 PNG 等位图；PDF / SVG 的线条与文字保持矢量。')
    ui.Button('重置样式', lambda: state.update(dict(DEFAULTS)), updateGUI=True, refresh_tree=False)
    finish_gui_layout(anchor, ui)
