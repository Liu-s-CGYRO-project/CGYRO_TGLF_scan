"""RUN_DB-backed CGYRO result browser for one-, two- and three-axis scans."""
from OMFITlib_cgyro_archive import catalog_runs, case_destination, output_final_time
from OMFITlib_gui_fonts import configure_window_fonts, style_widget
from OMFITlib_cgyro_archive import case_scans, latest_cases
from OMFITlib_cgyro_continue import point_status, previous_final_time
from OMFITlib_cgyro_result_index import (result_records, find_record, select_result, selected_result, scan_scope)
from OMFITlib_cgyro_storage import resolve_result
from OMFITlib_cgyro_db import legacy_branch, run_records, storage_state
from OMFITlib_cgyro_present import record_options, record_details
from OMFITlib_compare_core import cgyro_frequency_history
from OMFITlib_plot_window import fit_figure_window
from builtins import (Exception, KeyError, TypeError, ValueError, abs, all, any, dict, float, int, iter, next,
                      len, list, max, min, range, set, sorted, str, tuple, zip)
from collections import OrderedDict
import math
import numpy as np
import tkinter as tk
from tkinter import ttk, messagebox


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


def _run_options(root, resolve_stopped=True, stopped_token=None):
    """List only RUN_DB metadata; old arguments remain for API compatibility."""
    records = result_records(root.get('CGYRO_scan', {}), include_tasks=False)
    return records, record_options(records)


def _number_text(value):
    try:
        return '{:.10g}'.format(float(value))
    except (TypeError, ValueError):
        return str(value)


def _unique_numeric(rows, name):
    values, seen = [], set()
    for row in rows:
        try:
            value = float(row.get('values', {}).get(name, None))
        except (TypeError, ValueError):
            continue
        if not math.isfinite(value) or value in seen:
            continue
        seen.add(value)
        # A scalar comparison avoids allocating numpy temporaries for every
        # repeated coordinate. Retain np.isclose's asymmetric tolerance/order.
        if not any(abs(value - item) <= 1e-12 + 1e-10 * abs(item) for item in values):
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


def selected_record(root, resolve_stopped=True, list_options=True):
    view = _view_settings(root)
    if not list_options and view.get('run_token', ''):
        entry = find_record(root['CGYRO_scan'], view['run_token'])
        return view, entry['selection_key'], entry, {}
    records, options = _run_options(root)
    if not options:
        raise ValueError('尚无已收集的 CGYRO 扫描结果。')
    token = view.get('run_token', '')
    if token not in records:
        try:
            token = find_record(root['CGYRO_scan'], token)['selection_key']
        except ValueError:
            if token:
                raise ValueError('所选结果版本已不存在或不唯一，请在“结果记录”中重新选择。')
            public = [key for key, item in records.items() if item.get('kind', '') == 'scan']
            token = (public or list(options.values()))[-1]
        view['run_token'] = token
    return view, token, find_record(root['CGYRO_scan'], token), options


