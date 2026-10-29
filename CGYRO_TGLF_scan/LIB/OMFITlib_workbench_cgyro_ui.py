"""CGYRO page rendering. Host: ProjectUI actions/root/settings/ui/prefix and common view helpers.

Public methods remain inherited by ProjectUI for saved GUIs and callbacks.
Keep OMFITlib imports at module scope: native GUI execution clears its import hook.
"""
from builtins import ValueError, any, dict, float, getattr, int, isinstance, len, list, next, range, sorted, str, zip
from collections import OrderedDict
import math
import tkinter as tk
from tkinter import messagebox, ttk
from OMFITlib_workbench_catalog import SCAN_TABS as CGYRO_SCAN_TABS
from OMFITlib_cgyro_results import ResultBrowser
from OMFITlib_cgyro_present import run_caption, collection_caption
from OMFITlib_cgyro_queue import queue_records, queue_summary
from OMFITlib_cgyro_parameters import COMMON as CGYRO_COMMON, FIELDS as CGYRO_FIELDS, GROUPS as CGYRO_GROUPS, RUN_CONTROL_PARAMETERS, initialize_parameters, managed_parameter, numeric_source, parameter_catalog, scan_parameter_names
from OMFITlib_cgyro_scan_values import AXIS_KEYS, KY_MODES, VALUE_MODES, ky_values
from OMFITlib_cgyro_parameter_help import parameter_help
from OMFITlib_project import ION_CASES, MODULES, cgyro_ion_mode, cgyro_plan_issues, cgyro_plan_summary, collect_issues, location, read, runtime_issues, sync_cgyro_choices, sync_cgyro_ion_cases, sync_run_issues
from OMFITlib_cgyro_run_state import submission_pending
from OMFITlib_cgyro_radius_cleanup import preview_radius, radius_choices
from OMFITlib_cgyro_task_manager import TaskManager, confirm_scope
from OMFITlib_gui_deferred import TabPages, deferred_section
from OMFITlib_gui_controls import ParameterList, checkbox
from OMFITlib_cgyro_convergence import (BASELINE, DIRECTIONS, CONTENTS as SCAN_CONTENTS,
    active as convergence_active, initialize as initialize_convergence)

CGYRO_MAIN_TABS = ('input', 'parameters', 'results')


