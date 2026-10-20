"""Font settings with all OMFIT libraries captured before Tk callbacks run."""
from builtins import max, min, str
import tkinter as tk
from tkinter import filedialog, ttk
from OMFITlib_font_cache import FontCancelled, FontError, cache_directory, cached_fonts, set_proxy
from OMFITlib_font_download_ui import _dialog, _parent, ensure_fonts
from OMFITlib_font_manifest import FONT_BUNDLES
from OMFITlib_gui_fonts import (
    configure_window_fonts, font_size, font_status, MIN_SIZE, MAX_SIZE,
    refresh_window_fonts, set_font_size,
)


def _refresh_gui(parent):
    if cached_fonts('gui') is not None:
        refresh_window_fonts(parent)


def open_font_manager(parent=None):
    parent = _parent(parent)
    if parent is None:
        raise FontError('Font resources needs an existing Tk window.')
    dialog = tk.Toplevel(parent)
    dialog.title('OMFIT Font Resources')
    dialog.resizable(True, False)
    body = ttk.Frame(dialog, padding=16)
    body.pack(fill='both', expand=True)
    wrap = min(540, max(240, dialog.winfo_screenwidth() - 100))
    ttk.Label(body, text='Complete original fonts are shared by all project versions.', wraplength=wrap).pack(anchor='w')
    status = tk.StringVar(master=dialog, value='')
    ttk.Label(body, textvariable=status, justify='left', wraplength=wrap).pack(fill='x', pady=12)
    ttk.Label(body, text=str(cache_directory()), wraplength=wrap).pack(fill='x', pady=(0, 12))
    size = tk.StringVar(master=dialog, value=str(font_size(parent)))
    typography = ttk.Frame(body)
    typography.pack(fill='x', pady=(0, 12))
    ttk.Label(typography, text='GUI size / pt').grid(row=0, column=0, sticky='w', padx=(0, 8))
    ttk.Spinbox(typography, textvariable=size, from_=MIN_SIZE, to=MAX_SIZE, width=5).grid(row=0, column=1, sticky='w')

    def describe():
        ready = cached_fonts('gui') is not None
        runtime = font_status(parent)
        lines = ['GUI file: ' + ('ready' if ready else 'not downloaded'),
                 'Plot fonts: ' + ('ready' if cached_fonts('plot') is not None else 'not downloaded')]
        lines.append('GUI active: ' + (runtime.get('requested', '') if runtime['active'] else 'no'))
        lines.append('GUI size: {} pt | Tk backend: {}'.format(runtime['size'], runtime['backend']))
        actual = runtime['actual']
        if actual:
            lines.extend(key + ': ' + value for key, value in actual.items())
        if runtime['error']:
            lines.append(runtime['error'])
        status.set('\n'.join(lines))

    def refresh():
        _refresh_gui(parent)
        if cached_fonts('gui') is not None:
            configure_window_fonts(dialog)
        describe()

    def apply_size():
        try:
            # Applying a GUI size never requests the independent plot pack.
            ensure_fonts('gui', parent=dialog)
            set_font_size(parent, size.get())
            configure_window_fonts(dialog)
            describe()
        except (FontError, OSError, ValueError, tk.TclError) as exc:
            status.set(str(exc))

    ttk.Button(typography, text='Apply GUI font', command=apply_size).grid(row=0, column=2, sticky='e', padx=(12, 0))
    typography.columnconfigure(2, weight=1)

    def download():
        try:
            for key in FONT_BUNDLES:
                ensure_fonts(key, parent=dialog)
        except (FontError, OSError) as exc:
            status.set(str(exc))
            return
        refresh()

    def offline():
        path = filedialog.askopenfilename(parent=dialog, title='Import offline font ZIP', filetypes=[('Font ZIP', '*.zip')])
        if not path:
            return
        try:
            _dialog(dialog, None, import_path=path)
        except (FontError, OSError) as exc:
            status.set(str(exc))
            return
        refresh()

    actions = ttk.Frame(body)
    actions.pack(fill='x')
    ttk.Button(actions, text='Download missing fonts', command=download).grid(row=0, column=0, sticky='ew', padx=(0, 8))
    ttk.Button(actions, text='Import font ZIP...', command=offline).grid(row=0, column=1, sticky='ew')
    ttk.Button(actions, text='Close', command=dialog.destroy).grid(row=1, column=0, columnspan=2, sticky='e', pady=(10, 0))
    actions.columnconfigure(0, weight=1)
    actions.columnconfigure(1, weight=1)
    refresh()
    return dialog