def _result_node(root, entry, row):
    module = root['CGYRO_scan']
    if row.get('result_selection', None):
        return selected_result(module, row['result_selection'])
    point = next((point for point, candidate in entry['tasks'].items() if candidate is row), None)
    if point is None:
        matches = [point for point, candidate in entry['tasks'].items()
                   if candidate.get('result_path', None) == row.get('result_path', None)]
        if len(matches) != 1:
            raise ValueError('Ambiguous selected result coordinate')
        point = matches[0]
    return selected_result(module, select_result(module, entry, point))


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
    view, token, entry, _ = selected_record(root, list_options=False)
    axes = list(entry.get('scan_axes', []))
    dimensions = int(entry.get('dimensions', len(axes)))
    if dimensions not in (1, 2, 3) or len(axes) != dimensions:
        raise ValueError('运行记录中的参数轴信息无效。')
    tasks = entry.get('tasks', {})
    if not tasks:
        raise ValueError('所选运行没有已读取的计算点。')
    names = [str(axis['name']) for axis in axes]
    x_values = _unique_numeric(tasks.values(), names[0])
    if dimensions == 1:
        y_name = 'KY'
        y_values = _unique_numeric(tasks.values(), 'KY')
        filters = {}
    else:
        y_name = names[1]
        y_values = _unique_numeric(tasks.values(), y_name)
        ky_values = _unique_numeric(tasks.values(), 'KY')
        ky = _select_numeric(view.get('ky', ''), ky_values, 'ky')
        view['ky'] = _number_text(ky)
        filters = {'KY': ky}
        if dimensions == 3:
            z_values = _unique_numeric(tasks.values(), names[2])
            z_value = _select_numeric(view.get('slice_value', ''), z_values, names[2])
            view['slice_value'] = _number_text(z_value)
            filters[names[2]] = z_value
    omega = np.full((len(y_values), len(x_values)), np.nan)
    gamma = np.full((len(y_values), len(x_values)), np.nan)
    diagnostics, table_rows = [], []
    fraction = float(view.get('tail_fraction', .02))
    # The mapping key is the persisted point identity. Frozen point-table rows
    # and some migrated archives legitimately have no redundant task_id field.
    for point, row in tasks.items():
        values = row.get('values', {})
        try:
            numeric = {name: float(values[name]) for name in names + ['KY']}
        except (KeyError, TypeError, ValueError):
            diagnostics.append(str(point) + '：参数记录无效')
            continue
        if any(not np.isclose(numeric[name], value, rtol=1e-10, atol=1e-12)
               for name, value in filters.items()):
            continue
        x_value = numeric[names[0]]
        y_value = numeric[y_name]
        x_index = min(range(len(x_values)), key=lambda i: abs(x_values[i] - x_value))
        y_index = min(range(len(y_values)), key=lambda i: abs(y_values[i] - y_value))
        try:
            result = _result_node(root, entry, row)
            om, ga, om_error, ga_error = _frequency_summary(result, fraction)
            window = frequency_window(result, fraction)
            omega[y_index, x_index], gamma[y_index, x_index] = om, ga
            table_rows.append(dict(task_id=str(point),
                                   values=numeric, omega=om, gamma=ga,
                                   omega_error=om_error, gamma_error=ga_error, statistics_window=window))
        except (KeyError, TypeError, ValueError) as exc:
            diagnostics.append('{}：{}'.format(point, exc))
    if not np.any(np.isfinite(omega)) and not np.any(np.isfinite(gamma)):
        raise ValueError('当前切片没有可显示结果。' + ('\n' + '\n'.join(diagnostics[:5]) if diagnostics else ''))
    return dict(token=token, entry=entry, dimensions=dimensions, axes=axes,
                x_name=names[0], x=x_values, y_name=y_name, y=y_values,
                filters=filters, omega=omega, gamma=gamma, rows=table_rows,
                diagnostics=diagnostics, tail_fraction=fraction)


def frequency_window(result, fraction):
    """Describe the exact sample window used by this requested average."""
    count = int(result['n_time'])
    used = min(count, max(2, int(count * fraction)))
    times = result['t']
    return dict(tail_fraction=float(fraction), samples=used, total_samples=count,
                start_time=float(times[count - used]), end_time=float(times[-1]))


