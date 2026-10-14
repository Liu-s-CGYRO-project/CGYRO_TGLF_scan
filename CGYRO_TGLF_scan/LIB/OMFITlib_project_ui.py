"""Native OMFIT workbench with dependency-aware workflow controls."""
from OMFITlib_result_cleanup import active_jobs, clear_results
from builtins import all, any, bool, callable, dict, float, int, isinstance, iter, len, list, min, next, range, sorted, str, sum
from collections import OrderedDict
import json
import math
import tkinter as tk
from tkinter import font as tkfont, ttk, messagebox
from OMFITlib_gui_layout import finish_gui_layout
from OMFITlib_gui_controls import checkbox
from OMFITlib_tglf_workbench_ui import SCAN_TABS as CGYRO_SCAN_TABS, TGLFWorkbench
from OMFITlib_transfer_workflow import generation_issues, initialize_generation, loaded_file
from OMFITlib_project_runtime import initialize_runtime, applied_runtime, shared_issues, validate_runtime
from OMFITlib_gacode_installations import PROGRAMS, choices as installation_choices, installation_issues
from OMFITlib_cgyro_results import ResultBrowser
from OMFITlib_cgyro_parameters import (FIELDS as CGYRO_FIELDS, GROUPS as CGYRO_GROUPS,
    initialize_parameters, numeric_source, parameter_catalog, scan_parameter_names)
from OMFITlib_project import (ERROR_NOTICE_SUFFIX, ION_CASES, LABELS, MODULES, PAGES, cgyro_input_issues,
    cgyro_ion_mode, cgyro_plan_issues, cgyro_plan_summary, collect_issues, generated_tglf_sources, location, module,
    input_digest, pending_inputs, read, runtime_issues, summary, sync_cgyro_choices, sync_cgyro_ion_cases, text_value,
    tglf_input_issues, transfer_generated_rows, transfer_parameter_value, transfer_sources)

STATUS = {'prepared': '输入已准备', 'submitted': '已提交', 'loaded': '结果已读取',
          'submitted_or_finished': '已提交或执行返回',
          'published': '结果已归档', 'complete': '完成', 'running': '运行中',
          'failed': '失败', 'cancelled': '已中止', 'partial': '部分完成',
          'ready': '输入就绪', 'prepare_failed': '输入生成失败', 'preparing': '输入生成中',
          'returned': '脚本已返回', 'inputs_copied': '输入已复制', 'archived': '已保留旧数据'}
