# Both dimensions share packaging, run isolation and scheduler handling.
from OMFITlib_gui_api import task_action
task_action(root['SCRIPTS']['subscan_lin.py'], scan_dimensions=2)