class ResultBrowser:
    def __init__(self, root, ui, continue_callback=None):
        self.root, self.ui = root, ui
        self.continue_callback = continue_callback
        self.prefix = "root['SETTINGS']['WORKBENCH']['cgyro_result_view']"

    def render(self, title=True):
        if title:
            self.ui.TitleGUI('CGYRO · 扫描结果浏览')
        try:
            view, token, entry, options = selected_record(self.root, resolve_stopped=False)
        except ValueError as exc:
            _, options = _run_options(self.root)
            if options:
                self.ui.ComboBox(self.prefix + "['run_token']", options, '结果记录', state='readonly', updateGUI=True)
            self.ui.Label(str(exc), align='left')
            return
        self.ui.ComboBox(self.prefix + "['run_token']", options, '结果记录', state='readonly',
                         updateGUI=True, help=record_details(entry, token))
        if entry.get('resume_error', ''):
            self.ui.Label('续算记录需要核对：' + entry['resume_error'], align='left')
            return
        if not entry.get('tasks', {}):
            self.anchor = self.ui.Label('本次没有可绘制的结果；原始输入已保留，可选择未开始的点继续计算。', align='left')
            if self.continue_callback is not None:
                self.ui.Button('选择未完成点继续计算…', self._show_points)
            return
        if entry.get('collection_status', '') == 'empty':
            self.ui.Label('本次没有新增时间样本；当前结果由 RUN_DB 索引提供。', align='left')
        if entry.get('continuation_pending', {}):
            self.ui.Label('{} 个续算点尚未超过旧末时刻；当前结果按收敛状态与模拟时间择一保留。'.format(
                len(entry['continuation_pending'])), align='left', wraplength=600)
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
            description = ('ky 数值结果' if int(entry.get('scan_dimensions', dimensions)) == 0
                           else '{} × ky 数值结果'.format(names[0]))
        else:
            description = '{} × {} 数值结果'.format(names[0], names[1])
            if dimensions == 3:
                description += '，{} 由上方切片选择'.format(names[2])
            description += '，ky 由上方切片选择'
        self.anchor = self.ui.Label('{}；{} 个已有结果计算点（点击绘图或数值表后读取）。'.format(description, len(tasks)), align='left')
        with self.ui.same_row():
            self.ui.Button('查看数值表', self._show_table)
            self.ui.Button('绘制当前结果', lambda: self.root['PLOTS']['CGYRO_results'].plot())
        self.ui.Button('时间曲线 / 选择点续算…', self._show_points,
                       help='打开计算点列表，查看 ω、γ 随时间变化。只有点击窗口内的续算按钮才提交计算。')
        self.ui.Label('数值表显示参数、ky、平均 ω/γ 与相对波动，并标出当前范围的最大 γ。',
                      align='left', wraplength=600)

    def _show_points(self):
        """Select full task coordinates, independently of the heatmap slice."""
        _, token, entry, _ = selected_record(self.root, list_options=False)
        tasks = entry.get('resume_tasks', entry.get('tasks', {}))
        if not tasks:
            raise ValueError('所选运行没有可选择的计算点。')
        names = [str(axis['name']) for axis in entry.get('scan_axes', []) if not axis.get('fixed', False)]
        names = list(dict.fromkeys(names + ['KY']))
        window = tk.Toplevel(self.anchor.winfo_toplevel())
        configure_window_fonts(window)
        window.title('CGYRO · 时间曲线与续算')
        width = min(1000, window.winfo_screenwidth() - 64)
        window.geometry('{}x{}'.format(width, min(720, window.winfo_screenheight() - 100)))
        ttk.Label(window, text='{} | {}'.format(entry.get('runid', ''), entry.get('case_id', '')),
                  anchor='w', wraplength=width - 40).pack(fill=tk.X, padx=10, pady=10)
        ttk.Label(window, text='选择计算点（Ctrl / Shift 多选）。收敛状态取自求解器日志；时间曲线使用原始采样数据。',
                  wraplength=width - 40).pack(fill=tk.X, padx=10, pady=(0, 8))
        scope = scan_scope(entry)
        missing = scope['unknown']
        bindings = {}
        if missing:
            ttk.Label(window, text='{} 个旧点的结果文件未保留；其他点可从各自保存的检查点续算。'.format(len(missing)),
                      wraplength=width - 40).pack(fill=tk.X, padx=10, pady=(0, 8))
        frame = ttk.Frame(window)
        frame.pack(fill=tk.BOTH, expand=True, padx=10)
        columns = ['task'] + names + ['state', 'last_time', 'samples', 'size', 'checkpoint']
        table = ttk.Treeview(frame, columns=columns, show='headings', selectmode='extended')
        style_widget(table)
        headings = ['计算点'] + names + ['求解器状态', '最后采样时间', '样本数', '结果大小 (MiB)', '重启时间 / 状态']
        for column, heading in zip(columns, headings):
            table.heading(column, text=heading)
            table.column(column, width=160 if column in ('state', 'checkpoint') else 112, anchor='center')
        vertical = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=table.yview)
        horizontal = ttk.Scrollbar(frame, orient=tk.HORIZONTAL, command=table.xview)
        table.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        table.grid(row=0, column=0, sticky='nsew')
        vertical.grid(row=0, column=1, sticky='ns')
        horizontal.grid(row=1, column=0, sticky='ew')
        statuses, defaults = {}, []
        states = {'converged': '已收敛', 'max_time': '到时未收敛', 'failed': '求解失败', 'unknown': '未确认'}
        for point, row in tasks.items():
            summary = row.get('result_summary', {})
            physical = entry.get('tasks', {}).get(point, None)
            status = dict(convergence=row.get('solver_status', 'unknown'), checkpoint=None, reason='', restartable=False)
            mode = ''
            last_time = _number_text(row['final_time']) if row.get('final_time', None) is not None else '—'
            if physical is not None:
                try:
                    bindings[point] = select_result(self.root['CGYRO_scan'], entry, point)
                    status['restartable'] = summary.get('checkpoint_available', True)
                    status['reason'] = summary.get('checkpoint_reason', '') or '续算时只校验所选点的输入、检查点与配套文件。'
                    if row.get('checkpoint_time', None) is not None:
                        status['checkpoint'] = dict(time=row['checkpoint_time'], last_time=row.get('final_time', 0))
                    mode = 'pending'
                except (KeyError, TypeError, ValueError) as exc:
                    status['reason'] = str(exc)
            elif entry.get('input_sha256', {}).get(point, None):
                try:
                    bindings[point] = select_result(self.root['CGYRO_scan'], entry, point)
                    status['restartable'] = True
                    mode = 'pending'
                    status['reason'] = '所选点的原输入 / 检查点 ZIP 将在续算前校验。'
                except (KeyError, TypeError, ValueError) as exc:
                    status['reason'] = str(exc)
            if point not in bindings:
                bindings[point] = dict(error=status['reason'] or '该点没有保存结果或原始输入。', row=dict(row))
            statuses[str(point)] = status
            warning = row.get('continuation_pending', '')
            scheduler_state = row.get('scheduler_state', '')
            state_label = '续算待推进' if warning else states[status['convergence']]
            if scheduler_state and scheduler_state != 'COMPLETED':
                state_label = scheduler_state
            status['reason'] = '\n'.join(text for text in (status['reason'], warning,
                scheduler_state if scheduler_state != 'COMPLETED' else '') if text)
            tag = status['checkpoint']
            table.insert('', 'end', iid=str(point), values=[point] + [
                _number_text(row.get('values', {}).get(name, '—')) for name in names] + [
                state_label, last_time, summary.get('sample_count', '—'),
                _number_text(summary['bytes'] / 1048576.) if summary.get('bytes', None) is not None else '—',
                '检查点不可用' if summary.get('checkpoint_available', None) is False else
                _number_text(tag['time']) + '（收集时已核验）' if tag and summary.get('checkpoint_available', False) else
                _number_text(tag['time']) + '（待校验）' if tag else
                '原输入 / 检查点待校验' if mode == 'pending' else '不可重启'])
            effective = row.get('effective_time', {})
            try:
                defaults.append(float(effective.get('MAX_TIME', 0)))
                if tag:
                    previous_final = previous_final_time(row, tag)
                    defaults.append(previous_final - tag['time'] +
                                    float(effective.get('DELTA_T', 0)) * float(effective.get('PRINT_STEP', 1)))
            except (TypeError, ValueError):
                pass
        # OMFIT wraps StringVar(name=None, **kw); master must stay a keyword.
        details = tk.StringVar(master=window, value='未选择计算点。')
        ttk.Label(window, textvariable=details, wraplength=width - 40,
                  anchor='w').pack(fill=tk.X, padx=10, pady=8)

        def selection_changed(event=None):
            selected = list(table.selection())
            problems = ['{}: {}'.format(point, statuses[point]['reason']) for point in selected
                        if statuses[point]['reason']]
            details.set('已选 {} 个点。{}'.format(len(selected), '\n'.join(problems[:3])))

        def selected_points():
            points = list(table.selection())
            if not points:
                raise ValueError('请先选择至少一个计算点。')
            return points

        def draw():
            try:
                points = [point for point in selected_points() if point in entry.get('tasks', {})]
                if not points:
                    raise ValueError('所选点尚无时间样本。')
                self.root['PLOTS']['CGYRO_results'].plot(
                    time_traces=True, run_token=token, point_ids=points,
                    stopped_points=entry.get('stopped_run', False),
                    selections={point: bindings[point] for point in points})
            except Exception as exc:
                messagebox.showerror('时间曲线', str(exc), parent=window)

        table.bind('<<TreeviewSelect>>', selection_changed)
        if entry.get('stopped_run', False):
            table.selection_set([str(point) for point in tasks if statuses[str(point)]['restartable']
                and point not in entry.get('loaded_points', [])])
            selection_changed()
        selections = ttk.Frame(window)
        selections.pack(fill=tk.X, padx=10, pady=(0, 8))
        ttk.Button(selections, text='选择到时未收敛点', command=lambda: table.selection_set([
            point for point, status in statuses.items() if status['convergence'] == 'max_time'])).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(selections, text='全选', command=lambda: table.selection_set(table.get_children())).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(selections, text='清空', command=lambda: table.selection_remove(table.selection())).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(selections, text='绘制 omega & gamma vs time', command=draw).pack(side=tk.LEFT)
        if self.continue_callback is not None:
            controls = ttk.Frame(window)
            controls.pack(fill=tk.X, padx=10, pady=(4, 8))
            ttk.Label(controls, text='追加计算时间 Δt (a/cs)').pack(side=tk.LEFT, padx=(0, 8))
            duration = tk.StringVar(master=window, value=_number_text(max([100.] + [
                value for value in defaults if np.isfinite(value) and value > 0])))
            ttk.Entry(controls, textvariable=duration, width=14).pack(side=tk.LEFT, padx=(0, 10))

            def resume():
                try:
                    points = selected_points()
                    button.configure(state='disabled')
                    window.update_idletasks()
                    self.continue_callback(token, points, float(duration.get()),
                        selections={point: bindings[point] for point in points},
                        scope=scope)
                except Exception as exc:
                    if window.winfo_exists():
                        messagebox.showerror('CGYRO 续算', str(exc), parent=window)
                else:
                    if window.winfo_exists():
                        window.destroy()  # Reload the browser after the result token changes.
                finally:
                    if window.winfo_exists():
                        button.configure(state='normal')

            button = ttk.Button(controls, text='继续计算所选点' if entry.get('stopped_run', False) else '从检查点续算所选点', command=resume)
            button.pack(side=tk.LEFT)
            ttk.Label(window, text='时长从重启时间起算，需超过旧结果末尾；调度器墙钟时限仍使用环境配置。'
                      '确认未开始的点使用校验过的原输入，MAX_TIME 加 Δt；已有样本但缺少检查点会停止并说明原因。'
                      '已完成点默认不选，其他结果保留。',
                      wraplength=width - 40, anchor='w').pack(fill=tk.X, padx=10, pady=(0, 12))

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
        configure_window_fonts(window)
        window.title('CGYRO 数值结果')
        width = min(800, window.winfo_screenwidth() - 64)
        height = min(880, window.winfo_screenheight() - 100)
        window.geometry('{}x{}'.format(width, height))
        title = '{} | {}'.format(data['entry'].get('runid', ''), data['entry'].get('case_id', ''))
        if data['filters']:
            title += ' | ' + ', '.join('{}={:.7g}'.format(key, value)
                                      for key, value in data['filters'].items())
        ttk.Label(window, text=title, anchor='w', wraplength=width - 48).pack(fill=tk.X, padx=10, pady=(10, 6))
        frame = ttk.Frame(window)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        columns = ['task'] + names + ['KY', 'omega', 'gamma', 'omega_error', 'gamma_error', 'window', 'samples', 'peak']
        headings = ['计算点'] + names + ['ky', '平均 ω', '平均 γ', 'ω 相对波动', 'γ 相对波动', '统计时间窗口', '窗口样本数', '当前最大 γ']
        table = ttk.Treeview(frame, columns=columns, show='headings')
        style_widget(table)
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
                       '{:.7g}–{:.7g}'.format(row['statistics_window']['start_time'], row['statistics_window']['end_time']),
                       row['statistics_window']['samples'],
                       '✓' if row is peak else ''])
            table.insert('', 'end', values=values, tags=('peak',) if row is peak else ())
        table.tag_configure('peak', background='#fff2b2')
        ttk.Label(window, text='共 {} 行；末段比例 {:.3%}，窗口与样本数逐点列出。相对波动为窗口内标准差 / |平均值|。'.format(len(ordered), data['tail_fraction']),
                  anchor='w', wraplength=width - 48).pack(fill=tk.X, padx=10, pady=(0, 10))


