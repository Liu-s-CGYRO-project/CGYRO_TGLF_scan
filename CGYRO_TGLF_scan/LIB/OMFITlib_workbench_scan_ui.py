"""Shared CGYRO/TGLF scan fields. Host supplies ui, label and actions.factory; no solver calls.

Public methods remain inherited by ProjectUI for saved GUIs and callbacks.
Keep OMFITlib imports at module scope: native GUI execution clears its import hook.
"""
from builtins import float, isinstance, len
import tkinter as tk
from OMFITlib_cgyro_scan_values import value_list


class ScanControls:
    """Page mixin; state belongs to the host, never to a module singleton."""
    def scan_field(self, widget, width):
        """Keep short scan fields at their requested width inside native rows."""
        if isinstance(widget, tk.Misc):
            widget._cgyro_field_columns = width
            widget.configure(width=width)
            if widget.winfo_manager() == 'pack':
                widget.pack_configure(expand=False, fill=tk.NONE)
        return widget

    def scan_value_spec(self, parent, key, values):
        spec = parent.setdefault(key, self.actions.factory())
        spec.setdefault('mode', 'list')
        try:
            current = value_list(values, '取值')
            start, end = float(current[0]), float(current[-1])
            count = len(current)
        except (TypeError, ValueError, OverflowError):
            start, end, count = 0.1, 1.0, 10
        spec.setdefault('start', start)
        spec.setdefault('end', end)
        spec.setdefault('count', count)
        factor = spec.setdefault('factor', self.actions.factory())
        factor.setdefault('start', 1.0)
        factor.setdefault('end', 3.0)
        factor.setdefault('count', 3)
        return spec

    def scan_value_fields(self, spec, prefix, values_path, caption='取值列表'):
        mode = spec.get('mode', 'list')
        if mode == 'list':
            self.scan_field(self.ui.Entry(values_path, caption, width=28, updateGUI=True, refresh_tree=False,
                help='可填一个实际数值、列表 [16, 32, 48, 64]，或 NumPy 表达式，如 np.linspace(16, 64, 4)。'
                     '\n表达式在回车确认后生成实际数值；整数参数的各个取值必须是整数。'), 28)
        elif mode == 'original':
            self.label('保留各输入中该参数的原值。')
        else:
            if mode == 'factor':
                prefix += "['factor']"
            with self.ui.same_row():
                frame = getattr(self.ui, '_aux', {}).get('parentGUI', None)
                if isinstance(frame, tk.Misc):
                    frame._cgyro_max_columns = 3
                self.scan_field(self.ui.Entry(prefix + "['start']", '起点', width=8, updateGUI=True, refresh_tree=False), 8)
                self.scan_field(self.ui.Entry(prefix + "['end']", '终点', width=8, updateGUI=True, refresh_tree=False), 8)
                self.scan_field(self.ui.Entry(prefix + "['count']", '点数', width=7, updateGUI=True, refresh_tree=False,
                    help='包含起点和终点；点数为 1 时只取起点。'), 7)
