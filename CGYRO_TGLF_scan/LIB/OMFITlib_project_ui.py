"""Native OMFIT workbench with dependency-aware workflow controls."""
from builtins import any, bool, callable, dict, float, int, isinstance, iter, len, list, next, range, sorted, str
from collections import OrderedDict
import json
import math
import tkinter as tk
from tkinter import ttk
from OMFITlib_gui_layout import finish_gui_layout
from OMFITlib_transfer_workflow import generation_issues, initialize_generation, loaded_file
from OMFITlib_project_runtime import initialize_runtime, applied_runtime, shared_issues, validate_runtime
from OMFITlib_gacode_installations import PROGRAMS, choices as installation_choices, installation_issues
from OMFITlib_cgyro_results import ResultBrowser
from OMFITlib_cgyro_parameters import (FIELDS as CGYRO_FIELDS, GROUPS as CGYRO_GROUPS,
    initialize_parameters, numeric_source, parameter_catalog, scan_parameter_names)
from OMFITlib_project import (ION_CASES, LABELS, MODULES, PAGES, cgyro_input_issues,
    cgyro_ion_mode, cgyro_plan_issues, cgyro_plan_summary, collect_issues, generated_tglf_sources, location, module,
    pending_inputs, read, runtime_issues, summary, sync_cgyro_choices, sync_cgyro_ion_cases, text_value,
    tglf_input_issues, transfer_sources)

STATUS = {'prepared': '输入已准备', 'submitted': '已提交', 'loaded': '结果已读取',
          'submitted_or_finished': '已提交或执行返回',
          'published': '结果已归档', 'complete': '完成', 'running': '运行中',
          'failed': '失败', 'cancelled': '已中止', 'partial': '部分完成',
          'ready': '输入就绪', 'prepare_failed': '输入生成失败', 'preparing': '输入生成中',
          'returned': '脚本已返回', 'inputs_copied': '输入已复制', 'archived': '已保留旧数据'}
STATUS.update(awaiting_choice='等待用户选择', accepted='使用传入输入', kept_current='保留当前输入', superseded='已有新候选')


