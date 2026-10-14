"""Explicit two-state bindings for native OMFIT checkbuttons."""
from builtins import isinstance, str
import tkinter as tk


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
        # Each checkbutton needs its own variable. Tk's implicit variable can
        # otherwise replace OMFIT's explicit state with the blue alternate state.
        variable = tk.BooleanVar(master=control, value=value)
        control.configure(variable=variable, onvalue=1, offvalue=0)
        variable.set(value)
        control.state(['!alternate', 'selected' if value else '!selected'])
        control._omfit_boolean = variable
    return control
