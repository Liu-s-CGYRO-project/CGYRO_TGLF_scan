"""Render comparison pages with OMFIT's native Tk widget/layout function bodies.

Session, tree-location helpers, font/theme and help popups are host adapters.
The imported Entry, ComboBox, CheckBox, Button, Tab and same_row bodies are
unchanged. This checks real Linux widget geometry, not a complete OMFIT session.
"""
import argparse
import ast
from collections import OrderedDict
import copy
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import sys
import tkinter as tk
from tkinter import ttk, font as tkfont
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

from validate_native_execution import NativeHost, REPO, np, treeify
from validate_native_callbacks import fixtures


def screenshot(window, path):
    """Capture only this test window; WSLg does not expose a full-screen image."""
    from PIL import Image
    class XImage(C.Structure):
        _fields_ = [('width', C.c_int), ('height', C.c_int), ('xoffset', C.c_int), ('format', C.c_int),
                    ('data', C.c_void_p), ('byte_order', C.c_int), ('bitmap_unit', C.c_int),
                    ('bitmap_bit_order', C.c_int), ('bitmap_pad', C.c_int), ('depth', C.c_int),
                    ('bytes_per_line', C.c_int), ('bits_per_pixel', C.c_int),
                    ('red_mask', C.c_ulong), ('green_mask', C.c_ulong), ('blue_mask', C.c_ulong)]
    x11 = C.CDLL('libX11.so.6')
    x11.XOpenDisplay.argtypes, x11.XOpenDisplay.restype = [C.c_char_p], C.c_void_p
    x11.XGetImage.argtypes = [C.c_void_p, C.c_ulong, C.c_int, C.c_int, C.c_uint, C.c_uint, C.c_ulong, C.c_int]
    x11.XGetImage.restype = C.POINTER(XImage)
    x11.XDestroyImage.argtypes, x11.XCloseDisplay.argtypes = [C.POINTER(XImage)], [C.c_void_p]
    display = x11.XOpenDisplay(os.environ.get('DISPLAY', ':0').encode())
    assert display
    picture = None
    try:
        picture = x11.XGetImage(display, window.winfo_id(), 0, 0, window.winfo_width(), window.winfo_height(), C.c_ulong(-1).value, 2)
        assert picture
        obj = picture.contents
        assert obj.bits_per_pixel == 32 and obj.byte_order == 0 and obj.red_mask == 0xff0000
        raw = C.string_at(obj.data, obj.bytes_per_line * obj.height)
        Image.frombytes('RGB', (obj.width, obj.height), raw, 'raw', 'BGRX', obj.bytes_per_line).save(path)
    finally:
        if picture:
            x11.XDestroyImage(picture)
        x11.XCloseDisplay(display)


