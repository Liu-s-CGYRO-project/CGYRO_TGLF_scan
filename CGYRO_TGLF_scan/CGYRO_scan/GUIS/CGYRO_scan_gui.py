"""Use the same CGYRO workbench from the original module entry."""
from builtins import getattr
from OMFITlib_gui_layout import finish_gui_layout

project = getattr(root, '_OMFITparent', None)
if project is None or project.get('CGYRO_scan', None) is not root or 'main' not in project.get('GUIS', {}):
    raise ValueError('此入口需要完整 CGYRO / TGLF 工程，请从工程总控打开 CGYRO 扫描。')
anchor = OMFITx.Label('', align='left')
anchor.master.pack_forget()
OMFITx.CompoundGUI(project['GUIS']['main'], title='', panel_only=True)
finish_gui_layout(anchor, OMFITx)
