"""Default workbench for Linux OMFIT desktops."""
from OMFITlib_gui_api import adapt, gui_view
from OMFITlib_gui_layout import prepare_gui_fonts
prepare_gui_fonts(OMFITx)
OMFITx = adapt(OMFITx)
from OMFITlib_project import ProjectActions
from OMFITlib_project_ui import ProjectUI
from OMFITlib_project_runtime import register_runtime_server
from omfit_classes.namelist import NamelistName

defaultVars(workbench_page=None, panel_only=False)


def register_server(config):
    register_runtime_server(OMFIT['MainSettings']['SERVER'], config, NamelistName)
    try:
        OMFIT.addMainSettings(updateUserSettings=True)
    except Exception:
        # The connection is already usable in this session; report persistence separately.
        return False
    return True


actions = ProjectActions(root, OMFITtree, readers={'cgyro': OMFITgacode, 'tglf': OMFITgacode, 'tgyro': OMFITgacode, 'gacode': OMFITgacode},
                         resolve_server=lambda node: SERVER[node], workdir=OMFITworkDir, register_server=register_server,
                         remote_execute=OMFITx.remote_execute, root_name=rootName)
if workbench_page is not None:
    actions.open_page(workbench_page)
configure = lambda node: gui_view(OMFIT['scratch']['__moduleSetupGUI__'], base_override=relativeLocations(node))
open_templates = (lambda: gui_view(OMFIT['OMFITtemplates']['GUIS']['main'])) if 'OMFITtemplates' in OMFIT else None
ProjectUI(actions, OMFITx, configure=configure, open_templates=open_templates,
          servers=SERVER.listServers,
          open_servers=lambda: gui_view(OMFIT['scratch']['__preferencesGUI__'])).render(panel_only=panel_only)
