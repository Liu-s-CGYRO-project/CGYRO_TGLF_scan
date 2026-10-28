from OMFITlib_gui_api import plot_view
from OMFITlib_gui_api import adapt
OMFITx = adapt(OMFITx)
# -*-Python-*-
# Created by meneghini at 2015/07/05 14:26

OMFITx.TitleGUI('TGLF 刚度分析')

b = OMFITx.Button('计算刚度', "root['SCRIPTS']['runTGLFstiffness']")
b.configure(width=30)

if 'STIFFNESS' in root:
    OMFITx.Separator()
    OMFITx.Button('绘制刚度', lambda: plot_view(root['PLOTS']['plotStiffness']), refresh_tree=False)
