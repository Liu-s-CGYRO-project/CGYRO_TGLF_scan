"""Default workbench for Linux OMFIT desktops."""
from OMFITlib_project import ProjectActions
from OMFITlib_project_ui import ProjectUI

actions = ProjectActions(root, OMFITtree, readers={'cgyro': OMFITgacode, 'tglf': OMFITgacode, 'tgyro': OMFITgacode},
                         resolve_server=lambda node: SERVER[node], workdir=OMFITworkDir)
configure = lambda node: OMFIT['scratch']['__moduleSetupGUI__'].run(base_override=relativeLocations(node))
open_templates = (lambda: OMFIT['OMFITtemplates']['GUIS']['main'].run()) if 'OMFITtemplates' in OMFIT else None
ProjectUI(actions, OMFITx, configure=configure, open_templates=open_templates,
          servers=SERVER.listServers().keys()).render()
