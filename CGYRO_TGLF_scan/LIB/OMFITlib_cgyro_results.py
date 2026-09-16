"""RUN_DB-backed CGYRO result browser for one-, two- and three-axis scans."""
from builtins import (Exception, TypeError, ValueError, abs, any, dict, float, int,
                      len, list, max, min, range, sorted, str, tuple, zip)
from collections import OrderedDict
import numpy as np
import tkinter as tk
from tkinter import ttk


def _stable_keys(mapping):
    try:
        return list(mapping.keys())
    except Exception:
        return []


def _view_settings(root):
    workbench = root['SETTINGS']['WORKBENCH']
    view = workbench.setdefault('cgyro_result_view', {})
    view.setdefault('run_token', '')
    view.setdefault('ky', '')
    view.setdefault('slice_value', '')
    view.setdefault('tail_fraction', .02)
    return view


def _run_options(root):
    module = root.get('CGYRO_scan', {})
    run_db = module.get('RUN_DB', {})
    records = OrderedDict()
    options = OrderedDict()
    for runid in _stable_keys(run_db):
        if str(runid).startswith('__'):
            continue
        run = run_db[runid]
        for case_id in _stable_keys(run):
            if str(case_id).startswith('__'):
                continue
            case = run[case_id]
            if not hasattr(case, 'get'):
                continue
            info = case.get('__INFO__', None)
            tasks = case.get('__TASKS__', None)
            if info is None or tasks is None:
                continue
            token = str(info.get('run_token', '')).strip() or '{}::{}'.format(runid, case_id)
            entry = dict(info)
            entry.update(dict(runid=runid, case_id=case_id, tasks=tasks,
                              destination=[runid, case_id]))
            records[token] = entry
            label = '{} | {} | {}'.format(runid, case_id, token[:8])
            options[label] = token

    # Pre-1.13 records remain readable, while new records use RUN_DB only.
    legacy = module.get('RUN_INDEX', {})
    for token in _stable_keys(legacy):
        if token in records:
            continue
        entry = legacy[token]
        records[token] = entry
        label = '{} | {} | {}（旧记录）'.format(
            entry.get('runid', '未命名'), entry.get('case_id', '未知案例'), str(token)[:8])
        options[label] = token
    return records, options


def _number_text(value):
    try:
        return '{:.10g}'.format(float(value))
    except (TypeError, ValueError):
        return str(value)


def _unique_numeric(rows, name):
    values = []
    for row in rows:
        try:
            value = float(row.get('values', {}).get(name, None))
        except (TypeError, ValueError):
            continue
        if np.isfinite(value) and not any(np.isclose(value, item, rtol=1e-10, atol=1e-12) for item in values):
            values.append(value)
    return sorted(values)


def _select_numeric(text, choices, label):
    if not choices:
        raise ValueError(label + ' 没有可用取值。')
    try:
        requested = float(text)
    except (TypeError, ValueError):
        return choices[0]
    return min(choices, key=lambda value: abs(value - requested))


def selected_record(root):
    view = _view_settings(root)
    records, options = _run_options(root)
    if not options:
        raise ValueError('尚无已收集的 CGYRO 扫描结果。')
    token = view.get('run_token', '')
    if token not in records:
        token = list(options.values())[-1]
        view['run_token'] = token
    return view, token, records[token], options


def _result_node(root, entry, row):
    node = root['CGYRO_scan']['RUN_DB']
    result_path = row.get('result_path', None)
    if result_path is not None:
        destination = list(entry.get('destination', [])) + list(result_path)
    else:
        destination = row.get('destination', [])
    for key in destination:
        node = node[key]
    return node


def _frequency_summary(result, fraction):
    count = int(result['n_time'])
    if count < 1 or not 0 < fraction <= 1:
        raise ValueError('末段平均比例必须大于 0 且不超过 1。')
    omega = np.asarray(result['freq']['omega'][0], dtype=float).ravel()
    gamma = np.asarray(result['freq']['gamma'][0], dtype=float).ravel()
    if len(omega) != count or len(gamma) != count:
        raise ValueError('频率时间序列长度与 n_time 不一致。')
    tail = max(2, int(count * fraction))
    omega = omega[-tail:]
    gamma = gamma[-tail:]
    if not np.any(np.isfinite(omega)) or not np.any(np.isfinite(gamma)):
        raise ValueError('末段频率数据没有有限值。')
    omega_mean, gamma_mean = float(np.nanmean(omega)), float(np.nanmean(gamma))
    omega_error = float(np.nanstd(omega) / abs(omega_mean)) if omega_mean != 0 else np.nan
    gamma_error = float(np.nanstd(gamma) / abs(gamma_mean)) if gamma_mean != 0 else np.nan
    return omega_mean, gamma_mean, omega_error, gamma_error


