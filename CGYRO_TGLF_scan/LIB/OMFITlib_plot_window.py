"""Fit this project's native FigureNotebook pages without patching OMFIT.

Tk must allocate the notebook's tabs and toolbars before giving the remaining
space to the Matplotlib canvas. Changing figure inches alone cannot do that.
Call fit_figure_window after the final size/layout change in a plot renderer.
Agg and other non-Tk figures keep their requested export dimensions.
"""
from builtins import callable, getattr, int, isinstance, list, max, min, round, sum
from types import SimpleNamespace
import tkinter as tk
from tkinter import ttk


def fit_figure_window(figure):
    """Keep both native toolbars visible and resize only the attached canvas."""
    canvas = figure.canvas
    get_widget = getattr(canvas, 'get_tk_widget', None)
    if not callable(get_widget):
        return False
    widget = get_widget()
    if not isinstance(widget, tk.Misc) or not isinstance(widget.master.master, ttk.Notebook):
        return False
    notebook = widget.master.master
    try:
        layout = getattr(notebook, '_cgyro_plot_window', None)
        if layout is None:
            layout = notebook._cgyro_plot_window = PlotWindow(notebook)
        layout.add(figure, widget)
    except tk.TclError:
        # Plot windows can be closed while OMFIT finishes a render callback.
        return False
    return True


class PlotWindow:
    """One local controller per notebook; Matplotlib owns normal resize events."""
    def __init__(self, notebook):
        self.notebook = notebook
        self.window = notebook.winfo_toplevel()
        self.pending = None
        self.initialized = False
        self.pages = {}
        notebook.bind('<<NotebookTabChanged>>', self.queue_fit, add='+')
        self.window.bind('<Destroy>', self.closed, add='+')

    def add(self, figure, widget):
        page = widget.master
        # Older OMFIT versions request the full window height for the notebook.
        # fill=both lets Tk constrain the actual page, including the tab strip.
        if self.notebook.winfo_manager() == 'pack':
            self.notebook.pack_configure(fill=tk.BOTH, expand=True)
        if widget.winfo_manager() == 'pack':
            packed = [(child, child.pack_info()) for child in page.pack_slaves()]
            for child, _ in packed:
                child.pack_forget()
            # Packing order is allocation priority. Reserve every existing
            # toolbar first, preserving its order/options and all callbacks.
            for child, options in packed:
                if child is not widget:
                    child.pack(**options)
            widget.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        if page not in self.pages:
            widget.bind('<Map>', self.queue_fit, add='+')
        self.pages[page] = (figure, widget)
        if not self.initialized:
            self.initialized = True
            self.initial_geometry(figure, widget)
        self.queue_fit()

    def initial_geometry(self, figure, widget):
        """Start within the desktop; later renders never reset a user's resize."""
        window = self.window
        available_width = max(1, window.winfo_screenwidth() - 80)
        available_height = max(1, window.winfo_screenheight() - 120)
        page = widget.master
        controls = sum(child.winfo_reqheight() for child in page.pack_slaves() if child is not widget)
        # Leave room for tab headers, window decorations and the desktop panel.
        width = min(available_width, max(720, round(figure.bbox.width)))
        height = min(available_height, max(480, round(figure.bbox.height) + controls + 48))
        x = max(0, min(window.winfo_x(), window.winfo_screenwidth() - width - 40))
        y = max(0, min(window.winfo_y(), window.winfo_screenheight() - height - 80))
        window.geometry('{}x{}+{}+{}'.format(width, height, x, y))
        window.minsize(min(640, available_width), min(360, available_height))

    def queue_fit(self, event=None):
        # Several tab/map notifications may arrive in one Tk layout pass.
        if self.pending is None:
            self.pending = self.window.after_idle(self.fit_visible)

    def fit_visible(self):
        self.pending = None
        try:
            for figure, widget in list(self.pages.values()):
                if not widget.winfo_exists() or not widget.winfo_ismapped():
                    continue
                width, height = widget.winfo_width(), widget.winfo_height()
                if min(width, height) <= 1:
                    continue
                # set_size_inches(forward=True) can change the figure even
                # when its allocated Tk rectangle stays unchanged. In that
                # case force the backend's normal bitmap/resize path once.
                if (int(figure.bbox.width), int(figure.bbox.height)) != (width, height):
                    figure.canvas.resize(SimpleNamespace(width=width, height=height))
        except tk.TclError:
            return

    def closed(self, event):
        if event.widget is self.window and self.pending is not None:
            self.window.after_cancel(self.pending)
            self.pending = None