class CgyroPage:
    """Page mixin; state belongs to the host, never to a module singleton."""
    def render_cgyro(self):
        node = read(self.root, MODULES['cgyro'])
        if node is None:
            self.label('工程缺少 CGYRO_scan 模块。')
            return
        def render(page):
            if page == 'input':
                self.compound(('GUIS', 'CGYRO_controls'), workbench=self)
                self.show_message(first_line=True)
            elif page == 'parameters':
                rows = sync_cgyro_choices(self.root, self.settings, self.actions.factory)
                self.render_cgyro_parameters(node, rows)
            elif self.settings.get('cgyro_main_tab', 'input') == 'results':
                self.render_cgyro_results(node)
        self.cgyro_main_pages = TabPages(self.ui, OrderedDict(zip(
            CGYRO_MAIN_TABS, ('输入与扫描', '计算参数', '结果与记录'))),
            self.settings, 'cgyro_main_tab', render, action=True)
        self.cgyro_main_notebook = self.cgyro_main_pages.notebook
        self.cgyro_results_section = self.cgyro_main_pages.sections['results']

    def cgyro_main_tab_changed(self, event):
        self.cgyro_main_pages.changed(event)

    def render_cgyro_results(self, node):
        """Results and task controls, invoked only for the visible outer tab."""
        self.render_cgyro_recovery(node)
        manifest = node.get('RUN_MANIFEST', {})
        queued = queue_records(node)
        if queued:
            self.label(queue_summary(node))
            for _, entry in queued[:8]:
                row = entry['manifest']
                self.label(run_caption(row) + '；收集：' + collection_caption(row))
            if len(queued) > 8:
                self.label('其余 {} 个案例的记录保存在 RUN_HISTORY。'.format(len(queued) - 8))
        elif manifest:
            self.label(run_caption(manifest))
            self.label('收集：' + collection_caption(manifest))
        if manifest or queued:
            if submission_pending(manifest) or any(submission_pending(entry['manifest']) for _, entry in queued):
                self.label('提交待确认，请先同步作业状态。')
            with self.ui.same_row():
                self.guarded('同步作业状态', self.actions.sync_cgyro_run, sync_run_issues(self.root), refresh_tree=False)
                self.guarded('重新收集未归档结果', self.actions.collect, collect_issues(self.root),
                             help='只读取、归档已有输出；运行中的案例提示后跳过。需要补算时，进入下方“选择点续算”。')
        ResultBrowser(self.root, self.ui, continue_callback=self.actions.continue_cgyro,
            on_continued=getattr(self.ui, 'refresh_callback', lambda **kwargs: None)(scope='section')).render(title=False)
        self.render_cgyro_cleanup(node)
        self.nav('对比绘图（可选）', 'plots')

    def render_cgyro_cleanup(self, node):
        section = deferred_section(self.ui, lambda: self._render_cgyro_cleanup(node), local=True, container=True)
        if section is None:
            return self._render_cgyro_cleanup(node)
        section.show()

    def _render_cgyro_cleanup(self, node):
        """Do not enumerate archives on every ordinary control refresh."""
        changed = self.cgyro_tasks_refresh()
        self.ui.Button('任务管理 / 删除任务…',
                       lambda: self.open_cgyro_task_manager(changed), updateGUI=False, refresh_tree=False)
        self.settings.setdefault('cgyro_cleanup_open', False)
        self.settings.setdefault('cgyro_cleanup_radius', '')
        self.ui.Button('删除指定半径…', lambda: self.settings.__setitem__(
            'cgyro_cleanup_open', not self.settings['cgyro_cleanup_open']),
                       updateGUI=True, refresh_scope='section', refresh_tree=False)
        if not self.settings['cgyro_cleanup_open']:
            return
        options = radius_choices(node)
        # Native OMFIT takes (location, options, lbl), not a choices keyword.
        self.ui.ComboBox(self.prefix + "['cgyro_cleanup_radius']", [''] + list(options),
                         '删除范围', updateGUI=True, refresh_tree=False)
        self.ui.Button('删除该半径的记录和结果', self.confirm_cgyro_radius_cleanup, updateGUI=True,
                       state='normal' if self.settings['cgyro_cleanup_radius'] in options else 'disabled')

    def confirm_cgyro_radius_cleanup(self):
        node = read(self.root, MODULES['cgyro'])
        choice = self.settings.get('cgyro_cleanup_radius', '')
        options = radius_choices(node)
        if choice not in options:
            raise ValueError('请先选择需要删除的运行名和半径。')
        report = preview_radius(node, **options[choice])
        parent = getattr(self.ui, '_owner', None)
        if not isinstance(parent, tk.Misc):
            parent = getattr(self.ui, '_aux', {}).get('parentGUI', None)
        prompt = ('删除 {} 的任务记录、冻结输入和本工程内归档结果。\n'
                  '作业号：{}\n归档分支：{}\n\n'
                  '其他半径保留。远端作业和文件保留。此操作无法撤销。').format(
                      choice, ', '.join(report['jobs']) or '无', len(report['archives']))
        challenge = 'DELETE RADIUS ' + report['revision'][:8].upper()
        if confirm_scope(parent, prompt, challenge) == challenge:
            self.actions.remove_cgyro_radius(**options[choice], expected=report)
            self.settings['cgyro_cleanup_radius'] = ''
            self.settings['cgyro_cleanup_open'] = False

    def cgyro_tasks_refresh(self):
        """Task deletion affects the current page even after its dialog outlives a tab.

        Prefer the mounted result tab. The dialog can outlive that tab/window's
        body, so fall back to the current page after navigation or native reload.
        """
        parent, registry = getattr(self.ui, '_owner', None), getattr(self.ui, '_GUIs', None)
        if not isinstance(parent, tk.Misc) or not isinstance(registry, dict):
            return self.ui.refresh_callback(scope='page')
        key = str(parent.winfo_toplevel())
        section = getattr(self.ui, '_aux', {}).get('parentGUI', None)
        while isinstance(section, tk.Misc) and getattr(section, '_cgyro_action_refresh', None) is None:
            section = section.master
        def changed():
            gui = registry.get(key, None)
            if gui is not None:
                target = section if (isinstance(section, tk.Misc) and section.winfo_exists()
                                     and section.winfo_ismapped()) else gui.parentGUI
                self.ui.UpdateGUI(top=target, refresh_scope='page')
        return changed

    def open_cgyro_task_manager(self, on_changed=None):
        # _aux is process-global and may belong to a different settings GUI
        # by the time this button is clicked. The adapter captured our owner.
        parent = getattr(self.ui, '_owner', None)
        if not isinstance(parent, tk.Misc):
            parent = getattr(self.ui, '_aux', {}).get('parentGUI', None)
        if not isinstance(parent, tk.Misc):
            raise ValueError('任务管理需要在 OMFIT 图形界面中打开。')
        top = parent.winfo_toplevel()
        existing = getattr(top, '_cgyro_task_manager', None)
        if existing is not None and existing.window.winfo_exists():
            # The dialog survives tab rebuilding; reopening adopts this view.
            if on_changed is not None:
                existing.on_changed = on_changed
            existing.window.lift()
            return
        top._cgyro_task_manager = TaskManager(top, read(self.root, MODULES['cgyro']),
            self.actions.remove_cgyro_tasks, self.actions.factory,
            on_changed=on_changed if on_changed is not None else self.ui.UpdateGUI)

    def render_cgyro_recovery(self, node):
        section = deferred_section(self.ui, lambda: self._render_cgyro_recovery(node), local=True, container=True)
        if section is None:
            return self._render_cgyro_recovery(node)
        section.show()

    def _render_cgyro_recovery(self, node):
        """Available even in an empty reopened project after a desktop timeout."""
        self.settings.setdefault('cgyro_recovery_job', '')
        self.settings.setdefault('cgyro_recovery_manifest', '')
        self.settings.setdefault('cgyro_recovery_advanced', False)
        remote = node['SETTINGS'].get('REMOTE_SETUP', {})
        self.ui.Separator('恢复已提交的作业')
        self.label('服务器：' + str(remote.get('serverPicker', '') or '请先配置运行服务器'))
        with self.ui.same_row():
            self.ui.Entry(self.prefix + "['cgyro_recovery_job']", '主作业号', width=14,
                          updateGUI=False, refresh_tree=False)
            self.ui.Button('按作业号恢复', self.actions.recover_cgyro_job, updateGUI=True)
        self.ui.CheckBox(self.prefix + "['cgyro_recovery_advanced']", '指定旧清单位置（可选）',
                         updateGUI=True, refresh_tree=False)
        if self.settings['cgyro_recovery_advanced']:
            self.ui.Entry(self.prefix + "['cgyro_recovery_manifest']", '服务器上的 manifest.json',
                          width=50, updateGUI=False, refresh_tree=False,
                          help='通常无需填写；自动查找失败时使用原 OMFIT 暂存目录中的清单绝对路径。')
        self.label('按作业号接回任务；本次同步和收集只处理该作业。')

    def render_cgyro_scan_tabs(self):
        node = read(self.root, MODULES['cgyro'])
        self.cgyro_rows = []
        if node is None:
            self.label('工程缺少 CGYRO_scan 模块。')
            return
        def render(page):
            if page == 'input':
                self.cgyro_rows = self.render_cgyro_input()
            elif page == 'settings':
                self.cgyro_rows = sync_cgyro_choices(self.root, self.settings, self.actions.factory)
                self.render_cgyro_scan_settings(node, self.cgyro_rows)
            else:
                self.render_cgyro_run(node)
        self.cgyro_scan_pages = TabPages(self.ui, CGYRO_SCAN_TABS, self.settings, 'cgyro_scan_page', render)
        self.cgyro_scan_notebook = self.cgyro_scan_pages.notebook

    def select_cgyro_scan_page(self, page):
        self.cgyro_scan_pages.select(page)

    def cgyro_scan_page_changed(self, event):
        self.cgyro_scan_pages.changed(event)

    def render_cgyro_input(self):
        self.ui.ComboBox(self.prefix + "['cgyro_source_mode']", OrderedDict([
            ('Transfer_tool 半径输入', 'generated'), ('Transfer_tool 批量方案', 'schemes'), ('导入 input.cgyro', 'imported'),
            ('CGYRO 当前输入', 'current')]), '输入来源', state='readonly', updateGUI=True, refresh_tree=False)
        mode = self.settings['cgyro_source_mode']
        if mode == 'imported':
            self.ui.FilePicker(self.prefix + "['cgyro_file']", 'input.cgyro 文件', default='',
                transferRemoteFile=None, postcommand=lambda location=None: self.actions.import_input('cgyro'), updateGUI=True)
            source = self.settings.get('cgyro_import_source', {})
            if source.get('path', ''):
                self.label('已载入：' + str(source['path']))
        elif mode == 'generated':
            self.nav('生成 / 更换半径输入', 'transfer')
        elif mode == 'schemes':
            self.nav('生成 / 更换转换方案', 'transfer', transfer_tab='schemes')
        rows = sync_cgyro_choices(self.root, self.settings, self.actions.factory)
        self.ui.Separator('半径与主离子')
        if rows:
            if len(rows) > 1:
                with self.ui.same_row():
                    self.ui.Button('全部半径', self.actions.select_cgyro_radii,
                                   updateGUI=True, refresh_scope='section', refresh_tree=False)
                    self.ui.Button('清空选择', lambda: self.actions.select_cgyro_radii(False),
                                   updateGUI=True, refresh_scope='section', refresh_tree=False)
            for offset in range(0, len(rows), 2):
                with self.ui.same_row():
                    for row in rows[offset:offset + 2]:
                        caption = 'nr={}'.format(row['nr'])
                        if row['rho'] is not None:
                            caption += ' · rho={:g}'.format(row['rho'])
                        if row.get('scheme', ''):
                            caption = row['scheme_label'] + ' · ' + caption
                        checkbox(self.ui, self.prefix + "['cgyro_radii'][{!r}]".format(row['key']),
                                 self.settings['cgyro_radii'], row['key'], caption, updateGUI=True, refresh_tree=False)
        else:
            self.label('尚无输入，请生成半径输入或导入 input.cgyro。')
        sync_cgyro_ion_cases(self.settings, self.actions.factory)
        if self.settings.get('cgyro_ion_mode', None) not in ('original', 'hdt', 'custom'):
            self.settings['cgyro_ion_mode'] = cgyro_ion_mode(self.settings)
        self.ui.ComboBox(self.prefix + "['cgyro_ion_mode']", OrderedDict([
            ('保持原始粒子', 'original'), ('H / D / T 对比', 'hdt'), ('自选方案', 'custom')]),
            '主离子方案', state='readonly', updateGUI=True, refresh_tree=False, postcommand=self.actions.set_cgyro_ions)
        if self.settings['cgyro_ion_mode'] == 'custom':
            cases = list(ION_CASES.items())
            for offset in range(0, len(cases), 2):
                with self.ui.same_row():
                    for key, caption in cases[offset:offset + 2]:
                        checkbox(self.ui, self.prefix + "['cgyro_ion_cases'][{!r}]".format(key),
                                 self.settings['cgyro_ion_cases'], key, caption, updateGUI=True, refresh_tree=False)
        if any(self.settings['cgyro_ion_cases'].get(key, False) for key in ('H', 'D', 'T')):
            self.label('H / D / T：多个 Z=1 主离子先合并为一个，再分别设置质量。')
        return rows

    def render_cgyro_scan_settings(self, node, rows):
        base = MODULES['cgyro'] + ('SETTINGS',)
        physics = node['SETTINGS']['PHYSICS']
        if self.settings.get('cgyro_source_mode', '') == 'schemes':
            self.label('结果分别保存为“结果名称__transfer_方案”。所有方案共用下方扫描设置和计算参数。')
        self.settings['cgyro_scan_content'] = 'convergence' if convergence_active(physics) else int(node['SETTINGS']['SETUP']['idimrun'])
        with self.ui.same_row():
            self.scan_field(self.ui.Entry(location(base + ('EXPERIMENT', 'runid')), '结果名称',
                                          width=14, updateGUI=False, refresh_tree=False), 14)
            self.scan_field(self.ui.ComboBox(self.prefix + "['cgyro_scan_content']", SCAN_CONTENTS,
                '扫描内容', state='readonly', width=18, updateGUI=True, refresh_tree=False,
                postcommand=self.actions.select_cgyro_scan_content), 18)
        self.ui.Separator('ky 取值')
        ky_spec = self.scan_value_spec(physics, 'ky_spec', physics.get('kyarr', []))
        ky_prefix = location(base + ('PHYSICS', 'ky_spec'))
        self.scan_field(self.ui.ComboBox(ky_prefix + "['mode']", KY_MODES, '取值方式', state='readonly',
            width=14, updateGUI=True, refresh_tree=False, help='列表可直接填写 np.linspace(0.1, 1.0, 10)、np.arange(0.1, 1.01, 0.1)'
                ' 或 np.logspace(-2, 0, 9)。\n线性 / 对数范围按起点、终点和点数生成。ky 必须大于 0。'), 14)
        self.scan_value_fields(ky_spec, ky_prefix, location(base + ('PHYSICS', 'kyarr')), 'ky 列表 / 表达式')
        try:
            values = ky_values(physics)
            self.label('ky 预览：' + ', '.join('{:g}'.format(value) for value in values[:8]) +
                       (' …（共 {} 个）'.format(len(values)) if len(values) > 8 else ''))
        except (TypeError, ValueError, OverflowError) as exc:
            self.label(str(exc))
        dim = int(node['SETTINGS']['SETUP']['idimrun'])
        keys = AXIS_KEYS.get(dim, ())
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
        self.ui.Separator('constant 固定参数（可选）')
        physics.setdefault('constant_parameter', '')
        constants = OrderedDict([('不启用', '')])
        constants.update((name, name) for name in options if not managed_parameter(name) and name not in RUN_CONTROL_PARAMETERS)
        self.scan_field(self.ui.ComboBox(location(base + ('PHYSICS', 'constant_parameter')), constants,
            '固定参数', state='search', width=18, updateGUI=True, refresh_tree=False,
            help='每次扫描固定一个值。该值写入计算输入，并加入半径归档名称；'
                 '例如 nr=1_rho=0.33_BETAE_UNIT=0.0001。不能同时扫描这个参数。'), 18)
        constant = physics['constant_parameter']
        if constant:
            parameters = initialize_parameters(physics, source, self.actions.factory)
            if constant in parameters:
                self.scan_field(self.ui.Entry(location(base + ('PHYSICS', 'fixed_parameters', constant, 'value')),
                    constant + ' 固定值', width=18, updateGUI=False, refresh_tree=False,
                    help=parameter_help(constant)), 18)
        if convergence_active(physics):
            self.render_cgyro_convergence(node, rows, source)
            return
        group = str(dim) + 'd'
        if keys:
            node['SETTINGS']['PHYSICS'].setdefault(group, {})
        for index, (pkey, rkey) in enumerate(keys, 1):
            defaults = ('BETAE_UNIT', 'S', 'RLTS_1')
            cfg = physics[group]
            cfg.setdefault(pkey, defaults[index - 1])
            cfg.setdefault(rkey, [source.get(cfg[pkey], 0.0)])
            specs = cfg.setdefault('value_specs', self.actions.factory())
            spec = self.scan_value_spec(specs, rkey, cfg[rkey], str(cfg[pkey]), source)
            prefix = location(base + ('PHYSICS', group, 'value_specs', rkey))
            self.ui.Separator('参数轴 ' + str(index))
            with self.ui.same_row():
                self.scan_field(self.ui.ComboBox(location(base + ('PHYSICS', group, pkey)), options,
                    '参数', state='search', width=16, updateGUI=True, refresh_tree=False,
                    postcommand=lambda location=None, cfg=cfg, pkey=pkey, rkey=rkey, source=source:
                        self.cgyro_axis_parameter_changed(cfg, pkey, rkey, source),
                    help=parameter_help(str(cfg[pkey]))), 16)
                self.scan_field(self.ui.ComboBox(prefix + "['mode']", VALUE_MODES, '方式',
                    state='readonly', width=14, updateGUI=True, refresh_tree=False,
                    postcommand=lambda location=None, cfg=cfg, pkey=pkey, rkey=rkey, source=source:
                        self.cgyro_axis_mode_changed(cfg, pkey, rkey, source),
                    help='实际值范围直接生成数值；原值倍数分别乘以每个输入的原值；沿用输入只计算原值。'), 14)
            self.scan_value_fields(spec, prefix, location(base + ('PHYSICS', group, rkey)),
                postcommand=lambda location=None, cfg=cfg, pkey=pkey, rkey=rkey:
                    self.cgyro_axis_list_changed(cfg, pkey, rkey))
            linked = 2
            while pkey + str(linked) in cfg or rkey + str(linked) in cfg:
                self.scan_field(self.ui.ComboBox(location(base + ('PHYSICS', group, pkey + str(linked))), options,
                    '联动参数', state='search', width=18, default='', updateGUI=True, refresh_tree=False,
                    help=parameter_help(str(cfg.get(pkey + str(linked), '')))), 18)
                self.scan_field(self.ui.Entry(location(base + ('PHYSICS', group, rkey + str(linked))),
                    '同步取值', width=28, default=[], updateGUI=True, refresh_tree=False,
                    help='与参数 ' + str(index) + ' 的取值逐项对应。独立组合请使用多个参数轴。'), 28)
                linked += 1

    def render_cgyro_convergence(self, node, rows, source):
        physics = node['SETTINGS']['PHYSICS']
        config = initialize_convergence(physics, source, self.actions.factory)
        prefix = location(MODULES['cgyro'] + ('SETTINGS', 'PHYSICS', 'convergence'))
        self.ui.Separator('基准网格')
        self.label('每组只改变一个参数；其余参数沿用此基准和“计算参数”。修改后回车生效。')
        if rows:
            choices = OrderedDict(('nr={} · {}'.format(row['nr'], row['key']), row['key']) for row in rows)
            if self.settings.get('cgyro_parameter_reference', '') not in choices.values():
                self.settings['cgyro_parameter_reference'] = rows[0]['key']
            self.ui.ComboBox(self.prefix + "['cgyro_parameter_reference']", choices, '参考输入',
                             state='readonly', updateGUI=False, refresh_tree=False)
            self.ui.Button('从参考输入载入基准与取值', self.actions.load_cgyro_convergence_baseline,
                           updateGUI=True, refresh_scope='section', refresh_tree=False,
                           help='重新载入基准网格，并重新生成各检查方向的默认取值。其他计算参数保持当前设置。')
        names = list(BASELINE)
        for offset in range(0, len(names), 2):
            with self.ui.same_row():
                for name in names[offset:offset + 2]:
                    self.scan_field(self.ui.Entry(prefix + "['baseline'][{!r}]".format(name), name,
                        width=10, updateGUI=False, refresh_tree=False, help=parameter_help(name)), 10)
        self.ui.Separator('单变量检查方向')
        self.label('取值列表会包含本组基准；额外固定项可填字典，例如 E_MAX 组的 {\'N_ENERGY\': 64}。')
        for name, caption in DIRECTIONS.items():
            group = config['groups'][name]
            path = prefix + "['groups'][{!r}]".format(name)
            checkbox(self.ui, path + "['enabled']", group, 'enabled', name + ' · ' + caption,
                     updateGUI=False, refresh_tree=False)
            with self.ui.same_row():
                self.scan_field(self.ui.Entry(path + "['values']", '取值', width=24,
                    updateGUI=False, refresh_tree=False), 24)
                self.scan_field(self.ui.Entry(path + "['fixed']", '额外固定项', width=24,
                    updateGUI=False, refresh_tree=False), 24)
        self.label('时间上限、输出精度、节点和核数沿用现有配置。结果仍按参数坐标写入 RUN_DB。')
        checkbox(self.ui, prefix + "['reuse_results']", config, 'reuse_results',
                 '复用当前结果集内完整匹配的已完成结果', updateGUI=False, refresh_tree=False)
        self.label('复用只查所选半径/参数的轻量摘要；旧结果元数据不足时安排新计算，不自动读取文件补齐。')
        self.label('修改参数后重新预览；预览不提交作业。')
        self.ui.Button('预览收敛扫描计划', self.preview_cgyro_convergence,
                       updateGUI=False, refresh_tree=False)
        parent = getattr(self.ui, '_aux', {}).get('parentGUI', None)
        self.cgyro_convergence_preview = ttk.Frame(parent) if isinstance(parent, tk.Misc) else None
        if self.cgyro_convergence_preview is not None:
            self.cgyro_convergence_preview.pack(fill=tk.X)

    def preview_cgyro_convergence(self):
        """Explicit preview uses selected inputs and cached result summaries."""
        plan = self.actions.preview_cgyro_convergence()
        summary = '{} 个候选点：新提交 {}，复用 {}；{} 份扫描作业。'.format(
            plan['total_points'], plan['submit_points'], plan['reused_points'], plan['jobs'])
        lines = [summary]
        for group in plan['groups'][:24]:
            lines.append('nr={} · {} · {} {}：新 {}，复用 {}，共享基准/重复配置 {}；额外固定项 {}'.format(
                group['nr'], group['ion'], group['parameter'], group['values'], group['new_points'],
                group['reused_points'], group['shared'], group['fixed']))
        if len(plan['groups']) > 24:
            lines.append('其余 {} 份分组计入上方总数。'.format(len(plan['groups']) - 24))
        frame = getattr(self, 'cgyro_convergence_preview', None)
        if frame is None:
            self.label('\n'.join(lines))
            return plan
        for child in frame.winfo_children():
            child.destroy()
        for line in lines:
            ttk.Label(frame, text=line, wraplength=600, justify=tk.LEFT).pack(anchor=tk.W, pady=3)
        return plan

    def render_cgyro_run(self, node):
        problems = cgyro_plan_issues(self.root)
        if not problems:
            plan = cgyro_plan_summary(self.root)
            self.label(('{} 个半径/离子组合，至多 {} 份作业，共 {} 个候选点；复用后数量见“预览收敛扫描计划”。'.format(
                plan['cases'], plan['jobs'], plan['total_points'])) if plan.get('convergence', False) else
                '{} 个输入组合 × 每组 {} 点 = {} 个任务'.format(
                    plan['cases'], plan['points_per_case'], plan['total_points']))
        remote = node['SETTINGS'].get('REMOTE_SETUP', {})
        config = remote.get(str(remote.get('serverPicker', '') or ''), {})
        self.label('服务器：{}\n队列：{} · 每任务 {} 节点 × {} MPI/节点 × {} 线程/MPI'.format(
            remote.get('serverPicker', '未配置'), config.get('queue', '未配置'),
            config.get('nodes', '—'), config.get('ntasks_per_node', '—'),
            config.get('cpus_per_task', node['SETTINGS'].get('SETUP', {}).get('cpus_per_task', 1))))
        if config.get('scheduler', '') in ('slurm', 'pbs'):
            self.label('所有半径 / 离子先提交排队，再等待并收集；实际并行由队列资源决定。')
            if config.get('scheduler', '') == 'slurm':
                self.label('每案例并发上限 {} 点，H/D/T 三个案例可合计到三倍上限。'.format(config.get('array_parallel', '—')))
        issues = problems + runtime_issues(self.root, 'cgyro')
        if config.get('scheduler', '') in ('slurm', 'pbs'):
            self.ui.Entry(location(MODULES['cgyro'] + ('SETTINGS', 'SETUP', 'failed_point_retries')),
                          '失败点重试次数', default=2, width=8, refresh_tree=False,
                          help='0–3 次，默认 2。仅补跑可重试的失败点，成功点保留；取消、输入错误、积分报错、内存不足和超时不自动重算。')
        self.guarded('运行所选扫描', self.actions.run_cgyro, issues)
        self.nav('修改运行环境', 'run')
        if issues:
            self.label('需要：' + '；'.join(issues[:2]))

    def render_cgyro_parameters(self, node, rows):
        physics = node['SETTINGS']['PHYSICS']
        base = MODULES['cgyro'] + ('SETTINGS', 'PHYSICS')
        selected = [row for row in rows if self.settings['cgyro_radii'].get(row['key'], False)]
        available = selected or rows
        self.label('直接修改数值，回车生效；扫描轴的取值优先。')
        row, source, source_key = None, {}, ''
        if available:
            choices = OrderedDict(('nr={} · {}'.format(item['nr'], item['key']), item['key']) for item in available)
            if self.settings.get('cgyro_parameter_reference', '') not in choices.values():
                self.settings['cgyro_parameter_reference'] = available[0]['key']
            self.ui.ComboBox(self.prefix + "['cgyro_parameter_reference']", choices, '参考输入',
                             state='readonly', updateGUI=True, refresh_tree=False)
            row = next(item for item in available if item['key'] == self.settings['cgyro_parameter_reference'])
            source_key, source = row['key'], read(self.root, row['path'])
        else:
            self.label('可先设置常用参数；运行前需载入输入。')
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
        # Keep active, unavailable saved values visible until they are restored.
        for name, item in parameters.items():
            if name not in catalog and item.get('enabled', False):
                catalog[name] = dict(label='当前输入不支持', group='other', reference=None,
                                     kind='float', supported=False)
        # A one-time view migration clears old filters, without changing any
        # saved calculation values.
        if self.settings.get('cgyro_parameter_catalog_revision', 0) != 1:
            self.settings['cgyro_parameter_group'] = 'common'
            self.settings['cgyro_parameter_search'] = ''
            self.settings['cgyro_parameter_catalog_revision'] = 1
        scanned = (set(BASELINE) | {name for name, item in physics.get('convergence', {}).get('groups', {}).items()
                                    if item.get('enabled', False)}) if convergence_active(physics) else \
            scan_parameter_names(physics, int(node['SETTINGS']['SETUP']['idimrun']))
        self.ui.Button('全部沿用输入值', self.actions.inherit_cgyro_parameters,
                       updateGUI=True, refresh_scope='section', refresh_tree=False)
        filter_rows = [(name, spec['label'], spec['group'], name in CGYRO_COMMON)
                       for name, spec in catalog.items()]
        self.cgyro_parameter_list = ParameterList(self.ui, self.settings, 'cgyro_parameter_group',
            'cgyro_parameter_search', CGYRO_GROUPS, filter_rows,
            lambda names: self.cgyro_parameter_rows(names, base, catalog, parameters, source_values, scanned, source_key))
        section = deferred_section(self.ui, lambda: self.cgyro_parameter_options(node, row), local=True, container=True)
        if section is None:
            return self.cgyro_parameter_options(node, row)
        section.show()

    def cgyro_parameter_options(self, node, row):
        """Small dependent options must not reconstruct the parameter catalogue."""
        physics = node['SETTINGS']['PHYSICS']
        base = MODULES['cgyro'] + ('SETTINGS', 'PHYSICS')
        self.ui.Separator('时间缩放')
        checkbox(self.ui, location(base + ('scale_time_with_ky',)), physics, 'scale_time_with_ky',
                 '按 ky 缩放时间', updateGUI=True, refresh_tree=False)
        if physics['scale_time_with_ky']:
            self.label('ky > 1 时，步长与运行时长分别除以 ky。')
        self.ui.Separator('重启与源文件')
        self.ui.ComboBox(location(base + ('restart_mode',)), {'新计算': 0, '匹配结果重启': 1},
                         '运行方式', state='readonly', updateGUI=False, refresh_tree=False)
        checkbox(self.ui, self.prefix + "['cgyro_advanced']", self.settings, 'cgyro_advanced',
                 '直接编辑源 input.cgyro', updateGUI=True, refresh_tree=False)
        if self.settings['cgyro_advanced'] and row is not None:
            self.ui.EditASCIIobject(location(row['path']), '编辑参考输入', updateGUI=True)
        # Whole-scan validation belongs to Run/check/submit. Building every
        # radius/isotope input on each parameter edit makes typing expensive.

    def cgyro_parameter_rows(self, names, base, catalog, parameters, source_values, scanned, source_key):
        self.ui.Button('本页沿用输入值', lambda: self.actions.reset_cgyro_parameters(names, source_key),
                       updateGUI=True, refresh_scope='section', refresh_tree=False)
        for name in names:
            self.cgyro_parameter_row(base, name, catalog[name], parameters[name], source_values, scanned, source_key)

    def cgyro_parameter_row(self, base, name, spec, item, source_values, scanned, source_key):
        if name in scanned:
            self.label(name + (' · 由收敛扫描基准/取值设置' if convergence_active(
                read(self.root, MODULES['cgyro'] + ('SETTINGS', 'PHYSICS'), {})) else ' · 由扫描轴设置'))
            return
        if name == read(self.root, MODULES['cgyro'] + ('SETTINGS', 'PHYSICS', 'constant_parameter'), ''):
            self.label('{} · constant 固定值：{}（在扫描设置中修改）'.format(name, item['value']))
            return
        path = base + ('fixed_parameters', name)
        reference = ('输入值：{}'.format(source_values[name]) if name in source_values else
                     '文件未写入，显示参考值：{}；修改后才写入运行副本。'.format(spec['reference']))
        help_text = parameter_help(name, spec) + '\n\n' + reference
        help_text += '\n修改并回车后应用到所选输入；“沿用输入”取消覆盖，使用各输入自己的值。'
        with self.ui.same_row() as line:
            frame = getattr(line, 'frm_top', None)
            if isinstance(frame, tk.Misc):
                frame._cgyro_inline = True
            self.label(name + ' · ' + spec['label'])
            self.ui.Entry(location(path + ('value',)), '', width=14, updateGUI=False, refresh_tree=False,
                          state='normal' if spec.get('supported', True) else 'disabled', help=help_text,
                          postcommand=lambda location=None: self.actions.edit_cgyro_parameter(name))
            self.ui.Button('沿用输入', lambda: self.actions.reset_cgyro_parameters([name], source_key),
                           updateGUI=True, refresh_scope='section', refresh_tree=False)