def result_grid(root):
    view, token, entry, _ = selected_record(root)
    axes = list(entry.get('scan_axes', []))
    dimensions = int(entry.get('dimensions', len(axes)))
    if dimensions not in (1, 2, 3) or len(axes) != dimensions:
        raise ValueError('运行记录中的参数轴信息无效。')
    tasks = list(entry.get('tasks', {}).values())
    if not tasks:
        raise ValueError('所选运行没有已读取的计算点。')
    names = [str(axis['name']) for axis in axes]
    x_values = _unique_numeric(tasks, names[0])
    if dimensions == 1:
        y_name = 'KY'
        y_values = _unique_numeric(tasks, 'KY')
        filters = {}
    else:
        y_name = names[1]
        y_values = _unique_numeric(tasks, y_name)
        ky_values = _unique_numeric(tasks, 'KY')
        ky = _select_numeric(view.get('ky', ''), ky_values, 'ky')
        view['ky'] = _number_text(ky)
        filters = {'KY': ky}
        if dimensions == 3:
            z_values = _unique_numeric(tasks, names[2])
            z_value = _select_numeric(view.get('slice_value', ''), z_values, names[2])
            view['slice_value'] = _number_text(z_value)
            filters[names[2]] = z_value
    omega = np.full((len(y_values), len(x_values)), np.nan)
    gamma = np.full((len(y_values), len(x_values)), np.nan)
    diagnostics, table_rows = [], []
    fraction = float(view.get('tail_fraction', .02))
    for row in tasks:
        values = row.get('values', {})
        try:
            numeric = {name: float(values[name]) for name in names + ['KY']}
        except (KeyError, TypeError, ValueError):
            diagnostics.append(str(row.get('task_id', '?')) + '：参数记录无效')
            continue
        if any(not np.isclose(numeric[name], value, rtol=1e-10, atol=1e-12)
               for name, value in filters.items()):
            continue
        x_value = numeric[names[0]]
        y_value = numeric[y_name]
        x_index = min(range(len(x_values)), key=lambda i: abs(x_values[i] - x_value))
        y_index = min(range(len(y_values)), key=lambda i: abs(y_values[i] - y_value))
        try:
            om, ga, om_error, ga_error = _frequency_summary(
                _result_node(root, entry, row), fraction)
            omega[y_index, x_index], gamma[y_index, x_index] = om, ga
            table_rows.append(dict(task_id=str(row.get('task_id', '?')),
                                   values=numeric, omega=om, gamma=ga,
                                   omega_error=om_error, gamma_error=ga_error))
        except (KeyError, TypeError, ValueError) as exc:
            diagnostics.append('{}：{}'.format(row.get('task_id', '?'), exc))
    if not np.any(np.isfinite(omega)) and not np.any(np.isfinite(gamma)):
        raise ValueError('当前切片没有可显示结果。' + ('\n' + '\n'.join(diagnostics[:5]) if diagnostics else ''))
    return dict(token=token, entry=entry, dimensions=dimensions, axes=axes,
                x_name=names[0], x=x_values, y_name=y_name, y=y_values,
                filters=filters, omega=omega, gamma=gamma, rows=table_rows,
                diagnostics=diagnostics)


