"""Plot the currently selected CGYRO task-table slice."""
from OMFITlib_cgyro_results import plot_selected
from OMFITlib_plot_style import plot_context

with plot_context(root):

    plot_selected(root, FigureNotebook)
