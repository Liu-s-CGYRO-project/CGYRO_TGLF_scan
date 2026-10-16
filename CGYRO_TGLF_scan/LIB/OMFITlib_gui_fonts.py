"""Bundled CJK typography for project and template-manager windows.

The font is registered for this process only. Widget styles and font options
are scoped to each project window; native callbacks and named Tk fonts stay
untouched. Keep the standalone manager copy identical with build_gui_fonts.py.
"""
from builtins import any, bool, callable, dict, getattr, hasattr, int, isinstance, len, max, open, sorted, str, tuple
import ctypes
from ctypes.util import find_library
import os
import json
import sys
import threading
import warnings
import tkinter as tk
from tkinter import font as tkfont, ttk
from OMFITlib_gui_font_data import FONT_FILENAME, FONT_SHA256, FONT_FAMILY
from OMFITlib_font_ui import ensure_fonts
from OMFITlib_font_cache import cache_directory, cached_fonts


_lock = threading.RLock()
_path = None
_registered = False
_library = None
_registration_source = ''
# Loader changes must invalidate old interpreter caches even when the original
# font file stays identical across project releases.
FONT_PROFILE = 'gui-metrics-v6:' + FONT_SHA256
DEFAULT_SIZE = 11
MIN_SIZE = 9
MAX_SIZE = 18


def font_size(widget):
    """Use one point size for labels, numbers, entries and buttons at any DPI."""
    owner = widget._root()
    size = getattr(owner, '_project_cjk_size', None)
    if size is None:
        size = DEFAULT_SIZE
        try:
            saved = json.loads((cache_directory() / 'gui_preferences.json').read_text(encoding='utf-8'))
            value = saved.get('size', DEFAULT_SIZE) if isinstance(saved, dict) else DEFAULT_SIZE
            if isinstance(value, int) and not isinstance(value, bool) and MIN_SIZE <= value <= MAX_SIZE:
                size = value
        except (OSError, ValueError):
            pass
        owner._project_cjk_size = size
    return size


def set_font_size(widget, value):
    """Persist local GUI typography, independently of scientific plot sizes."""
    size = int(value)
    if not MIN_SIZE <= size <= MAX_SIZE:
        raise ValueError('GUI size must be between {} and {} pt.'.format(MIN_SIZE, MAX_SIZE))
    path = cache_directory() / 'gui_preferences.json'
    temporary = path.with_name('.gui_preferences.{}.{}.tmp'.format(os.getpid(), threading.get_ident()))
    try:
        temporary.write_text(json.dumps({'size': size}) + '\n', encoding='utf-8')
        os.replace(str(temporary), str(path))
    finally:
        if temporary.exists():
            temporary.unlink()
    widget._root()._project_cjk_size = size
    refresh_window_fonts(widget)


def font_path(parent=None):
    """Reuse old font caches; acquire the independent pack only when needed."""
    global _path
    if _path is None:
        _path = ensure_fonts('gui', parent=parent)[FONT_FILENAME]
    return _path


def _register(path, retry=False):
    """Add an application font without editing Fontconfig or system fonts."""
    global _registered, _library, _registration_source
    with _lock:
        if _registered and not (retry and sys.platform.startswith('linux')):
            return
        if sys.platform.startswith('linux'):
            # Conda Tk can use another Fontconfig than the system resolver.
            # Resolve through Tk's already loaded dependency graph first.
            try:
                import _tkinter
                library = ctypes.CDLL(_tkinter.__file__)
                getattr(library, 'FcConfigAppFontAddFile')
                _registration_source = 'Tk dependency'
            except (AttributeError, ImportError, OSError):
                library = ctypes.CDLL(find_library('fontconfig') or 'libfontconfig.so.1')
                _registration_source = 'Fontconfig resolver'
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
            _registration_source = 'Windows private font'
        else:
            raise RuntimeError('Bundled GUI fonts support Linux/Xft and Windows')
        _library = library
        _registered = True


def _backend(widget):
    try:
        return str(widget.tk.call('tk::pkgconfig', 'get', 'fontsystem'))
    except tk.TclError:
        return str(widget.tk.call('tk', 'windowingsystem'))


def font_status(widget):
    """Report actual Tk selection, separately from downloaded-file readiness."""
    result = dict(getattr(widget._root(), '_project_cjk_diagnostic', {}))
    result.setdefault('active', False)
    result.setdefault('actual', {})
    result.setdefault('error', '')
    result['backend'] = _backend(widget)
    result['size'] = font_size(widget)
    return result


