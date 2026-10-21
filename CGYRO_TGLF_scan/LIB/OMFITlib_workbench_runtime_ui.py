"""Runtime configuration page. Editing changes drafts; only explicit action callbacks apply or probe.

Public methods remain inherited by ProjectUI for saved GUIs and callbacks.
Keep OMFITlib imports at module scope: native GUI execution clears its import hook.
"""
from builtins import all, any, bool, callable, dict, isinstance, iter, len, list, next, str
from collections import OrderedDict
import tkinter as tk
from tkinter import ttk
from OMFITlib_workbench_catalog import STATUS
from OMFITlib_project_runtime import initialize_runtime, applied_runtime, shared_issues, validate_runtime
from OMFITlib_gacode_installations import PROGRAMS, choices as installation_choices, installation_issues
from OMFITlib_project import MODULES, collect_issues, location, read, text_value, sync_run_issues
from OMFITlib_cgyro_present import run_caption, collection_caption, record_details


class RuntimePage:
    """Page mixin; state belongs to the host, never to a module singleton."""
    def select_runtime(self, name):
        self.settings['page'] = 'run'

    def render_run(self):
        config = initialize_runtime(self.root, self.actions.factory)
        prefix = "root['SETTINGS']['GACODE_RUNTIME']"
        self.runtime_apply(config)
        self.ui.Tab('常用配置')
        self.environment(config, prefix)
        self.ui.Tab('安装路径')
        self.gacode_installations(config)
        self.ui.Tab('脚本与命令')
        self.runtime_commands(prefix)
        self.ui.Tab('运行记录')
        manifest = read(self.root, ('CGYRO_scan', 'RUN_MANIFEST'), {})
        self.ui.Separator('CGYRO 当前运行')
        self.label(run_caption(manifest) if manifest else '尚无运行记录。')
        if manifest:
            self.note('收集：' + collection_caption(manifest), record_details(manifest))
        self.guarded('同步 CGYRO 作业状态', self.actions.sync_cgyro_run, sync_run_issues(self.root))
        self.guarded('收集 CGYRO 当前结果', self.actions.collect, collect_issues(self.root),
                     help='读取并归档已有输出；不提交计算，也不等待仍在运行的案例。')
        self.ui.Separator('TGLF 多剖面运行')
        cases = self.root.get('TGLF_CASES', {})
        if not cases:
            self.label('尚无多剖面案例。')
        for case in cases.values():
            run = case.get('runs', {}).get(case.get('selected_run', None), {})
            self.label('{}：{}'.format(case.get('label', '未命名案例'), STATUS.get(run.get('status', None), run.get('status', '尚未运行'))))
        self.nav('选择记录 / 重试 / 查看错误', 'multi')
        self.label('此页显示工程中保存的运行状态。')
        self.ui.Separator('结果管理')
        self.ui.Button('清空全部结果…', self.clear_all_results, updateGUI=True)
        self.ui.Tab('操作历史')
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

    def runtime_section(self, caption):
        label = self.label(caption)
        label._cgyro_role = 'heading'

    def runtime_note(self, caption):
        label = self.label(caption)
        label._cgyro_role = 'muted'

    def runtime_field(self, control, caption, wide=False, short=False):
        """Mark native controls for aligned layout, retaining their callbacks."""
        control.master._cgyro_form = (control, caption, wide, short)
        return control

    def runtime_entry(self, path, caption, wide=False, short=False, **kwargs):
        return self.runtime_field(self.ui.Entry(path, caption, **kwargs), caption, wide, short)

    def runtime_choice(self, path, options, caption, wide=False, **kwargs):
        return self.runtime_field(self.ui.ComboBox(path, options, caption, **kwargs), caption, wide=wide)

    def environment(self, config, prefix):
        self.runtime_section('01  服务器与目录')
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
        self.runtime_choice(prefix + "['serverPicker']", choices,
                            '服务器配置', state='disabled' if draft is not None else 'readonly', updateGUI=True,
                            postcommand=lambda location=None: self.actions.sync_runtime_endpoint(replace_directory=True))
        server_issues = self.actions.runtime_server_issues()
        with self.ui.same_row():
            self.guarded('新增服务器', self.actions.begin_runtime_server,
                         ['请先保存或取消当前新增'] if draft is not None else
                         ([] if self.actions.register_server is not None else ['当前宿主未提供服务器登记入口']))
            self.guarded('读取连接信息', self.actions.sync_runtime_endpoint,
                         server_issues + (['请先保存或取消当前新增'] if draft is not None else []))
        if server_issues and draft is None:
            self.label('；'.join(server_issues))
        if draft is not None:
            self.runtime_note('新配置 · 地址格式：用户名@主机[:端口]')
            for key, label in [('serverPicker', '新配置名'), ('server', '服务器地址'),
                               ('tunnel', '隧道（可选）'), ('workDir', '工作根目录')]:
                self.runtime_field(self.server_text_entry(draft, key, label), label, wide=key == 'workDir')
            with self.ui.same_row():
                self.ui.Button('保存并选用', self.actions.register_runtime_endpoint, updateGUI=True)
                self.ui.Button('取消新增', self.actions.cancel_runtime_server, updateGUI=True)
        else:
            self.runtime_entry(prefix + "['server']", '服务器地址', updateGUI=True)
            self.runtime_entry(prefix + "['tunnel']", '隧道（可选）', updateGUI=True)
            self.runtime_entry(prefix + "['workDir']", '工作根目录', wide=True, updateGUI=True,
                               help='各程序在此目录下使用独立子目录。')
        self.runtime_section('02  程序版本')
        self.shared_gacode_install(config)
        detection = self.root.get('PROJECT_STATE', {}).get('gacode_detection', {})
        for program, (caption, _) in PROGRAMS.items():
            self.runtime_choice(prefix + "[{!r}]".format(program + '_install'),
                                installation_choices(config, detection, program), caption,
                                state='readonly', updateGUI=True)
        self.runtime_note('共用安装统一设置版本与脚本；各程序也可分别选择。')
        self.runtime_section('03  共用作业调度')
        self.runtime_choice(prefix + "['scheduler']", OrderedDict([('本机执行', 'local'), ('Slurm', 'slurm'), ('PBS', 'pbs')]),
                            '作业调度', wide=True, updateGUI=True)
        if config['scheduler'] != 'local':
            self.runtime_pair(prefix, (('queue', '队列 / 分区'), ('wall_time', '运行时限')))
        self.runtime_section('04  默认并行资源')
        self.runtime_pair(prefix, (('nodes', '节点数'), ('cores', '每节点 MPI 数')))
        self.runtime_pair(prefix, (('cpus_per_task', '每进程线程数'), ('array_parallel', 'CGYRO 并发点数')))

    def runtime_pair(self, prefix, fields):
        """Keep related native fields side by side, stacking in narrow windows."""
        with self.ui.same_row():
            for key, caption in fields:
                self.runtime_entry(prefix + "[{!r}]".format(key), caption,
                                   wide=True, width=12, updateGUI=True)

    def runtime_commands(self, prefix):
        self.runtime_section('共用环境脚本')
        self.runtime_note('点击“…”展开编辑，修改后应用到整个工程。')
        self.runtime_entry(prefix + "['environment']", '环境初始化', wide=True, multiline=True, updateGUI=True,
                           help='各程序选同一安装时，GACODE_ROOT 自动同步。分别选版时，各程序在加载平台环境前绑定所选路径，其余命令保留。')
        self.runtime_section('程序命令')
        for key, caption in [('cgyro_command', 'CGYRO'), ('tglf_command', 'TGLF'),
                             ('tgyro_command', 'TGYRO'), ('prepare_command', '多剖面输入生成')]:
            self.runtime_entry(prefix + "[{!r}]".format(key), caption, wide=True, multiline=True, updateGUI=True)
        self.runtime_note('{mpi}：总 MPI 数；{n_radii}：TGYRO 实际径向任务数。')
        transfer = read(self.root, MODULES['transfer'])
        if transfer is not None:
            self.runtime_entry(location(MODULES['transfer'] + ('SETTINGS', 'SETUP', 'p_tgyro')),
                               '转换半径数', short=True, updateGUI=True)
        if self.open_servers is not None:
            self.runtime_section('OMFIT 设置')
            self.ui.Button('个人服务器设置', self.open_servers, updateGUI=True)

    def runtime_apply(self, config):
        """One apply action outside the tabs, shared by every settings page."""
        draft = self.settings.get('server_draft', None)
        pending = applied_runtime(self.root) is None or bool(shared_issues(self.root))
        detection = self.root.get('PROJECT_STATE', {}).get('gacode_detection', {})
        issues = (validate_runtime(config) + installation_issues(config, detection)
                  + self.actions.runtime_server_issues(match_connection=True))
        if draft is not None:
            issues = ['请先保存或取消新增服务器']
        if self.settings.get('gacode_draft', None) is not None:
            issues = ['请先保存或取消 GACODE 安装编辑']
        if draft is not None:
            status = '服务器草稿未保存'
        elif self.settings.get('gacode_draft', None) is not None:
            status = '安装路径草稿未保存'
        elif pending:
            status = '修改未应用 · 请先完成配置' if issues else '修改未应用 · 点击蓝色按钮同步'
        else:
            status = '配置已同步'
        label = self.label(status)
        label._cgyro_role = 'pending' if pending else 'muted'
        button = self.ui.Button('应用到整个工程' if pending else '配置已同步',
                                lambda: self.apply_runtime_button(label, button), updateGUI=False,
                                state='disabled' if issues or not pending else 'normal', help='；'.join(issues))
        button._cgyro_role = 'pending' if pending else 'primary'
        if issues and draft is None:
            self.label('待填写：' + '；'.join(issues))

    def apply_runtime_button(self, label, button):
        """Paint progress before waiting; redraw only the owning GUI afterward."""
        if not isinstance(button, tk.Misc):
            return self.actions.apply_runtime()
        top = button.winfo_toplevel()
        registry = self.ui._GUIs
        gui = registry.get(str(top), None)
        def progress(message):
            if label.winfo_exists():
                label.configure(text=message)
                label.update_idletasks()
        button.configure(text='正在应用…')
        progress('正在准备运行配置…')
        try:
            return self.actions.apply_runtime(progress=progress)
        except Exception as exc:
            self.actions.report_error('应用配置', exc)
            raise
        finally:
            if top.winfo_exists() and gui is not None:
                def refresh():
                    if registry.get(str(top), None) is gui and top.winfo_exists():
                        self.ui.UpdateGUI(top=top)
                # Let the native button/error callbacks return before clearing
                # controls. Do not emit OMFIT's global <<update_GUI>> event.
                top.after_idle(refresh)

    def shared_gacode_install(self, config):
        installs = config['gacode_installs']
        selected = [str(config.get(program + '_install', '') or '') for program in PROGRAMS]
        name = selected[0] if selected and all(value == selected[0] for value in selected) else ''
        self.settings['gacode_selected'] = name if name in installs else ''
        options = OrderedDict([('各程序分别选择', '')])
        options.update(OrderedDict((str(key), key) for key in installs))
        editing = (self.settings.get('gacode_draft', None) is not None
                   or self.settings.get('server_draft', None) is not None)
        self.runtime_choice(self.prefix + "['gacode_selected']", options, '共用安装',
                            state='disabled' if editing else 'readonly', updateGUI=True,
                            postcommand=self.actions.select_gacode_install,
                            help='选择安装后，四个程序版本与环境脚本的 GACODE_ROOT 同步。分别选版时显示“各程序分别选择”。')

    def gacode_installations(self, config):
        self.runtime_section('检测安装')
        self.runtime_field(self.server_text_entry(config, 'gacode_scan_dir', '搜索目录'), '搜索目录', wide=True)
        detection = self.root.get('PROJECT_STATE', {}).get('gacode_detection', {})
        installs = config['gacode_installs']
        draft = self.settings.get('gacode_draft', None)
        server_draft = self.settings.get('server_draft', None) is not None
        with self.ui.same_row():
            self.guarded('自动检测', self.actions.detect_gacode,
                         ['请先保存或取消编辑'] if draft is not None or server_draft else [])
            self.guarded('新增路径', self.actions.begin_gacode_install,
                         ['请先保存或取消编辑'] if draft is not None else [])
        self.runtime_note('检测 Gacode* 文件夹中的程序；不启动计算。')
        self.runtime_section('选用安装')
        self.shared_gacode_install(config)
        self.runtime_note('选择后立即同步环境脚本，运行前点击“应用到整个工程”。')
        self.runtime_section('路径维护')
        if installs:
            options = OrderedDict((str(name), name) for name in installs)
            if self.settings.get('gacode_entry', '') not in installs:
                self.settings['gacode_entry'] = next(iter(installs))
            self.runtime_choice(self.prefix + "['gacode_entry']", options, '编辑对象',
                                state='disabled' if draft is not None else 'readonly', updateGUI=True)
            name = self.settings['gacode_entry']
            self.runtime_note(str(installs[name]))
            captions = installation_choices(config, detection)
            detail = next((caption for caption, value in captions.items() if value == name), '')
            if detail.startswith(str(name)):
                detail = detail[len(str(name)):].strip()
            if detail:
                self.runtime_note(detail)
            with self.ui.same_row():
                self.guarded('编辑路径', lambda: self.actions.begin_gacode_install(edit=True),
                             ['请先保存或取消编辑'] if draft is not None else [])
                used = any(config[program + '_install'] == name for program in PROGRAMS)
                self.guarded('移除路径', self.actions.remove_gacode_install,
                             ['请先更换使用此安装的程序'] if used else
                             (['请先保存或取消编辑'] if draft is not None else []))
        if draft is not None:
            self.runtime_section('编辑安装' if draft.get('original', '') else '新增安装')
            self.runtime_field(self.server_text_entry(draft, 'name', '安装名称'), '安装名称')
            self.runtime_field(self.server_text_entry(draft, 'path', '安装根目录'), '安装根目录', wide=True)
            with self.ui.same_row():
                self.ui.Button('保存路径', self.actions.save_gacode_install, updateGUI=True)
                self.ui.Button('取消编辑', self.actions.cancel_gacode_install, updateGUI=True)
        elif not installs:
            self.runtime_note('暂无安装路径，先自动检测或手动新增。')
        self.runtime_note('编辑对象用于维护路径；选用版本请用上方“共用安装”。')

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
