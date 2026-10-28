"""Small controls with explicit data and refresh boundaries."""
from builtins import all, getattr, isinstance, len, list, max, min, str, tuple
import tkinter as tk
from tkinter import ttk
from OMFITlib_gui_api import set_checkbox_value, style_checkbox
from OMFITlib_gui_deferred import deferred_section
from OMFITlib_gui_fonts import style_widget

PARAMETER_PAGE_SIZE = 24
SEARCH_DELAY_MS = 180


def parameter_matches(rows, group, query):
    """Search the complete name/label catalog; groups apply only without text."""
    terms = str(query).strip().casefold().split()
    return [name for name, label, category, common in rows
            if (all(term in (name + ' ' + label).casefold() for term in terms) if terms else
                group == 'all' or (group == 'common' and common) or group == category)]


class ParameterList:
    """Filter a captured input catalog, rebuilding only a bounded row panel.

    No result access, input catalog rebuild, or native expression evaluation
    happens while typing a search. Scientific editors remain native OMFIT
    controls; their commits invalidate hidden Run previews as usual.
    """
    def __init__(self, ui, state, group_key, search_key, groups, rows, render):
        self.state, self.group_key, self.search_key = state, group_key, search_key
        self.rows, self.render = rows, render
        self.page, self.pending, self.selection = 0, None, None
        if state[group_key] not in groups.values():
            state[group_key] = 'all'
        self.names = parameter_matches(rows, state[group_key], state[search_key])
        parent = getattr(ui, '_aux', {}).get('parentGUI', None)
        if not isinstance(parent, tk.Misc):
            render(self.names)  # Non-Tk inspection/export has no widget limit.
            return
        self.toolbar = ttk.Frame(parent)
        self.toolbar.pack(side=tk.TOP, fill=tk.X)
        ttk.Label(self.toolbar, text='显示').grid(row=0, column=0, sticky='w')
        self.groups = groups
        self.group = ttk.Combobox(self.toolbar, values=list(groups), state='readonly', width=16)
        self.group.current(list(groups.values()).index(state[group_key]))
        self.group.grid(row=0, column=1, sticky='ew')
        ttk.Label(self.toolbar, text='搜索全部参数').grid(row=0, column=2, sticky='w')
        self.query = tk.StringVar(master=self.toolbar, value=str(state[search_key]))
        self.search = ttk.Entry(self.toolbar, textvariable=self.query, width=24)
        self.search.grid(row=0, column=3, sticky='ew')
        self.toolbar.columnconfigure(3, weight=1)
        self.count = ttk.Label(self.toolbar)
        self.count.grid(row=1, column=0, columnspan=2, sticky='w')
        buttons = ttk.Frame(self.toolbar)
        buttons.grid(row=1, column=2, columnspan=2, sticky='e')
        self.previous = ttk.Button(buttons, text='上一页', command=lambda: self.move(-1))
        self.following = ttk.Button(buttons, text='下一页', command=lambda: self.move(1))
        self.previous.pack(side=tk.LEFT)
        self.following.pack(side=tk.LEFT)
        for widget in (self.group, self.search, self.count, self.previous, self.following):
            style_widget(widget)
        self.section = deferred_section(ui, lambda: render(self.visible_names()), local=True, container=True)
        self.group.bind('<<ComboboxSelected>>', lambda event: self.filter())
        self.search.bind('<Return>', self.flush)
        self.search.bind('<KP_Enter>', self.flush)
        self.trace = self.query.trace_add('write', self.schedule)
        self.toolbar.bind('<Destroy>', self.close, add='+')
        self.show()

    def visible_names(self):
        start = self.page * PARAMETER_PAGE_SIZE
        return self.names[start:start + PARAMETER_PAGE_SIZE]

    def schedule(self, *args):
        self.state[self.search_key] = self.query.get()
        self.cancel()
        self.pending = self.toolbar.after(SEARCH_DELAY_MS, self.filter)

    def cancel(self):
        if self.pending is not None:
            self.toolbar.after_cancel(self.pending)
            self.pending = None

    def flush(self, event=None):
        self.filter()
        return 'break'

    def filter(self):
        self.cancel()
        self.state[self.group_key] = self.groups[self.group.get()]
        self.state[self.search_key] = self.query.get()
        names = parameter_matches(self.rows, self.state[self.group_key], self.query.get())
        if names != self.names:
            self.names, self.page = names, 0
        self.show()

    def move(self, offset):
        self.page = max(0, min((len(self.names) - 1) // PARAMETER_PAGE_SIZE, self.page + offset))
        self.show()

    def show(self):
        visible = self.visible_names()
        start = self.page * PARAMETER_PAGE_SIZE
        text = ('显示 {}–{} / {} 项'.format(start + 1, start + len(visible), len(self.names))
                if visible else '没有匹配的参数')
        self.count.configure(text=text + '（目录 {} 项）'.format(len(self.rows)))
        self.previous.configure(state='normal' if self.page else 'disabled')
        self.following.configure(state='normal' if start + len(visible) < len(self.names) else 'disabled')
        selection = tuple(visible)
        if selection != self.selection:
            self.selection = selection
            if self.section is None:
                self.render(visible)
            else:
                # A view filter must not invalidate sibling tabs or rebuild
                # its search field. Only native parameter commits do that.
                self.section.built = False
                self.section.show()

    def close(self, event):
        if event.widget is self.toolbar:
            self.cancel()
            self.query.trace_remove('write', self.trace)


def boolean_value(value):
    text = str(value).strip().lower()
    if text in ('true', '.true.', '1', '1.0'):
        return True
    if text in ('false', '.false.', '0', '0.0'):
        return False
    raise ValueError('布尔选项必须为 True / False 或 1 / 0。')


def checkbox(ui, path, mapping, key, caption, default=False, updateGUI=False, **kwargs):
    value = boolean_value(mapping.get(key, default))
    mapping[key] = value
    control = ui.CheckBox(path, caption, default=default, updateGUI=updateGUI, **kwargs)[0]
    if isinstance(control, tk.Misc):
        set_checkbox_value(control, value)
        style_checkbox(control)
    return control
