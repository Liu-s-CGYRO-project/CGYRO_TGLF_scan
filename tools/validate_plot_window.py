"""Validate the project's plot adapter with OMFIT's unchanged FigureNotebook.

Run on a Linux Tk desktop; pass the directory containing omfit_plot.py.
Session globals and OMFIT toolbar actions are host adapters. The native notebook
class, Matplotlib canvas, navigation toolbar and Tk geometry are executed.
This does not open a user's project or run an OMFIT session/solver.
"""
import argparse
import ast
from collections import OrderedDict
import hashlib
import json
from pathlib import Path
import sys
import tkinter as tk
from tkinter import ttk
import types

from validate_compare_layout import screenshot
from validate_native_execution import NativeHost
import matplotlib
matplotlib.use('TkAgg')
from matplotlib import _pylab_helpers, pyplot
from matplotlib.backends._backend_tk import FigureManagerTk, NavigationToolbar2Tk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import numpy as np

class FigureMap(OrderedDict):
    def value_for_index(self, index):
        return list(self.values())[index]

    def index(self, label):
        return list(self).index(label)


class ApplicationToolbar:
    def __init__(self, figure, **options):
        self.bar = tk.Frame(figure.canvas.get_tk_widget().master)
        for text in ('Select', 'Copy', 'Paste', 'Legend', 'Crosshair', 'Help'):
            self._Button(text=text, command=lambda: None)
        self.bar.pack(side=tk.BOTTOM, fill=tk.X)

    def _Button(self, text, command, file=None):
        button = tk.Button(self.bar, text=text, command=command)
        button.pack(side=tk.LEFT)
        return button


def validate(source, output):
    output.mkdir(parents=True, exist_ok=True)
    host = NativeHost(source)
    before = list(sys.meta_path)
    loaded = host.execute('from OMFITlib_compare_style import apply_figure_layout',
                          host.modules[('CGYRO_TGLF_scan',)])
    apply_figure_layout = loaded['apply_figure_layout']
    assert sys.meta_path == before and not any(name.startswith('OMFITlib_') for name in sys.modules)
    raw = (source / 'omfit_plot.py').read_text(encoding='utf-8')
    node, = [item for item in ast.parse(raw).body if isinstance(item, ast.ClassDef) and item.name == 'FigureNotebook']
    evidence = hashlib.sha256(ast.get_source_segment(raw, node).encode()).hexdigest()
    root = tk.Tk()
    root.withdraw()
    root.tk.globalsetvar('figsOnTop', 0)
    errors = []
    root.report_callback_exception = lambda *error: errors.append(repr(error))
    scope = dict(tk=tk, ttk=ttk, np=np, pyplot=pyplot, matplotlib=matplotlib,
                 OMFITaux={'rootGUI': root, 'GUI': None}, _active_FigureNotebooks={},
                 SortedDict=FigureMap, Figure=Figure, FigureCanvasTkAgg=FigureCanvasTkAgg,
                 NavigationToolbar2=NavigationToolbar2Tk, OMFITfigure=ApplicationToolbar,
                 backend_mod=types.SimpleNamespace(FigureManagerTk=FigureManagerTk),
                 _pylab_helpers=_pylab_helpers, types=types,
                 tk_center=lambda window, parent, **options: window.geometry('+40+40'))
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(source / 'omfit_plot.py'), 'exec'), scope)
    report = dict(native_figure_notebook_sha256=evidence, matplotlib=matplotlib.__version__,
                  tk=root.tk.call('info', 'patchlevel'), viewports=[], native_imports_cleaned=True,
                  complete_omfit_session_tested=False)

    def settle():
        for _ in range(6):
            root.update_idletasks()
            root.update()

    try:
        notebook = scope['FigureNotebook'](0, 'CGYRO scan comparison')
        figures = []
        for rho in (.5, .5875, .675, .7625, .85):
            figure, axes = notebook.subplots(nrows=2, ncols=2, label='rho={}, Original'.format(rho),
                                             figsize=(12.5, 6.5), dpi=120)
            for axis, title in zip(axes.flat, ('omega/ky', 'Relative time fluctuation of omega',
                                              'gamma/ky', 'Relative time fluctuation of gamma')):
                for value in (16, 32, 48, 60):
                    axis.plot(np.linspace(.1, 1, 15), np.sin(np.linspace(0, 3, 15)) / value,
                              label='Original - N_THETA={}'.format(value))
                axis.set_title(title)
                axis.legend(fontsize=9)
            for axis in axes[-1]:
                axis.set_xlabel('ky rho_s')
            apply_figure_layout(figure)
            figures.append(figure)
        settle()
        for width, height in ((710, 710), (860, 640), (1360, 800), (1920, 1080)):
            notebook.master.geometry('{}x{}+20+20'.format(width, height))
            for index in (0, 4, 1, 0):
                notebook.notebook.select(index)
                settle()
                widget = figures[index].canvas.get_tk_widget()
                page = widget.master
                controls = [child for child in page.pack_slaves() if child is not widget]
                assert len(controls) >= 2
                assert all(child.winfo_ismapped() and child.winfo_y() >= widget.winfo_height()
                           and child.winfo_y() + child.winfo_height() <= page.winfo_height() for child in controls)
                assert page.winfo_rooty() + page.winfo_height() <= notebook.master.winfo_rooty() + notebook.master.winfo_height()
                assert tuple(round(value) for value in figures[index].bbox.size) == (widget.winfo_width(), widget.winfo_height())
                report['viewports'].append(dict(width=width, height=height, tab=index, visible_toolbars=len(controls)))
            if (width, height) in ((860, 640), (1360, 800)):
                screenshot(notebook.master, output / '{}x{}.png'.format(width, height))
        assert not errors, errors
        report.update(toolbars_visible=True, canvas_matches_page=True, tab_switching_verified=True)
        (output / 'native_plot_window.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report, indent=2))
    finally:
        root.destroy()
        _pylab_helpers.Gcf.figs.clear()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('omfit_source', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    validate(args.omfit_source, args.output)
