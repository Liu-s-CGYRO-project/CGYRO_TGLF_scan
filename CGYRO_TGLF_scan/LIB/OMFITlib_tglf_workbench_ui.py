"""A single, narrow TGLF workbench for local inputs and radial scans."""
from builtins import abs, any, bool, dict, enumerate, float, getattr, int, isinstance, iter, len, list, max, min, next, range, sorted, str, sum, zip
from collections import OrderedDict
import tkinter as tk
from tkinter import font as tkfont, ttk
from OMFITlib_project import MODULES, location, read, runtime_issues
from OMFITlib_tglf_preparation import preparation_resources
from OMFITlib_tglf_workbench import (COMMON, INTEGERS, MODES, PROFILE_PATH, initialize,
    numeric_parameters, parameter_value, plan, radial_input_issues, selected_rows)


class TGLFWorkbench:
    def __init__(self, view):
        self.view, self.actions, self.root, self.ui = view, view.actions, view.root, view.ui
        self.settings, self.rows = initialize(self.root, self.actions.factory)
        self.prefix = view.prefix + "['tglf']"
        self.available = [row for row in self.rows if row['group'] == self.settings['source']]
        try:
            self.selected = selected_rows(self.root, self.settings)
        except (TypeError, ValueError, KeyError):
            self.selected = []
        self.reference = (self.selected or self.available or [None])[0]
        self.source = read(self.root, self.reference['path'], {}) if self.reference else {}

    def label(self, text):
        return self.view.label(text)

    def render(self):
        self.ui.ComboBox(self.prefix + "['page']", OrderedDict([
            ('输入与扫描', 'scan'), ('计算参数', 'parameters'), ('结果与记录', 'results'),
            ('多个剖面对比', 'multi')]), 'TGLF', state='readonly', updateGUI=True)
        page = self.settings['page']
        if page == 'multi':
            self.view.compound(('GUIS', 'TGLF_multi'))
        elif page == 'parameters':
            self.parameters()
        elif page == 'results':
            self.results()
        else:
            self.scan()

    def scan(self):
        self.ui.Separator('01  输入')
        groups = OrderedDict()
        for caption, name in [('剖面文件（input.gacode）', 'radial'),
                              ('Transfer_tool 生成的半径输入', 'transfer'),
                              ('当前 / 导入 TGLF 文件', 'current'), ('局部互转文件', 'local')]:
            if name in ('radial', 'current') or any(row['group'] == name for row in self.rows) or self.settings['source'] == name:
                groups[caption] = name
        self.ui.ComboBox(self.prefix + "['source']", groups, '输入来源', state='readonly', updateGUI=True)
        if self.settings['source'] == 'radial':
            self.profile()
        elif self.settings['source'] == 'current':
            self.ui.FilePicker(self.view.prefix + "['tglf_file']", 'TGLF 文件', default='', transferRemoteFile=None,
                postcommand=lambda location=None: self.actions.import_input('tglf'), updateGUI=True,
                help='支持 input.tglf 和 out.tglf.localdump，按内容自动识别。更换后自动保存原输入和结果。')
            source = self.view.settings.get('tglf_import_source', {})
            if source.get('path', None):
                self.label('已载入：' + source['path'])
        elif self.available:
            with self.ui.same_row():
                self.ui.Button('全选', lambda: self.select(True), updateGUI=True)
                self.ui.Button('清空', lambda: self.select(False), updateGUI=True)
            for start in range(0, len(self.available), 2):
                with self.ui.same_row():
                    for row in self.available[start:start + 2]:
                        self.view.cgyro_checkbox(self.prefix + "['selected'][{!r}]".format(row['key']),
                            self.settings['selected'], row['key'], row['label'])
        if self.settings['source'] == 'radial' and not self.available:
            self.view.show_message(first_line=True)
            return
        if not self.available:
            self.label('请先载入输入文件。')
        else:
            anchor = self.label('已选 {} 个输入'.format(len(self.selected)))
            choices = OrderedDict((row['label'], row['key']) for row in self.available)
            if self.settings.get('preview', None) not in choices.values():
                self.settings['preview'] = self.available[0]['key']
            self.ui.ComboBox(self.prefix + "['preview']", choices, '查看源文件', state='readonly', updateGUI=True)
            row = next(row for row in self.available if row['key'] == self.settings['preview'])
            self.ui.Button('查看 / 编辑输入', lambda: self.view.show_transfer_input(anchor, row['path'], row['label']))
        self.ui.Separator('02  扫描设置')
        self.ui.ComboBox(self.prefix + "['mode']", MODES, '计算方式', state='readonly', updateGUI=True)
        mode = self.settings['mode']
        values = numeric_parameters(self.source)
        values.update((name, item['value']) for name, item in self.settings['parameters'].items()
                      if item.get('enabled', False))
        choices = sorted(name for name in values if name != 'NS')
        if mode in ('1d', '2d'):
            for index in range(1, 3 if mode == '2d' else 2):
                self.ui.ComboBox(self.prefix + "['parameter{}']".format(index), choices,
                                 '扫描参数 {}'.format(index), state='readonly', updateGUI=True)
                self.ui.Entry(self.prefix + "['values{}']".format(index), '取值列表', width=30,
                              updateGUI=True, help='填写实际数值，如 [0.5, 1, 1.5]；仅计算所列值。')
            self.label('填写实际取值列表；不会额外插入原始值。两个参数取所有组合。')
        elif mode == 'uq':
            self.ui.ComboBox(self.prefix + "['uq_count']", list(range(1, 6)), '参数数', state='readonly', updateGUI=True)
            continuous = [name for name in choices if not isinstance(values[name], bool) and name not in INTEGERS]
            for index in range(int(self.settings['uq_count'])):
                item = self.settings['uq'].setdefault(str(index), self.actions.factory())
                item.setdefault('name', continuous[min(index, len(continuous) - 1)] if continuous else '')
                name = item['name']
                if item.get('reference_name', name) != name:
                    item['mean'] = values.get(name, 0.0)
                    item['std'] = max(abs(float(values.get(name, 1.0))) * 0.1, 0.01)
                item['reference_name'] = name
                item.setdefault('mean', values.get(name, 0.0))
                item.setdefault('std', max(abs(float(values.get(name, 1.0))) * 0.1, 0.01))
                prefix = self.prefix + "['uq'][{!r}]".format(str(index))
                self.ui.ComboBox(prefix + "['name']", continuous, '参数 {}'.format(index + 1), state='readonly', updateGUI=True)
                with self.ui.same_row():
                    self.ui.Entry(prefix + "['mean']", '均值', width=10, updateGUI=True)
                    self.ui.Entry(prefix + "['std']", '标准差', width=10, updateGUI=True)
            self.ui.Entry(self.prefix + "['samples']", '样本数', width=12, updateGUI=True)
            self.ui.ComboBox(self.prefix + "['sampling']", {'Latin Hypercube': 'L', 'Hammersley': 'M'},
                             '采样方法', state='readonly', updateGUI=True)
            self.label('各参数按独立正态分布采样；均值和标准差是实际数值。')
        self.view.cgyro_checkbox(self.prefix + "['single_Ti']", self.settings, 'single_Ti', '温度扫描同步到输入中同温的热离子')
        self.ui.Separator('03  运行')
        self.ui.Entry(self.prefix + "['parallel']", '并发任务数', width=12, updateGUI=True)
        problems = runtime_issues(self.root, 'tglf')
        try:
            prepared = plan(self.root, self.settings)
            self.label('{} 个输入 × {} 个计算点 = {} 个任务'.format(
                len(prepared['sources']), prepared['points_per_input'], prepared['total']))
        except (TypeError, ValueError, KeyError) as exc:
            problems.append(str(exc))
        remote = read(self.root, MODULES['tglf'] + ('SETTINGS', 'REMOTE_SETUP'), {})
        self.label('队列：{} · 时限：{}'.format(remote.get('queue', None) or '本地', remote.get('w', None) or '—'))
        with self.ui.same_row():
            self.view.guarded('运行 TGLF', self.actions.run_tglf_plan, problems)
            self.view.nav('环境与队列', 'run')
        if problems:
            self.label('需要补充：' + '；'.join(problems[:2]))
        self.view.show_message(first_line=True)

    def profile(self):
        profile = read(self.root, PROFILE_PATH)
        source = self.settings.get('profile_source', {})
        if profile is not None and source.get('tree_path', None) and not self.settings['profile_file']:
            address = self.actions.root_name + location(source['tree_path'])[4:]
            self.settings['profile_file'] = address  # Fill the empty field saved by 1.17.1.
            source['path'] = address
        self.ui.FilePicker(self.prefix + "['profile_file']", '剖面文件', default='', transferRemoteFile=None,
            postcommand=lambda location=None: self.actions.import_tglf_profile(), updateGUI=True,
            help='直接载入完整剖面。生成范围为 0.01–0.99，间隔 0.01；之后可只计算其中部分半径。')
        if profile is not None and not self.settings['profile_file']:
            self.label('已载入工程中的 input.gacode')
        transfer = read(self.root, ('Transfer_tool', 'INPUTS', 'input.gacode'))
        if transfer is not None:
            self.ui.Button('使用 Transfer_tool 当前剖面', self.actions.use_transfer_tglf_profile, updateGUI=True)
        with self.ui.same_row():
            self.ui.ComboBox(self.prefix + "['profile_coordinate']", ['rho', 'r/a'], '径向坐标',
                             state='readonly', width=12, updateGUI=True)
            self.ui.ComboBox(self.prefix + "['include_ions']", {'热离子': 'thermal', '全部离子': 'all'},
                             '离子范围', state='readonly', width=12, updateGUI=True)
        issues = runtime_issues(self.root, 'tgyro')
        try:
            remote = read(self.root, MODULES['tgyro'] + ('SETTINGS', 'REMOTE_SETUP'), {})
            preparation_resources(remote)
        except ValueError as exc:
            issues.append(str(exc))
        if profile is None:
            issues.append('请载入 input.gacode')
        self.view.guarded('生成输入文件', self.actions.generate_tglf_inputs, issues)
        if self.available:
            stale = radial_input_issues(self.root, self.settings)
            if stale:
                self.label('；'.join(stale))
            self.ui.ComboBox(self.prefix + "['radius_mode']", {'全部半径': 'all', '按范围选择': 'range', '指定半径列表': 'list'},
                             '计算半径', state='readonly', updateGUI=True)
            if self.settings['radius_mode'] == 'range':
                with self.ui.same_row():
                    self.ui.Entry(self.prefix + "['radius_start']", '起始', width=8, updateGUI=True)
                    self.ui.Entry(self.prefix + "['radius_end']", '结束', width=8, updateGUI=True)
                    self.ui.Entry(self.prefix + "['radius_step']", '间隔', width=8, updateGUI=True)
            elif self.settings['radius_mode'] == 'list':
                self.ui.Entry(self.prefix + "['radius_values']", '半径列表', width=28, updateGUI=True,
                              help='例如 [0.3, 0.5, 0.7]。半径需在已生成的输入中。')

    def select(self, selected):
        self.settings['selected'].update({row['key']: selected for row in self.available})

    def parameters(self):
        self.label('修改后回车，应用到本次所选输入；扫描取值优先。恢复后沿用各文件原值。')
        self.label('此流程计算通量和谱，自动开启 USE_TRANSPORT_MODEL。')
        if self.reference:
            self.label('参考：' + self.reference['label'])
        values = numeric_parameters(self.source)
        catalog = OrderedDict(COMMON)
        catalog.update((name, (value, '输入参数')) for name, value in values.items() if name not in catalog)
        self.ui.ComboBox(self.prefix + "['parameter_group']", {'常用参数': 'common', '全部参数': 'all'},
                         '显示', state='readonly', updateGUI=True)
        self.ui.Entry(self.prefix + "['search']", '搜索', width=24, updateGUI=True)
        self.ui.Button('全部恢复文件原值', self.reset_parameters, updateGUI=True)
        for name, (reference, label) in catalog.items():
            if name in ('NS',) or (self.settings['parameter_group'] == 'common' and name not in COMMON):
                continue
            if str(self.settings['search']).strip().upper() not in (name + ' ' + label).upper():
                continue
            item = self.settings['parameters'].setdefault(name, self.actions.factory())
            item.setdefault('enabled', False)
            if not item['enabled']:
                item['value'] = values.get(name, reference)
            prefix = self.prefix + "['parameters'][{!r}]".format(name)
            hint = '仅修改后写入计算副本。' if name not in values else '输入值：' + str(values[name])
            with self.ui.same_row() as line:
                frame = getattr(line, 'frm_top', None)
                if isinstance(frame, tk.Misc):
                    frame._cgyro_inline = True
                self.label(name + ' · ' + label)
                callback = lambda location=None, name=name, reference=values.get(name, reference): self.edit_parameter(name, reference)
                if isinstance(reference, bool):
                    self.ui.ComboBox(prefix + "['value']", {'开启': True, '关闭': False}, '', width=12,
                                     updateGUI=True, state='readonly', postcommand=callback, help=hint)
                else:
                    self.ui.Entry(prefix + "['value']", '', width=12, updateGUI=True, postcommand=callback, help=hint)
                self.ui.Button('恢复', lambda name=name: self.settings['parameters'][name].__setitem__('enabled', False), updateGUI=True)

    def edit_parameter(self, name, reference):
        item = self.settings['parameters'][name]
        item['value'] = parameter_value(name, item['value'], reference)
        item['enabled'] = True

    def reset_parameters(self):
        for item in self.settings['parameters'].values():
            item['enabled'] = False

    def results(self):
        runs = read(self.root, ('TGLF_scan', 'RUN_DB'), {})
        if not runs:
            self.label('尚无新界面的运行记录。原有 TGLF 结果仍在工程数据树中。')
            self.view.nav('已有结果绘图', 'plots')
            return
        choices = OrderedDict((key + ' · ' + str(runs[key].get('mode', '')), key) for key in sorted(runs.keys(), reverse=True))
        if self.settings.get('result_run', None) not in choices.values():
            self.settings['result_run'] = next(iter(choices.values()))
        self.ui.ComboBox(self.prefix + "['result_run']", choices, '运行记录', state='readonly', updateGUI=True)
        record = runs[self.settings['result_run']]
        points = record.get('points', {})
        complete = sum(point.get('status', None) == 'complete' for point in points.values())
        anchor = self.label('已完成 {} / {}；输入、扫描值、结果及日志保存在 TGLF_scan / RUN_DB。'.format(complete, len(points)))
        self.ui.Button('查看结果表', lambda: self.result_table(anchor, record))
        if complete:
            self.view.task('查看通量趋势', ('TGLF_scan', 'PLOTS', 'workbench_result'), record=record)
            choices = OrderedDict((key + ' · ' + point['label'] + ' · ' + ', '.join(
                '{}={:g}'.format(name, value) for name, value in point['parameters'].items()), key)
                for key, point in points.items() if point.get('status', None) == 'complete')
            if self.settings.get('result_point', None) not in choices.values():
                self.settings['result_point'] = next(iter(choices.values()))
            self.ui.ComboBox(self.prefix + "['result_point']", choices, '计算点', state='readonly', updateGUI=True)
            self.view.task('查看该点的频率 / 增长率谱', ('TGLF_scan', 'PLOTS', 'workbench_result'),
                           record=record, point_id=self.settings['result_point'])
        self.view.nav('旧结果与 CGYRO 对比', 'plots')

    def result_table(self, anchor, record):
        window = tk.Toplevel(anchor.winfo_toplevel())
        window.title('TGLF 结果 · ' + record['id'])
        window.geometry('900x650')
        frame = ttk.Frame(window)
        frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        columns = ('point', 'input', 'parameters', 'status', 'qe', 'qi')
        style = ttk.Style(window)
        font = tkfont.Font(root=window, font=style.lookup('Treeview', 'font') or 'TkDefaultFont')
        style_name = 'TGLFResults' + str(window).replace('.', '_') + '.Treeview'
        style.configure(style_name, rowheight=font.metrics('linespace') + 8)
        table = ttk.Treeview(frame, columns=columns, show='headings', style=style_name)
        table._tglf_font = font
        for key, title, width in zip(columns, ('任务', '输入 / 半径', '扫描值', '状态', 'Qe / QGB', 'Qi / QGB'), (90, 160, 210, 80, 110, 110)):
            table.heading(key, text=title)
            table.column(key, width=width, anchor='w')
        for key, point in record.get('points', {}).items():
            fluxes = point.get('fluxes', [])
            qe = sum(row['heat'] for row in fluxes if row['species'] == 'elec')
            qi = sum(row['heat'] for row in fluxes if row['species'] != 'elec')
            status = {'complete': '完成', 'failed': '失败', 'prepared': '待运行', 'cancelled': '已中止'}.get(point.get('status', None), point.get('status', ''))
            table.insert('', 'end', iid=key, values=(key, point['label'],
                ', '.join('{}={:g}'.format(name, value) for name, value in point['parameters'].items()) or '原值',
                status, '{:.6g}'.format(qe) if fluxes else '—', '{:.6g}'.format(qi) if fluxes else '—'))
        y = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=table.yview)
        x = ttk.Scrollbar(frame, orient=tk.HORIZONTAL, command=table.xview)
        table.configure(yscrollcommand=y.set, xscrollcommand=x.set)
        table.grid(row=0, column=0, sticky='nsew')
        y.grid(row=0, column=1, sticky='ns')
        x.grid(row=1, column=0, sticky='ew')
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        details = tk.Text(window, height=7, wrap='word')
        details.pack(fill=tk.X, padx=8, pady=(0, 8))
        details.configure(state='disabled')
        def select(event=None):
            selected = table.selection()
            if not selected:
                return
            point = record['points'][selected[0]]
            lines = [point['label'], '输入：' + location(point['source'])]
            for row in point.get('fluxes', []):
                lines.append('{species}: Γ/ΓGB={particle:.6g}, Q/QGB={heat:.6g}, Π/ΠGB={momentum:.6g}'.format(**row))
            if point.get('error', None):
                lines.append(str(point['error']))
                log = point.get('diagnostics', {}).get('run_log', '')
                if log:
                    lines.append(str(log))
            details.configure(state='normal')
            details.delete('1.0', tk.END)
            details.insert('1.0', '\n'.join(lines))
            details.configure(state='disabled')
        table.bind('<<TreeviewSelect>>', select)
        ttk.Button(window, text='关闭', command=window.destroy).pack(pady=(0, 8))