def _update_retained_fonts(owner, family=None):
    """Named-font changes also reach hidden tabs and previously styled fields."""
    offsets = getattr(owner, '_project_cjk_font_offsets', {})
    size = font_size(owner)
    for font in getattr(owner, '_project_cjk_font_cache', {}).values():
        options = {'size': max(MIN_SIZE, size + offsets.get(str(font), 0))}
        if family:
            options['family'] = family
        font.configure(**options)


def font_family(widget, retry=False):
    """Retry old failures after an update or font import; never cache them forever."""
    owner = widget._root()
    if getattr(owner, '_project_cjk_loading', False):
        return None
    state = getattr(owner, '_project_cjk_family', None)
    if not retry and state is not None and state[0] == FONT_PROFILE and state[1]:
        return state[1]
    failed = getattr(owner, '_project_cjk_failed', None)
    if not retry and failed is not None and failed[0] == FONT_PROFILE:
        if failed[1] or cached_fonts('gui') is None:
            return None
    family = None
    actual = {}
    error = ''
    try:
        owner._project_cjk_loading = True
        if sys.platform.startswith('linux') and _backend(widget) == 'x11':
            raise RuntimeError('This Tk uses X11 bitmap fonts; GUI fonts need Tk with Xft support.')
        _register(font_path(parent=widget), retry=retry)
        probe = tkfont.Font(root=widget, family=FONT_FAMILY, size=12)
        actual = {key: str(widget.tk.call('font', 'actual', str(probe), '-displayof', str(widget), '-family', char))
                  for key, char in (('CJK', '\u6392'), ('Latin', 'A'), ('digits', '0'))}
        if any(value.casefold() != FONT_FAMILY.casefold() for value in actual.values()):
            raise RuntimeError('Tk selected a fallback font: ' + str(actual))
        family = FONT_FAMILY
        _update_retained_fonts(owner, family)
    except (AttributeError, ImportError, OSError, RuntimeError, ValueError, tk.TclError) as exc:
        error = str(exc)
        warnings.warn('OMFIT CJK font: ' + str(exc), RuntimeWarning, stacklevel=2)
    finally:
        owner._project_cjk_loading = False
    owner._project_cjk_family = (FONT_PROFILE, family)
    owner._project_cjk_failed = None if family else (FONT_PROFILE, cached_fonts('gui') is not None)
    owner._project_cjk_diagnostic = {'active': bool(family), 'actual': actual, 'error': error,
                                   'registration': _registration_source, 'requested': FONT_FAMILY}
    return family


def refresh_window_fonts(parent):
    """Retry typography after an offline import, touching project windows only."""
    owner = parent._root()
    if hasattr(owner, '_project_cjk_family'):
        del owner._project_cjk_family
    owner._project_cjk_failed = None
    family = font_family(parent, retry=True)
    _update_retained_fonts(owner, family)
    stack = [owner]
    while stack:
        widget = stack.pop()
        if getattr(widget, '_project_cjk_default_font', None) is not None:
            configure_window_fonts(widget)
        metrics = getattr(widget, '_project_cjk_metrics_handler', None)
        if callable(metrics):
            metrics()
        layout = getattr(widget, '_cgyro_gui_layout', None)
        refresh = getattr(layout, 'refresh_font_metrics', None)
        if callable(refresh):
            refresh()
        elif layout is not None:
            layout._queue_scroll()
        stack.extend(widget.winfo_children())


def gui_font(widget, base='TkDefaultFont', **overrides):
    """Keep weight/slant and normalize GUI sizes; retain each named Tk font."""
    options = tkfont.Font(root=widget, font=base or 'TkDefaultFont').actual()
    family = font_family(widget)
    if family:
        options['family'] = family
    size = font_size(widget)
    options['size'] = size
    options.update(overrides)
    owner = widget._root()
    cache = getattr(owner, '_project_cjk_font_cache', None)
    if cache is None:
        cache = owner._project_cjk_font_cache = {}
    offset = int(options['size']) - size
    key = (FONT_PROFILE, offset, tuple(sorted(options.items())))
    if key not in cache:
        cache[key] = tkfont.Font(root=widget, **options)
        offsets = getattr(owner, '_project_cjk_font_offsets', None)
        if offsets is None:
            offsets = owner._project_cjk_font_offsets = {}
        offsets[str(cache[key])] = offset
    return cache[key]


