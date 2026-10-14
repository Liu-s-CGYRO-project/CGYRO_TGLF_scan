"""Multi-input.gacode case manager, embedded in OMFIT."""
from OMFITlib_gui_api import adapt
OMFITx = adapt(OMFITx)
from OMFITlib_tglf_multi_ui import MultiInputUI

MultiInputUI(root, OMFITx, OMFITtree).render()
