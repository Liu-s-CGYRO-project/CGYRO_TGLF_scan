"""One editor for project-wide appearance; scientific plot options stay local."""
from builtins import dict
from collections import OrderedDict
from OMFITlib_plot_style import DEFAULTS, settings
from OMFITlib_gui_layout import section_group, finish_gui_layout
from OMFITlib_gui_controls import checkbox
from OMFITlib_gui_api import adapt
from OMFITlib_font_ui import open_font_manager


def render_style(root, ui):
    ui = adapt(ui)
    state = settings(root)
    path = "root['SETTINGS']['PLOT_STYLE']"
    anchor = ui.Label('工程主界面的绘图入口共用此样式；修改后重新绘图生效。', align='left')

    def entry(key, label, help=''):
        ui.Entry(path + '[{!r}]'.format(key), label, default=DEFAULTS[key], width=10,
                 help=help, kwlabel={'width': 12, 'anchor': 'w'})

    with section_group(ui, '界面字体'):
        ui.Button('界面字体与字号', open_font_manager)
    with section_group(ui, '字体与线条'):
        with ui.same_row():
            entry('chinese_font_family', '中文字体', '默认思源宋体（Source Han Serif CN）；首次使用下载到共享缓存，后续无需重复下载。')
            entry('font_family', '英文字体', '默认 Liberation Sans，作为 Arial 的相近替代；字体独立缓存，用于英文、数字和常用数学符号。')
        entry('chinese_font_file', '中文字体文件', '可选：填写 .ttf、.otf 或 .ttc 文件路径。留空使用缓存的默认字体；指定文件后自动读取其字体名称。')
        entry('font_file', '英文字体文件', '可选：填写英文字体文件路径，覆盖缓存的默认字体。中英文混排需要 Matplotlib 3.6 或以上版本。')
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
    ui.Button('重置样式', lambda: state.update(dict(DEFAULTS)), updateGUI=True)
    finish_gui_layout(anchor, ui)
