"""Transfer_tool's existing plot functions, grouped by purpose."""
from OMFITlib_transfer_plot_ui import TransferPlotsUI

TransferPlotsUI(root, OMFITx, readers={'gEQDSK': OMFITgeqdsk, 'statefile': OMFITnc,
                                     'trpltout.nc': OMFITnc, 'input.profiles': OMFITgacode}).render()