class ResultBrowser:
    def __init__(self, root, ui):
        self.root, self.ui = root, ui
        self.prefix = "root['SETTINGS']['WORKBENCH']['cgyro_result_view']"

    def render(self):
        self.ui.TitleGUI('CGYRO · 扫描结果浏览')
        try:
            view, token, entry, options = selected_record(self.root)
        except ValueError as exc:
            self.ui.Label(str(exc), align='left')
            return
        self.ui.ComboBox(self.prefix + "['run_token']", options, '结果记录', updateGUI=True)
        axes = list(entry.get('scan_axes', []))
        tasks = list(entry.get('tasks', {}).values())
        dimensions = int(entry.get('dimensions', len(axes)))
        names = [str(axis['name']) for axis in axes]
        if dimensions >= 2:
            ky_values = _unique_numeric(tasks, 'KY')
            ky_options = OrderedDict((_number_text(value), _number_text(value)) for value in ky_values)
            if view.get('ky', '') not in ky_options.values() and ky_options:
                view['ky'] = list(ky_options.values())[0]
            self.ui.ComboBox(self.prefix + "['ky']", ky_options, 'ky 切片', updateGUI=True)
        if dimensions == 3:
            values = _unique_numeric(tasks, names[2])
            options_z = OrderedDict((_number_text(value), _number_text(value)) for value in values)
            if view.get('slice_value', '') not in options_z.values() and options_z:
                view['slice_value'] = list(options_z.values())[0]
            self.ui.ComboBox(self.prefix + "['slice_value']", options_z, names[2] + ' 切片', updateGUI=True)
        self.ui.Entry(self.prefix + "['tail_fraction']", '末段平均比例', default=.02,
                      help='0.02 表示对时间序列最后 2% 求平均。')
        if dimensions == 1:
            description = '{} × ky 数值结果'.format(names[0])
        else:
            description = '{} × {} 数值结果'.format(names[0], names[1])
            if dimensions == 3:
                description += '，{} 由上方切片选择'.format(names[2])
            description += '，ky 由上方切片选择'
        self.anchor = self.ui.Label('{}；{} 个已读取计算点。'.format(description, len(tasks)), align='left')
        with self.ui.same_row():
            self.ui.Button('查看当前数值表', self._show_table)
            self.ui.Button('绘制当前结果（可选）', lambda: self.root['PLOTS']['CGYRO_results'].plot())
        self.ui.Label('数值表显示参数、ky、平均 ω/γ 与相对波动，并标出当前范围的最大 γ。', align='left')

    def _show_table(self):
        data = result_grid(self.root)
        rows = data['rows']
        if not rows:
            raise ValueError('当前筛选范围没有可显示的数值结果。')
        names = [str(axis['name']) for axis in data['axes']]
        ordered = sorted(rows, key=lambda row: tuple(row['values'][name] for name in names + ['KY']))
        peak = max((row for row in ordered if np.isfinite(row['gamma'])),
                   key=lambda row: row['gamma'], default=None)
        window = tk.Toplevel(self.anchor.winfo_toplevel())
        window.title('CGYRO 数值结果')
        window.geometry('1200x620')
        title = '{} | {}'.format(data['entry'].get('runid', ''), data['entry'].get('case_id', ''))
        if data['filters']:
            title += ' | ' + ', '.join('{}={:.7g}'.format(key, value)
                                      for key, value in data['filters'].items())
        ttk.Label(window, text=title, anchor='w').pack(fill=tk.X, padx=10, pady=(10, 6))
        frame = ttk.Frame(window)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        columns = ['task'] + names + ['KY', 'omega', 'gamma', 'omega_error', 'gamma_error', 'peak']
        headings = ['任务'] + names + ['ky', '平均 ω', '平均 γ', 'ω 相对波动', 'γ 相对波动', '当前最大 γ']
        table = ttk.Treeview(frame, columns=columns, show='headings')
        for column, heading in zip(columns, headings):
            table.heading(column, text=heading)
            table.column(column, anchor='center', width=118 if column != 'task' else 92,
                         stretch=column not in ('task', 'peak'))
        y_scroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=table.yview)
        x_scroll = ttk.Scrollbar(frame, orient=tk.HORIZONTAL, command=table.xview)
        table.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        table.grid(row=0, column=0, sticky='nsew')
        y_scroll.grid(row=0, column=1, sticky='ns')
        x_scroll.grid(row=1, column=0, sticky='ew')
        for row in ordered:
            values = ([row['task_id']] + [_number_text(row['values'][name]) for name in names] +
                      [_number_text(row['values']['KY']), '{:.8g}'.format(row['omega']),
                       '{:.8g}'.format(row['gamma']),
                       '{:.3%}'.format(row['omega_error']) if np.isfinite(row['omega_error']) else '—',
                       '{:.3%}'.format(row['gamma_error']) if np.isfinite(row['gamma_error']) else '—',
                       '✓' if row is peak else ''])
            table.insert('', 'end', values=values, tags=('peak',) if row is peak else ())
        table.tag_configure('peak', background='#fff2b2')
        ttk.Label(window, text='共 {} 行；相对波动为当前末段时间序列的标准差 / |平均值|。'.format(len(ordered)),
                  anchor='w').pack(fill=tk.X, padx=10, pady=(0, 10))


def plot_selected(root, notebook):
    data = result_grid(root)
    title = '{} | {}'.format(data['entry'].get('runid', ''), data['entry'].get('case_id', ''))
    suffix = ', '.join('{}={:.6g}'.format(name, value) for name, value in data['filters'].items())
    if suffix:
        title += ' | ' + suffix
    nb = notebook(0, 'CGYRO result browser')
    fig, axes = nb.subplots(1, 2, figsize=(12, 5.2), label=title)
    for axis, values, label, cmap in zip(axes, (data['omega'], data['gamma']),
                                         (r'$\omega$', r'$\gamma$'), ('coolwarm', 'viridis')):
        mesh = axis.pcolormesh(data['x'], data['y'], values, shading='auto', cmap=cmap)
        axis.set_xlabel(data['x_name'])
        axis.set_ylabel(r'$k_y\rho_s$' if data['y_name'] == 'KY' else data['y_name'])
        axis.set_title(label)
        fig.colorbar(mesh, ax=axis)
    valid = np.argwhere(np.isfinite(data['gamma']))
    if len(valid):
        best = valid[np.argmax([data['gamma'][tuple(index)] for index in valid])]
        axes[1].plot(data['x'][best[1]], data['y'][best[0]], marker='x', color='white', markersize=9, markeredgewidth=2)
    fig.suptitle(title)
    fig.tight_layout()
    return fig
