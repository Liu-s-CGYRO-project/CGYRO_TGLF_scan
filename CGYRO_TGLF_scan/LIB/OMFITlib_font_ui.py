"""First-use font progress and offline import, with no network work on Tk."""
from builtins import dict, getattr, isinstance, next, str
import queue
import threading
import tkinter as tk
from tkinter import filedialog, ttk
from OMFITlib_font_cache import (
    FontCancelled, FontError, cache_directory, cached_fonts,
    ensure_cached_fonts, import_font_pack, set_proxy,
)
from OMFITlib_font_manifest import FONT_BUNDLES


def _parent(parent):
    if threading.current_thread() is not threading.main_thread():
        return None
    parent = parent if parent is not None else tk._default_root
    return parent if parent is not None and parent.winfo_exists() else None


def _dialog(parent, kind, import_path=None):
    """ASCII bootstrap labels stay legible before the CJK font is available."""
    dialog = tk.Toplevel(parent)
    dialog.title('OMFIT Font Resources')
    dialog.resizable(False, False)
    body = ttk.Frame(dialog, padding=16)
    body.pack(fill='both', expand=True)
    label = 'First-use font download. Later starts use the local cache.'
    ttk.Label(body, text=label, wraplength=500).pack(anchor='w')
    status = tk.StringVar(master=dialog, value='Preparing fonts...')
    ttk.Label(body, textvariable=status, wraplength=500, justify='left').pack(fill='x', pady=12)
    bar = ttk.Progressbar(body, length=500, mode='indeterminate')
    bar.pack(fill='x')
    controls = ttk.Frame(body)
    controls.pack(fill='x', pady=(14, 0))
    events, cancel = queue.Queue(), threading.Event()
    state = dict(result=None, done=False, busy=False, after=None, alive=True)

    def report(message, done, total):
        events.put(('progress', message, done, total))

    def worker(path):
        try:
            if path is None:
                result = ensure_cached_fonts(kind, progress=report, cancel=cancel)
            else:
                imported, result = import_font_pack(path, progress=report, cancel=cancel)
                if kind is not None and imported != kind:
                    raise FontError('This ZIP contains {} fonts; please import the {} font ZIP.'.format(imported, kind))
            events.put(('done', result))
        except Exception as exc:
            events.put(('error', str(exc)))

    def start(path=None):
        if state['busy']:
            return
        cancel.clear()
        state['busy'] = True
        retry.configure(state='disabled')
        offline.configure(state='disabled')
        status.set('Preparing fonts...')
        bar.configure(mode='indeterminate')
        bar.start(15)
        threading.Thread(target=worker, args=(path,), name='omfit-font-download', daemon=True).start()

    def choose():
        path = filedialog.askopenfilename(parent=dialog, title='Import offline font ZIP', filetypes=[('Font ZIP', '*.zip')])
        if path:
            start(path)

    def close():
        state['alive'] = False
        cancel.set()
        bar.stop()
        if state['after'] is not None:
            dialog.after_cancel(state['after'])
            state['after'] = None
        dialog.destroy()

    def poll():
        state['after'] = None
        while state['alive']:
            try:
                event = events.get_nowait()
            except queue.Empty:
                break
            if event[0] == 'progress':
                message, done, total = event[1:]
                if total:
                    bar.stop()
                    bar.configure(mode='determinate', maximum=total, value=done)
                    message += '\n{:.1f}% - {:.1f} / {:.1f} MiB'.format(100 * done / total, done / 1048576, total / 1048576)
                else:
                    bar.configure(mode='indeterminate')
                    bar.start(15)
                status.set(message)
            elif event[0] == 'done':
                state['result'], state['done'] = event[1], True
                close()
                return
            else:
                state['busy'] = False
                bar.stop()
                status.set(event[1])
                retry.configure(state='normal' if kind is not None else 'disabled')
                offline.configure(state='normal')
        if state['alive']:
            state['after'] = dialog.after(100, poll)

    retry = ttk.Button(controls, text='Retry download', command=start)
    retry.pack(side='left')
    offline = ttk.Button(controls, text='Import font ZIP...', command=choose)
    offline.pack(side='left', padx=8)
    ttk.Button(controls, text='Cancel', command=close).pack(side='right')
    dialog.protocol('WM_DELETE_WINDOW', close)
    def destroyed(event):
        if event.widget is dialog:
            cancel.set()
            state['alive'] = False
            if state['after'] is not None:
                try:
                    parent.after_cancel(state['after'])
                except tk.TclError:
                    pass
                state['after'] = None

    dialog.bind('<Destroy>', destroyed, add='+')
    state['after'] = dialog.after(100, poll)
    start(import_path)
    parent.wait_window(dialog)
    if not state['done']:
        raise FontCancelled('Font download cancelled. Open Font resources to retry or import an offline ZIP.')
    return state['result']


def ensure_fonts(kind, parent=None):
    result = cached_fonts(kind)
    if result is not None:
        return result
    parent = _parent(parent)
    if parent is None:
        return ensure_cached_fonts(kind)
    return _dialog(parent, kind)


def _refresh_gui(parent):
    if cached_fonts('gui') is not None:
        from OMFITlib_gui_fonts import refresh_window_fonts
        refresh_window_fonts(parent)


def open_font_manager(parent=None):
    parent = _parent(parent)
    if parent is None:
        raise FontError('Font resources needs an existing Tk window.')
    dialog = tk.Toplevel(parent)
    dialog.title('OMFIT Font Resources')
    body = ttk.Frame(dialog, padding=16)
    body.pack(fill='both', expand=True)
    ttk.Label(body, text='Complete original fonts are shared by all project versions.').pack(anchor='w')
    status = tk.StringVar(master=dialog, value='')
    ttk.Label(body, textvariable=status, justify='left').pack(fill='x', pady=12)
    ttk.Label(body, text=str(cache_directory()), wraplength=540).pack(fill='x', pady=(0, 12))

    def refresh():
        status.set('\n'.join(('GUI' if key == 'gui' else 'Plot') + ' fonts: ' +
                            ('ready' if cached_fonts(key) is not None else 'not downloaded') for key in FONT_BUNDLES))
        _refresh_gui(parent)

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
    ttk.Button(actions, text='Download missing fonts', command=download).pack(side='left')
    ttk.Button(actions, text='Import font ZIP...', command=offline).pack(side='left', padx=8)
    ttk.Button(actions, text='Close', command=dialog.destroy).pack(side='right')
    refresh()
    return dialog
