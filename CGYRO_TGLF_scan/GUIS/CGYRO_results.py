"""Open the task-indexed CGYRO result browser."""
from OMFITlib_gui_api import adapt
OMFITx = adapt(OMFITx)
from OMFITlib_cgyro_results import ResultBrowser
from OMFITlib_project import ProjectActions
from OMFITlib_gui_layout import finish_gui_layout

anchor = OMFITx.Label('', align='left')
anchor.master.pack_forget()
actions = ProjectActions(root, factory=OMFITtree)
ResultBrowser(root, OMFITx, continue_callback=actions.continue_cgyro).render()
finish_gui_layout(anchor, OMFITx)