def fit_field_height(widget, style_name, font):
    """Give entries and comboboxes one text height, border and vertical inset."""
    style = ttk.Style(widget)
    # A fallback CJK face may be taller than the primary Latin font metrics.
    # Ideographic advance gives a conservative square-em floor in that case.
    line = max(font.metrics('linespace'), font.metrics('ascent') + font.metrics('descent'),
               (font.measure('\u56fd') * 6 + 4) // 5)
    height = line + 2 * max(2, line // 8)
    # The textarea already includes its upper/lower safety margin. Adding
    # outer vertical padding again made editable comboboxes needlessly tall.
    style.configure(style_name, font=font, padding=(6, 0), borderwidth=1)
    owner = widget._root()
    cache = getattr(owner, '_project_cjk_field_elements', None)
    if cache is None:
        cache = owner._project_cjk_field_elements = {}
    key = (style.theme_use(), height)
    if key not in cache:
        element = 'ProjectCJKField{}.spacer'.format(len(cache))
        image = tk.PhotoImage(master=widget, width=1, height=height)
        style.element_create(element, 'image', image, sticky='ns')
        # Retain the transparent geometry image after the library is reloaded.
        cache[key] = (element, image)
    element = cache[key][0]

    def reserve(items):
        result = []
        for name, options in items:
            if name.startswith('ProjectCJKField'):
                continue
            options = dict(options)
            children = options.get('children', None)
            if children:
                options['children'] = reserve(children)
            result.append((name, options))
        if any(name.rsplit('.', 1)[-1] == 'textarea' for name, options in result):
            # A sibling in the native padding parcel raises the textarea's
            # height too. Outer padding alone leaves that clipping area short.
            result.insert(0, (element, {'side': 'left', 'sticky': 'ns'}))
        return result

    current = style.layout(style_name)
    fitted = reserve(current)
    if fitted != current:
        style.layout(style_name, fitted)
    _watch_field_style(widget, style_name, style.theme_use())


def fit_combobox_text(widget, style_name, font):
    """Compatibility entry point for older layout helpers."""
    fit_field_height(widget, style_name, font)


def _sync_field_style(widget):
    state = widget._project_cjk_field_watch
    if (str(widget.cget('style')) == state['style'] and state['profile'] == FONT_PROFILE
            and ttk.Style(widget).theme_use() == state['theme']):
        return
    handler = getattr(widget.winfo_toplevel(), '_project_cjk_style_handler', style_widget)
    handler(widget)


def _watch_field_style(widget, style_name, theme):
    """Reapply geometry after native validation selects valid/error styles."""
    state = getattr(widget, '_project_cjk_field_watch', None)
    if state is None:
        state = widget._project_cjk_field_watch = {'timer': None}

        def apply():
            state['timer'] = None
            try:
                if widget.winfo_exists():
                    # Hot reloads replace this handler without adding bindings.
                    state['handler'](widget)
            except tk.TclError:
                return

        def queue(event):
            try:
                if state['timer'] is None and widget.winfo_exists():
                    # Native OMFIT validates a key edit with after(1, ...).
                    state['timer'] = widget.after(5, apply)
            except tk.TclError:
                return

        def close(event):
            if event.widget is widget and state['timer'] is not None:
                widget.after_cancel(state['timer'])
                state['timer'] = None

        for sequence in ('<Configure>', '<KeyPress>', '<KeyRelease>', '<Return>', '<KP_Enter>',
                         '<Escape>', '<FocusIn>', '<FocusOut>', '<<virtualKey>>',
                         '<<ComboboxSelected>>', '<<ThemeChanged>>'):
            widget.bind(sequence, queue, add='+')
        widget.bind('<Destroy>', close, add='+')
    state.update(dict(style=style_name, theme=theme, profile=FONT_PROFILE, handler=_sync_field_style))


def _sync_combobox_popdown(widget, create=False):
    """Set the native list font and row spacing before Tk measures its window."""
    if not widget.winfo_exists():
        return
    if create:
        # Tk creates this Tcl-only Listbox lazily. It is absent from Python's
        # widget tree and does not pass through our normal Map font handler.
        popup = str(widget.tk.call('ttk::combobox::PopdownWindow', str(widget)))
    else:
        popup = str(widget) + '.popdown'
    listbox = popup + '.f.l'
    if not widget.tk.call('winfo', 'exists', listbox):
        return
    font = gui_font(widget, widget.cget('font') or 'TkDefaultFont')
    gap = max(3, font.metrics('linespace') // 5)
    # Native Listbox lineHeight = font linespace + 1 + 2*selectborderwidth.
    # This adds real room to every row, rather than adding empty options or
    # resizing text without updating Tk's item geometry and hit testing.
    widget.tk.call(listbox, 'configure', '-font', str(font), '-selectborderwidth', gap)


def _configure_combobox_popdown(widget, font):
    """Keep the original postcommand and selection/keyboard bindings intact."""
    pattern = '*' + str(widget).lstrip('.') + '*Listbox.'
    widget.option_add(pattern + 'font', str(font), 80)
    widget.option_add(pattern + 'selectBorderWidth', max(3, font.metrics('linespace') // 5), 80)
    state = getattr(widget, '_project_cjk_post', None)
    if state is None:
        state = widget._project_cjk_post = {'script': None}
        def prepare():
            state['handler'](widget, create=True)
        state['command'] = widget.register(prepare)
    # Dispatch through state so live code updates do not retain an old closure.
    state['handler'] = _sync_combobox_popdown
    current = str(widget.cget('postcommand'))
    if current != state['script']:
        # Tcl quotes the original script as a list element, preserving spaces,
        # newlines, substitutions and its error behavior. Run it once first,
        # then synchronize fonts before native ConfigureListbox/PlacePopdown.
        original = widget.tk.call('list', 'uplevel', '#0', current)
        callback = widget.tk.call('list', state['command'])
        script = str(widget.tk.call('format', '%s\n%s', original, callback))
        widget.configure(postcommand=script)
        state['script'] = script
    _sync_combobox_popdown(widget)


def style_widget(widget):
    """Change typography only, including popdown fonts and table headings."""
    kind = widget.winfo_class()
    if kind in ('Toplevel', 'Tk', 'TFrame', 'Frame', 'Canvas', 'TScrollbar', 'Scrollbar'):
        return
    style = ttk.Style(widget)
    if kind in ('TButton', 'TCheckbutton', 'TRadiobutton', 'TNotebook', 'Treeview', 'TLabelframe', 'TEntry', 'TCombobox', 'TSpinbox'):
        original = getattr(widget, '_project_cjk_base_style', None)
        current = str(widget.cget('style')) or kind
        if original is None or current != getattr(widget, '_project_cjk_applied_style', None):
            original = current
            widget._project_cjk_base_style = original
        role = original + '.Tab' if kind == 'TNotebook' else original + '.Label' if kind == 'TLabelframe' else original
        font = gui_font(widget, style.lookup(role, 'font') or 'TkDefaultFont')
        window_name = str(widget.winfo_toplevel()).replace('.', '_')
        name = 'ProjectCJK' + window_name + '.' + original
        gap = max(3, font.metrics('linespace') // 6)
        style.configure(name, font=font)
        if kind == 'TNotebook':
            style.configure(name + '.Tab', font=font, padding=(10, gap + 2))
        elif kind == 'TLabelframe':
            style.configure(name + '.Label', font=font)
        elif kind == 'Treeview':
            style.configure(name, font=font, rowheight=font.metrics('linespace') + 8)
            heading = gui_font(widget, style.lookup(original + '.Heading', 'font') or font, weight='bold')
            style.configure(name + '.Heading', font=heading)
        else:
            style.configure(name, font=font, padding=(6, gap))
        widget.configure(style=name)
        widget._project_cjk_applied_style = name
    if 'font' in widget.keys():
        options = {}
        if getattr(widget, '_cgyro_role', '') == 'heading':
            options = {'size': font_size(widget) + 1, 'weight': 'bold'}
        font = gui_font(widget, widget.cget('font') or style.lookup(kind, 'font') or 'TkDefaultFont', **options)
        widget.configure(font=font)
        if kind == 'Text':
            gap = max(2, font.metrics('linespace') // 6)
            widget.configure(spacing1=gap, spacing2=gap, spacing3=gap)
        if kind in ('TEntry', 'TCombobox'):
            fit_field_height(widget, str(widget.cget('style')) or kind, font)
        if kind == 'TCombobox':
            _configure_combobox_popdown(widget, font)


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
    if getattr(window, '_project_cjk_profile', None) != FONT_PROFILE:
        font_family(window)
        window._project_cjk_profile = FONT_PROFILE
    font = gui_font(window)
    window._project_cjk_default_font = font
    # The toplevel path limits option defaults to this window's descendants.
    window.option_add('*' + str(window).lstrip('.') + '*Font', str(font), 80)
    window._project_cjk_style_handler = style_widget
    binding = getattr(window, '_project_cjk_map_binding', None)
    if binding and getattr(window, '_project_cjk_binding_profile', None) != FONT_PROFILE:
        try:
            window.unbind('<Map>', binding)
        except tk.TclError:
            pass
        window._project_cjk_map_binding = None
    if not getattr(window, '_project_cjk_map_binding', None):
        def mapped(event):
            try:
                if isinstance(event.widget, tk.Misc) and event.widget.winfo_toplevel() is window:
                    window._project_cjk_style_handler(event.widget)
            except tk.TclError:
                # A window may have been closed by another queued callback.
                return
        window._project_cjk_map_binding = window.bind('<Map>', mapped, add='+')
        window._project_cjk_binding_profile = FONT_PROFILE
    # A Map hook alone misses controls already visible when code is upgraded.
    style_widgets(window)

