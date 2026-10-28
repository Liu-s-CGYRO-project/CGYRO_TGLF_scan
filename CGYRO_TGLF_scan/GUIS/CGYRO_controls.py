"""Input, scan and run sub-tabs inside the native CGYRO workbench."""
from OMFITlib_gui_api import gui_view
defaultVars(workbench=None)

if workbench is None:
    gui_view(root['GUIS']['main'], workbench_page='cgyro')
else:
    workbench.render_cgyro_scan_tabs()

