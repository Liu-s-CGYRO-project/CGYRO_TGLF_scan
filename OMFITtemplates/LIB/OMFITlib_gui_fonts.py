"""Bundled CJK typography for project and template-manager windows.

The font is registered for this process only. Widget styles and font options
are scoped to each project window; native callbacks and named Tk fonts stay
untouched. Keep the standalone manager copy identical with build_gui_fonts.py.
"""
from builtins import dict, getattr, int, isinstance, max, open, sorted, str, tuple
import base64
import ctypes
from ctypes.util import find_library
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import threading
import warnings
import zlib
import tkinter as tk
from tkinter import font as tkfont, ttk
from OMFITlib_gui_font_data import FONT_B85, FONT_SHA256, FONT_FAMILY


_lock = threading.RLock()
_path = None
_registered = False
_library = None


def font_path():
    """Decode the licensed full font once, using an atomic private cache file."""
    global _path
    with _lock:
        if _path is not None:
            return _path
        data = zlib.decompress(base64.b85decode(FONT_B85))
        if hashlib.sha256(data).hexdigest() != FONT_SHA256:
            raise ValueError('Bundled CJK font checksum mismatch')
        cache = Path(os.environ.get('XDG_CACHE_HOME') or
                     os.environ.get('LOCALAPPDATA') or (Path.home() / '.cache')) / 'omfit-cgyro' / 'fonts'
        try:
            cache.mkdir(parents=True, exist_ok=True, mode=0o700)
        except OSError:
            cache = Path(tempfile.mkdtemp(prefix='omfit-cjk-'))
        target = cache / (FONT_SHA256 + '.otf')
        if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != FONT_SHA256:
            with tempfile.NamedTemporaryFile(dir=cache, suffix='.otf', delete=False) as output:
                temporary = Path(output.name)
                output.write(data)
            try:
                os.replace(temporary, target)
            finally:
                if temporary.exists():
                    temporary.unlink()
        _path = str(target)
        return _path


def _register():
    """Add an application font without editing Fontconfig or system fonts."""
    global _registered, _library
    with _lock:
        if _registered:
            return
        path = font_path()
        if sys.platform.startswith('linux'):
            library = ctypes.CDLL(find_library('fontconfig') or 'libfontconfig.so.1')
            library.FcConfigGetCurrent.argtypes = []
            library.FcConfigGetCurrent.restype = ctypes.c_void_p
            library.FcConfigAppFontAddFile.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
            library.FcConfigAppFontAddFile.restype = ctypes.c_int
            config = library.FcConfigGetCurrent()
            if not config or not library.FcConfigAppFontAddFile(config, os.fsencode(path)):
                raise RuntimeError('Fontconfig could not load the bundled CJK font')
        elif sys.platform == 'win32':
            library = ctypes.WinDLL('gdi32', use_last_error=True)
            library.AddFontResourceExW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_void_p]
            library.AddFontResourceExW.restype = ctypes.c_int
            # FR_PRIVATE: no system installation or broadcast to other apps.
            if not library.AddFontResourceExW(path, 0x10, None):
                raise RuntimeError('Windows could not load the private CJK font')
        else:
            raise RuntimeError('Bundled GUI fonts support Linux/Xft and Windows')
        _library = library
        _registered = True


def font_family(widget):
    """Resolve once per interpreter; report an unavailable renderer once."""
    owner = widget._root()
    state = getattr(owner, '_project_cjk_family', None)
    if state is not None and state[0] == FONT_SHA256:
        return state[1]
    family = None
    try:
        _register()
        probe = tkfont.Font(root=widget, family=FONT_FAMILY, size=12)
        actual = str(widget.tk.call('font', 'actual', str(probe), '-family', '排'))
        if actual.casefold() != FONT_FAMILY.casefold():
            raise RuntimeError('Tk did not select the bundled font (actual: ' + actual + ')')
        family = FONT_FAMILY
    except (AttributeError, ImportError, OSError, RuntimeError, ValueError, tk.TclError) as exc:
        warnings.warn('OMFIT CJK font: ' + str(exc), RuntimeWarning, stacklevel=2)
    owner._project_cjk_family = (FONT_SHA256, family)
    return family


