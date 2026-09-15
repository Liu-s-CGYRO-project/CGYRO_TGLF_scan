"""Keep native Tk commands attached to their owning OMFIT GUI.

Some OMFIT controls consult the global last-rendered GUI inside a deferred
callback (notably Entry's multiline editor and FilePicker). Scope only this
project's widget commands; do not patch OMFITx or Tk globally.
"""
from builtins import bool, dict, isinstance, list, set, str, tuple
import tkinter as tk


COMMON_TEXT = {'Tree': '数据树', 'File': '文件', 'Directory': '目录',
               'Update': '应用', 'is string': '按字符串保存'}


def alive(widget):
    try:
        return isinstance(widget, tk.Misc) and bool(widget.winfo_exists())
    except tk.TclError:
        return False


def owner(widget, registry):
    while isinstance(widget, tk.Misc):
        gui = registry.get(str(widget), None)
        if gui is not None and alive(widget):
            return gui
        widget = widget.master
    return None


def bind_actions(content, api):
    aux = getattr(api, '_aux', None)
    registry = getattr(api, '_GUIs', None)
    if not isinstance(aux, dict) or not isinstance(registry, dict):
        return
    gui = owner(content, registry)
    if gui is not None:
        _walk(content, gui, aux, registry)


def _walk(parent, gui, aux, registry):
    for widget in parent.winfo_children():
        options = widget.keys()
        if 'text' in options:
            text = str(widget.cget('text'))
            if text in COMMON_TEXT:
                widget.configure(text=COMMON_TEXT[text])
        if 'command' in options and widget.winfo_class() in ('TButton', 'TCheckbutton', 'TRadiobutton', 'Button', 'Checkbutton', 'Radiobutton'):
            original = str(widget.cget('command'))
            if original and original != getattr(widget, '_cgyro_scoped_command', None):
                command = tuple(widget.tk.splitlist(original))
                widget.configure(command=_callback(widget, command, gui, aux, registry))
                widget._cgyro_scoped_command = str(widget.cget('command'))
        _walk(widget, gui, aux, registry)


def _callback(widget, command, gui, aux, registry):
    def invoke(*args):
        # A callback must never borrow an unrelated GUI's module or locks.
        if registry.get(str(gui.top), None) is not gui or not alive(widget):
            return
        previous_top, previous_parent = aux.get('topGUI', None), aux.get('parentGUI', None)
        existing = set(registry)
        aux.update(dict(topGUI=gui.top, parentGUI=widget.master))
        try:
            result = widget.tk.call(*command, *args)
            # Native multiline editors are created during the command. Give
            # their Apply button the same owner and local Chinese captions.
            if alive(widget.master):
                _walk(widget.master, gui, aux, registry)
            # Native submodule GUIs opened from these buttons belong to the
            # same workflow, even though their TopLevels are root children.
            for key, child_gui in list(registry.items()):
                if key not in existing and alive(child_gui.parentGUI):
                    _walk(child_gui.parentGUI, child_gui, aux, registry)
            return result
        finally:
            previous_gui = registry.get(str(previous_top), None)
            if previous_gui is not None and alive(previous_top):
                aux.update(dict(topGUI=previous_top, parentGUI=previous_parent if alive(previous_parent)
                           else previous_gui.parentGUI))
            elif registry.get(str(gui.top), None) is gui and alive(gui.top):
                aux.update(dict(topGUI=gui.top, parentGUI=gui.parentGUI))
            else:
                aux.update(dict(topGUI=None, parentGUI=None))
    return invoke
