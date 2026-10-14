"""Local OMFIT widget adapter: full help text without global tooltip patches."""
from builtins import callable, getattr, isinstance, list, max, min, set, str, tuple
import inspect
import tkinter as tk
from tkinter import ttk


def show_help(parent, text):
    if isinstance(text, (list, tuple)):
        text = '\n'.join(str(value) for value in text)
    top = tk.Toplevel(parent.winfo_toplevel())
    top.title('说明')
    top.transient(parent.winfo_toplevel())
    sw, sh = top.winfo_screenwidth(), top.winfo_screenheight()
    width, height = min(720, sw - 80), min(460, sh - 100)
    x = max(0, min(parent.winfo_rootx(), sw - width - 20))
    y = max(0, min(parent.winfo_rooty(), sh - height - 50))
    top.geometry('{}x{}+{}+{}'.format(width, height, x, y))
    frame = ttk.Frame(top, padding=12)
    frame.pack(fill='both', expand=True)
    body = tk.Text(frame, wrap='word', width=1, height=1, padx=10, pady=8,
                   font='TkDefaultFont', borderwidth=0)
    scroll = ttk.Scrollbar(frame, command=body.yview)
    body.configure(yscrollcommand=scroll.set)
    body.grid(row=0, column=0, sticky='nsew')
    scroll.grid(row=0, column=1, sticky='ns')
    frame.columnconfigure(0, weight=1)
    frame.rowconfigure(0, weight=1)
    body.insert('1.0', str(text))
    body.configure(state='disabled')
    ttk.Button(frame, text='关闭', command=top.destroy).grid(row=1, column=0, columnspan=2, pady=(10, 0))
    top.bind('<Escape>', lambda event: top.destroy())
    body.focus_set()
    return top


def children(parent):
    result = []
    if isinstance(parent, tk.Misc):
        for child in parent.winfo_children():
            result.append(child)
            result.extend(children(child))
    return result


class ProjectWidgets:
    def __init__(self, api):
        self._api = api
        self._project_widget_adapter = True

    def __getattr__(self, name):
        function = getattr(self._api, name)
        if name not in ('Entry', 'ComboBox', 'Button', 'CheckBox', 'FilePicker', 'RadioButtons') or not callable(function):
            return function

        def create(*args, **kwargs):
            parent = getattr(self._api, '_aux', {}).get('parentGUI')
            help_text = kwargs.get('help', '')
            # Respect native positional signatures; never rewrite entry values.
            if not help_text:
                try:
                    help_text = inspect.signature(function).bind_partial(*args, **kwargs).arguments.get('help', '')
                except (TypeError, ValueError):
                    pass
            before = set(parent.winfo_children()) if isinstance(parent, tk.Misc) else set()
            result = function(*args, **kwargs)
            added = []
            if isinstance(parent, tk.Misc):
                for frame in parent.winfo_children():
                    if frame not in before:
                        added.extend([frame] + children(frame))
            defaults = []
            for widget in added:
                if widget.winfo_class() != 'TButton':
                    continue
                caption = str(widget.cget('text'))
                if caption in ('D', 'd'):
                    widget.configure(text='恢复默认')
                    defaults.append(widget)
                elif caption == '?' and help_text:
                    widget.configure(command=lambda w=widget, text=help_text: show_help(w, text))
            if name == 'CheckBox' and result:
                for control in result:
                    if isinstance(control, tk.Misc) and not control.instate(['alternate']):
                        variable = tk.BooleanVar(master=control, value=control.instate(['selected']))
                        control.configure(variable=variable, onvalue=True, offvalue=False)
                        control._omfit_boolean = variable
                # Native reset changes widget state directly; keep our private
                # variable in step so the following click cannot invert it twice.
                for button in defaults:
                    command = tuple(button.tk.splitlist(str(button.cget('command'))))
                    def reset(command=command, button=button, controls=result):
                        value = button.tk.call(*command)
                        for control in controls:
                            variable = getattr(control, '_omfit_boolean', None)
                            if variable is not None and control.winfo_exists():
                                variable.set(control.instate(['selected']))
                        return value
                    button.configure(command=reset)
            return result
        return create


def adapt(api):
    return api if getattr(api, '_project_widget_adapter', False) else ProjectWidgets(api)
