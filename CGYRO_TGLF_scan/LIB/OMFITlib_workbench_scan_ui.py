"""Shared CGYRO/TGLF scan fields. Host supplies ui, label and actions.factory; no solver calls.

Public methods remain inherited by ProjectUI for saved GUIs and callbacks.
Keep OMFITlib imports at module scope: native GUI execution clears its import hook.
"""
from builtins import dict, float, isinstance, len
import tkinter as tk
from OMFITlib_cgyro_scan_values import parameter_range_defaults, range_values, value_list
from OMFITlib_cgyro_parameters import FIELDS, parameter_value


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

    def scan_value_spec(self, parent, key, values, parameter=None, source=None):
        spec = parent.setdefault(key, self.actions.factory())
        spec.setdefault('mode', 'list')
        try:
            current = value_list(values, '取值')
            defaults = parameter_range_defaults(parameter, current) if parameter else dict(
                start=float(current[0]), end=float(current[-1]), count=len(current))
        except (TypeError, ValueError, OverflowError):
            if parameter and (parameter in (source or {}) or parameter in FIELDS):
                reference = source[parameter] if source is not None and parameter in source else FIELDS[parameter][2]
                value = parameter_value(parameter, reference)
                defaults = dict(start=value, end=value, count=1)
            else:
                defaults = dict(start=.1, end=1., count=10)
        for name, value in defaults.items():
            spec.setdefault(name, value)
        if parameter:
            spec.setdefault('parameter', parameter)
        factor = spec.setdefault('factor', self.actions.factory())
        factor.setdefault('start', 1.0)
        factor.setdefault('end', 3.0)
        factor.setdefault('count', 3)
        return spec

    def cgyro_axis_parameter_changed(self, cfg, pkey, rkey, source, location=None):
        """A newly selected parameter starts at its own input value."""
        name = cfg[pkey]
        spec = cfg['value_specs'][rkey]
        if spec.get('parameter', name) == name:
            return
        cfg[rkey] = [parameter_value(name, source[name] if name in source else FIELDS[name][2])]
        mode = spec.get('mode', 'list')
        spec.clear()
        self.scan_value_spec(cfg['value_specs'], rkey, cfg[rkey], name, source)['mode'] = mode

    def cgyro_axis_list_changed(self, cfg, pkey, rkey, location=None):
        defaults = parameter_range_defaults(cfg[pkey], cfg[rkey])
        cfg['value_specs'][rkey].update(defaults)

    def cgyro_axis_mode_changed(self, cfg, pkey, rkey, source, location=None):
        spec, name = cfg['value_specs'][rkey], cfg[pkey]
        if spec['mode'] == 'list':
            parameter_range_defaults(name, cfg[rkey])
            cfg[rkey] = [parameter_value(name, value) for value in value_list(cfg[rkey], name)]
        elif spec['mode'] == 'range':
            try:
                for value in range_values(spec, name):
                    parameter_value(name, value)
            except ValueError:
                try:
                    defaults = parameter_range_defaults(name, cfg[rkey])
                except ValueError:
                    value = source[name] if name in source else FIELDS[name][2]
                    defaults = parameter_range_defaults(name, [value])
                spec.update(defaults)

    def scan_value_fields(self, spec, prefix, values_path, caption='取值列表', postcommand=None):
        mode = spec.get('mode', 'list')
        if mode == 'list':
            self.scan_field(self.ui.Entry(values_path, caption, width=28, updateGUI=True, refresh_tree=False,
                postcommand=postcommand,
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
