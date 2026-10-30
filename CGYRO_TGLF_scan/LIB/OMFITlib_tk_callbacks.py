"""Small Tk lifecycle helpers, independent of OMFIT controls and font resources."""
from builtins import KeyboardInterrupt, any, bool, getattr, int, isinstance, len, max
import threading
import time
import tkinter as tk
from tkinter import ttk

SAVE_RETRY_MS = 100


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
        self.dialog = self.timer = None
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
        self.done.set(True)

    def _destroyed(self, event):
        if event.widget is self.dialog:
            self.cancel()

    def wait(self, seconds, message):
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
