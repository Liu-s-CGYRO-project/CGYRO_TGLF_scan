"""Plot the selected completed multi-profile TGLF runs."""
from OMFITlib_tglf_multi_plot import plot_cases
from OMFITlib_plot_style import plot_context

with plot_context(root):

    plot_cases(root, FigureNotebook)
