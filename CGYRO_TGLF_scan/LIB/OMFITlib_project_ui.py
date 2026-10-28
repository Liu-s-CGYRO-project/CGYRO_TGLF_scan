"""Workbench facade. Page mixins render controls; ProjectActions owns effects.

Keep this class and inherited method names stable for native/saved GUIs.
New pages enter through workbench_catalog; see MAINTAINER_GUIDE.md.
"""
from OMFITlib_result_cleanup import active_jobs, clear_results
from builtins import dict, isinstance, list, str
import tkinter as tk
from tkinter import messagebox, ttk
from OMFITlib_gui_layout import finish_gui_layout
from OMFITlib_gui_deferred import deferred_section
from OMFITlib_gui_controls import checkbox
from OMFITlib_gui_api import show_help, gui_view
from OMFITlib_tglf_workbench_ui import TGLFWorkbench
from OMFITlib_workbench_catalog import STATUS, render_page
from OMFITlib_transfer_workflow import generation_issues, initialize_generation
from OMFITlib_project import ERROR_NOTICE_SUFFIX, LABELS, MODULES, PAGES, cgyro_input_issues, module, pending_inputs, read, runtime_issues, summary

from OMFITlib_workbench_cgyro_ui import CgyroPage
from OMFITlib_workbench_runtime_ui import RuntimePage
from OMFITlib_workbench_transfer_ui import TransferPage
from OMFITlib_workbench_scan_ui import ScanControls


