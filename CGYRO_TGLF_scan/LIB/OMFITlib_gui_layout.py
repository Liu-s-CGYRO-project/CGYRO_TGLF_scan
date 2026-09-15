"""Local font and geometry adjustments for this project's native OMFIT pages."""
from builtins import all, int, isinstance, len, list, max, min, range, str, tuple
import hashlib
import tkinter as tk
from tkinter import font as tkfont, ttk


def finish_gui_layout(label):
    """Style the page containing an OMFITx.Label, retaining native bindings.

    OMFITx.Label returns a label in a row frame in the GUI's content frame.
    Only that content subtree is changed; OMFIT's fonts and global theme remain
    intact. Non-Tk hosts (batch checks and tree-only tests) require no layout.
    """
    if not isinstance(label, tk.Misc):
        return
    content = label.master.master
    if getattr(content, '_cgyro_gui_layout', None) is not None:
        return
    content._cgyro_gui_layout = NativeLayout(content, label)


class NativeLayout:
    def __init__(self, content, label):
        self.content = content
        self.style = ttk.Style(content)
        base = label.cget('font') or self.style.lookup(label.cget('style') or 'TLabel', 'font') or 'TkDefaultFont'
        original = tkfont.Font(root=content, font=base).actual()
        probe = tkfont.Font(root=content, **original)
        family = str(content.tk.call('font', 'actual', str(probe), '-family', '中'))
        self.normal = tkfont.Font(root=content, family=family, size=original['size'])
        self.bold = tkfont.Font(root=content, family=family, size=original['size'], weight='bold')
        self.gap = max(4, self.normal.metrics('linespace') // 5)
        self.tag = hashlib.sha256(repr(self.normal.actual()).encode('utf-8')).hexdigest()[:12]
        self.rows = []
        self._walk(content)
        self.reflow()

    def _style_name(self, widget, font, **options):
        old = str(widget.cget('style')) or widget.winfo_class()
        name = 'CGYRO.' + self.tag + '.' + old
        self.style.configure(name, font=(font.actual('family'), font.actual('size'), font.actual('weight')), **options)
        widget.configure(style=name)

    def _walk(self, parent):
        children = parent.winfo_children()
        # Native same_row holds one frame per OMFIT control. Reflow those
        # frames, not the label/entry/default/help widgets within each control.
        row = len(children) > 1 and all(child.winfo_class() == 'TFrame' and
            child.winfo_manager() == 'pack' and str(child.pack_info().get('side', '')) == 'left' for child in children)
        for child in children:
            kind = child.winfo_class()
            if kind == 'Toplevel':
                continue
            if kind == 'TLabel':
                current = child.cget('font') or self.style.lookup(child.cget('style') or 'TLabel', 'font') or 'TkDefaultFont'
                bold = tkfont.Font(root=child, font=current).actual('weight') == 'bold'
                child.configure(font=self.bold if bold else self.normal, width=0,
                                padding=(0, self.gap if bold else self.gap // 2))
            elif kind in ('TEntry', 'TCombobox'):
                child.configure(font=self.normal)
                self._style_name(child, self.normal, padding=(4, self.gap))
                if kind == 'TCombobox':
                    child.option_add('*' + str(child).lstrip('.') + '*Listbox.font', self.normal)
            elif kind in ('TButton', 'TCheckbutton', 'TRadiobutton'):
                self._style_name(child, self.normal, padding=(6, self.gap))
                child.configure(width=0)
            elif kind == 'TNotebook':
                old = str(child.cget('style')) or 'TNotebook'
                name = 'CGYRO.' + self.tag + '.' + old
                self.style.configure(name + '.Tab', font=(self.normal.actual('family'), self.normal.actual('size')),
                                     padding=(10, self.gap + 2))
                child.configure(style=name)
            elif kind == 'Text':
                child.configure(font=self.normal, spacing1=self.gap, spacing2=self.gap, spacing3=self.gap)
            self._walk(child)
        if row:
            self.rows.append((parent, children))
            for child in children:
                child.pack_forget()
            parent.bind('<Configure>', lambda event, frame=parent, items=children: self._row(frame, items), add='+')

    def _row(self, frame, items):
        if not frame.winfo_exists():
            return
        width = frame.winfo_width()
        if width <= 1:
            width = max(1, self.content.winfo_toplevel().winfo_width() - 40)
        required = max(item.winfo_reqwidth() + 10 for item in items)
        columns = max(1, min(len(items), width // max(1, required)))
        if getattr(frame, '_cgyro_columns', None) == columns:
            return
        frame._cgyro_columns = columns
        for index in range(len(items)):
            frame.columnconfigure(index, weight=1 if index < columns else 0, uniform='cgyro' if index < columns else '')
        for index, item in enumerate(items):
            item.grid(row=index // columns, column=index % columns, sticky='ew', padx=5, pady=self.gap // 2)

    def reflow(self):
        for frame, items in self.rows:
            self._row(frame, items)
