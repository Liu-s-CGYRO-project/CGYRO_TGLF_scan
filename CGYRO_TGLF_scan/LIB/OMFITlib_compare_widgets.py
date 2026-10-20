"""Reusable OMFIT selectors and one native Tk legend editor."""
from OMFITlib_gui_fonts import configure_window_fonts
from OMFITlib_cgyro_archive import canonical_case_key, case_parts as archived_case_parts

# OMFIT libraries inherit a pylab namespace; keep Python scalar/iterator semantics.
from builtins import (
    RuntimeError,
    ValueError,
    dict,
    enumerate,
    float,
    hasattr,
    int,
    isinstance,
    len,
    list,
    min,
    range,
    reversed,
    set,
    str,
    zip,
)
import os
from collections import Counter, OrderedDict
from decimal import Decimal, InvalidOperation
import numpy as np
from OMFITlib_compare_state import (
    dict_path,
    has_values,
    stable_keys,
    sync_flags,
)

LEGEND_ORDER_OPTIONS = ['Plot order', 'Natural', 'Isotope mass', 'Alphabetical', 'Reverse alphabetical', 'Manual order']


def _display_scan_values(values):
    """Unify old numeric string keys and new numbers for native Entry display.

    Keep archive keys and saved selections intact. Conversion is presentation
    only, including reset defaults; never shorten a value at lost precision.
    """
    if isinstance(values, str) or not hasattr(values, '__iter__'):
        return values
    result = []
    for value in values:
        try:
            number = Decimal(str(value))
            if number.is_finite():
                if number == number.to_integral_value():
                    value = int(number)
                elif Decimal(str(float(number))) == number:
                    value = float(number)
        except (InvalidOperation, ValueError):
            pass  # Non-numeric options retain their literal value.
        result.append(value)
    return result