class ProjectUI(CgyroPage, RuntimePage, TransferPage, ScanControls):
    """Own shared view context; page mixins must not define __init__."""
    def __init__(self, actions, ui, configure=None, open_templates=None, servers=(), open_servers=None):
        self.actions, self.root, self.ui = actions, actions.root, ui
        self.settings = actions.settings
        self.configure, self.open_templates = configure, open_templates
        self.servers, self.open_servers = servers, open_servers
        self.panel_only = False
        self.compact = False
        self.prefix = "root['SETTINGS']['WORKBENCH']"
        self.page_content = self.page_picker = None

    def label(self, value):
        return self.ui.Label(value, align='left', wraplength=600 if self.compact else 840)

    def show_message(self, first_line=False):
        value = str(self.settings['message'] or '')
        if not value:
            return
        error = value.endswith(ERROR_NOTICE_SUFFIX)
        label = self.label(value.splitlines()[0][:200] if first_line or error else value)
        if value != '配置检查通过' and not error:
            return
        # Consume transient feedback so redraws and saved projects cannot pin it.
        # Full errors are retained in activity records and native OMFIT reports.
        self.settings['message'] = ''
        if not isinstance(label, tk.Misc):
            return
        row, top = label.master, label.winfo_toplevel()
        timer = [None]
        def dismiss():
            timer[0] = None
            if row.winfo_exists():
                row.destroy()
        def cancel(event):
            if event.widget is label and timer[0] is not None:
                try:
                    top.after_cancel(timer[0])
                except tk.TclError:
                    pass
                timer[0] = None
        timer[0] = top.after(5000 if error else 3000, dismiss)
        label.bind('<Destroy>', cancel, add='+')

    def nav(self, label, page, **changes):
        aux = getattr(self.ui, '_aux', {})
        parent = aux.get('parentGUI', None)
        if not isinstance(parent, tk.Misc):
            return self.ui.Button(label, lambda: self.select_page(page, **changes), updateGUI=False, refresh_tree=False)
        row = ttk.Frame(parent)
        packing = aux.get('packing', tk.TOP)
        row.pack(side=packing, expand=packing != tk.TOP, fill=tk.X, padx=5, pady=1)
        button = ttk.Button(row, text=label, command=lambda: self.select_page(page, **changes))
        button.pack(side=tk.LEFT, expand=True, fill=tk.X)
        return button

    def select_page(self, page, **changes):
        """Navigation changes view state, not the project data tree."""
        self.settings.update(changes)
        if self.panel_only:
            self.settings['cgyro_panel_page'] = page
            self.ui.UpdateGUI()
            return
        if page == self.settings['page'] and not changes:
            return
        self.actions.open_page(page)
        if self.page_content is None:
            self.ui.UpdateGUI()
            return
        selected = self.settings['page']
        for caption, key in PAGES.items():
            if key == selected:
                self.page_picker.set(caption)
                break
        self.page_content.refresh.request()

    def check_configuration(self):
        self.actions.check()
        self.refresh_page()

    def refresh_page(self):
        """Refresh the current work page without rerunning main.py or imports."""
        if self.page_content is not None:
            self.page_content.refresh.request()
        else:
            self.ui.UpdateGUI()

    def render_page_picker(self):
        parent = getattr(self.ui, '_aux', {}).get('parentGUI', None)
        if not isinstance(parent, tk.Misc):
            self.ui.ComboBox(self.prefix + "['page']", PAGES, '工作页面', default='overview', updateGUI=True)
            return
        # Native ComboBox always emits update_treeGUI and updateGUI reruns
        # main.py (including all LIB imports). A saved view selector needs
        # neither; real input/parameter controls retain native semantics.
        row = ttk.Frame(parent)
        row.pack(side=tk.TOP, fill=tk.X, padx=5, pady=1)
        ttk.Label(row, text='工作页面 = ').pack(side=tk.LEFT)
        picker = self.page_picker = ttk.Combobox(row, state='readonly', values=list(PAGES))
        picker.pack(side=tk.LEFT, expand=True, fill=tk.X)
        picker.current(list(PAGES.values()).index(self.settings['page']))
        picker.bind('<<ComboboxSelected>>', lambda event: self.select_page(PAGES[picker.get()]))
        ttk.Button(row, text='重置', command=lambda: self.select_page('overview')).pack(side=tk.LEFT)

    def render_selected_page(self):
        if isinstance(self.page_intro, tk.Misc):
            self.page_intro.configure(text='服务器 → 程序版本 → 计算资源' if self.settings['page'] == 'run'
                                      else '选择输入 → 设置参数 → 运行 → 查看结果')
        if self.settings['page'] not in ('cgyro', 'tglf'):
            self.show_message()
        render_page(self, self.settings['page'])

    def guarded(self, label, callback, issues, help='', refresh=True, refresh_tree=True):
        """Shared action button; disabled reasons are shown before usage notes."""
        explanation = '\n'.join(part for part in ('；'.join(issues), help) if part)
        return self.ui.Button(label, callback, updateGUI=refresh, state='disabled' if issues else 'normal',
                              help=explanation, refresh_tree=refresh_tree)

    def note(self, caption, details=''):
        """Short inline guidance; lengthy paths/errors belong in scrollable help."""
        label = self.label(caption)
        if isinstance(label, tk.Misc):
            label._cgyro_role = 'note'
        if details:
            self.ui.Button('查看说明', lambda: show_help(label, details), refresh_tree=False)
        return label

    def task(self, label, path, issues=(), **kwargs):
        problems = list(issues) + (['工程缺少此入口'] if read(self.root, path) is None else [])
        def invoke():
            if problems:
                raise ValueError('；'.join(problems))
            if 'GUIS' in path:
                return gui_view(read(self.root, path), **kwargs)
            return self.actions.call(label, path, **kwargs)
        # Opening a browser/plot dialog does not change the launching page.
        # Data-changing scripts still refresh their action boundary.
        self.guarded(label, invoke, problems, refresh='GUIS' not in path, refresh_tree='GUIS' not in path)

    def compound(self, path, **kwargs):
        task = read(self.root, path)
        if task is None:
            self.label('工程缺少此功能入口：' + '/'.join(path))
        else:
            self.ui.CompoundGUI(task, title='', **kwargs)

    def render(self, panel_only=False):
        self.panel_only = panel_only
        self.compact = True
        if panel_only:
            self.ui.TitleGUI('CGYRO · 线性扫描')
            intro = self.label('CGYRO 线性扫描')
            page = self.settings.setdefault('cgyro_panel_page', 'cgyro')
            if page not in PAGES.values():
                page = self.settings['cgyro_panel_page'] = 'cgyro'
            if page != 'cgyro':
                self.nav('返回 CGYRO 扫描', 'cgyro')
            render_page(self, page)
            finish_gui_layout(intro, self.ui, compact=self.compact, fit_tabs=True)
            return
        self.ui.TitleGUI('CGYRO / TGLF · 工程总控')
        intro = self.label('服务器 → 程序版本 → 计算资源' if self.settings['page'] == 'run' else
                           ('选择输入 → 设置参数 → 运行 → 查看结果' if self.compact else
                            '输入准备  →  传递与验证  →  运行与收集  →  绘图对比'))
        self.page_intro = intro
        self.render_page_picker()
        with self.ui.same_row():
            self.ui.Button('检查配置', self.check_configuration, updateGUI=False, refresh_tree=False,
                           help='检查运行配置和 CGYRO 输入；不连接服务器、不提交计算。')
            self.ui.Button('刷新', self.refresh_page, refresh_tree=False,
                           help='更新当前工作页面，保留窗口、工作页面选择和其他页面。')
        # Keep the header and the loaded action/library objects while replacing
        # only the selected body, including explicit Refresh.
        self.page_content = deferred_section(self.ui, self.render_selected_page,
                                             local=True, container=True, action=True)
        if self.page_content is None:
            self.render_selected_page()
        else:
            # The adapter was captured before the body existed. Async action
            # completions must find the current body through this persistent
            # content frame, including after an explicit native refresh.
            self.page_content.parent.master._cgyro_action_refresh = self.page_content.refresh
            self.page_content.show()
        finish_gui_layout(intro, self.ui, compact=self.compact, fit_tabs=True)

    def render_overview(self):
        s = summary(self.root)
        self.ui.Separator('1  输入转换工具 · 输入准备')
        self.label('可用文件：{}；TGLF 剖面：{}。'.format(s['transfer_inputs'], '已载入' if s['profiles'] else '未载入'))
        with self.ui.same_row():
            self.nav('导入 / 转换 / 传递输入', 'transfer')
            self.nav('批量导入 input.gacode', 'multi')
        self.ui.Separator('2  CGYRO / TGLF · 计算任务')
        self.label('CGYRO 当前输入：' + ('已载入；运行前检查参数' if s['cgyro_input'] else '未载入'))
        self.label('TGLF 单文件：{}；多剖面案例：{}，已选 {}。'.format(
            '已载入' if s['tglf_input'] else '未载入', s['multi_cases'], s['multi_selected']))
        with self.ui.same_row():
            self.nav('CGYRO 扫描', 'cgyro')
            self.nav('TGLF 扫描', 'tglf')
        self.ui.Separator('3  运行与结果')
        self.label('CGYRO 当前状态：{}；归档运行：{}；TGLF 谱结果半径：{}。'.format(
            STATUS.get(s['cgyro_status'], s['cgyro_status']), s['cgyro_runs'], s['tglf_radii']))
        with self.ui.same_row():
            self.nav('运行环境与记录', 'run')
            self.nav('绘图与模型对比', 'plots')
            self.nav('模板 / GitHub', 'templates')
        self.ui.Separator('结果管理')
        self.ui.Button('全局图形样式', lambda: gui_view(self.root['GUIS']['Plot_style']), refresh_tree=False)
        self.ui.Button('优化 CGYRO 归档（去重）', self.actions.optimize_cgyro_storage, updateGUI=True,
                       help='相同结果只保存一份；检查点检测后优先保留当前文件，损坏时保留有效 .old，无法确认则保留两份并告警。原 ZIP 和服务器文件不变，完成后另存工程。')
        self.ui.Button('清空全部结果…', self.clear_all_results, updateGUI=True,
                       help='清空已保存的计算结果与运行记录，保留输入和配置。点击后会确认。')

    def clear_all_results(self):
        if active_jobs(self.root):
            raise ValueError('还有正在运行或已提交的任务。请先结束任务并收集结果，再清空。')
        parent = getattr(self.ui, '_aux', {}).get('parentGUI', None)
        if messagebox.askokcancel('清空全部结果',
                '清空本工程的 CGYRO、TGLF、TGYRO 计算结果和运行记录。\n'
                '保留输入文件、已生成的半径输入、参数和运行配置。\n\n'
                '远程文件与已经导出的图片不受影响。此操作无法撤销。',
                parent=parent, icon='warning'):
            clear_results(self.root, self.actions.factory)

    def cgyro_checkbox(self, path, mapping, key, caption):
        return checkbox(self.ui, path, mapping, key, caption, updateGUI=True)

    def render_tglf(self):
        TGLFWorkbench(self).render()

    def render_multi(self):
        self.compound(('GUIS', 'TGLF_multi'))

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
            self.label('配置检查：' + ('；'.join(runtime_issues(self.root, name)) or '通过'))

    def render_plots(self):
        self.label('选择运行记录、半径和扫描值，即可对比绘图。')
        with self.ui.same_row():
            self.nav('Transfer_tool 剖面绘图', 'transfer', transfer_tab='plots')
            self.task('CGYRO 扫描结果浏览', ('GUIS', 'CGYRO_results'),
                      issues=[] if read(self.root, ('CGYRO_scan', 'RUN_DB'), {}) else ['尚无已收集的 CGYRO 扫描结果'])
        with self.ui.same_row():
            self.nav('多剖面结果对比', 'multi')
            self.task('TGYRO 结果绘图', MODULES['tgyro'] + ('GUIS', 'Plotgui'))
        self.compound(('GUIS', 'CGYRO_vs_TGLF'))

    def render_templates(self):
        self.label('通过 GitHub 分发代码与设置。更新时可保留计算结果，或使用模板提供的示例。')
        self.label('模板库：https://github.com/Liu-s-CGYRO-project/CGYRO_TGLF_scan')
        self.guarded('打开 OMFIT 模板管理器', self.open_templates or (lambda: None),
                     [] if self.open_templates else ['当前工程未载入 OMFITtemplates'], refresh=False, refresh_tree=False)
        self.label('个人服务器和路径可在更新时保留；计算记录和输入历史不进入代码模板。')
