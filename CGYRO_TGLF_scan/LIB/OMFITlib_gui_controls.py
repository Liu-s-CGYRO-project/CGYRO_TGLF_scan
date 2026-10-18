"""Explicit two-state bindings for native OMFIT checkbuttons."""
from builtins import isinstance, str
import tkinter as tk
from OMFITlib_gui_api import set_checkbox_value, style_checkbox


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
