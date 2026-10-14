"""Open the task-indexed CGYRO result browser."""
from OMFITlib_cgyro_results import ResultBrowser
from OMFITlib_gui_layout import finish_gui_layout

anchor = OMFITx.Label('', align='left')
anchor.master.pack_forget()
ResultBrowser(root, OMFITx).render()
finish_gui_layout(anchor, OMFITx)