class ComparisonWidgets:
    def __init__(self, root, ui):
        self.root = root
        self.ui = ui

    def _dict_path(self, prefix, *keys):
        return dict_path(prefix, *keys)


    def _normalize_value_list(self, values):
        return np.array(stable_keys(dict.fromkeys(values)))


    def _is_nonempty_selection(self, value):
        return has_values(value)

    def _prune_mapping_keys(self, mapping, valid):
        for key in list(mapping):
            if key not in valid:
                del mapping[key]

    def _intersection_of_keysets(self, collections):
        if not collections:
            return []
        visible = ({key for key in values if not str(key).startswith('__')}
                   for values in collections.values())
        return stable_keys(dict.fromkeys(set.intersection(*visible)))


    def _split_2d_param_name(self, name):
        parts = str(name).split('+', 1)
        return (parts[0].strip(), parts[1].strip() if len(parts) == 2 else 'para2')

    def _case_parts(self, value):
        return archived_case_parts(value)

    def _case_caption(self, value):
        """Short display text only; never replace stored case identifiers."""
        parts = self._case_parts(value)
        if parts is None:
            return canonical_case_key(value)
        nr, rho, ion = parts
        radius = 'nr=' + nr if rho == 'unknown' else 'ρ=' + rho
        return '{} · {}'.format(radius, '原始' if ion == 'BASE' else ion)

    def _choice_label(self, value):
        text = str(value)
        caption = self._case_caption(value)
        if caption != text:
            return caption, text
        return (text, '') if len(text) <= 18 else (text[:17] + '…', text)

    def _choice_labels(self, values):
        labels = {value: self._choice_label(value) for value in values}
        counts = Counter(label for label, _ in labels.values())
        for value, (label, help_text) in labels.items():
            if counts[label] > 1 and self._case_caption(value) != str(value):
                # Equal radii and isotopes from different source inputs still
                # need distinct visible choices. Keep the isotope in full.
                labels[value] = ('{} · {}'.format(str(value).split('__', 1)[0], label), help_text)
        return labels

    def _parameter_entry(self, path, name, values, default_values=None):
        label, full_name = self._choice_label(name)
        self.ui.Entry(path, label, default=_display_scan_values(values if default_values is None else default_values),
                      preentry=_display_scan_values,
                      width=24, multiline=True,
                      kwlabel={'width': 20, 'anchor': 'w'},
                      help=(full_name + '\n' if full_name else '') + '所选扫描值；可使用列表。重置恢复当前结果的全部取值。')

    def _render_index_checkbox_grid(self, path_template, values, cols=2, labels=None):
        labels = self._choice_labels(values) if labels is None else labels
        for begin in range(0, len(values), cols):
            with self.ui.same_row():
                for idx in range(begin, min(begin + cols, len(values))):
                    label, help_text = labels[values[idx]]
                    self.ui.CheckBox(path_template.format(idx=idx), label,
                                     updateGUI=True, width=18, help=help_text)

    def _render_key_checkbox_grid(self, path_builder, values, cols=2, labels=None):
        labels = self._choice_labels(values) if labels is None else labels
        for begin in range(0, len(values), cols):
            with self.ui.same_row():
                for key in values[begin:begin + cols]:
                    label, help_text = labels[key]
                    self.ui.CheckBox(path_builder(key), label, updateGUI=True, width=18, help=help_text)

    def _render_parameter_entries(self, state, flag_key, selected_key, parameters,
                                  checkbox_path_builder, entry_path_builder, value_keys_builder,
                                  unchecked_policy='empty', entry_renderer=None):
        selected = state.setdefault(selected_key, {})
        flags = sync_flags(state, flag_key, parameters, selected_key)
        self._prune_mapping_keys(selected, parameters)
        # Match the shared compact layout's two columns. Splitting groups of
        # three into two columns left a separate short row after every group.
        for begin in range(0, len(parameters), 2):
            with self.ui.same_row():
                for idx in range(begin, min(begin + 2, len(parameters))):
                    name = parameters[idx]
                    label, help_text = self._choice_label(name)
                    self.ui.CheckBox(checkbox_path_builder(idx, name), label,
                                     updateGUI=True, width=18, help=help_text)
        for idx, name in enumerate(parameters):
            if flags.get(idx, None):
                available = self._normalize_value_list(value_keys_builder(name))
                if name not in selected:
                    selected[name] = available.copy()
                if entry_renderer is None or not entry_renderer(name, selected):
                    self._parameter_entry(entry_path_builder(name), name, selected[name], default_values=available)
            else:
                selected.pop(name, None)
        if not parameters:
            self.ui.Label('所选案例没有共同的扫描参数。', align='left')
        return selected


    def _render_tglf_parameter_selection_block(self, tglf_state, path_builder, tglf_results,
                                              para_list, spectra_mode, rhos):
        key = 'selected_paras_2d' if spectra_mode == '2D' else 'selected_paras'
        selected = tglf_state.setdefault(key, {})
        flags = sync_flags(tglf_state, 'para_flag', para_list, key)
        self._prune_mapping_keys(selected, para_list)
        self._render_index_checkbox_grid(path_builder('TGLF', 'para_flag')+'[{idx}]', para_list)
        for idx, name in enumerate(para_list):
            if not flags.get(idx, None):
                selected.pop(name, None)
                continue
            nodes = [tglf_results[rho][name] for rho in rhos if rho in tglf_results and name in tglf_results[rho]]
            if spectra_mode == '2D':
                p1_name, p2_name = self._split_2d_param_name(name)
                first = self._normalize_value_list(k for node in nodes for k in node.keys())
                second = self._normalize_value_list(k2 for node in nodes for sub in node.values() for k2 in sub.keys())
                cfg = selected.setdefault(name, {'para1_values': first.copy(), 'para2_values': second.copy()})
                for field, title, available in [('para1_values', p1_name, first), ('para2_values', p2_name, second)]:
                    self._parameter_entry(path_builder('TGLF', key, name, field),
                                          '{}: {}'.format(name, title), cfg.get(field, []), default_values=available)
            else:
                available = self._normalize_value_list(k for node in nodes for k in node.keys())
                selected.setdefault(name, available.copy())
                self._parameter_entry(path_builder('TGLF', key, name), name, selected[name], default_values=available)
        if not para_list:
            self.ui.Label('所选半径没有共同的 TGLF 扫描参数。', align='left')

    def _selected_param_keys(self, selected):
        return [str(key) for key, value in selected.items() if has_values(value)]

    def _render_legend_order_controls(self, path_builder, state, default_legend_order='', editor_title='图例顺序'):
        self.ui.ComboBox(path_builder('legend_order_mode'), OrderedDict(zip(
            ['按绘图顺序', '自然排序', '按质量 H → D → T', '字母顺序', '字母逆序', '手动指定'], LEGEND_ORDER_OPTIONS)),
                         '图例排序', default='Plot order', updateGUI=True, width=22,
                         kwlabel={'width': 16, 'anchor': 'w'},
                         help='按质量：H、D、T 依次排列，同种离子内自然排序；其他或无法识别的图例排在后面。')
        if state.get('legend_order_mode', None) == 'Manual order':
            self.ui.Entry(path_builder('legend_order_text'),
                          '排序关键词', default=default_legend_order, width=24,
                          kwlabel={'width': 16, 'anchor': 'w'}, help='按显示顺序填写图例名称或关键词，用逗号分隔；支持 re:正则表达式。')
            self.ui.Button('编辑图例顺序…', lambda: self._edit_legend_order(state, default_legend_order, editor_title), width=18)
        self.ui.Label('在图中点击图例，可显示或隐藏对应曲线。', align='left')

    def _edit_legend_order(self, state, default_text, title):
        """Use the existing Tk application; Cancel never opens another toolkit/dialog."""
        import tkinter as tk
        from tkinter import ttk
        parent = tk._default_root
        if parent is None:
            raise RuntimeError('Open the comparison panel in OMFIT before editing the legend list.')
        win = tk.Toplevel(parent)
        configure_window_fonts(win)
        win.title(title)
        win.geometry('480x380')
        ttk.Label(win, text='拖动条目调整顺序；可添加关键词或 re:正则表达式。', wraplength=440).pack(padx=10, pady=8)
        box = tk.Listbox(win, exportselection=False)
        box.pack(fill='both', expand=True, padx=10)
        text = state.get('legend_order_text', None) or default_text
        for item in dict.fromkeys(part.strip() for part in text.split(',') if part.strip()):
            box.insert(tk.END, item)
        row = ttk.Frame(win)
        row.pack(fill='x', padx=10, pady=8)
        entry = ttk.Entry(row)
        entry.pack(side='left', fill='x', expand=True)

        def add():
            value = entry.get().strip()
            if value:
                box.insert(tk.END, value)
                entry.delete(0, tk.END)

        def remove():
            for idx in reversed(box.curselection()):
                box.delete(idx)

        ttk.Button(row, text='添加', command=add).pack(side='left')
        ttk.Button(row, text='删除', command=remove).pack(side='left')
        dragging = [None]

        def move(event):
            src, dst = dragging[0], box.nearest(event.y)
            if src is None or dst == src or not 0 <= src < box.size():
                return
            value = box.get(src)
            box.delete(src)
            box.insert(dst, value)
            dragging[0] = dst

        box.bind('<Button-1>', lambda event: dragging.__setitem__(0, box.nearest(event.y)))
        box.bind('<B1-Motion>', move)

        def save():
            state['legend_order_text'] = ','.join(dict.fromkeys(box.get(0, tk.END)))
            win.destroy()
            self.ui.UpdateGUI()

        footer = ttk.Frame(win)
        footer.pack(pady=8)
        ttk.Button(footer, text='保存', command=save).pack(side='left', padx=5)
        ttk.Button(footer, text='取消', command=win.destroy).pack(side='left', padx=5)
        win.transient(parent)
        win.grab_set()
        win.wait_window()

    def _select_export_directory(self, initial_dir=''):
        import tkinter as tk
        from tkinter import filedialog
        parent = tk._default_root
        if parent is None:
            raise RuntimeError('Open the comparison panel in OMFIT before choosing an export folder.')
        return filedialog.askdirectory(parent=parent, title='选择导出目录',
                                       initialdir=initial_dir if os.path.isdir(initial_dir) else os.getcwd()) or None

    def _render_tolerance_toggle(self, path, state, key, label, **unused):
        with self.ui.same_row():
            self.ui.CheckBox(path(key), label, default=False, updateGUI=True, width=24)
            self.ui.Entry(path('error_tolerance'), '相对波动上限', default=0.01, width=10,
                          kwlabel={'width': 10, 'anchor': 'w'},
                          help='相对时间波动阈值，0.01 表示 1%。勾选过滤后，ω 或 γ 的相对波动超过此值的点被排除；未勾选时不执行过滤。')
