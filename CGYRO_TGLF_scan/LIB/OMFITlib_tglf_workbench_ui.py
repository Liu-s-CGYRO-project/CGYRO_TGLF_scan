"""A single, narrow TGLF workbench for local inputs and radial scans."""
from OMFITlib_gui_fonts import configure_window_fonts, gui_font, style_widget
from OMFITlib_gui_api import plot_view
from builtins import abs, any, bool, dict, enumerate, float, getattr, int, isinstance, iter, len, list, max, min, next, range, set, sorted, str, sum, zip
from collections import OrderedDict
from datetime import datetime, timezone
import math
import tkinter as tk
from tkinter import font as tkfont, messagebox, simpledialog, ttk
from OMFITlib_gui_layout import section_group
from OMFITlib_gui_deferred import TabPages
from OMFITlib_gui_controls import ParameterList, checkbox
from OMFITlib_project import MODULES, location, read, runtime_issues
from OMFITlib_tglf_preparation import preparation_resources
from OMFITlib_tglf_workbench import (COMMON, INTEGERS, MODES, PROFILE_PATH, SCENARIOS, USER_SCENARIO_PREFIX,
    apply_scenario, fully_failed, generation_overrides, generation_seed, initialize, parameter_value,
    plan, radial_input_issues, save_preset, scan_parameter_names, scenario_choices, selected_rows, uq_parameter_count)
from OMFITlib_tglf_parameters import GROUPS, parameter_catalog, parameter_values, scalar
from OMFITlib_tglf_parameter_help import parameter_help

TABS = OrderedDict([('scan', '输入与扫描'), ('parameters', '计算参数'),
                    ('results', '结果与记录'), ('multi', '多个剖面对比')])
from OMFITlib_workbench_catalog import SCAN_TABS  # Shared with CGYRO; retained public alias.


from OMFITlib_tglf_records import point_current, record_summary, run_records


