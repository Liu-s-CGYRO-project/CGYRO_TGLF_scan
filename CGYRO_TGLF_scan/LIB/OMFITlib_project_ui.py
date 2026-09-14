"""Native OMFIT workbench with dependency-aware workflow controls."""
from builtins import dict, isinstance, len, list, next, str
from OMFITlib_project import (LABELS, MODULES, PAGES, cgyro_input_issues, collect_issues, generated_tglf_sources,
    location, module, pending_inputs, read, runtime_issues, summary, text_value, tglf_input_issues, transfer_sources)

STATUS = {'prepared': '输入已准备', 'submitted': '已提交', 'loaded': '结果已读取',
          'submitted_or_finished': '已提交或执行返回',
          'published': '结果已归档', 'complete': '完成', 'running': '运行中',
          'failed': '失败', 'cancelled': '已中止', 'partial': '部分完成',
          'ready': '输入就绪', 'prepare_failed': '输入生成失败', 'preparing': '输入生成中',
          'returned': '脚本已返回', 'inputs_copied': '输入已复制', 'archived': '已保留旧数据'}
STATUS.update(awaiting_choice='等待用户选择', accepted='使用传入输入', kept_current='保留当前输入', superseded='已有新候选')


class ProjectUI:
    def __init__(self, actions, ui, configure=None, open_templates=None, servers=()):
        self.actions, self.root, self.ui = actions, actions.root, ui
        self.settings = actions.settings
        self.configure, self.open_templates = configure, open_templates
        self.servers = list(servers)
        self.prefix = "root['SETTINGS']['WORKBENCH']"

    def label(self, value):
        self.ui.Label(value, align='left', wraplength=840)

    def nav(self, label, page):
        self.ui.Button(label, lambda: self.actions.open_page(page), updateGUI=True)

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

    def compound(self, path):
        task = read(self.root, path)
        if task is None:
            self.label('工程缺少此功能入口：' + '/'.join(path))
        else:
            self.ui.CompoundGUI(task, title='')

    def render(self):
        self.ui.TitleGUI('CGYRO / TGLF · Project 总控')
        self.label('输入准备  →  传递与验证  →  运行与收集  →  绘图对比')
        with self.ui.same_row():
            self.ui.ComboBox(self.prefix + "['page']", PAGES, '工作页面', default='overview', updateGUI=True)
            self.ui.Button('检查前置条件', self.actions.check, updateGUI=True)
            self.ui.Button('刷新', lambda: None, updateGUI=True)
        if self.settings['message']:
            self.label(self.settings['message'])
        if pending_inputs(self.root) and self.settings['page'] != 'review':
            self.nav('有待确认的 TGLF 输入 · 查看差异', 'review')
        getattr(self, 'render_' + self.settings['page'])()

    def render_overview(self):
        s = summary(self.root)
        self.ui.Separator('1  Transfer tool · 输入准备')
        self.label('可用文件：{}；TGLF 剖面：{}。'.format(s['transfer_inputs'], '已载入' if s['profiles'] else '未载入'))
        with self.ui.same_row():
            self.nav('导入 / 转换 / 传递输入', 'transfer')
            self.nav('批量导入 input.gacode', 'multi')
        self.ui.Separator('2  CGYRO / TGLF · 计算任务')
        cg_issues = cgyro_input_issues(self.root)
        self.label('CGYRO：' + ('；'.join(cg_issues) if cg_issues else 'Transfer 输入已准备并传递'))
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
        self.label('CGYRO：先完成 Transfer 输入准备，再验证并传递。上游输入变化后需要重新传递。\n'
                   '已有完整 input.cgyro 也从 Transfer tool 载入并验证。\n'
                   'TGLF 多剖面：导入 input.gacode → 生成局部输入 → 计算 → 结果对比。')

    def render_transfer(self):
        self.ui.Tab('导入与转换')
        self.compound(('Transfer_tool', 'GUIS', 'transfer'))
        self.ui.Tab('传递输入')
        sources = transfer_sources(self.root)
        if sources:
            if self.settings['transfer_source'] not in sources.values():
                self.settings['transfer_source'] = next(iter(sources.values()))
            self.ui.ComboBox(self.prefix + "['transfer_source']", sources, '选择输入 / 生成结果', updateGUI=True)
            self.label('按文件类型选择目标。验证通过才完成传递；目标原输入会保存在输入历史中。')
            with self.ui.same_row():
                self.ui.Button('验证并送入 CGYRO', lambda: self.actions.handoff('cgyro'), updateGUI=True)
                self.ui.Button('验证并送入 TGLF 单文件', lambda: self.actions.handoff('tglf'), updateGUI=True)
            with self.ui.same_row():
                self.ui.Button('送入 TGLF 剖面流程', lambda: self.actions.handoff('profiles'), updateGUI=True)
                self.ui.Button('设为 Transfer 当前剖面', lambda: self.actions.handoff('transfer'), updateGUI=True)
        else:
            self.label('先载入输入，或运行 profiles_gen 生成文件。缺少输入时无法传递到计算模块。')
        self.ui.Tab('生成与高级工具')
        self.label('Transfer 的 TGYRO 生成步骤使用自己的 input.tglf 与 input.tgyro。先载入种子输入；已有 TGLF 输入时会先比较并询问是否替换。')
        for kind in ('tglf', 'tgyro'):
            self.ui.FilePicker(self.prefix + "['transfer_" + kind + "_file']", 'Transfer input.' + kind, default='',
                postcommand=lambda location=None, kind=kind: self.actions.import_transfer_seed(kind), updateGUI=True)
        self.run_controls('transfer')
        with self.ui.same_row():
            self.task('PROFILES_GEN / 离子设置', MODULES['profiles'] + ('GUIS', 'standaloneGUI'))
            self.task('TGYRO 完整设置', MODULES['tgyro'] + ('GUIS', 'TGYROgui'))
        self.label('生成的 input.cgyro_N / input.tglf_N 可在“传递输入”中逐个选择。')

    def render_cgyro(self):
        node = read(self.root, MODULES['cgyro'])
        if node is None:
            self.label('工程缺少 CGYRO_scan 模块。')
            return
        base = MODULES['cgyro'] + ('SETTINGS',)
        self.ui.Tab('输入与扫描')
        self.label('前置状态：' + ('；'.join(cgyro_input_issues(self.root)) or 'Transfer 输入已验证并传递'))
        with self.ui.same_row():
            self.nav('回到 Transfer 输入准备', 'transfer')
        self.ui.FilePicker(self.prefix + "['cgyro_file']", '载入已有 input.cgyro 到 Transfer tool', default='',
                           postcommand=lambda location=None: self.actions.import_input('cgyro'), updateGUI=True)
        self.ui.Entry(location(base + ('EXPERIMENT', 'runid')), '运行名称')
        with self.ui.same_row():
            self.ui.Entry(location(base + ('PHYSICS', 'nr')), '半径标识 nr')
            self.ui.Entry(location(base + ('PHYSICS', 'mass')), '案例标签 mass')
        self.label('nr 与 mass 用于结果分组；实际物种以输入为准。此入口执行线性扫描。')
        self.ui.ComboBox(location(base + ('SETUP', 'idimrun')), {'一维扫描': 1, '二维扫描': 2}, '扫描维数', updateGUI=True)
        self.ui.Entry(location(base + ('PHYSICS', 'kyarr')), 'ky 列表', help='例如 [0.1, 0.2, 0.3]')
        dim = node['SETTINGS']['SETUP']['idimrun']
        keys = [('1d', 'Para', '扫描参数'), ('1d', 'Range', '参数值列表')] if dim == 1 else [
            ('2d', 'Para_x', '参数 X'), ('2d', 'Range_x', 'X 值列表'), ('2d', 'Para_y', '参数 Y'), ('2d', 'Range_y', 'Y 值列表')]
        for group, key, label in keys:
            self.ui.Entry(location(base + ('PHYSICS', group, key)), label)
        self.ui.ComboBox(location(base + ('PHYSICS', 'restart_mode')), {'新计算': 0, '从匹配结果重启': 1}, '运行方式')
        self.ui.Tab('运行与收集')
        self.run_controls('cgyro')
        self.ui.CheckBox(location(base + ('SETUP', 'idownsync')), '扫描返回后收集结果')
        self.nav('进入统一绘图页', 'plots')

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
            self.label('没有待确认的输入。可在 Transfer tool 选择转换结果并传入 TGLF。')
            self.nav('返回 Transfer tool', 'transfer')
        for key, record in pending.items():
            self.ui.Separator(record['title'])
            target = 'Transfer tool 的 TGLF 种子输入' if record.get('destination', None) == 'transfer' else 'TGLF 当前单文件输入'
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
            self.label('选择覆盖后，原输入及其对应结果均保存在 Project → PROJECT_STATE → activity。')

    def required_issues(self, name, paths):
        node = module(self.root, name)
        pending = ['请先确认 Transfer tool 的 TGLF 输入'] if name == 'transfer' and pending_inputs(self.root, 'transfer') else []
        return pending + runtime_issues(self.root, name) + ['缺少 ' + '/'.join(path) for path in paths if read(node, path) is None]

    def run_controls(self, name):
        if read(self.root, MODULES[name]) is None:
            self.label('缺少 ' + LABELS[name])
            return
        self.ui.Button('设置 ' + LABELS[name] + ' 运行环境', lambda: self.select_runtime(name), updateGUI=True)
        if name == 'cgyro':
            issues = cgyro_input_issues(self.root) + runtime_issues(self.root, name)
            self.label('运行条件：' + ('；'.join(issues) or '输入已传递，基础配置已填写'))
            with self.ui.same_row():
                self.guarded('仅生成输入', lambda: self.actions.run_cgyro(prepare=True), issues)
                self.guarded('运行配置的扫描', self.actions.run_cgyro, issues)
                self.guarded('收集当前结果', self.actions.collect, collect_issues(self.root))
        elif name == 'transfer':
            for script, label, required in [
                ('tgyro_tglf.py', '运行 TGYRO', (('INPUTS', 'input.gacode'), ('INPUTS', 'input.tglf'), ('INPUTS', 'input.tgyro'))),
                ('profiles_gen4input.py', '生成各半径局部输入', (('INPUTS', 'input.gacode'), ('OUTPUTS', 'TGYRO')))]:
                issues = self.required_issues(name, required)
                self.guarded(label, lambda script=script, required=required: self.actions.run(name, script, required), issues)
                if issues:
                    self.label(label + '需要：' + '；'.join(issues))
        else:
            self.label('配置检查：' + ('；'.join(runtime_issues(self.root, name)) or '基础字段已填写；目标程序与资源尚未验证'))

    def select_runtime(self, name):
        self.settings.update(dict(runtime_module=name, page='run'))

    def render_run(self):
        self.ui.Tab('环境设置')
        self.ui.ComboBox(self.prefix + "['runtime_module']", {LABELS[key]: key for key in MODULES}, '配置模块', updateGUI=True)
        name = self.settings['runtime_module']
        node = read(self.root, MODULES[name])
        if node is None:
            self.label('工程缺少此模块。')
        else:
            self.environment(name, node)
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
        self.label('这里显示 Project 保存的状态。不会在打开页面时轮询或提交任务。')
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
        self.label('完整历史在 Project → PROJECT_STATE 中；输入历史和旧结果随工程保存。')

    def environment(self, name, node):
        base = MODULES[name] + ('SETTINGS',)
        remote = node['SETTINGS']['REMOTE_SETUP']
        picker = text_value(remote, 'serverPicker')
        choices = dict.fromkeys(['localhost'] + self.servers + [key for key in remote.keys() if isinstance(remote[key], dict)])
        if picker:
            choices[picker] = None
        self.ui.ComboBox(location(base + ('REMOTE_SETUP', 'serverPicker')), list(choices), 'OMFIT 服务器', state='normal', updateGUI=True)
        with self.ui.same_row():
            self.ui.Button('同步 OMFIT 连接配置', lambda: self.actions.sync_endpoint(name), updateGUI=True)
            if self.configure:
                self.ui.Button('OMFIT 模块设置', lambda: self.configure(node), updateGUI=True)
        for key, label in [('server', '实际服务器'), ('tunnel', '隧道'), ('workDir', '远程工作目录')]:
            self.ui.Entry(location(base + ('REMOTE_SETUP', key)), label)
        if name == 'cgyro':
            cfg = remote.get(picker, None)
            if isinstance(cfg, dict):
                self.label('以下为 CGYRO 提交器实际使用的配置。')
                path = base + ('REMOTE_SETUP', picker)
                for key, label in [('server', '该配置服务器'), ('workDir', '该配置工作目录')]:
                    self.ui.Entry(location(path + (key,)), label, default='')
                self.ui.ComboBox(location(path + ('scheduler',)), ['local', 'slurm', 'pbs'], '调度器', default='', updateGUI=True)
                self.ui.Entry(location(path + ('environment',)), '环境初始化', default='', multiline=True)
                self.ui.Entry(location(path + ('executable',)), 'CGYRO 命令', default='', multiline=True)
                if text_value(cfg, 'scheduler') in ('slurm', 'pbs'):
                    keys = [('queue', '队列 / 分区', ''), ('w', '时限', ''), ('nodes', '节点数', 1)]
                    keys += [('ntasks_per_node', '每节点 MPI 数', 1), ('array_parallel', '同时运行的扫描点', 1)] if cfg['scheduler'] == 'slurm' else [('ppn', '每节点核数', 1)]
                    for key, label, default in keys:
                        self.ui.Entry(location(path + (key,)), label, default=default)
            else:
                self.label('选择服务器后点击“同步 OMFIT 连接配置”，再填写命令和资源。')
        else:
            command = text_value(node['SETTINGS']['SETUP'], 'executable')
            self.label('当前命令：\n' + (command or '未解析 / 未设置'))
            if self.settings.get('command_module', None) != name:
                self.settings.update(dict(command_module=name, command_draft=command))
            self.ui.Entry(self.prefix + "['command_draft']", '编辑执行命令', default='', multiline=True)
            self.ui.Button('保存为手动命令', lambda: self.actions.save_command(name), updateGUI=True)
            if name == 'transfer':
                self.label('Transfer 此处保存环境初始化脚本，具体程序由运行步骤追加。')
                for key, label in [('num_nodes', '节点数'), ('num_cores', '每节点核数'), ('p_tgyro', 'TGYRO 半径数')]:
                    self.ui.Entry(location(base + ('SETUP', key)), label)
        self.label('检查结果：' + ('；'.join(runtime_issues(self.root, name)) or '基础字段已填写；未连接计算端验证'))

    def render_plots(self):
        self.label('选择已有结果后绘图。支持 CGYRO 与 TGLF 的同模型和跨模型对比。')
        with self.ui.same_row():
            self.nav('多 input.gacode 结果对比', 'multi')
            self.task('TGYRO 结果绘图', MODULES['tgyro'] + ('GUIS', 'Plotgui'))
        self.compound(('GUIS', 'CGYRO_vs_TGLF'))

    def render_templates(self):
        self.label('通过 GitHub 分发代码与设置。更新时可保留计算结果，或使用模板提供的示例。')
        self.label('模板库：https://github.com/Liu-s-CGYRO-project/CGYRO_TGLF_scan')
        self.guarded('打开 OMFIT 模板管理器', self.open_templates or (lambda: None),
                     [] if self.open_templates else ['当前工程未载入 OMFITtemplates'])
        self.label('个人服务器和路径可在更新时保留；计算记录和输入历史不进入代码模板。')
