"""Standalone editor for the project's shared plotting style."""
from OMFITlib_gui_api import adapt
OMFITx = adapt(OMFITx)
from OMFITlib_plot_style_ui import render_style

OMFITx.TitleGUI('全局图形样式')
render_style(root, OMFITx)
