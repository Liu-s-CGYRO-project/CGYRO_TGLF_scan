from OMFITlib_gui_api import plot_view
from OMFITlib_gui_api import adapt
OMFITx = adapt(OMFITx)
# -*-Python-*-
# Created by meneghini at 2015/03/28 14:31

defaultVars(showButtons=True)

param = root['SETTINGS']['PHYSICS']['scanParameter']
param2 = root['SETTINGS']['PHYSICS']['scanParameter2D']

OMFITx.TitleGUI('TGLF 二维扫描')

if 'input.tglf' in root['FILES']:
    from OMFITlib_gui_deferred import TabPages

    def render_page(page):
        if page == 'constraints':
            OMFITx.CompoundGUI(root['GUIS']['constraints_GUI'], title='', input_tglf=root['FILES']['input.tglf'])
        else:
            OMFITx.CompoundGUI(root['GUIS']['scanGUI'], paramN='2D' if page == 'second' else '',
                              showButtons=False, show_constraints=False)

    pages = TabPages(OMFITx, {'first': 'Parameter 1', 'second': 'Parameter 2', 'constraints': 'Constraints'},
                     root['SETTINGS'].setdefault('GUI', {}), 'scan2d_tab', render_page)
    OMFITx.Tab('')
    if showButtons:
        OMFITx.Button('运行 TGLF 二维扫描', "root['SCRIPTS']['runTGLFscan2D']")
        if 'scanResults2D' in root and len(root['scanResults2D']) and param2 + '+' + param in root['scanResults2D']:
            OMFITx.CheckBox("root['SETTINGS']['PHYSICS']['combine_ions']", '绘图时合并离子', default=True, refresh_tree=False)
            OMFITx.Button('绘制 TGLF 二维扫描结果', lambda: plot_view(root['PLOTS']['plotScan2D'], fig=figure()), refresh_tree=False)
else:
    OMFITx.Label('请先在 FILES 中准备 input.tglf')
    OMFITx.ObjectPicker("root['FILES']['input.tglf']", "input.tglf", OMFITgacode)