class ProjectUI:
    def __init__(self, actions, ui, configure=None, open_templates=None, servers=(), open_servers=None):
        self.actions, self.root, self.ui = actions, actions.root, ui
        self.settings = actions.settings
        self.configure, self.open_templates = configure, open_templates
        self.servers, self.open_servers = servers, open_servers
        self.panel_only = False
        self.compact = False
        self.prefix = "root['SETTINGS']['WORKBENCH']"

    def label(self, value):
        return self.ui.Label(value, align='left', wraplength=600 if self.compact else 840)

    def nav(self, label, page):
        callback = (lambda: self.settings.__setitem__('cgyro_panel_page', page)) if self.panel_only else (
            lambda: self.actions.open_page(page))
        self.ui.Button(label, callback, updateGUI=True)

    def guarded(self, label, callback, issues):
        self.ui.Button(label, callback, updateGUI=True, state='disabled' if issues else 'normal',
                       help='；'.join(issues))

    def task(self, label, path, issues=(), **kwargs):
        problems = list(issues) + (['工程缺少此入口'] if read(self.root, path) is None else [])
        def invoke():
            if problems:
                raise ValueError('；'.join(problems))
            return self.actions.call(label, path, **kwargs)
        self.guarded(label, invoke, problems)

    def compound(self, path, **kwargs):
        task = read(self.root, path)
        if task is None:
            self.label('工程缺少此功能入口：' + '/'.join(path))
        else:
            self.ui.CompoundGUI(task, title='', **kwargs)

    def render(self, panel_only=False):
        self.panel_only = panel_only
        self.compact = panel_only or self.settings['page'] == 'cgyro'
        if panel_only:
            self.ui.TitleGUI('CGYRO · 线性扫描')
            intro = self.label('CGYRO 线性扫描')
            page = self.settings.setdefault('cgyro_panel_page', 'cgyro')
            if page not in PAGES.values():
                page = self.settings['cgyro_panel_page'] = 'cgyro'
            if page != 'cgyro':
                self.nav('返回 CGYRO 扫描', 'cgyro')
            getattr(self, 'render_' + page)()
            finish_gui_layout(intro, self.ui, compact=self.compact)
            return
        self.ui.TitleGUI('CGYRO / TGLF · 工程总控')
        intro = self.label('选择输入 → 设置参数 → 运行 → 查看结果' if self.compact else
                           '输入准备  →  传递与验证  →  运行与收集  →  绘图对比')
        self.ui.ComboBox(self.prefix + "['page']", PAGES, '工作页面', default='overview', updateGUI=True)
        with self.ui.same_row():
            self.ui.Button('检查前置条件', self.actions.check, updateGUI=True)
            self.ui.Button('刷新', lambda: None, updateGUI=True)
        if self.settings['message'] and self.settings['page'] != 'cgyro':
            self.label(self.settings['message'])
        if pending_inputs(self.root) and self.settings['page'] != 'review':
            self.nav('有待确认的 TGLF 输入 · 查看差异', 'review')
        getattr(self, 'render_' + self.settings['page'])()
        finish_gui_layout(intro, self.ui, compact=self.compact)

    def render_overview(self):
        s = summary(self.root)
        self.ui.Separator('1  输入转换工具 · 输入准备')
        self.label('可用文件：{}；TGLF 剖面：{}。'.format(s['transfer_inputs'], '已载入' if s['profiles'] else '未载入'))
        with self.ui.same_row():
            self.nav('导入 / 转换 / 传递输入', 'transfer')
            self.nav('批量导入 input.gacode', 'multi')
        self.ui.Separator('2  CGYRO / TGLF · 计算任务')
        cg_issues = cgyro_input_issues(self.root)
        self.label('CGYRO：' + ('；'.join(cg_issues) if cg_issues else '转换工具输入已准备并传递'))
        self.label('TGLF 单文件：{}；多剖面案例：{}，已选 {}。'.format(
            '已载入' if s['tglf_input'] else '未载入', s['multi_cases'], s['multi_selected']))
        with self.ui.same_row():
            self.nav('CGYRO 扫描', 'cgyro')
            self.nav('TGLF 单文件 / 扫描', 'tglf')
            self.nav('TGLF 多剖面计算', 'multi')
        self.ui.Separator('3  运行与结果')
        self.label('CGYRO 当前状态：{}；归档运行：{}；TGLF 谱结果半径：{}。'.format(
            STATUS.get(s['cgyro_status'], s['cgyro_status']), s['cgyro_runs'], s['tglf_radii']))
        with self.ui.same_row():
            self.nav('运行环境与记录', 'run')
            self.nav('绘图与模型对比', 'plots')
            self.nav('模板 / GitHub', 'templates')
        self.ui.Separator('流程规则')
        self.label('CGYRO：Transfer_tool 生成半径输入后，选择输入案例与 1–3 个参数轴批量运行。\n'
                   '已有完整 input.cgyro 也可直接载入并作为一个 nr 使用。\n'
                   'TGLF 多剖面：导入 input.gacode → 生成局部输入 → 计算 → 结果对比。')

    def render_transfer(self):
        self.ui.Tab('Transfer_tool 运行')
        self.compound(('Transfer_tool', 'GUIS', 'transfer'), show_run_button=False)
        self.run_controls('transfer')
        self.ui.Tab('生成结果与传递')
        radial = sync_cgyro_choices(self.root, self.settings, self.actions.factory)
        if radial:
            details = ['nr={}'.format(row['nr']) +
                       (' (rho={:g})'.format(row['rho']) if row['rho'] is not None else '') for row in radial]
            self.label('CGYRO：{}。无需逐个选择输入。'.format('，'.join(details)))
            with self.ui.same_row():
                self.nav('设置并运行 CGYRO', 'cgyro')
        else:
            self.label('CGYRO：运行 Transfer_tool 后自动读取全部 nr。')
        sources = {label: value for label, value in transfer_sources(self.root).items()
                   if not json.loads(value)[-1].split('_')[0] == 'input.cgyro'}
        if sources:
            if self.settings['transfer_source'] not in sources.values():
                self.settings['transfer_source'] = next(iter(sources.values()))
            self.ui.ComboBox(self.prefix + "['transfer_source']", sources, 'TGLF / 剖面输入', updateGUI=True)
            kind = json.loads(self.settings['transfer_source'])[-1].split('_')[0]
            if kind == 'input.tglf':
                self.ui.Button('验证并送入 TGLF 单文件', lambda: self.actions.handoff('tglf'), updateGUI=True)
            elif kind == 'input.gacode':
                self.ui.Button('送入 TGLF 剖面流程', lambda: self.actions.handoff('profiles'), updateGUI=True)
                self.ui.Button('设为 转换工具当前剖面', lambda: self.actions.handoff('transfer'), updateGUI=True)
        else:
            self.label('先载入输入，或运行 profiles_gen 生成文件。缺少输入时无法传递到计算模块。')
        self.ui.Tab('局部输入互转')
        self.compound(('Transfer_tool', 'GUIS', 'convert'))
        self.ui.Tab('高级设置')
        self.label('已有种子输入继续使用；缺少时，运行按钮自动使用内置种子。这里只在需要调整模型参数或换用其他种子时操作。')
        node = module(self.root, 'transfer')
        for kind in ('tglf', 'tgyro'):
            branch = 'INPUTS' if 'input.' + kind in node['INPUTS'] else 'TEMPLATES'
            self.label(('当前输入 · ' if branch == 'INPUTS' else '内置种子 · ') + loaded_file(node, branch, 'input.' + kind))
            value = read(node, (branch, 'input.' + kind))
            if value is not None:
                self.ui.EditASCIIobject(location(MODULES['transfer'] + (branch, 'input.' + kind)),
                    '编辑 input.' + kind + ' 参数', updateGUI=True)
            self.ui.FilePicker(self.prefix + "['transfer_" + kind + "_file']", '转换工具 input.' + kind, default='',
                postcommand=lambda location=None, kind=kind: self.actions.import_transfer_seed(kind), updateGUI=True)
        self.label('起止半径、坐标和点数以“Transfer_tool 运行”页为准；离子数量、质量和电荷每次运行时从当前剖面同步。')
        self.nav('统一 GACODE 环境配置', 'run')

    def render_cgyro(self):
        node = read(self.root, MODULES['cgyro'])
        if node is None:
            self.label('工程缺少 CGYRO_scan 模块。')
            return
        base = MODULES['cgyro'] + ('SETTINGS',)
        self.ui.Tab('输入与扫描')
        self.ui.ComboBox(self.prefix + "['cgyro_source_mode']", OrderedDict([
            ('Transfer_tool 半径输入', 'generated'), ('导入 input.cgyro', 'imported'),
            ('CGYRO 当前输入', 'current')]), '输入来源', state='readonly', updateGUI=True)
        mode = self.settings['cgyro_source_mode']
        if mode == 'imported':
            self.ui.FilePicker(self.prefix + "['cgyro_file']", 'input.cgyro 文件', default='',
                transferRemoteFile=None, postcommand=lambda location=None: self.actions.import_input('cgyro'), updateGUI=True)
            source = self.settings.get('cgyro_import_source', {})
            if source.get('path', ''):
                self.label('已载入：' + str(source['path']))
        elif mode == 'generated':
            self.nav('生成 / 更换半径输入', 'transfer')
        rows = sync_cgyro_choices(self.root, self.settings, self.actions.factory)
        self.ui.Separator('1  选择半径与主离子')
        if rows:
            if len(rows) > 1:
                with self.ui.same_row():
                    self.ui.Button('全部半径', self.actions.select_cgyro_radii, updateGUI=True)
                    self.ui.Button('清空选择', lambda: self.actions.select_cgyro_radii(False), updateGUI=True)
            for offset in range(0, len(rows), 2):
                with self.ui.same_row():
                    for row in rows[offset:offset + 2]:
                        caption = 'nr={}'.format(row['nr'])
                        if row['rho'] is not None:
                            caption += ' · rho={:g}'.format(row['rho'])
                        self.cgyro_checkbox(self.prefix + "['cgyro_radii'][{!r}]".format(row['key']),
                                             self.settings['cgyro_radii'], row['key'], caption)
        else:
            self.label('尚无输入，请生成半径输入或导入 input.cgyro。')
        sync_cgyro_ion_cases(self.settings, self.actions.factory)
        if self.settings.get('cgyro_ion_mode', None) not in ('original', 'hdt', 'custom'):
            self.settings['cgyro_ion_mode'] = cgyro_ion_mode(self.settings)
        self.ui.ComboBox(self.prefix + "['cgyro_ion_mode']", OrderedDict([
            ('保持原始粒子', 'original'), ('H / D / T 对比', 'hdt'), ('自选方案', 'custom')]),
            '主离子方案', state='readonly', updateGUI=True, postcommand=self.actions.set_cgyro_ions)
        if self.settings['cgyro_ion_mode'] == 'custom':
            cases = list(ION_CASES.items())
            for offset in range(0, len(cases), 2):
                with self.ui.same_row():
                    for key, caption in cases[offset:offset + 2]:
                        self.cgyro_checkbox(self.prefix + "['cgyro_ion_cases'][{!r}]".format(key),
                                             self.settings['cgyro_ion_cases'], key, caption)
        self.ui.Separator('2  设置扫描')
        self.ui.Entry(location(base + ('EXPERIMENT', 'runid')), '结果名称', updateGUI=True)
        self.ui.Entry(location(base + ('PHYSICS', 'kyarr')), 'ky 取值', updateGUI=True,
                      help='输入列表，例如 [0.1, 0.2, 0.3]。')
        self.ui.ComboBox(location(base + ('SETUP', 'idimrun')), OrderedDict([
            ('只扫 ky，保持输入参数', 0), ('ky + 1 个参数', 1),
            ('ky + 2 个参数', 2), ('ky + 3 个参数', 3)]), '扫描内容', state='readonly', updateGUI=True)
        dim = int(node['SETTINGS']['SETUP']['idimrun'])
        keys = {1: [('Para', 'Range')],
                2: [('Para_x', 'Range_x'), ('Para_y', 'Range_y')],
                3: [('Para_x', 'Range_x'), ('Para_y', 'Range_y'), ('Para_z', 'Range_z')],
        }.get(dim, [])
        selected = [row for row in rows if self.settings['cgyro_radii'].get(row['key'], False)]
        source = read(self.root, (selected or rows)[0]['path'], {}) if rows else {}
        options = OrderedDict((name, name) for name in CGYRO_FIELDS)
        for name in sorted(source.keys(), key=str):
            if str(name) == 'KY' or not str(name).isupper():
                continue
            try:
                if math.isfinite(float(source[name])):
                    options[str(name)] = str(name)
            except (TypeError, ValueError):
                continue
        group = str(dim) + 'd'
        if keys:
            node['SETTINGS']['PHYSICS'].setdefault(group, {})
        for index, (pkey, rkey) in enumerate(keys, 1):
            defaults = ('BETAE_UNIT', 'S', 'RLTS_1')
            cfg = node['SETTINGS']['PHYSICS'][group]
            cfg.setdefault(pkey, defaults[index - 1])
            cfg.setdefault(rkey, [source.get(cfg[pkey], 0.0)])
            self.ui.Separator('参数轴 ' + str(index))
            self.ui.ComboBox(location(base + ('PHYSICS', group, pkey)), options, '参数',
                             state='normal', width=24, updateGUI=True)
            self.ui.Entry(location(base + ('PHYSICS', group, rkey)), '取值列表', width=28, updateGUI=True)
            linked = 2
            while pkey + str(linked) in cfg or rkey + str(linked) in cfg:
                self.ui.ComboBox(location(base + ('PHYSICS', group, pkey + str(linked))), options,
                                 '联动参数', state='normal', width=24, default='', updateGUI=True)
                self.ui.Entry(location(base + ('PHYSICS', group, rkey + str(linked))),
                              '同步取值', width=28, default=[], updateGUI=True,
                              help='与参数 ' + str(index) + ' 的取值逐项对应。独立组合请使用多个参数轴。')
                linked += 1
        self.ui.Separator('3  运行')
        problems = cgyro_plan_issues(self.root)
        if not problems:
            plan = cgyro_plan_summary(self.root)
            self.label('{} 个输入组合 × 每组 {} 点 = {} 个任务'.format(
                plan['cases'], plan['points_per_case'], plan['total_points']))
        remote = node['SETTINGS'].get('REMOTE_SETUP', {})
        config = remote.get(str(remote.get('serverPicker', '') or ''), {})
        self.label('服务器：{}\n队列：{} · 每任务 {} 节点 × {} MPI'.format(
            remote.get('serverPicker', '未配置'), config.get('queue', '未配置'),
            config.get('nodes', '—'), config.get('ntasks_per_node', '—')))
        issues = problems + runtime_issues(self.root, 'cgyro')
        self.guarded('运行所选扫描', self.actions.run_cgyro, issues)
        self.nav('修改运行环境', 'run')
        if issues:
            self.label('需要：' + '；'.join(issues[:2]))
        if self.settings['message']:
            self.label(str(self.settings['message']).splitlines()[0][:200])
        self.ui.Tab('计算参数')
        self.render_cgyro_parameters(node, rows)
        self.ui.Tab('结果与记录')
        manifest = node.get('RUN_MANIFEST', {})
        if manifest:
            self.label('最近运行：{} · {}'.format(manifest.get('case_id', ''),
                STATUS.get(manifest.get('status', ''), manifest.get('status', ''))))
            if manifest.get('job_id', None):
                self.label('作业：' + str(manifest['job_id']))
            self.guarded('重新收集未归档结果', self.actions.collect, collect_issues(self.root))
        ResultBrowser(self.root, self.ui).render(title=False)
        self.nav('对比绘图（可选）', 'plots')

    def render_cgyro_parameters(self, node, rows):
        physics = node['SETTINGS']['PHYSICS']
        base = MODULES['cgyro'] + ('SETTINGS', 'PHYSICS')
        selected = [row for row in rows if self.settings['cgyro_radii'].get(row['key'], False)]
        available = selected or rows
        self.label('勾选的项目统一修改；其余沿用各输入。扫描轴的取值优先。')
        if not available:
            self.label('先在“输入与扫描”中载入输入。')
            return
        choices = OrderedDict(('nr={} · {}'.format(row['nr'], row['key']), row['key']) for row in available)
        if self.settings.get('cgyro_parameter_reference', '') not in choices.values():
            self.settings['cgyro_parameter_reference'] = available[0]['key']
        self.ui.ComboBox(self.prefix + "['cgyro_parameter_reference']", choices, '参考输入',
                         state='readonly', updateGUI=True)
        row = next(item for item in available if item['key'] == self.settings['cgyro_parameter_reference'])
        source = read(self.root, row['path'])
        parameters = initialize_parameters(physics, source, self.actions.factory)
        sources = [read(self.root, item['path']) for item in available]
        catalog = parameter_catalog(sources)
        source_values = numeric_source(source)
        for name, spec in catalog.items():
            item = parameters.setdefault(name, self.actions.factory())
            item.setdefault('enabled', False)
            item.setdefault('value', source_values.get(name, spec['reference']))
            if not item['enabled']:
                item['value'] = source_values.get(name, spec['reference'])
        # Keep unavailable saved overrides visible so the user can disable them.
        for name in parameters:
            if name not in catalog:
                catalog[name] = dict(label='当前输入不支持', group='other', reference=None, kind='float')
        self.settings.setdefault('cgyro_parameter_group', 'common')
        self.settings.setdefault('cgyro_parameter_search', '')
        self.ui.ComboBox(self.prefix + "['cgyro_parameter_group']", CGYRO_GROUPS, '参数分组',
                         state='readonly', width=24, updateGUI=True)
        self.ui.Entry(self.prefix + "['cgyro_parameter_search']", '搜索参数', width=28, updateGUI=True)
        group = self.settings['cgyro_parameter_group']
        query = str(self.settings['cgyro_parameter_search']).strip().upper()
        names = [name for name, spec in catalog.items()
                 if (group == 'all' or (group == 'common' and name in CGYRO_FIELDS) or spec['group'] == group)
                 and (not query or query in name or query in spec['label'].upper())]
        scanned = scan_parameter_names(physics, int(node['SETTINGS']['SETUP']['idimrun']))
        with self.ui.same_row():
            self.ui.Button('本页读取参考值',
                           lambda: self.actions.reset_cgyro_parameters(names, row['key']), updateGUI=True)
            self.ui.Button('全部沿用输入', self.actions.inherit_cgyro_parameters, updateGUI=True)
        if not names:
            self.label('没有匹配的参数。')
        previous_group = None
        labels = {value: label for label, value in CGYRO_GROUPS.items()}
        for name in names:
            spec = catalog[name]
            if spec['group'] != previous_group:
                self.ui.Separator(labels.get(spec['group'], '其他输入参数'))
                previous_group = spec['group']
            if name in scanned:
                self.label(name + ' · 由扫描轴设置')
                continue
            item = parameters[name]
            path = base + ('fixed_parameters', name)
            source_value = source_values.get(name, '未显式写入')
            with self.ui.same_row() as line:
                # Keep each setting on one row, with its numeric field aligned
                # at the right. Preserve the controls' native OMFIT bindings.
                frame = getattr(line, 'frm_top', None)
                if isinstance(frame, tk.Misc):
                    frame._cgyro_inline = True
                self.cgyro_checkbox(location(path + ('enabled',)), item, 'enabled',
                                     name + ' · ' + spec['label'])
                self.ui.Entry(location(path + ('value',)), '', width=14, updateGUI=True,
                              state='normal' if item['enabled'] else 'disabled',
                              help='参考输入：{}。勾选后，此值应用到本轮全部所选输入。'.format(source_value))
        self.ui.Separator('时间缩放')
        self.cgyro_checkbox(location(base + ('scale_time_with_ky',)), physics, 'scale_time_with_ky', '按 ky 缩放时间')
        if physics['scale_time_with_ky']:
            self.label('ky > 1 时，步长与运行时长分别除以 ky。')
        self.ui.Separator('重启与源文件')
        self.ui.ComboBox(location(base + ('restart_mode',)), {'新计算': 0, '匹配结果重启': 1},
                         '运行方式', state='readonly', updateGUI=True)
        self.cgyro_checkbox(self.prefix + "['cgyro_advanced']", self.settings, 'cgyro_advanced', '直接编辑源 input.cgyro')
        if self.settings['cgyro_advanced']:
            self.ui.EditASCIIobject(location(row['path']), '编辑参考输入', updateGUI=True)
        problems = cgyro_plan_issues(self.root)
        if problems:
            self.label('需要：' + '；'.join(problems[:2]))

    def cgyro_checkbox(self, path, mapping, key, caption):
        value = mapping.get(key, False)
        value = str(value).lower() in ('true', '.true.', '1', '1.0')
        mapping[key] = value
        # Native CheckBox returns one widget per location, including a single path.
        control = self.ui.CheckBox(path, caption, default=False, updateGUI=True)[0]
        variable = tk.BooleanVar(master=control, value=value)
        control.configure(variable=variable, onvalue=1, offvalue=0)
        variable.set(value)
        control.state(['!alternate', 'selected' if value else '!selected'])
        control._cgyro_boolean = variable
        return control

    def render_tglf(self):
        node = read(self.root, MODULES['tglf'])
        if node is None:
            self.label('工程缺少 TGLF 模块。')
            return
        self.ui.Tab('单个 input.tglf')
        self.ui.FilePicker(self.prefix + "['tglf_file']", '导入 input.tglf', default='',
                           postcommand=lambda location=None: self.actions.import_input('tglf'), updateGUI=True)
        self.label('当前输入：' + ('已载入' if 'input.tglf' in node.get('FILES', {}) else '未载入'))
        issues = runtime_issues(self.root, 'tglf') + tglf_input_issues(self.root)
        with self.ui.same_row():
            self.task('编辑 TGLF 模型与数值参数', MODULES['tglf'] + ('GUIS', 'TGLF_GUI'),
                      issues=tglf_input_issues(self.root), showButtons=False)
            self.guarded('运行当前 input.tglf', lambda: self.actions.run('tglf', 'runTGLF', (('FILES', 'input.tglf'),)), issues)
        self.label('运行条件：' + ('；'.join(issues) or '基础字段已填写，运行前将再次检查'))
        self.ui.Tab('参数与径向扫描')
        self.label('从剖面准备局部输入，再选择径向、1D、2D 或 UQ 扫描。')
        generated = generated_tglf_sources(self.root)
        if generated:
            if self.settings.get('generated_tglf_source', None) not in generated.values():
                self.settings['generated_tglf_source'] = next(iter(generated.values()))
            self.ui.ComboBox(self.prefix + "['generated_tglf_source']", generated, '已生成输入的半径', updateGUI=True)
            self.ui.Button('比较并传入当前 TGLF 单文件', self.actions.use_generated_tglf, updateGUI=True)
        self.label('按半径生成的输入独立保存。切换半径或运行扫描会使用对应副本；传入当前单文件输入时先确认覆盖。')
        with self.ui.same_row():
            self.task('剖面准备 / PROFILES_GEN', MODULES['profiles'] + ('GUIS', 'standaloneGUI'))
            self.task('径向 / 1D / 2D / UQ 工作流', ('TGLF_scan', 'GUIS', 'tglf_scan_gui'),
                      issues=['请先处理 TGLF 输入覆盖选择'] if pending_inputs(self.root) else [])
        with self.ui.same_row():
            self.task('单文件 1D 扫描设置', MODULES['tglf'] + ('GUIS', 'scanGUI'), issues=tglf_input_issues(self.root))
            self.task('单文件 2D 扫描设置', MODULES['tglf'] + ('GUIS', 'scan2DGUI'), issues=tglf_input_issues(self.root))
            self.task('单文件 UQ 设置', MODULES['tglf'] + ('GUIS', 'uqGUI'), issues=tglf_input_issues(self.root))
        self.label('普通批量扫描沿用原提交器，其并行数和队列时限的统一配置仍待后续修复。')
        self.ui.Tab('多个剖面对比')
        self.nav('进入多 input.gacode 计算页面', 'multi')
        self.ui.Tab('执行配置')
        self.run_controls('tglf')

    def render_multi(self):
        self.compound(('GUIS', 'TGLF_multi'))

    def render_review(self):
        pending = pending_inputs(self.root)
        if not pending:
            self.label('没有待确认的输入。可在 输入转换工具 选择转换结果并传入 TGLF。')
            self.nav('返回 输入转换工具', 'transfer')
        for key, record in pending.items():
            self.ui.Separator(record['title'])
            target = '输入转换工具 的 TGLF 种子输入' if record.get('destination', None) == 'transfer' else 'TGLF 当前单文件输入'
            self.label('目标：' + target + '。当前文件可能由 TGYRO 生成或由你导入。\n'
                       '下面逐项比较参数；选择整体保留或整体替换，不自动混合两套输入。')
            with self.ui.same_row():
                self.ui.Button('保留当前 TGLF 输入', lambda key=key: self.actions.resolve_input(key, False), updateGUI=True)
                self.ui.Button('使用待传入输入，并保存原版本', lambda key=key: self.actions.resolve_input(key, True), updateGUI=True)
            if not record['differences']:
                self.label('两份输入的参数内容一致；仍由你决定采用哪个来源。')
            else:
                self.label('差异共 {} 项。格式：参数 · 类型 ｜ 当前值 → 待传入值'.format(len(record['differences'])))
                for name, change, before, after in record['differences']:
                    self.label('{} · {}\n当前：{}\n待传入：{}'.format(name, change, before, after))
            self.label('选择覆盖后，原输入及其对应结果均保存在 工程 → PROJECT_STATE → activity。')

    def required_issues(self, name, paths):
        node = module(self.root, name)
        pending = ['请先确认 输入转换工具 的 TGLF 输入'] if name == 'transfer' and pending_inputs(self.root, 'transfer') else []
        return pending + runtime_issues(self.root, name) + ['缺少 ' + '/'.join(path) for path in paths if read(node, path) is None]

    def run_controls(self, name):
        if read(self.root, MODULES[name]) is None:
            self.label('缺少 ' + LABELS[name])
            return
        if name != 'transfer':
            self.nav('统一 GACODE 环境配置', 'run')
        if name == 'cgyro':
            self.nav('设置并运行 CGYRO', 'cgyro')
        elif name == 'transfer':
            node = module(self.root, 'transfer')
            options = initialize_generation(node, self.actions.factory)
            issues = self.required_issues('transfer', ()) + generation_issues(
                node, node['SETTINGS']['PHYSICS']['start_from'], options)
            self.guarded('运行 Transfer_tool', self.actions.run_transfer, issues)
            if issues:
                self.label('需要补充：' + '；'.join(issues))
        else:
            self.label('配置检查：' + ('；'.join(runtime_issues(self.root, name)) or '基础字段已填写；目标程序与资源尚未验证'))

    def select_runtime(self, name):
        self.settings['page'] = 'run'

    def render_run(self):
        self.ui.Tab('环境设置')
        self.environment()
        self.ui.Tab('运行记录')
        manifest = read(self.root, ('CGYRO_scan', 'RUN_MANIFEST'), {})
        self.ui.Separator('CGYRO 当前运行')
        self.label('状态：{}；作业：{}\n目录：{}'.format(STATUS.get(manifest.get('status', None), manifest.get('status', '尚无记录')),
                    manifest.get('job_id', '—'), manifest.get('workDir', '—')))
        self.guarded('收集 CGYRO 当前结果', self.actions.collect, collect_issues(self.root))
        self.ui.Separator('TGLF 多剖面运行')
        cases = self.root.get('TGLF_CASES', {})
        if not cases:
            self.label('尚无多剖面案例。')
        for case in cases.values():
            run = case.get('runs', {}).get(case.get('selected_run', None), {})
            self.label('{}：{}'.format(case.get('label', '未命名案例'), STATUS.get(run.get('status', None), run.get('status', '尚未运行'))))
        self.nav('选择记录 / 重试 / 查看错误', 'multi')
        self.label('这里显示 工程保存的状态。不会在打开页面时轮询或提交任务。')
        self.ui.Tab('操作与输入历史')
        records = read(self.root, ('PROJECT_STATE', 'activity'), {})
        if not records:
            self.label('尚无通过总控页执行的操作。')
        for record in list(records.values())[-20:][::-1]:
            self.ui.Separator(record['title'])
            self.label('{} · {}{}'.format(record['created'], STATUS.get(record['status'], record['status']),
                '\n' + record['error'] if record.get('error', None) else ''))
            if record.get('previous_inputs', None):
                self.label('保留的旧输入：' + '；'.join(record['previous_inputs'].keys()))
        self.label('完整历史在 工程 → PROJECT_STATE 中；输入历史和旧结果随工程保存。')

    def environment(self):
        config = initialize_runtime(self.root, self.actions.factory)
        prefix = "root['SETTINGS']['GACODE_RUNTIME']"
        self.label('各程序共用服务器和基础环境，GACODE 版本可分别选择。')
        self.ui.Separator('服务器与工作目录')
        servers = self.servers() if callable(self.servers) else self.servers
        choices = OrderedDict([('localhost（本机）', 'localhost')])
        for name in servers:
            if name == 'localhost':
                continue
            caption = str(servers[name]) if isinstance(servers, dict) else str(name)
            choices[caption] = name
        picker = text_value(config, 'serverPicker')
        draft = self.settings.get('server_draft', None)
        if picker and picker not in choices.values():
            choices[picker + '（工程保存的配置名）'] = picker
        self.ui.ComboBox(prefix + "['serverPicker']", choices,
                         '服务器配置名', state='disabled' if draft is not None else 'readonly', updateGUI=True,
                         postcommand=lambda location=None: self.actions.sync_runtime_endpoint(replace_directory=True))
        server_issues = self.actions.runtime_server_issues()
        with self.ui.same_row():
            self.guarded('新增服务器', self.actions.begin_runtime_server,
                         ['请先保存或取消当前新增'] if draft is not None else
                         ([] if self.actions.register_server is not None else ['当前宿主未提供服务器登记入口']))
            self.guarded('从 OMFIT 读取连接信息', self.actions.sync_runtime_endpoint,
                         server_issues + (['请先保存或取消当前新增'] if draft is not None else []))
            if self.open_servers is not None:
                self.ui.Button('OMFIT 个人服务器设置', self.open_servers, updateGUI=True)
        if server_issues and draft is None:
            self.label('；'.join(server_issues))
        if draft is not None:
            self.ui.Separator('新增服务器')
            for key, label in [('serverPicker', '新配置名'), ('server', '服务器地址（用户名@主机[:端口]）'),
                               ('tunnel', '连接隧道（可留空）'), ('workDir', '工作根目录')]:
                self.server_text_entry(draft, key, label)
            with self.ui.same_row():
                self.ui.Button('保存并选用', self.actions.register_runtime_endpoint, updateGUI=True)
                self.ui.Button('取消新增', self.actions.cancel_runtime_server, updateGUI=True)
        else:
            self.ui.Entry(prefix + "['server']", '服务器地址', updateGUI=True)
            self.ui.Entry(prefix + "['tunnel']", '连接隧道（可留空）', updateGUI=True)
            self.ui.Entry(prefix + "['workDir']", '工作根目录', updateGUI=True)
        self.label('此目录下自动使用 cgyro、tglf、tgyro、transfer 等子目录，避免同名输入互相覆盖。')
        self.ui.Separator('共用 GACODE 环境')
        self.ui.Entry(prefix + "['environment']", '环境初始化脚本', multiline=True,
                      help='统一填写编译器、MPI、GACODE_PLATFORM 等基础环境。下方所选安装会覆盖 GACODE_ROOT 并重新载入 gacode_setup。')
        self.gacode_installations(config, prefix, draft is not None)
        self.ui.Separator('CGYRO 扫描资源')
        self.ui.ComboBox(prefix + "['scheduler']", OrderedDict([('本机执行', 'local'), ('Slurm', 'slurm'), ('PBS', 'pbs')]),
                         '作业调度', updateGUI=True)
        if config['scheduler'] != 'local':
            with self.ui.same_row():
                self.ui.Entry(prefix + "['queue']", '队列 / 分区')
                self.ui.Entry(prefix + "['wall_time']", '运行时限')
        with self.ui.same_row():
            self.ui.Entry(prefix + "['nodes']", '节点数', width=8)
            self.ui.Entry(prefix + "['cores']", '每节点 MPI 数', width=8)
        with self.ui.same_row():
            self.ui.Entry(prefix + "['cpus_per_task']", '每进程线程数', width=8)
            self.ui.Entry(prefix + "['array_parallel']", '同时运行的扫描点', width=8)
        self.ui.CheckBox(self.prefix + "['runtime_advanced']", '显示程序命令与并行细节', default=False, updateGUI=True)
        if self.settings.get('runtime_advanced', False):
            for key, label in [('cgyro_command', 'CGYRO 扫描命令'), ('tglf_command', 'TGLF 计算命令'),
                               ('tgyro_command', 'TGYRO 计算命令'), ('prepare_command', '多剖面输入生成命令')]:
                self.ui.Entry(prefix + "[{!r}]".format(key), label, multiline=True)
            self.label('{mpi} 自动使用节点数 × 每节点 MPI 数；{n_radii} 按 TGYRO 实际径向任务所需进程数替换。')
            self.label('剖面转换与单次 TGLF 延续原来的同步执行方式；批作业命令可在此设置。')
            transfer = read(self.root, MODULES['transfer'])
            if transfer is not None:
                self.ui.Entry(location(MODULES['transfer'] + ('SETTINGS', 'SETUP', 'p_tgyro')), '转换用 TGYRO 半径数')
        detection = self.root.get('PROJECT_STATE', {}).get('gacode_detection', {})
        issues = (validate_runtime(config) + installation_issues(config, detection)
                  + self.actions.runtime_server_issues(match_connection=True))
        if draft is not None:
            issues = ['请先保存或取消新增服务器']
        if self.settings.get('gacode_draft', None) is not None:
            issues = ['请先保存或取消 GACODE 安装编辑']
        if draft is not None:
            status = '新增配置尚未保存。'
        elif applied_runtime(self.root) is None:
            status = '已从现有 CGYRO 配置预填；点击应用后，各模块开始共用此配置。'
        elif shared_issues(self.root):
            status = '配置有未应用的修改，请应用后再运行。'
        else:
            status = '统一配置已应用。环境只需在本页维护。'
        self.label(status)
        if issues and draft is None:
            self.label('待填写：' + '；'.join(issues))
        self.guarded('应用到整个工程', self.actions.apply_runtime, issues)

    def gacode_installations(self, config, prefix, server_draft=False):
        self.ui.Separator('GACODE 安装与自动检测')
        self.server_text_entry(config, 'gacode_scan_dir', '搜索目录')
        detection = self.root.get('PROJECT_STATE', {}).get('gacode_detection', {})
        installs = config['gacode_installs']
        draft = self.settings.get('gacode_draft', None)
        with self.ui.same_row():
            self.guarded('自动检测', self.actions.detect_gacode,
                         ['请先保存或取消编辑'] if draft is not None or server_draft else [])
            self.guarded('新增路径', self.actions.begin_gacode_install,
                         ['请先保存或取消编辑'] if draft is not None else [])
        self.label('扫描搜索目录下的 Gacode* 文件夹；检查实际程序，不运行计算。')
        if installs:
            options = installation_choices(config, detection)
            if self.settings.get('gacode_entry', '') not in installs:
                self.settings['gacode_entry'] = next(iter(installs))
            self.ui.ComboBox(self.prefix + "['gacode_entry']", options, '安装列表',
                             state='disabled' if draft is not None else 'readonly', updateGUI=True)
            name = self.settings['gacode_entry']
            self.label(str(installs[name]))
            with self.ui.same_row():
                self.guarded('编辑路径', lambda: self.actions.begin_gacode_install(edit=True),
                             ['请先保存或取消编辑'] if draft is not None else [])
                used = any(config[program + '_install'] == name for program in PROGRAMS)
                self.guarded('移除路径', self.actions.remove_gacode_install,
                             ['请先更换使用此安装的程序'] if used else
                             (['请先保存或取消编辑'] if draft is not None else []))
        if draft is not None:
            self.server_text_entry(draft, 'name', '安装名称')
            self.server_text_entry(draft, 'path', '安装根目录')
            with self.ui.same_row():
                self.ui.Button('保存路径', self.actions.save_gacode_install, updateGUI=True)
                self.ui.Button('取消编辑', self.actions.cancel_gacode_install, updateGUI=True)
        for program, (caption, _) in PROGRAMS.items():
            self.ui.ComboBox(prefix + "[{!r}]".format(program + '_install'),
                             installation_choices(config, detection, program), caption + ' 版本',
                             state='readonly', updateGUI=True)
        self.label('TGYRO 与 profiles_gen 可用完整安装；CGYRO 可保留专用版本。应用时再次检查路径。')

    def server_text_entry(self, draft, key, caption):
        """Plain text in an OMFIT row, without Python expression evaluation.

        Write only the isolated draft as the user types, so Save also sees the
        last field without an extra Enter/FocusOut. Keep the Tk variable alive.
        """
        label = self.ui.Label(caption + ' = ', align='left')
        variable = tk.StringVar(master=label.master, value=str(draft.get(key, '') or ''))
        entry = ttk.Entry(label.master, textvariable=variable)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))
        trace = variable.trace_add('write', lambda *args: draft.__setitem__(key, variable.get()))
        def release(event):
            if event.widget is entry:
                variable.trace_remove('write', trace)
        entry.bind('<Destroy>', release, add='+')
        entry._server_text_variable = variable
        return entry

    def render_plots(self):
        self.label('扫描结果浏览以数值表显示 1–3 个参数轴；对比绘图用于跨案例或跨模型比较。')
        with self.ui.same_row():
            self.task('CGYRO 扫描结果浏览', ('GUIS', 'CGYRO_results'),
                      issues=[] if read(self.root, ('CGYRO_scan', 'RUN_DB'), {}) else ['尚无已收集的 CGYRO 扫描结果'])
            self.nav('多 input.gacode 结果对比', 'multi')
            self.task('TGYRO 结果绘图', MODULES['tgyro'] + ('GUIS', 'Plotgui'))
        self.compound(('GUIS', 'CGYRO_vs_TGLF'))

    def render_templates(self):
        self.label('通过 GitHub 分发代码与设置。更新时可保留计算结果，或使用模板提供的示例。')
        self.label('模板库：https://github.com/Liu-s-CGYRO-project/CGYRO_TGLF_scan')
        self.guarded('打开 OMFIT 模板管理器', self.open_templates or (lambda: None),
                     [] if self.open_templates else ['当前工程未载入 OMFITtemplates'])
        self.label('个人服务器和路径可在更新时保留；计算记录和输入历史不进入代码模板。')
