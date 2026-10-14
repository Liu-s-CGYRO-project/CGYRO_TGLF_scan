"""OMFIT plotting entry; library modules own collection and rendering."""
from OMFITlib_compare_dispatch import run_plot
from OMFITlib_plot_style import plot_context

with plot_context(root):

    run_plot(root)