class NativeWidgets:
    def __init__(self, source, root, window, font_size=11):
        self.window, self.root, self.events = window, root, []
        canvas = self.canvas = tk.Canvas(window, highlightthickness=0)
        scroll = ttk.Scrollbar(window, orient='vertical', command=canvas.yview)
        scroll.pack(side='right', fill='y')
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side='left', fill='both', expand=True)
        body = ttk.Frame(canvas, padding=(12, 10))
        item = canvas.create_window(0, 0, window=body, anchor='nw')
        canvas.bind('<Configure>', lambda event: canvas.itemconfigure(item, width=event.width))
        body.bind('<Configure>', lambda event: canvas.configure(scrollregion=canvas.bbox('all')))
        self.body = body
        sentinel = object()
        aux = dict(parentGUI=body, topGUI=window, packing=tk.TOP, same_row=None, notebook=None,
                   tab_name='', tab_list={'': body}, compoundGUIid='', open_tabs={}, configure_size=[])
        ns = dict(tk=tk, ttk=ttk, np=np, array=np.array, copy=copy, os=os, root=root,
                  OrderedDict=OrderedDict, SortedDict=OrderedDict, special1=sentinel,
                  _aux=aux, _GUIs={str(window): SimpleNamespace(notebooks={})},
                  OMFITaux={'rootGUI': window}, OMFITexception=RuntimeError, rightClick='Button-3',
                  Combobox=ttk.Combobox, _absLocation=lambda value: value,
                  _for_each_collection=lambda value: (value, None), Lock=lambda *a, **kw: False,
                  _tk_ttk_process_kw=lambda kind, kw: dict(kw), _reveal=lambda *a: None,
                  helpTip=SimpleNamespace(showtip=lambda *a, **kw: None), openInBrowser=lambda *a: None,
                  tolist=lambda value: value if isinstance(value, (list, tuple)) else [value],
                  manage_user_errors=lambda command, **kwargs: command(), printe=print)
        def evaluate(location):
            return [evaluate(item) for item in location] if isinstance(location, list) else eval(location, ns)
        def representation(location, preentry=None, collect=False):
            value = evaluate(location)
            return repr(preentry(value) if preentry else value)
        def default(location, value=sentinel):
            if isinstance(location, list):
                for loc, val in zip(location, value if isinstance(value, list) else [value] * len(location)):
                    default(loc, val)
            else:
                expression = ast.parse(location, mode='eval').body
                parent = eval(compile(ast.Expression(expression.value), '<binding>', 'eval'), ns)
                key = ast.literal_eval(expression.slice)
                if key not in parent:
                    assert value is not sentinel, location
                    parent[key] = copy.deepcopy(value)
            return value, True
        ns.update(_eval=evaluate, repr_eval=representation, _setDefault=default)
        self.helpers = ModuleType('utils_widgets')
        self.helpers.OMFITfont = lambda weight='', size=0, *args: ('Helvetica', font_size + size, weight or 'normal')
        ns['OMFITfont'] = self.helpers.OMFITfont
        path = Path(source) / 'omfit_classes/OMFITx.py'
        text = path.read_text(encoding='utf-8')
        wanted = {'Entry', '_Entry', 'ComboBox', 'CheckBox', 'Button', 'Label', '_Label',
                  'Separator', 'Tab', 'same_row', '_helpButton', '_urlButton'}
        nodes = [n for n in ast.parse(text).body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in wanted]
        assert len(nodes) == len(wanted)
        self.evidence = {n.name: hashlib.sha256(ast.get_source_segment(text, n).encode()).hexdigest() for n in nodes}
        for node in nodes:
            node.decorator_list = []
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), ns)
        self.namespace, self.aux = ns, aux

    def TitleGUI(self, title):
        self.window.title(title)

    def __getattr__(self, name):
        if name not in self.namespace:
            raise AttributeError(name)
        function = self.namespace[name]
        if name.startswith('_'):
            return function
        if name == 'same_row':
            return function
        def call(*args, **kwargs):
            result = function(*args, **kwargs)
            self.events.append((self.aux['tab_name'], name, args, result))
            return result
        return call

    def settle(self):
        for _ in range(4):
            self.window.update()
            for frame, callback in self.aux['configure_size']:
                # Native OMFIT binds these callbacks to Configure events.
                if frame.winfo_ismapped() and frame.winfo_width() > 1:
                    callback()
        self.window.update()

    def check_geometry(self, check_footer=True):
        self.settle()
        left, top = self.body.winfo_rootx(), self.body.winfo_rooty()
        right, bottom = left + self.body.winfo_width(), top + self.body.winfo_height()
        controls = []
        def walk(widget):
            for child in widget.winfo_children():
                if child.winfo_ismapped() and child.winfo_class() in ('TLabel', 'TEntry', 'TCombobox', 'TCheckbutton', 'TButton'):
                    x, y, w, h = child.winfo_rootx(), child.winfo_rooty(), child.winfo_width(), child.winfo_height()
                    assert w > 8 and h > 8, ('collapsed', child, w, h)
                    assert left <= x and top <= y and x + w <= right and y + h <= bottom, ('clipped', child, x-left, y-top, w, h)
                    controls.append((child, (x, y, x+w, y+h)))
                    if child.winfo_class() == 'TLabel':
                        font = tkfont.Font(root=child, font=child.cget('font'))
                        assert h >= font.metrics('linespace') * max(1, len(str(child.cget('text')).splitlines())), ('label-height', child)
                walk(child)
        walk(self.window)
        for index, (one, a) in enumerate(controls):
            for two, b in controls[index+1:]:
                overlap = min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1])
                assert not overlap, ('overlap', one, two)
        if check_footer:
            footer = {args[0]: result for tab, name, args, result in self.events if tab == '' and name == 'Button'}
            assert set(footer) == {'检查选择', '绘制所选数据'}
            assert all(widget.winfo_ismapped() for widget in footer.values())
            self.canvas.yview_moveto(1)
            self.settle()
            bottom = self.canvas.winfo_rooty() + self.canvas.winfo_height()
            assert all(self.canvas.winfo_rooty() <= widget.winfo_rooty() and
                       widget.winfo_rooty() + widget.winfo_height() <= bottom for widget in footer.values()), 'Footer unreachable by scrolling'
        self.canvas.yview_moveto(0)
        self.settle()
        return len(controls)


