"""Input, scan and run sub-tabs inside the native TGLF workbench."""
from OMFITlib_gui_api import gui_view
defaultVars(workbench=None)

if workbench is None:
    gui_view(root['GUIS']['main'], workbench_page='tglf')
else:
    workbench.render_scan_tabs()