def plot_time_traces(root, notebook, token, point_ids, legend_font_size=10, stopped_points=False, selections=None):
    """Plot native cumulative time samples; never average or re-zero a restart."""
    if selections is None:
        entry = find_record(root['CGYRO_scan'], token)
        selections = {point: select_result(root['CGYRO_scan'], entry, point) for point in point_ids}
    else:
        entry = next(iter(selections.values()))['info'] if selections else {}
    tasks = {point: binding['row'] for point, binding in selections.items()}
    if not point_ids or any(point not in tasks for point in point_ids):
        raise ValueError('请选择有效的计算点。')
    names = [str(axis['name']) for axis in entry.get('scan_axes', []) if not axis.get('fixed', False)]
    series = []
    for point in point_ids:
        row = tasks[point]
        result = selected_result(root['CGYRO_scan'], selections[point])
        times, omega, gamma = cgyro_frequency_history(result)
        values = row.get('values', {})
        label = ', '.join('{}={}'.format('ky' if name == 'KY' else name, _number_text(values[name]))
                          for name in list(dict.fromkeys(names + ['KY'])))
        series.append((times, omega, gamma, label))
    # User case/run names can contain Chinese. Keep figure text derived from
    # solver coordinates, with no opaque task ID or long archive name in legends.
    title = 'CGYRO frequency history'
    if entry.get('rho', None) is not None:
        title += ' | rho=' + _number_text(entry['rho'])
    ion = str(entry.get('ion_case', ''))
    if ion.isascii() and ion:
        title += ' | ' + ion
    nb = notebook(0, 'CGYRO omega and gamma vs time')
    legend_columns = min(1 if len(names) > 1 else 2, len(series))
    legend_rows = (len(series) + legend_columns - 1) // legend_columns
    legend_height = .35 + .03 * legend_font_size * legend_rows
    figure_height = 5.2 + legend_height
    fig, axes = nb.subplots(1, 2, figsize=(12, figure_height), label=title)
    for times, omega, gamma, label in series:
        marker = 'o' if len(times) == 1 else None
        line, = axes[0].plot(times, np.where(np.isfinite(omega), omega, np.nan), label=label, marker=marker)
        axes[1].plot(times, np.where(np.isfinite(gamma), gamma, np.nan), label=label,
                     color=line.get_color(), marker=marker)
    for axis, symbol in zip(axes, (r'$\omega$', r'$\gamma$')):
        axis.set_xlabel(r'Time ($a/c_s$)')
        axis.set_ylabel(symbol + r' ($c_s/a$)')
        axis.set_title(symbol + ' vs time')
        axis.grid(True, alpha=.25)
    handles, labels = axes[0].get_legend_handles_labels()
    # Keep a long multi-point legend inside the saved figure, with adequate rows.
    bottom = legend_height / figure_height
    fig.legend(handles, labels, loc='upper center', bbox_to_anchor=(.5, bottom),
               ncol=legend_columns, fontsize=legend_font_size)
    fig.suptitle(title)
    fig.tight_layout(rect=(0, bottom, 1, .94))
    fit_figure_window(fig)
    return fig


