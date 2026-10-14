"""Compatibility shortcut to the single maintained comparison panel."""
from OMFITlib_gui_api import adapt
OMFITx = adapt(OMFITx)
from OMFITlib_gui_layout import finish_gui_layout

anchor = OMFITx.Label('', align='left')
anchor.master.pack_forget()
root['SETTINGS']['PHYSICS']['compare_mode'] = 'CGYRO_vs_CGYRO'
OMFITx.CompoundGUI(root['GUIS']['CGYRO_vs_TGLF'])
finish_gui_layout(anchor, OMFITx)
