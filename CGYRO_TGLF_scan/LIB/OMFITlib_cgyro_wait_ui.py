"""Compact the native wait panel for one job; retain native stop controls.

Queue polls describe scheduler state, not simulated time or solver success.
The native progress bar stays indeterminate until collection can verify outputs.
No result readers, background Tk calls or whole-window GUI updates are used.
"""
from builtins import (all, getattr, hasattr, isinstance, len, list, str)
import tkinter as tk
from tkinter import ttk


class NativeWaitView:
    def __init__(self, ui, job_id, markers):
        self.job_id, self.markers = str(job_id), markers
        self.root = getattr(ui, '_aux', {}).get('rootGUI', None)
        if not isinstance(self.root, tk.Misc):
            self.root = getattr(tk, '_default_root', None)
        self.widgets = {}
        self.status = '作业 {}：正在等待调度状态。'.format(self.job_id)
        self.output_tail = ''

    def __enter__(self):
        if isinstance(self.root, tk.Misc):
            if not hasattr(self.root, '_cgyro_wait_views'):
                self.root._cgyro_wait_views = {}
                def mapped(event, root=self.root):
                    for view in list(root._cgyro_wait_views.values()):
                        view.attach(event.widget)
                self.root.bind_class('Text', '<Map>', mapped, add='+')
            self.root._cgyro_wait_views[self] = self
        return self

    def attach(self, widget):
        if not isinstance(widget, tk.Text) or widget in self.widgets:
            return
        try:
            original = widget.get('1.0', 'end-1c')
            if not self.markers or not all(marker in original for marker in self.markers):
                return
            options = {key: widget.cget(key) for key in ('height', 'width', 'wrap', 'font', 'state')}
            # Keep the original command in the Text for exact-job Kill local
            # matching. Eliding it removes its layout cost, not its identity.
            widget.configure(state='normal')
            widget.insert('1.0', self.status + '\n等待期间显示队列状态；结束后收集并校验结果。\n')
            widget.tag_add('cgyro_wait_command', '3.0', 'end-1c')
            widget.tag_configure('cgyro_wait_command', elide=True)
            widget.configure(height=3, width=64, wrap='word', state='disabled')
            bars = [child for child in widget.master.winfo_children() if isinstance(child, ttk.Progressbar)]
            for bar in bars:
                bar.stop()
                bar.configure(mode='indeterminate')
                bar.start(80)
            self.widgets[widget] = (original, options, bars)
            top = widget.winfo_toplevel()
            if top is not self.root:
                # A reused workflow window may retain a height from the earlier
                # step. Let Tk fit the compact panel, progress and buttons.
                top.geometry('')
        except tk.TclError:
            return  # Native execution may finish while a Map event is pending.

    def progress(self, output):
        """Called by native OMFIT on the Tk thread when new stdout arrives."""
        previous = self.status
        tail = str(output)[-8192:]
        lines = tail.splitlines() if tail != self.output_tail else ()
        self.output_tail = tail
        for line in lines:
            fields = line.split('|')
            if len(fields) == 5 and fields[:2] == ['CGYRO_WAIT', self.job_id]:
                if all(value.isdigit() for value in fields[2:]):
                    self.status = '作业 {}：排队 {}，运行 {}，其他活动状态 {}。'.format(self.job_id, *fields[2:])
            elif fields == ['CGYRO_WAIT_LEFT', self.job_id]:
                self.status = '作业 {}：已离开队列，等待收集校验。'.format(self.job_id)
        phase = 0
        for widget, (_, _, bars) in list(self.widgets.items()):
            try:
                if self.status != previous:
                    widget.configure(state='normal')
                    widget.delete('1.0', '1.end')
                    widget.insert('1.0', self.status)
                    widget.configure(state='disabled')
                for bar in bars:
                    phase = bar['value']
            except tk.TclError:
                continue
        return phase  # Preserve the native animation; this is not a percentage.

    def __exit__(self, *_):
        if isinstance(self.root, tk.Misc):
            self.root._cgyro_wait_views.pop(self, None)
        for widget, (original, options, bars) in self.widgets.items():
            try:
                widget.configure(state='normal')
                widget.delete('1.0', 'end')
                widget.tag_delete('cgyro_wait_command')
                widget.insert('1.0', original)
                widget.configure(**options)
                for bar in bars:
                    bar.stop()
            except tk.TclError:
                pass
        self.widgets.clear()