def plot_selected(root, notebook):
    data = result_grid(root)
    # A single coordinate has no cell width for a center-based color mesh.
    # Plot the remaining coordinate directly, with markers for single points.
    populated = np.isfinite(data['omega']) | np.isfinite(data['gamma'])
    x_indices = np.flatnonzero(np.any(populated, axis=0))
    y_indices = np.flatnonzero(np.any(populated, axis=1))
    line_plot = len(x_indices) == 1 or len(y_indices) == 1
    fixed_values = dict(data['filters'])
    plot_values = (data['omega'], data['gamma'])
    if line_plot:
        if len(x_indices) == 1:
            fixed_index = x_indices[0]
            coordinate_name, coordinates = data['y_name'], data['y']
            fixed_name, fixed_value = data['x_name'], data['x'][fixed_index]
            plot_values = tuple(values[:, fixed_index] for values in plot_values)
        else:
            fixed_index = y_indices[0]
            coordinate_name, coordinates = data['x_name'], data['x']
            fixed_name, fixed_value = data['y_name'], data['y'][fixed_index]
            plot_values = tuple(values[fixed_index, :] for values in plot_values)
        # A ky-only run stores a compatibility coordinate, not a scan axis.
        if int(data['entry'].get('scan_dimensions', data['dimensions'])) != 0 or fixed_name == 'KY':
            fixed_values[fixed_name] = fixed_value
    title = '{} | {}'.format(data['entry'].get('runid', ''), data['entry'].get('case_id', ''))
    suffix = ', '.join('{}={:.6g}'.format(name, value) for name, value in fixed_values.items())
    if suffix:
        title += ' | ' + suffix
    title += ' | tail {:.3%} (per-point time windows in the numeric table)'.format(data['tail_fraction'])
    nb = notebook(0, 'CGYRO result browser')
    fig, axes = nb.subplots(1, 2, figsize=(12, 5.2), label=title)
    for axis, values, label, cmap in zip(axes, plot_values,
                                         (r'$\omega$', r'$\gamma$'), ('coolwarm', 'viridis')):
        if line_plot:
            axis.plot(coordinates, values, marker='o', markersize=4, linewidth=1.5)
            axis.set_xlabel(r'$k_y\rho_s$' if coordinate_name == 'KY' else coordinate_name)
            axis.set_ylabel(label)
            axis.grid(True, alpha=.25)
        else:
            mesh = axis.pcolormesh(data['x'], data['y'], values, shading='auto', cmap=cmap)
            axis.set_xlabel(data['x_name'])
            axis.set_ylabel(r'$k_y\rho_s$' if data['y_name'] == 'KY' else data['y_name'])
            fig.colorbar(mesh, ax=axis)
        axis.set_title(label)
    if line_plot:
        valid = np.flatnonzero(np.isfinite(plot_values[1]))
        if len(valid):
            best = valid[np.argmax(plot_values[1][valid])]
            axes[1].plot(coordinates[best], plot_values[1][best], marker='x', color='tab:red',
                         markersize=9, markeredgewidth=2, linestyle='none')
    else:
        valid = np.argwhere(np.isfinite(data['gamma']))
        if len(valid):
            best = valid[np.argmax([data['gamma'][tuple(index)] for index in valid])]
            axes[1].plot(data['x'][best[1]], data['y'][best[0]], marker='x', color='white', markersize=9, markeredgewidth=2)
    fig.suptitle(title)
    fig.tight_layout(rect=(0, 0, 1, .94))
    fit_figure_window(fig)
    return fig
