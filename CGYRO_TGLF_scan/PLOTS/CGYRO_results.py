"""Plot the currently selected CGYRO task-table slice."""
from builtins import globals
from OMFITlib_cgyro_results import plot_selected, plot_time_traces
from OMFITlib_plot_style import plot_context
# OMFITpythonPlot.defaultVars() calls pyplot.gcf(), creating a separate empty
# Figure before our notebook. Read injected options without making a figure;
# each renderer creates its own notebook after validating the selected data.
_plot_options = globals()

with plot_context(root) as style:

    if _plot_options.get('time_traces', False):
        plot_time_traces(root, FigureNotebook, _plot_options.get('run_token', ''),
                         _plot_options.get('point_ids', None), style['legend_font_size'],
                         stopped_points=_plot_options.get('stopped_points', False),
                         selections=_plot_options.get('selections', None))
    else:
        plot_selected(root, FigureNotebook)