class TGLFWorkbench:
    def __init__(self, view):
        self.view, self.actions, self.root, self.ui = view, view.actions, view.root, view.ui
        self.prefix = view.prefix + "['tglf']"
        self.load_selection()

    def load_selection(self):
        """Refresh input references when a changed tab is next rendered."""
        self.settings, self.rows = initialize(self.root, self.actions.factory)
        self.available = [row for row in self.rows if row['group'] == self.settings['source']]
        try:
            self.selected = selected_rows(self.root, self.settings)
        except (TypeError, ValueError, KeyError):
            self.selected = []
        self.reference = (self.selected or self.available or [None])[0]
        seed = generation_seed(self.root) if self.settings['source'] == 'radial' else None
        self.source = read(self.root, self.reference['path'], {}) if self.reference else (seed if seed is not None else {})

    def label(self, text):
        return self.view.label(text)

    def render(self):
        def render(page):
            self.load_selection()
            if page == 'multi':
                self.view.compound(('GUIS', 'TGLF_multi'))
            elif page == 'parameters':
                self.parameters()
            elif page == 'results':
                self.results()
            else:
                self.scan()
        self.pages = TabPages(self.ui, TABS, self.settings, 'page', render)
        self.notebook = self.pages.notebook

    def select_page(self, page):
        self.pages.select(page)

    def page_changed(self, event):
        self.pages.changed(event)

    def scan(self):
        # CompoundGUI gives the sub-tabs their own native Notebook context.
        self.view.compound(('GUIS', 'TGLF_controls'), workbench=self)
        self.view.show_message(first_line=True)

    def render_scan_tabs(self):
        def render(page):
            self.load_selection()
            if page == 'input':
                self.input()
            elif page == 'settings':
                self.scan_settings()
            else:
                self.run()
        self.scan_pages = TabPages(self.ui, SCAN_TABS, self.settings, 'scan_page', render)
        self.scan_notebook = self.scan_pages.notebook

    def select_scan_page(self, page):
        self.scan_pages.select(page)

    def scan_page_changed(self, event):
        self.scan_pages.changed(event)

    def input(self):
        groups = OrderedDict()
        for caption, name in [('剖面文件（input.gacode）', 'radial'),
                              ('Transfer_tool 生成的半径输入', 'transfer'),
                              ('当前 / 导入 TGLF 文件', 'current'), ('局部互转文件', 'local')]:
            if name in ('radial', 'current') or any(row['group'] == name for row in self.rows) or self.settings['source'] == name:
                groups[caption] = name
        self.ui.ComboBox(self.prefix + "['source']", groups, '输入来源', state='readonly', updateGUI=True, refresh_tree=False)
        if self.settings['source'] == 'radial':
            self.profile()
        elif self.settings['source'] == 'current':
            self.ui.FilePicker(self.view.prefix + "['tglf_file']", 'TGLF 文件', default='', transferRemoteFile=None,
                postcommand=lambda location=None: self.actions.import_input('tglf'), updateGUI=True,
                help='支持 input.tglf 和 out.tglf.localdump，按内容自动识别。更换后自动保存原输入和结果。')
            source = self.view.settings.get('tglf_import_source', {})
            if source.get('path', None):
                self.label('已载入：' + source['path'])

    def scan_settings(self):
        if not self.available:
            self.label('请先准备输入文件。')
            self.ui.Button('准备输入', lambda: self.select_scan_page('input'))
            return
        self.radius_selection()
        if self.available:
            anchor = self.label('已选 {} 个输入'.format(len(self.selected)))
            preview_rows = self.selected or self.available
            choices = OrderedDict((row['label'], row['key']) for row in preview_rows)
            if self.settings.get('preview', None) not in choices.values():
                self.settings['preview'] = preview_rows[0]['key']
            self.ui.ComboBox(self.prefix + "['preview']", choices, '查看输入', state='readonly', updateGUI=False, refresh_tree=False)
            def show_input():
                row = next(row for row in preview_rows if row['key'] == self.settings['preview'])
                self.view.show_transfer_input(anchor, row['path'], row['label'])
            self.ui.Button('查看 / 编辑输入', show_input, refresh_tree=False)
        self.ui.ComboBox(self.prefix + "['mode']", MODES, '计算方式', state='readonly', updateGUI=True, refresh_tree=False)
        mode = self.settings['mode']
        values = parameter_values(self.source)
        scanned = scan_parameter_names(self.settings)
        values.update((name, item['value']) for name, item in self.settings['parameters'].items()
                      if item.get('enabled', False) and name in values and name not in scanned)
        choices = sorted(values)
        if mode in ('1d', '2d', '3d'):
            for index in range(1, int(mode[0]) + 1):
                self.ui.ComboBox(self.prefix + "['parameter{}']".format(index), choices,
                                 '扫描参数 {}'.format(index), state='readonly', updateGUI=True,
                                 help=parameter_help(self.settings['parameter' + str(index)], self.source), refresh_tree=False)
                self.ui.ComboBox(self.prefix + "['value_mode{}']".format(index),
                    {'原值倍数': 'factor', '实际值范围': 'range', '指定数值列表': 'list'},
                    '取值方式', state='readonly', updateGUI=True,
                    help='原值倍数与 OMFIT 原生扫描一致；多半径时分别乘以每个输入的原值。', refresh_tree=False)
                if self.settings['value_mode' + str(index)] == 'list':
                    self.ui.Entry(self.prefix + "['values{}']".format(index), '取值列表', width=30,
                                  updateGUI=False, help='例如 [0.5, 1, 1.5]；仅计算所列值。', refresh_tree=False)
                else:
                    with self.ui.same_row():
                        self.ui.Entry(self.prefix + "['scan_start{}']".format(index), '起点', width=8, updateGUI=False, refresh_tree=False)
                        self.ui.Entry(self.prefix + "['scan_end{}']".format(index), '终点', width=8, updateGUI=False, refresh_tree=False)
                        self.ui.Entry(self.prefix + "['scan_count{}']".format(index), '点数', width=8, updateGUI=False, refresh_tree=False)
        elif mode == 'uq':
            self.ui.Entry(self.prefix + "['uq_count']", '参数数量', width=8, updateGUI=True,
                          help='整数 1–5；回车后更新下方参数行。', refresh_tree=False)
            try:
                count = uq_parameter_count(self.settings)
            except ValueError as exc:
                self.label(str(exc))
                return
            continuous = [name for name in choices if not isinstance(values[name], bool) and name not in INTEGERS]
            for index in range(count):
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
                self.ui.ComboBox(prefix + "['name']", continuous, '参数 {}'.format(index + 1), state='readonly', updateGUI=True,
                                 help=parameter_help(name, self.source), refresh_tree=False)
                with self.ui.same_row():
                    self.ui.Entry(prefix + "['mean']", '均值', width=10, updateGUI=False, refresh_tree=False)
                    self.ui.Entry(prefix + "['std']", '标准差', width=10, updateGUI=False, refresh_tree=False)
            self.ui.Entry(self.prefix + "['samples']", '样本数', width=12, updateGUI=False, refresh_tree=False)
            self.ui.ComboBox(self.prefix + "['sampling']", {'Latin Hypercube': 'L', 'Hammersley': 'M'},
                             '采样方法', state='readonly', updateGUI=False, refresh_tree=False)
            self.label('各参数按独立正态分布采样；均值和标准差是实际数值。')
        if mode != 'single':
            self.view.cgyro_checkbox(self.prefix + "['single_Ti']", self.settings, 'single_Ti', '温度扫描同步到输入中同温的热离子')

    def run(self):
        self.ui.Entry(self.prefix + "['parallel']", '并发任务数', width=12, updateGUI=False, refresh_tree=False)
        problems = runtime_issues(self.root, 'tglf')
        try:
            prepared = plan(self.root, self.settings)
            self.label('本次运行：{} 个输入，{} 个任务'.format(len(prepared['sources']), prepared['total']))
        except (TypeError, ValueError, KeyError) as exc:
            problems.append(str(exc))
        remote = read(self.root, MODULES['tglf'] + ('SETTINGS', 'REMOTE_SETUP'), {})
        self.label('队列：{} · 时限：{}'.format(remote.get('queue', None) or '本地', remote.get('w', None) or '—'))
        with self.ui.same_row():
            self.view.guarded('运行 TGLF', self.actions.run_tglf_plan, problems)
            self.view.nav('环境与队列', 'run')
        if problems:
            self.label('需要补充：' + '；'.join(problems[:2]))

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
                             state='readonly', width=12, updateGUI=True, refresh_tree=False)
            self.ui.ComboBox(self.prefix + "['include_ions']", {'热离子': 'thermal', '全部离子': 'all'},
                             '离子范围', state='readonly', width=12, updateGUI=True, refresh_tree=False)
        self.generation_parameters()
        issues = runtime_issues(self.root, 'tgyro')
        try:
            remote = read(self.root, MODULES['tgyro'] + ('SETTINGS', 'REMOTE_SETUP'), {})
            preparation_resources(remote)
            generation_overrides(self.root, self.settings)
        except ValueError as exc:
            issues.append(str(exc))
        if profile is None:
            issues.append('请载入 input.gacode')
        self.view.guarded('生成输入文件', self.actions.generate_tglf_inputs, issues)
        if self.available:
            stale = radial_input_issues(self.root, self.settings)
            if stale:
                self.label('；'.join(stale))

    def radius_selection(self):
        if self.settings['source'] == 'radial' and self.available:
            self.ui.ComboBox(self.prefix + "['radius_mode']", OrderedDict([
                ('单个半径', 'single'), ('半径范围', 'range'), ('半径列表', 'list'), ('全部半径', 'all')]),
                '计算半径', state='readonly', updateGUI=True, refresh_tree=False)
            if self.settings['radius_mode'] == 'single':
                choices = OrderedDict((row['label'], row['rho']) for row in self.available)
                self.ui.ComboBox(self.prefix + "['radius']", choices, '半径', state='readonly', updateGUI=True, refresh_tree=False)
            if self.settings['radius_mode'] == 'range':
                with self.ui.same_row():
                    self.ui.Entry(self.prefix + "['radius_start']", '起始', width=8, updateGUI=True, refresh_tree=False)
                    self.ui.Entry(self.prefix + "['radius_end']", '结束', width=8, updateGUI=True, refresh_tree=False)
                    self.ui.Entry(self.prefix + "['radius_step']", '间隔', width=8, updateGUI=True, refresh_tree=False)
            elif self.settings['radius_mode'] == 'list':
                self.ui.Entry(self.prefix + "['radius_values']", '半径列表', width=28, updateGUI=True,
                              help='例如 [0.3, 0.5, 0.7]。半径需在已生成的输入中。', refresh_tree=False)
        elif self.settings['source'] == 'transfer' and self.available:
            with self.ui.same_row():
                self.ui.Button('全选', lambda: self.select(True), updateGUI=True, refresh_scope='section')
                self.ui.Button('清空', lambda: self.select(False), updateGUI=True, refresh_scope='section')
            for start in range(0, len(self.available), 2):
                with self.ui.same_row():
                    for row in self.available[start:start + 2]:
                        self.view.cgyro_checkbox(self.prefix + "['selected'][{!r}]".format(row['key']),
                            self.settings['selected'], row['key'], row['label'])

    def generation_parameters(self):
        seed = generation_seed(self.root)
        if seed is None:
            return
        with section_group(self.ui, 'TGLF 参数'):
            self.preset_controls(seed)
            for fields in ((('SAT_RULE', '饱和规则'), ('NKY', 'ky 点数')),
                           (('KYGRID_MODEL', 'ky 网格'), ('NMODES', '模态数')),
                           (('USE_BPER', 'A∥ 扰动'), ('USE_BPAR', 'B∥ 扰动'))):
                with self.ui.same_row():
                    for name, label in fields:
                        self.parameter_field(name, seed, label)
            with self.ui.same_row():
                self.units_field(seed)
                self.ui.Button('更多 TGLF 参数', lambda: self.select_page('parameters'))

    def units_field(self, source):
        combo = getattr(self, 'preset_combo', None)
        self.ui.ComboBox(self.prefix + "['units_override']", {'沿用输入': '', 'GYRO': 'GYRO', 'CGYRO': 'CGYRO'},
                         '归一化', width=12, state='readonly', updateGUI=False, refresh_tree=False,
                         help=parameter_help('UNITS', source),
                         postcommand=lambda location=None: self.mark_custom(combo))

    def parameter_field(self, name, source, label):
        if name in scan_parameter_names(self.settings):
            return self.label(name + ' · 由扫描设置控制')
        reference = scalar(source.get(name, COMMON[name][0]))
        item = self.settings['parameters'].setdefault(name, self.actions.factory())
        item.setdefault('enabled', False)
        if not item['enabled']:
            item['value'] = reference
        prefix = self.prefix + "['parameters'][{!r}]['value']".format(name)
        combo = getattr(self, 'preset_combo', None)
        callback = lambda location=None: self.edit_parameter(name, reference, combo)
        help_text = parameter_help(name, source)
        return self.parameter_editor(prefix, label, reference, callback, help_text, width=8)

    def parameter_editor(self, prefix, label, reference, callback, help_text, width=12):
        # Numeric solver codes are numeric inputs too. Keep their meaning in
        # help, not in a second dropdown-only list of supported values.
        options = dict(width=width, updateGUI=False, refresh_tree=False, postcommand=callback, help=help_text)
        if isinstance(reference, bool):
            return self.ui.ComboBox(prefix, {'开启': True, '关闭': False}, label, state='readonly', **options)
        return self.ui.Entry(prefix, label, **options)

    def preset_controls(self, source):
        self.preset_combo = self.ui.ComboBox(self.prefix + "['scenario']", scenario_choices(self.settings),
            '参数预设', state='readonly', updateGUI=True, refresh_tree=False,
            postcommand=lambda location=None: apply_scenario(self.settings, source, self.actions.factory),
            help='内置方案复用 OMFIT 的 SAT0、SAT1、SAT2、JET、ST、ITER 设置。\n'
                 '选择后可继续修改。扫描参数始终由扫描设置控制。\n'
                 '另存预设仅保存已修改的固定值和归一化设置，随工程保存；沿用输入的值仍随各输入变化。')
        parent = self.preset_combo.winfo_toplevel() if isinstance(self.preset_combo, tk.Misc) else None
        with self.ui.same_row():
            self.ui.Button('另存为我的预设', lambda: self.save_current_preset(source, parent),
                           updateGUI=True, refresh_scope='section')
            if self.settings['scenario'].startswith(USER_SCENARIO_PREFIX):
                name = self.settings['scenario'][len(USER_SCENARIO_PREFIX):]
                self.ui.Button('删除预设“{}”'.format(name), lambda: self.delete_preset(name, parent),
                               updateGUI=True, refresh_scope='section')

    def save_current_preset(self, source, parent):
        name = simpledialog.askstring('保存 TGLF 参数预设', '预设名称：', parent=parent)
        if name is None or not name.strip():
            return
        name = name.strip()
        if name in self.settings['presets'] and not messagebox.askyesno(
                '替换 TGLF 参数预设', '替换已有预设“{}”？'.format(name), parent=parent):
            return
        save_preset(self.settings, source, name, self.actions.factory)

    def delete_preset(self, name, parent):
        if messagebox.askyesno('删除 TGLF 参数预设', '删除“{}”？当前参数保持不变。'.format(name), parent=parent):
            del self.settings['presets'][name]
            self.mark_custom()

    def mark_custom(self, combo=None):
        self.settings['scenario'] = 'custom'
        if isinstance(combo, tk.Misc):
            combo.set(SCENARIOS['custom'][0])

    def select(self, selected):
        self.settings['selected'].update({row['key']: selected for row in self.available})

    def parameters(self):
        self.label('数值修改后回车；扫描中的参数在“输入与扫描”设置。')
        if self.reference:
            self.label('参考：' + self.reference['label'])
        self.preset_controls(self.source)
        catalog = parameter_catalog(self.source)
        self.units_field(self.source)
        self.label('NS = {} · 粒子种类数沿用参考输入；USE_TRANSPORT_MODEL = True · 当前工作台计算输运谱。'.format(
            scalar(self.source.get('NS', 2))))
        self.ui.Button('全部沿用输入值', self.reset_parameters, updateGUI=True,
                       refresh_scope='section', refresh_tree=False)
        scanned = scan_parameter_names(self.settings)
        # Typing a filter uses this captured catalog, not input/result files.
        rows = [(name, spec[1], spec[2], name in COMMON) for name, spec in catalog.items()]
        self.parameter_list = ParameterList(self.ui, self.settings, 'parameter_group', 'search', GROUPS, rows,
            lambda names, combo=self.preset_combo: self.parameter_rows(names, catalog, scanned, combo))

    def parameter_rows(self, names, catalog, scanned, combo):
        for name in names:
            reference, label, category = catalog[name]
            if name in scanned:
                self.label(name + ' · ' + label + ' · 由扫描设置控制')
                continue
            item = self.settings['parameters'].setdefault(name, self.actions.factory())
            item.setdefault('enabled', False)
            if not item['enabled']:
                item['value'] = reference
            prefix = self.prefix + "['parameters'][{!r}]".format(name)
            hint = parameter_help(name, self.source)
            with self.ui.same_row() as line:
                frame = getattr(line, 'frm_top', None)
                if isinstance(frame, tk.Misc):
                    frame._cgyro_inline = True
                self.label(name + ' · ' + label)
                # Capture this mounted tab's control: another cached input tab
                # may build its own preset menu before this callback runs.
                callback = lambda location=None, name=name, reference=reference: self.edit_parameter(name, reference, combo)
                self.parameter_editor(prefix + "['value']", '', reference, callback, hint)
                self.ui.Button('沿用输入', lambda name=name: self.reset_parameter(name, combo), updateGUI=True,
                               refresh_scope='section', refresh_tree=False)

    def edit_parameter(self, name, reference, combo=None):
        item = self.settings['parameters'][name]
        item['value'] = parameter_value(name, item['value'], reference)
        item['enabled'] = True
        self.mark_custom(combo)

    def reset_parameters(self):
        for item in self.settings['parameters'].values():
            item['enabled'] = False
        self.settings['units_override'] = ''
        self.settings['scenario'] = 'input'

    def reset_parameter(self, name, combo=None):
        self.settings['parameters'][name]['enabled'] = False
        self.mark_custom(combo)

    def results(self):
        module = self.root.get('TGLF_scan', {})
        runs = run_records(module)
        if not runs:
            self.label('尚无新界面的运行记录。原有 TGLF 结果仍在工程数据树中。')
            self.view.nav('已有结果绘图', 'plots')
            return
        failed = [key for key, record in runs.items() if fully_failed(record)]
        if failed:
            with self.ui.same_row():
                checkbox(self.ui, self.prefix + "['show_failed_runs']", self.settings,
                         'show_failed_runs', '显示失败记录（{}）'.format(len(failed)), updateGUI=True)
                self.ui.Button('清理失败记录', self.actions.clear_failed_tglf_records, updateGUI=True)
        choices = OrderedDict()
        for key in sorted(runs.keys(), reverse=True):
            if not self.settings['show_failed_runs'] and key in failed:
                continue
            caption = record_summary(runs[key], key)
            unique, repeat = caption, 1
            while unique in choices:
                repeat += 1
                unique = caption + '（{}）'.format(repeat)
            choices[unique] = key
        if not choices:
            self.label('暂无可查看的结果。')
            return
        if self.settings.get('result_run', None) not in choices.values():
            self.settings['result_run'] = next(iter(choices.values()))
        self.ui.ComboBox(self.prefix + "['result_run']", choices, '运行记录', state='readonly', updateGUI=True, refresh_tree=False)
        record = runs[self.settings['result_run']]
        points = record.get('points', {})
        current_points = {key: point for key, point in points.items() if point_current(module, point)}
        complete = len(current_points)
        anchor = self.label('当前保留 {} / {} 个结果；已替换或重置的点请在原生扫描中查看。'.format(complete, len(points)))
        identity = self.label('记录编号：' + str(self.settings['result_run']))
        if isinstance(identity, tk.Misc):
            identity._cgyro_role = 'muted'
        self.ui.Button('查看结果表', lambda: self.result_table(anchor, record), refresh_tree=False)
        if complete:
            path = ('TGLF_scan', 'PLOTS', 'workbench_result')
            problems = [] if read(self.root, path) is not None else ['工程缺少此绘图入口']
            self.view.guarded('查看通量趋势', lambda: plot_view(read(self.root, path), record=record),
                              problems, refresh=False, refresh_tree=False)
            choices = OrderedDict((key + ' · ' + point['label'] + ' · ' + (', '.join(
                '{}={:g}'.format(name, value) for name, value in point['parameters'].items()) or '原值'), key)
                for key, point in current_points.items())
            if self.settings.get('result_point', None) not in choices.values():
                self.settings['result_point'] = next(iter(choices.values()))
            self.ui.ComboBox(self.prefix + "['result_point']", choices, '计算点', state='readonly', updateGUI=False, refresh_tree=False)
            self.view.guarded('查看该点的频率 / 增长率谱',
                lambda: plot_view(read(self.root, path), record=record, point_id=self.settings['result_point']),
                problems, refresh=False, refresh_tree=False)
        self.view.nav('结果对比绘图', 'plots')

    def result_table(self, anchor, record):
        window = tk.Toplevel(anchor.winfo_toplevel())
        configure_window_fonts(window)
        window.title('TGLF 结果 · ' + record_summary(record, record['id']))
        window.withdraw()
        point_count = max(1, len(record.get('points', {})))
        max_width = max(1, int(window.winfo_screenwidth() * 0.9))
        max_height = max(1, int(window.winfo_screenheight() * 0.85))
        automatic_size = [None]
        frame = ttk.Frame(window)
        frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        columns = ('point', 'input', 'parameters', 'status', 'qe', 'qi')
        style = ttk.Style(window)
        font = gui_font(window, style.lookup('Treeview', 'font') or 'TkDefaultFont')
        style_name = 'TGLFResults' + str(window).replace('.', '_') + '.Treeview'
        row_height = font.metrics('linespace') + 8
        style.configure(style_name, font=font, rowheight=row_height)
        table = ttk.Treeview(frame, columns=columns, show='headings', style=style_name,
                             height=min(point_count, 12))
        style_widget(table)
        table._tglf_font = font
        for key, title, width in zip(columns, ('任务', '输入 / 半径', '扫描值', '状态', 'Qe / QGB', 'Qi / QGB'), (90, 160, 210, 80, 110, 110)):
            table.heading(key, text=title)
            table.column(key, width=width, anchor='w')
        for key, point in record.get('points', {}).items():
            current = point_current(self.root.get('TGLF_scan', {}), point)
            fluxes = point.get('fluxes', []) if current else []
            qe = sum(row['heat'] for row in fluxes if row['species'] == 'elec')
            qi = sum(row['heat'] for row in fluxes if row['species'] != 'elec')
            status = {'complete': '完成', 'failed': '失败', 'prepared': '待运行', 'cancelled': '已中止'}.get(point.get('status', None), point.get('status', ''))
            if point.get('status', None) == 'complete' and not current:
                status = '已替换 / 重置'
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
        details_frame = ttk.Frame(window)
        details = tk.Text(details_frame, height=2, width=1, wrap='word')
        details.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        details_scroll = ttk.Scrollbar(details_frame, orient=tk.VERTICAL, command=details.yview)
        details_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        details.configure(yscrollcommand=details_scroll.set)
        details.configure(state='disabled')
        details_font = gui_font(details, details.cget('font'))
        details.configure(font=details_font)
        details._tglf_font = details_font
        footer = ttk.Frame(window)
        footer.pack(fill=tk.X, padx=8, pady=(0, 8))

        def fit_window():
            current_size = (window.winfo_width(), window.winfo_height())
            manual_size = automatic_size[0] is not None and current_size != automatic_size[0]
            window.update_idletasks()
            chrome_height = window.winfo_reqheight() - int(table.cget('height')) * row_height
            visible_rows = max(1, min(point_count, 12, (max_height - chrome_height) // row_height))
            table.configure(height=visible_rows)
            window.update_idletasks()
            window.minsize(min(420, max_width), min(max_height, max(1, chrome_height + row_height)))
            # Only follow content while the user has kept the automatic size.
            if not manual_size:
                width = min(max_width, max(420, window.winfo_reqwidth()))
                height = min(max_height, window.winfo_reqheight())
                window.geometry('{}x{}'.format(width, height))
                window.update_idletasks()
                automatic_size[0] = ((window.winfo_width(), window.winfo_height())
                                     if window.winfo_ismapped() else (width, height))

        def hide_details():
            details_frame.pack_forget()
            hide_button.pack_forget()
            fit_window()

        hide_button = ttk.Button(footer, text='收起详情', command=hide_details)
        ttk.Button(footer, text='关闭', command=window.destroy).pack(side=tk.RIGHT)

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
            detail_rows = max(2, min(len('\n'.join(lines).splitlines()), 8,
                                      max_height // max(1, details_font.metrics('linespace') * 3)))
            details.configure(state='disabled', height=detail_rows)
            details_frame.pack(fill=tk.X, padx=8, pady=(0, 8), before=footer)
            hide_button.pack(side=tk.LEFT)
            fit_window()
        table.bind('<<TreeviewSelect>>', select)
        table.bind('<Double-1>', lambda event: select() if table.identify_row(event.y) else None)
        fit_window()
        window.deiconify()