def gui_font(widget, base='TkDefaultFont', **overrides):
    """Keep size/weight/slant; return a retained font for this interpreter."""
    options = tkfont.Font(root=widget, font=base or 'TkDefaultFont').actual()
    family = font_family(widget)
    if family:
        options['family'] = family
    options.update(overrides)
    owner = widget._root()
    cache = getattr(owner, '_project_cjk_font_cache', None)
    if cache is None:
        cache = owner._project_cjk_font_cache = {}
    key = (FONT_SHA256, tuple(sorted(options.items())))
    if key not in cache:
        cache[key] = tkfont.Font(root=widget, **options)
    return cache[key]


def style_widget(widget):
    """Change typography only, including popdown fonts and table headings."""
    kind = widget.winfo_class()
    if kind in ('Toplevel', 'Tk', 'TFrame', 'Frame', 'Canvas', 'TScrollbar', 'Scrollbar'):
        return
    style = ttk.Style(widget)
    if kind in ('TButton', 'TCheckbutton', 'TRadiobutton', 'TNotebook', 'Treeview', 'TLabelframe'):
        original = getattr(widget, '_project_cjk_base_style', None)
        current = str(widget.cget('style')) or kind
        if original is None or current != getattr(widget, '_project_cjk_applied_style', None):
            original = current
            widget._project_cjk_base_style = original
        role = original + '.Tab' if kind == 'TNotebook' else original + '.Label' if kind == 'TLabelframe' else original
        font = gui_font(widget, style.lookup(role, 'font') or 'TkDefaultFont')
        window_name = str(widget.winfo_toplevel()).replace('.', '_')
        name = 'ProjectCJK' + window_name + '.' + original
        if kind == 'TNotebook':
            style.configure(name + '.Tab', font=font)
        elif kind == 'TLabelframe':
            style.configure(name + '.Label', font=font)
        elif kind == 'Treeview':
            old_height = style.lookup(original, 'rowheight') or 0
            style.configure(name, font=font, rowheight=max(widget.winfo_pixels(str(old_height)), font.metrics('linespace') + 8))
            heading = gui_font(widget, style.lookup(original + '.Heading', 'font') or font, weight='bold')
            style.configure(name + '.Heading', font=heading)
        else:
            style.configure(name, font=font)
        widget.configure(style=name)
        widget._project_cjk_applied_style = name
    elif 'font' in widget.keys():
        font = gui_font(widget, widget.cget('font') or style.lookup(kind, 'font') or 'TkDefaultFont')
        widget.configure(font=font)
        if kind == 'TCombobox':
            # Match only this combobox, including a popdown created later.
            widget.option_add('*' + str(widget).lstrip('.') + '*Listbox.font', str(font), 80)
            popdown = str(widget) + '.popdown.f.l'
            if widget.tk.call('winfo', 'exists', popdown):
                widget.tk.call(popdown, 'configure', '-font', str(font))


def style_widgets(parent):
    """Apply to existing descendants; later controls use the local Map hook."""
    style_widget(parent)
    for child in parent.winfo_children():
        if child.winfo_class() != 'Toplevel':
            style_widgets(child)


def configure_window_fonts(window):
    """Register a project window without changing Tk's global named fonts."""
    if not isinstance(window, tk.Misc):
        return
    font = gui_font(window)
    window._project_cjk_default_font = font
    # The toplevel path limits option defaults to this window's descendants.
    window.option_add('*' + str(window).lstrip('.') + '*Font', str(font), 80)
    if not getattr(window, '_project_cjk_map_binding', None):
        def mapped(event):
            try:
                if isinstance(event.widget, tk.Misc) and event.widget.winfo_toplevel() is window:
                    style_widget(event.widget)
            except tk.TclError:
                # A window may have been closed by another queued callback.
                return
        window._project_cjk_map_binding = window.bind('<Map>', mapped, add='+')

