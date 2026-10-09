"""Default workbench for Linux OMFIT desktops."""
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


actions = ProjectActions(root, OMFITtree, readers={'cgyro': OMFITgacode, 'tglf': OMFITgacode, 'tgyro': OMFITgacode},
                         resolve_server=lambda node: SERVER[node], workdir=OMFITworkDir, register_server=register_server,
                         remote_execute=OMFITx.remote_execute)
if workbench_page is not None:
    actions.open_page(workbench_page)
configure = lambda node: OMFIT['scratch']['__moduleSetupGUI__'].run(base_override=relativeLocations(node))
open_templates = (lambda: OMFIT['OMFITtemplates']['GUIS']['main'].run()) if 'OMFITtemplates' in OMFIT else None
ProjectUI(actions, OMFITx, configure=configure, open_templates=open_templates,
          servers=SERVER.listServers,
          open_servers=lambda: OMFIT['scratch']['__preferencesGUI__'].run()).render(panel_only=panel_only)
