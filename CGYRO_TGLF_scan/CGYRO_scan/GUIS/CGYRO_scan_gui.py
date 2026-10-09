"""Use the same CGYRO workbench from the original module entry."""
from builtins import getattr

project = getattr(root, '_OMFITparent', None)
if project is None or project.get('CGYRO_scan', None) is not root or 'main' not in project.get('GUIS', {}):
    raise ValueError('此入口需要完整 CGYRO / TGLF 工程，请从工程总控打开 CGYRO 扫描。')
OMFITx.CompoundGUI(project['GUIS']['main'], title='', panel_only=True)
