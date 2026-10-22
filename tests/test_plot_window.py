"""Exercise native Tk/Matplotlib geometry, including the legacy packing failure.

Run with a desktop/display: python -m unittest discover -s tests -p test_plot_window.py
OMFIT's application toolbar is represented by real Tk buttons, with the same
parent and packing order. No solver, result tree or running OMFIT is required.
"""
import io
from pathlib import Path
import sys
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace
import unittest

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.backends._backend_tk import NavigationToolbar2Tk
from matplotlib.figure import Figure

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'CGYRO_TGLF_scan/LIB'))
from OMFITlib_plot_window import fit_figure_window
from OMFITlib_compare_style import apply_figure_layout


class LegacyNotebook:
    """Native widgets with the canvas-before-toolbar order in OMFIT 0.12.13."""
    def __init__(self, root):
        self.master = tk.Toplevel(root)
        self.master.geometry('710x710+40+40')
        self.notebook = ttk.Notebook(self.master)
        self.master.bind('<Configure>', self._update_size)
        self.clicks = 0

    def _update_size(self, event=None):
        self.notebook.configure(width=self.master.winfo_width(), height=self.master.winfo_height())

    def subplots(self, figsize=(16, 10), label='scan', **options):
        page = tk.Frame(self.notebook)
        self.notebook.add(page, text=label)
        self.notebook.pack()
        figure = Figure(figsize=figsize, dpi=110)
        axes = figure.subplots(**options)
        canvas = FigureCanvasTkAgg(figure=figure, master=page)
        canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        native = NavigationToolbar2Tk(canvas, page)
        application = tk.Frame(page)
        def click():
            self.clicks += 1
        button = tk.Button(application, text='OMFIT figure tools', command=click)
        button.pack(side=tk.LEFT)
        application.pack(side=tk.BOTTOM, fill=tk.X)
        canvas.manager = SimpleNamespace(window=self.master, resize=lambda w, h: canvas.get_tk_widget().configure(width=w, height=h))
        figure._test_controls = (native, application, button)
        return figure, axes


class PlotWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.root = tk.Tk()
        except tk.TclError as error:
            raise unittest.SkipTest('A Tk desktop/display is required: ' + str(error))
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        self.errors = []
        self.root.report_callback_exception = lambda *error: self.errors.append(error)
        self.host = LegacyNotebook(self.root)

    def tearDown(self):
        if self.host.master.winfo_exists():
            self.host.master.destroy()
        self.root.update()
        self.assertFalse(self.errors)

    def settle(self):
        for _ in range(4):
            self.root.update_idletasks()
            self.root.update()

    def check_page(self, figure):
        widget = figure.canvas.get_tk_widget()
        page = widget.master
        self.assertTrue(widget.winfo_ismapped())
        self.assertLessEqual(widget.winfo_x() + widget.winfo_width(), page.winfo_width())
        self.assertLessEqual(widget.winfo_y() + widget.winfo_height(), page.winfo_height())
        for control in figure._test_controls[:2]:
            self.assertTrue(control.winfo_ismapped())
            self.assertGreaterEqual(control.winfo_y(), widget.winfo_y() + widget.winfo_height())
            self.assertLessEqual(control.winfo_y() + control.winfo_height(), page.winfo_height())
        self.assertLessEqual(page.winfo_rooty() + page.winfo_height(),
                             self.host.master.winfo_rooty() + self.host.master.winfo_height())
        self.assertEqual(tuple(round(dimension) for dimension in figure.bbox.size),
                         (widget.winfo_width(), widget.winfo_height()))

    def test_native_toolbar_and_canvas_fit_small_and_large_windows(self):
        figure, axes = self.host.subplots(nrows=2, ncols=2)
        for axis in axes.flat:
            axis.plot([.1, .2, .3], [1, 2, 1], label='N_THETA=32')
            axis.set_xlabel('ky')
            axis.legend()
        self.settle()
        # Reproduce the reported failure before installing the project adapter.
        self.assertFalse(figure._test_controls[0].winfo_ismapped())
        apply_figure_layout(figure)
        self.settle()
        self.assertLessEqual(self.host.master.winfo_width(), self.root.winfo_screenwidth() - 80)
        self.assertLessEqual(self.host.master.winfo_height(), self.root.winfo_screenheight() - 120)
        for width, height in ((640, 440), (860, 640), (1360, 768), (1920, 1080), (710, 710)):
            with self.subTest(width=width, height=height):
                self.host.master.geometry('{}x{}'.format(width, height))
                self.settle()
                self.check_page(figure)
                figure._test_controls[2].invoke()
        self.assertEqual(self.host.clicks, 5)
        # The existing Matplotlib zoom control still has its original binding.
        toolbar = figure._test_controls[0]
        toolbar._buttons['Zoom'].invoke()
        self.assertIn('zoom', str(toolbar.mode).lower())

    def test_tab_switch_and_new_page_do_not_reset_user_geometry(self):
        figures = [self.host.subplots(label='rho=0.5')[0]]
        fit_figure_window(figures[0])
        self.settle()
        self.host.master.geometry('900x650+50+50')
        self.settle()
        geometry = self.host.master.geometry()
        figures.append(self.host.subplots(figsize=(5, 3), label='rho=0.85')[0])
        fit_figure_window(figures[-1])
        self.settle()
        self.assertEqual(self.host.master.geometry(), geometry)
        for index in (1, 0, 1):
            self.host.notebook.select(index)
            self.settle()
            self.check_page(figures[index])
        self.assertIs(figures[0].canvas.get_tk_widget().master.master._cgyro_plot_window,
                      figures[1].canvas.get_tk_widget().master.master._cgyro_plot_window)

    def test_reapply_size_at_unchanged_widget_geometry(self):
        figure, _ = self.host.subplots()
        fit_figure_window(figure)
        self.settle()
        geometry = self.host.master.geometry()
        apply_figure_layout(figure, {'style': {'figure_width': 28, 'figure_height': 18}})
        # The global plot context may set display DPI after the renderer ends.
        figure.set_dpi(160)
        self.settle()
        self.assertEqual(self.host.master.geometry(), geometry)
        self.check_page(figure)

    def test_close_with_pending_fit_cancels_only_owned_callback(self):
        figure, _ = self.host.subplots()
        fit_figure_window(figure)
        layout = self.host.notebook._cgyro_plot_window
        pending = layout.pending
        self.assertIsNotNone(pending)
        self.host.master.destroy()
        self.root.update()
        self.assertNotIn(pending, self.root.tk.call('after', 'info'))

    def test_non_tk_export_keeps_requested_size(self):
        figure = Figure(figsize=(11, 6), dpi=100)
        FigureCanvasAgg(figure)
        self.assertFalse(fit_figure_window(figure))
        apply_figure_layout(figure, {'style': {'figure_width': 9, 'figure_height': 5}})
        image = io.BytesIO()
        figure.savefig(image, format='png')
        self.assertEqual(tuple(figure.get_size_inches()), (9, 5))
        self.assertTrue(image.getvalue().startswith(b'\x89PNG'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
