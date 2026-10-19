"""Plot the currently selected CGYRO task-table slice."""
from OMFITlib_cgyro_results import plot_selected, plot_time_traces
from OMFITlib_plot_style import plot_context
defaultVars(time_traces=False, run_token='', point_ids=None)

with plot_context(root) as style:

    if time_traces:
        plot_time_traces(root, FigureNotebook, run_token, point_ids, style['legend_font_size'])
    else:
        plot_selected(root, FigureNotebook)