def validate(source, output):
    output.mkdir(parents=True, exist_ok=True)
    host = NativeHost(source)
    fixture = fixtures()
    report = dict(viewports=[], complete_omfit_session_tested=False, solver_executed=False)
    for mode, font_size in ((mode, size) for size in (11, 14, 18)
                           for mode in ('CGYRO_vs_CGYRO', 'CGYRO_vs_TGLF', 'TGLF_vs_TGLF', 'TGLF_vs_CGYRO')):
        window = tk.Tk()
        try:
            window.tk.call('tk', 'scaling', 1.5)
            style = ttk.Style(window)
            style.theme_use('clam')
            style.configure('.', font=('Helvetica', font_size))
            style.configure('flat.TButton', width=2, padding=(2, 1))
            with patch.dict(sys.modules, {'omfit_classes.utils_base': host.registry}):
                root = treeify(fixture['fixture'](mode), host.factory)
            root['LIB'] = host.modules[('CGYRO_TGLF_scan',)]['LIB']
            root['GUIS'] = {name: SimpleNamespace(run=lambda: None) for name in ('main', 'TGLF_multi')}
            plotted = []
            root['PLOTS'] = {name: SimpleNamespace(plot=lambda name=name: plotted.append(name))
                             for name in ('CGYRO_vs_CGYRO', 'CGYRO_vs_TGLF')}
            before_font = style.lookup('TLabel', 'font')
            ui = NativeWidgets(source, root, window, font_size)
            with patch.dict(sys.modules, {'utils_widgets': ui.helpers, 'omfit_classes.utils_base': host.registry}):
                entry = REPO / 'CGYRO_TGLF_scan/GUIS/CGYRO_vs_TGLF.py'
                before = list(sys.meta_path)
                host.execute(entry.read_text(encoding='utf-8'), root, OMFITx=ui,
                             OMFIT={'OMFITtemplates': {'GUIS': {'main': SimpleNamespace(run=lambda: None)}}})
                assert sys.meta_path == before
                assert not any(name.startswith('OMFITlib_') for name in sys.modules)
                assert style.lookup('TLabel', 'font') == before_font
                for width, height in ((860, 640), (1080, 800)):
                    window.geometry('{}x{}+20+20'.format(width, height))
                    for index, page in enumerate(ui.aux['notebook'].tabs()):
                        ui.aux['notebook'].select(page)
                        ui.settle()
                        controls = ui.check_geometry()
                        report['viewports'].append(dict(mode=mode, font_size=font_size, tab=index+1,
                                                       width=width, height=height, controls=controls))
                        if width == 860 and font_size in (11, 18) and mode in ('CGYRO_vs_CGYRO', 'CGYRO_vs_TGLF'):
                            screenshot(window, output / ('{}_font{}_tab{}.png'.format(mode, font_size, index+1)))
                for _, name, args, button in ui.events:
                    if name == 'Button' and args[0] == '绘制所选数据':
                        button.invoke()
                        assert plotted == ['CGYRO_vs_CGYRO' if mode == 'CGYRO_vs_CGYRO' else 'CGYRO_vs_TGLF']
                report['native_widget_bodies'] = ui.evidence
        finally:
            for callback in window.tk.call('after', 'info'):
                # The callback belongs to a child Button; let that child delete
                # its Tcl command during destroy rather than deleting it twice.
                window.tk.call('after', 'cancel', callback)
            window.destroy()
    report['tk'] = tk.TkVersion
    report['all_controls_within_scrollable_content'] = True
    report['footer_reachable_by_scrolling'] = True
    report['global_omfit_style_preserved'] = True
    report['no_control_overlap'] = True
    report['actual_tk_button_invoked_after_native_import_cleanup'] = True
    (output / 'layout_validation.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: value for key, value in report.items() if key not in ('native_widget_bodies', 'viewports')}, indent=2))
    print('Checked viewports:', len(report['viewports']))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('omfit_source', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    validate(args.omfit_source, args.output)
