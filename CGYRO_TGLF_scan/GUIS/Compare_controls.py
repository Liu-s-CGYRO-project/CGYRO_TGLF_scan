"""Native child Notebook for one comparison mode."""
from OMFITlib_gui_api import gui_view
defaultVars(comparison=None, mode='CGYRO_vs_TGLF', open_templates=None)

if comparison is None:
    gui_view(root['GUIS']['CGYRO_vs_TGLF'])
else:
    comparison.render_controls(mode, open_templates=open_templates)