STATUS.update(dict(awaiting_choice='等待用户选择', accepted='使用传入输入', kept_current='保留当前输入', superseded='已有新候选'))


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
        self.compact = True
        if panel_only:
            self.ui.TitleGUI('CGYRO · 线性扫描')
            intro = self.label('CGYRO 线性扫描')
            page = self.settings.setdefault('cgyro_panel_page', 'cgyro')
            if page not in PAGES.values():
                page = self.settings['cgyro_panel_page'] = 'cgyro'
            if page != 'cgyro':
                self.nav('返回 CGYRO 扫描', 'cgyro')
            getattr(self, 'render_' + page)()
            finish_gui_layout(intro, self.ui, compact=self.compact, fit_tabs=True)
            return
        self.ui.TitleGUI('CGYRO / TGLF · 工程总控')
        intro = self.label('服务器 → 程序版本 → 计算资源' if self.settings['page'] == 'run' else
                           ('选择输入 → 设置参数 → 运行 → 查看结果' if self.compact else
                            '输入准备  →  传递与验证  →  运行与收集  →  绘图对比'))
        self.ui.ComboBox(self.prefix + "['page']", PAGES, '工作页面', default='overview', updateGUI=True)
        with self.ui.same_row():
            self.ui.Button('检查配置', self.actions.check, updateGUI=True,
                           help='检查运行配置和 CGYRO 输入；不连接服务器、不提交计算。')
            self.ui.Button('刷新', lambda: None, updateGUI=True)
        if self.settings['page'] not in ('cgyro', 'tglf'):
            self.show_message()
        getattr(self, 'render_' + self.settings['page'])()
        finish_gui_layout(intro, self.ui, compact=self.compact, fit_tabs=True)

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
            self.nav('TGLF 扫描', 'tglf')
        self.ui.Separator('3  运行与结果')
        self.label('CGYRO 当前状态：{}；归档运行：{}；TGLF 谱结果半径：{}。'.format(
            STATUS.get(s['cgyro_status'], s['cgyro_status']), s['cgyro_runs'], s['tglf_radii']))
        with self.ui.same_row():
            self.nav('运行环境与记录', 'run')
            self.nav('绘图与模型对比', 'plots')
            self.nav('模板 / GitHub', 'templates')
        self.ui.Separator('结果管理')
        self.ui.Button('全局图形样式', lambda: self.root['GUIS']['Plot_style'].run())
        self.ui.Button('清空全部结果…', self.clear_all_results, updateGUI=True,
                       help='清空已保存的计算结果与运行记录，保留输入和配置。点击后会确认。')
        self.ui.Separator('流程规则')
        self.label('CGYRO：Transfer_tool 生成半径输入后，选择输入案例与 1–3 个参数轴批量运行。\n'
                   '已有完整 input.cgyro 也可直接载入并作为一个 nr 使用。\n'
                   'TGLF 多剖面：导入 input.gacode → 生成局部输入 → 计算 → 结果对比。')

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

    def render_transfer(self):
        self.ui.Tab('Transfer_tool 运行')
        frame = getattr(self.ui, '_aux', {}).get('parentGUI', None)
        notebook = frame.master if isinstance(frame, tk.Misc) and isinstance(frame.master, ttk.Notebook) else None
        self.compound(('Transfer_tool', 'GUIS', 'transfer'), show_run_button=False)
        self.run_controls('transfer')
        files = transfer_generated_rows(self.root)
        ready = next((row for row in files if 'cgyro' in row['paths']), None)
        if ready is not None:
            self.ui.Button('设置 CGYRO 扫描',
                lambda: self.settings.update(dict(page='cgyro', cgyro_source_mode=ready['mode'])), updateGUI=True)
        self.ui.Tab('生成文件')
        self.transfer_files(files)
        self.ui.Tab('剖面绘图')
        self.compound(('Transfer_tool', 'GUIS', 'plots'))
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
        if notebook is not None:
            pages = ['run', 'files', 'plots', 'convert', 'advanced']
            selected = self.settings.setdefault('transfer_tab', 'run')
            if selected not in pages:
                selected = self.settings['transfer_tab'] = 'run'
            notebook.select(pages.index(selected))
            def remember(event):
                if event.widget is notebook:
                    try:
                        self.settings['transfer_tab'] = pages[notebook.index(notebook.select())]
                    except tk.TclError:
                        pass
            notebook.bind('<<NotebookTabChanged>>', remember, add='+')

    def transfer_files(self, rows):
        if not rows:
            self.label('尚无生成文件。运行 Transfer_tool 或完成局部输入互转后在这里查看。')
            return
        count = sum(1 for row in rows if row['mode'] == 'generated')
        anchor = self.label('已生成 {} 组半径输入。'.format(count) if count else '已有局部互转文件。')
        options = OrderedDict((row['label'], row['key']) for row in rows)
        if self.settings.get('transfer_preview', None) not in options.values():
            self.settings['transfer_preview'] = rows[0]['key']
        self.ui.ComboBox(self.prefix + "['transfer_preview']", options, '查看文件', state='readonly', updateGUI=True)
        row = next(row for row in rows if row['key'] == self.settings['transfer_preview'])
        with self.ui.same_row():
            for code in ('cgyro', 'tglf'):
                path = row['paths'].get(code, None)
                caption = row['label'] + ' / input.' + code
                self.ui.Button('查看 / 编辑 input.' + code,
                    lambda path=path, caption=caption: self.show_transfer_input(anchor, path, caption),
                    state='normal' if path is not None else 'disabled')
        self.label('双击数值可编辑；计算半径在 CGYRO 扫描页选择。')

    def show_transfer_input(self, anchor, path, caption):
        value = read(self.root, path)
        if value is None:
            raise ValueError('生成文件已变化，请刷新页面。')
        # Edit a draft of the live mapping. Only an explicit save replaces it.
        state = dict(parameters={}, edits={}, digest='', selected='', loading=False)
        code = 'cgyro' if str(path[-1]).startswith('input.cgyro') else 'tglf'
        window = tk.Toplevel(anchor.winfo_toplevel())
        window.title('生成输入 · ' + caption)
        width = min(720, window.winfo_screenwidth() - 64)
        height = min(840, window.winfo_screenheight() - 100)
        window.geometry('{}x{}'.format(width, height))
        ttk.Label(window, text=caption, anchor='w').pack(fill=tk.X, padx=10, pady=(10, 6))
        frame = ttk.Frame(window)
        frame.pack(fill=tk.BOTH, expand=True, padx=10)
        style = ttk.Style(window)
        preview_font = tkfont.Font(root=window, font=style.lookup('Treeview', 'font') or 'TkDefaultFont')
        style_name = 'TransferPreview' + str(window).replace('.', '_') + '.Treeview'
        style.configure(style_name, font=preview_font, rowheight=preview_font.metrics('linespace') + 8)
        table = ttk.Treeview(frame, columns=('parameter', 'value'), show='headings', style=style_name)
        table._transfer_font = preview_font
        table.heading('parameter', text='参数')
        table.heading('value', text='数值')
        table.column('parameter', width=260, anchor='w')
        table.column('value', width=360, anchor='w')
        y_scroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=table.yview)
        x_scroll = ttk.Scrollbar(frame, orient=tk.HORIZONTAL, command=table.xview)
        table.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        table.grid(row=0, column=0, sticky='nsew')
        y_scroll.grid(row=0, column=1, sticky='ns')
        x_scroll.grid(row=1, column=0, sticky='ew')
        table.tag_configure('changed', background='#e7f2ff')
        editor = ttk.Frame(window)
        editor.pack(fill=tk.X, padx=10, pady=(8, 0))
        parameter_name = tk.StringVar(master=window)
        parameter_text = tk.StringVar(master=window)
        status = tk.StringVar(master=window, value='双击数值编辑，回车确认；保存修改后生效。')
        ttk.Label(editor, textvariable=parameter_name, width=22, anchor='w').pack(side=tk.LEFT)
        entry = ttk.Entry(editor, textvariable=parameter_text)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        feedback = ttk.Label(window, textvariable=status, anchor='w', wraplength=width - 32)
        feedback.pack(fill=tk.X, padx=10, pady=(6, 0))
        if code == 'cgyro':
            ttk.Label(window, text='此处修改源输入，运行时仍按扫描页设置。', anchor='w',
                      wraplength=width - 32).pack(fill=tk.X, padx=10, pady=(4, 0))
        else:
            ttk.Label(window, text='TGLF 扫描直接读取所选源文件；计算参数页的修改优先。', anchor='w',
                      wraplength=width - 32).pack(fill=tk.X, padx=10, pady=(4, 0))
        ttk.Label(window, text=location(path), anchor='w', wraplength=width - 32).pack(fill=tk.X, padx=10, pady=6)
        buttons = ttk.Frame(window)
        buttons.pack(fill=tk.X, padx=10, pady=(0, 10))

        def select(event=None):
            selection = table.selection()
            if not selection:
                return
            name = str(table.item(selection[0], 'values')[0])
            state['selected'], state['loading'] = name, True
            parameter_name.set(name)
            parameter_text.set(state['edits'].get(name, str(state['parameters'][name])))
            state['loading'] = False

        def changed(*args):
            name = state['selected']
            if state['loading'] or not name:
                return
            text = parameter_text.get()
            if text == str(state['parameters'][name]):
                state['edits'].pop(name, None)
            else:
                state['edits'][name] = text
            for item in table.get_children():
                if table.item(item, 'values')[0] == name:
                    table.set(item, 'value', text)
                    table.item(item, tags=('changed',) if name in state['edits'] else ())
                    break
            save_button.configure(state='normal' if state['edits'] else 'disabled')
            status.set('待保存 {} 项。'.format(len(state['edits'])) if state['edits'] else '双击数值编辑，保存后生效。')

        def confirm(event=None):
            name = state['selected']
            if name:
                try:
                    parsed = transfer_parameter_value(code, name, parameter_text.get(), state['parameters'][name])
                    parameter_text.set(str(parsed))
                except (ValueError, TypeError, SyntaxError, OverflowError) as exc:
                    status.set(str(exc))
                    entry.focus_set()
            return 'break'

        def edit(event):
            if table.identify_column(event.x) == '#2':
                item = table.identify_row(event.y)
                if item:
                    table.selection_set(item)
                    select()
                    entry.focus_set()
                    entry.selection_range(0, tk.END)

        def load(message='已重载，未保存的修改已撤销。'):
            current = read(self.root, path)
            if current is None:
                raise ValueError('生成文件已变化，请关闭后重新打开。')
            state['digest'] = input_digest(current)
            state['parameters'] = {str(key): item for key, item in current.items() if not str(key).startswith('__')}
            state['edits'].clear()
            state['selected'], state['loading'] = '', True
            children = table.get_children()
            if children:
                table.delete(*children)
            for name, item in state['parameters'].items():
                table.insert('', 'end', values=(name, str(item)))
            state['loading'] = False
            children = table.get_children()
            if children:
                table.selection_set(children[0])
                select()
            save_button.configure(state='disabled')
            status.set(message)

        def save():
            try:
                saved = self.actions.save_transfer_input(path, state['edits'], state['digest'])
                count = sum(input_digest(saved[name]) != input_digest(state['parameters'][name]) for name in state['edits'])
                load('已保存 {} 项修改。'.format(count))
            except Exception as exc:
                status.set('保存失败：' + str(exc))

        def reload():
            try:
                load()
            except Exception as exc:
                status.set(str(exc))

        save_button = ttk.Button(buttons, text='保存修改', command=save, state='disabled')
        save_button.pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(buttons, text='重载 / 撤销', command=reload).pack(side=tk.LEFT)
        ttk.Button(buttons, text='关闭', command=window.destroy).pack(side=tk.RIGHT)
        parameter_text.trace_add('write', changed)
        table.bind('<<TreeviewSelect>>', select)
        table.bind('<Double-1>', edit)
        table.bind('<Return>', lambda event: entry.focus_set())
        entry.bind('<Return>', confirm)
        load('双击数值编辑，回车确认；保存修改后生效。')

    def render_cgyro(self):
        node = read(self.root, MODULES['cgyro'])
        if node is None:
            self.label('工程缺少 CGYRO_scan 模块。')
            return
        self.ui.Tab('输入与扫描')
        self.compound(('GUIS', 'CGYRO_controls'), workbench=self)
        self.show_message(first_line=True)
        rows = self.cgyro_rows
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

    def render_cgyro_scan_tabs(self):
        node = read(self.root, MODULES['cgyro'])
        self.cgyro_rows = []
        if node is None:
            self.label('工程缺少 CGYRO_scan 模块。')
            return
        selected = self.settings['cgyro_scan_page']
        if selected not in CGYRO_SCAN_TABS:
            selected = 'input'
        self.cgyro_scan_notebook = None
        for page, caption in CGYRO_SCAN_TABS.items():
            self.ui.Tab(caption)
            if self.cgyro_scan_notebook is None:
                # Native Tab returns None; read its owned frame and Notebook.
                frame = getattr(self.ui, '_aux', {}).get('parentGUI', None)
                if isinstance(frame, tk.Misc) and isinstance(frame.master, ttk.Notebook):
                    self.cgyro_scan_notebook = frame.master
            if page == 'input':
                self.cgyro_rows = self.render_cgyro_input()
            elif page == 'settings':
                self.render_cgyro_scan_settings(node, self.cgyro_rows)
            else:
                self.render_cgyro_run(node)
        self.select_cgyro_scan_page(selected)
        if self.cgyro_scan_notebook is not None:
            self.cgyro_scan_notebook.bind('<<NotebookTabChanged>>', self.cgyro_scan_page_changed, add='+')

    def select_cgyro_scan_page(self, page):
        self.settings['cgyro_scan_page'] = page
        if self.cgyro_scan_notebook is not None:
            try:
                self.cgyro_scan_notebook.select(list(CGYRO_SCAN_TABS).index(page))
            except tk.TclError:
                return

    def cgyro_scan_page_changed(self, event):
        if event.widget is self.cgyro_scan_notebook:
            try:
                self.settings['cgyro_scan_page'] = list(CGYRO_SCAN_TABS)[
                    self.cgyro_scan_notebook.index(self.cgyro_scan_notebook.select())]
            except tk.TclError:
                return

    def render_cgyro_input(self):
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
        self.ui.Separator('半径与主离子')
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
        return rows

    def render_cgyro_scan_settings(self, node, rows):
        base = MODULES['cgyro'] + ('SETTINGS',)
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

    def render_cgyro_run(self, node):
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
                             state='readonly', updateGUI=True)
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
        scanned = scan_parameter_names(physics, int(node['SETTINGS']['SETUP']['idimrun']))
        self.ui.ComboBox(self.prefix + "['cgyro_parameter_group']", CGYRO_GROUPS, '参数分组',
                         state='readonly', width=24, updateGUI=True)
        self.ui.Entry(self.prefix + "['cgyro_parameter_search']", '搜索参数', width=28, updateGUI=True)
        group = self.settings['cgyro_parameter_group']
        query = str(self.settings['cgyro_parameter_search']).strip().upper()
        names = [name for name, spec in catalog.items()
                 if (group == 'all' or (group == 'common' and name in CGYRO_FIELDS) or spec['group'] == group)
                 and (not query or query in name or query in spec['label'].upper())]
        with self.ui.same_row():
            self.ui.Button('本组沿用输入值',
                           lambda: self.actions.reset_cgyro_parameters(names, source_key), updateGUI=True)
            self.ui.Button('全部沿用输入值', self.actions.inherit_cgyro_parameters, updateGUI=True)
        if not names:
            self.label('没有匹配的参数。')
        previous_group = None
        labels = {value: label for label, value in CGYRO_GROUPS.items()}
        for name in names:
            spec = catalog[name]
            if spec['group'] != previous_group:
                self.ui.Separator(labels.get(spec['group'], '其他输入参数'))
                previous_group = spec['group']
            self.cgyro_parameter_row(base, name, spec, parameters[name], source_values, scanned, source_key)
        self.ui.Separator('时间缩放')
        self.cgyro_checkbox(location(base + ('scale_time_with_ky',)), physics, 'scale_time_with_ky', '按 ky 缩放时间')
        if physics['scale_time_with_ky']:
            self.label('ky > 1 时，步长与运行时长分别除以 ky。')
        self.ui.Separator('重启与源文件')
        self.ui.ComboBox(location(base + ('restart_mode',)), {'新计算': 0, '匹配结果重启': 1},
                         '运行方式', state='readonly', updateGUI=True)
        self.cgyro_checkbox(self.prefix + "['cgyro_advanced']", self.settings, 'cgyro_advanced', '直接编辑源 input.cgyro')
        if self.settings['cgyro_advanced'] and row is not None:
            self.ui.EditASCIIobject(location(row['path']), '编辑参考输入', updateGUI=True)
        problems = cgyro_plan_issues(self.root)
        if problems:
            self.label('需要：' + '；'.join(problems[:2]))

    def cgyro_parameter_row(self, base, name, spec, item, source_values, scanned, source_key):
        if name in scanned:
            self.label(name + ' · 由扫描轴设置')
            return
        path = base + ('fixed_parameters', name)
        reference = ('输入值：{}'.format(source_values[name]) if name in source_values else
                     '文件未写入，显示参考值：{}；修改后才写入运行副本。'.format(spec['reference']))
        help_text = reference + '\n修改并回车后应用到所选输入；“沿用输入”取消覆盖，使用各输入自己的值。'
        with self.ui.same_row() as line:
            frame = getattr(line, 'frm_top', None)
            if isinstance(frame, tk.Misc):
                frame._cgyro_inline = True
            self.label(name + ' · ' + spec['label'])
            if name == 'DELTA_T_METHOD':
                self.ui.ComboBox(location(path + ('value',)), OrderedDict([
                    ('0 固定 RK4', 0), ('1 自适应 Cash-Karp', 1),
                    ('2 自适应 Bogacki-Shampine', 2), ('3 自适应 Verner', 3)]), '',
                    width=24, state='readonly', updateGUI=True, help=help_text,
                    postcommand=lambda location=None: self.actions.edit_cgyro_parameter(name))
            else:
                self.ui.Entry(location(path + ('value',)), '', width=14, updateGUI=True,
                              state='normal' if spec.get('supported', True) else 'disabled', help=help_text,
                              postcommand=lambda location=None: self.actions.edit_cgyro_parameter(name))
            self.ui.Button('沿用输入', lambda: self.actions.reset_cgyro_parameters([name], source_key), updateGUI=True)

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

    def render_plots(self):
        self.label('选择运行记录、半径和扫描值，即可对比绘图。')
        with self.ui.same_row():
            self.ui.Button('Transfer_tool 剖面绘图',
                           lambda: self.settings.update(dict(page='transfer', transfer_tab='plots')), updateGUI=True)
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
                     [] if self.open_templates else ['当前工程未载入 OMFITtemplates'])
        self.label('个人服务器和路径可在更新时保留；计算记录和输入历史不进入代码模板。')
