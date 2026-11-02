"""Small Tk lifecycle helpers, independent of OMFIT controls and font resources."""
from builtins import KeyboardInterrupt, any, bool, getattr, id, int, isinstance, len, max, str, tuple
import inspect
import threading
import time
import tkinter as tk
from tkinter import ttk

SAVE_RETRY_MS = 100


def begin_view_open(api):
    """Filter only the native launcher's unconditional view-open tree events.

    Shared by project views and the template manager. Business events and
    later edits keep their existing handlers. The temporary tag is removed
    after the native launcher returns, including an unsuccessful opening.
    The returned transient counters aid diagnosis; they are not project data.
    """
    aux = getattr(api, '_aux', {})
    parent = aux.get('parentGUI', None)
    if not isinstance(parent, tk.Misc) or aux.get('is_compoundGUI', False):
        return
    root = getattr(api, 'OMFITaux', {}).get('rootGUI', None)
    if not isinstance(root, tk.Misc):
        return
    top = parent.winfo_toplevel()
    gui = getattr(api, '_GUIs', {}).get(str(top), None)
    if gui is None or getattr(top, '_cgyro_open_filter', None) is not None:
        return
    tag = 'OMFITViewOpen' + str(id(top))
    events = dict(active=True, observed=0, suppressed=0)

    def repaint(event):
        events['observed'] += 1
        frame = inspect.currentframe()
        try:
            # The immediate emitter owns the event, not an enclosing GUI.run.
            # A data-changing helper invoked during opening must still pass.
            while frame is not None:
                if frame.f_code is tk.Misc.event_generate.__code__:
                    frame = frame.f_back
                    if frame is not None and (
                            (frame.f_code.co_name == 'update' and frame.f_locals.get('self', None) is gui)
                            or (frame.f_code.co_name == 'run' and frame.f_locals.get('self', None) is gui.pythonFile)):
                        events['suppressed'] += 1
                        return 'break'
                    return
                frame = frame.f_back
        finally:
            del frame

    def finish():
        events['active'] = False
        top._cgyro_open_filter = None
        root.bindtags(tuple(value for value in root.bindtags() if value != tag))
        root.unbind_class(tag, '<<update_treeGUI>>')
        root.deletecommand(command)

    command = root.bind_class(tag, '<<update_treeGUI>>', repaint)
    root.bindtags((tag,) + root.bindtags())
    # Unlike idle work, this cannot run inside native update_idletasks().
    top._cgyro_open_filter = root.after(0, finish)
    return events


def _exists(widget):
    try:
        return bool(widget.winfo_exists())
    except tk.TclError:
        return False


def unbind_callback(widget, sequence, binding):
    """Remove our registered callback, preserving neighbours on Python 3.9.

    Only tkinter's known command form is edited. Unknown Tcl wrappers are left
    intact: deleting their command would leave a dangling binding. Repeated
    disposal and a parent already destroyed by Tk are harmless.
    """
    if not binding:
        return False
    try:
        if not _exists(widget):
            return False
        lines = widget.bind(sequence).split('\n')
        prefix = 'if {"[' + binding + ' '
        kept = [line for line in lines if not line.lstrip().startswith(prefix)]
        if len(kept) == len(lines) or any(binding in line for line in kept):
            return False
        widget.bind(sequence, '\n'.join(kept))
        if widget.tk.call('info', 'commands', binding):
            widget.deletecommand(binding)
        return True
    except tk.TclError:
        if _exists(widget):
            raise
        return False


class RetryWait:
    """Pause a synchronous task without sleeping on the Tk event thread.

    The dialog owns its timer and cancellation only; it never cancels a solver
    or edits a manifest. Headless/worker callers retain ordinary timed waits.
    The caller must recheck its job identity after Tk dispatched other events.
    """
    def __init__(self, ui, title):
        self.parent = getattr(ui, 'OMFITaux', {}).get('rootGUI', None)
        self.title = title
        self.dialog = self.timer = self.done = None
        self.cancelled = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        if self.dialog is not None:
            if self.timer is not None:
                self.parent.after_cancel(self.timer)
                self.timer = None
            if _exists(self.dialog):
                self.dialog.destroy()

    def cancel(self):
        self.cancelled = True
        if self.done is not None:
            self.done.set(True)

    def _destroyed(self, event):
        if event.widget is self.dialog:
            self.cancel()

    def wait(self, seconds, message):
        if self.cancelled:
            raise KeyboardInterrupt('Waiting stopped; the job and collected files are preserved.')
        if threading.current_thread() is not threading.main_thread() or not isinstance(self.parent, tk.Misc):
            time.sleep(seconds)
            return
        if self.cancelled or not _exists(self.parent):
            raise KeyboardInterrupt('Waiting stopped; the job and collected files are preserved.')
        if self.dialog is None:
            self.dialog = tk.Toplevel(self.parent)
            self.dialog.title(self.title)
            self.done = tk.BooleanVar(master=self.parent, value=False)
            self.message = tk.StringVar(master=self.dialog, value='')
            ttk.Label(self.dialog, textvariable=self.message, padding=12).pack(fill='x')
            ttk.Button(self.dialog, text='Stop waiting', command=self.cancel).pack(padx=12, pady=(0, 12))
            self.dialog.protocol('WM_DELETE_WINDOW', self.cancel)
            self.dialog.bind('<Destroy>', self._destroyed, add='+')
        self.message.set(message)
        self.done.set(False)
        self.dialog.deiconify()
        previous_grab = self.dialog.grab_current()
        self.dialog.grab_set()
        self.timer = self.parent.after(max(1, int(seconds * 1000)), lambda: self.done.set(True))
        try:
            self.parent.wait_variable(self.done)
        finally:
            if self.timer is not None:
                self.parent.after_cancel(self.timer)
                self.timer = None
            if _exists(self.dialog):
                self.dialog.grab_release()
                self.dialog.withdraw()
            if previous_grab is not None and _exists(previous_grab):
                previous_grab.grab_set()
        if self.cancelled:
            raise KeyboardInterrupt('Waiting stopped; the job and collected files are preserved.')
