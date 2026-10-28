"""Transfer_tool's existing plot functions, grouped by purpose."""
from OMFITlib_gui_api import adapt
OMFITx = adapt(OMFITx)
from OMFITlib_transfer_plot_ui import TransferPlotsUI
from OMFITlib_gui_deferred import deferred_section

plots = TransferPlotsUI(root, OMFITx, readers={'gEQDSK': OMFITgeqdsk, 'statefile': OMFITnc,
                                     'trpltout.nc': OMFITnc, 'input.profiles': OMFITgacode})
section = deferred_section(OMFITx, plots.render, local=True, container=True, action=True)
if section is None:
    plots.render()
else:
    section.show()
