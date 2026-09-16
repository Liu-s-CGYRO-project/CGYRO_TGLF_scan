"""One Tk interface shared by the OMFIT module and the standalone launcher."""
from builtins import all, any, bool, dict, float, int, len, list, max, min, open, range, set, sorted, str, sum, tuple, zip
import os
from pathlib import Path
import queue
import tempfile
import threading
import webbrowser
import tkinter as tk
from tkinter import filedialog, font as tkfont, messagebox, ttk

from OMFITlib_template_archive import TemplateError, human_size, json_bytes, parse_json
from OMFITlib_template_paths import default_library, legacy_preferences_path, preferences_path
from OMFITlib_template_github import DEFAULT_REPOSITORY, INITIAL_README, GitHub, GitHubError, login, repository
from OMFITlib_template_proxy import PROXY_MODES, connection_label, manual_proxy, network_preferences
from OMFITlib_template_versions import MANAGER_VERSION, SORT_OPTIONS, sort_releases
from OMFITlib_template_manager_ui import ManagerUpdateUI
from OMFITlib_template_cli import CLI_REPOSITORY, ensure_cli
from OMFITlib_template_live import Prepared
from OMFITlib_template_service import (
    Cancelled, EXTENSION, Template, apply_update, inspect_project, list_library,
    plan_update, publish, read_history, release_name, transfer,
)

DATA_OPTIONS = {'保留当前案例与结果': 'keep', '切换到模板示例': 'examples'}
SETTING_OPTIONS = {'保留当前设置，补全新增项': 'keep', '使用模板设置': 'template'}


class TemplateManager(ManagerUpdateUI):
    def __init__(self, window, current_project='', library=None, preferences=None, session=None):
        self.window = window
        self.session = session
        self.last_output = None
        self.publish_plan = None
        self.package_path = None
        self.preferences = Path(preferences) if preferences is not None else preferences_path()
        read_preferences = self.preferences
        if preferences is None and not self.preferences.exists():
            read_preferences = legacy_preferences_path()
        saved, preference_error = {}, ''
        try:
            if read_preferences.is_file():
                saved = parse_json(read_preferences.read_bytes())
                if not isinstance(saved, dict):
                    raise TemplateError('偏好设置需要是 JSON 对象')
        except (OSError, TemplateError) as exc:
            saved, preference_error = {}, str(exc)
        self.busy = False
        self.plan = None
        self.live_plan = None
        self.releases = []
        self.selected_release = None
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.widgets = []
        self.close_requested = False
        self.alive = True
        self.github_login = ''
        self._login_after = None
        self._login_generation = 0
        self._login_remaining = 0
        # OMFIT replaces these classes with factories accepting name=None, **kw.
        # Explicit keywords also bind variables to this window's interpreter.
        self.library = tk.StringVar(master=window, value=str(library or saved.get('library') or default_library()))
        self.shared = tk.StringVar(master=window, value=str(saved.get('shared', '')))
        self.repository = tk.StringVar(master=window, value=str(saved.get('repository', DEFAULT_REPOSITORY)))
        network = network_preferences(saved.get('network', {}))
        mode = network['mode']
        self.proxy_mode = tk.StringVar(master=window, value=next((label for label, value in PROXY_MODES.items() if value == mode), next(iter(PROXY_MODES))))
        self.proxy_host = tk.StringVar(master=window, value=str(network['host']))
        self.proxy_port = tk.StringVar(master=window, value=str(network['port']))
        self.proxy_username = tk.StringVar(master=window, value=str(network['username']))
        self.proxy_password = tk.StringVar(master=window, value='')
        self.proxy_info = tk.StringVar(master=window, value='')
        self.proxy_dialog = None
        self.manager_update_dialog = None
        self.manager_update_result = None
        self._manager_check_generation = 0
        self._manager_auto_cancel = threading.Event()
        self.manager_version_info = tk.StringVar(master=window, value='管理器 ' + MANAGER_VERSION)
        self.connection_info = tk.StringVar(master=window, value='打开后自动连接上次的 GitHub 仓库。公开模板可直接浏览；发布与私有仓库需要登录。')
        self.upload_info = tk.StringVar(master=window, value='先准备模板包，核对仓库、账号和上传文件后发布。')
        self.publish_auth_info = tk.StringVar(master=window, value='')
        source = saved.get('view_source', 'GitHub')
        self.view_source = tk.StringVar(master=window, value=source if source in ('GitHub', '本地模板库', '共享模板库') else 'GitHub')
        self.search = tk.StringVar(master=window, value='')
        self.author_filter = tk.StringVar(master=window, value='全部作者')
        self._updating_authors = False
        order = saved.get('sort', 'published')
        self.release_sort = tk.StringVar(master=window, value=next((label for label, key in SORT_OPTIONS.items()
                                                                  if key == order), next(iter(SORT_OPTIONS))))
        current_project = session.project_path() if session is not None else (current_project or saved.get('current', ''))
        self.current = tk.StringVar(master=window, value=current_project if str(current_project).lower().endswith('.zip') else '')
        self.output = tk.StringVar(master=window, value='')
        self.template_path = tk.StringVar(master=window, value='')
        self.data_policy = tk.StringVar(master=window, value=next(iter(DATA_OPTIONS)))
        self.settings_policy = tk.StringVar(master=window, value=next(iter(SETTING_OPTIONS)))
        self.source = tk.StringVar(master=window, value=self.current.get())
        self.roots = tk.StringVar(master=window, value='')
        self.include_examples = tk.BooleanVar(master=window, value=False)
        self.publish_destination = tk.StringVar(master=window, value='本地模板库' if library is not None else 'GitHub')
        self.metadata = {k: tk.StringVar(master=window, value='') for k in ('id', 'name', 'author', 'version', 'description')}
        self.status = tk.StringVar(master=window, value='连接 GitHub，选择版本；也可使用已下载的本地模板。')
        self.release_info = tk.StringVar(master=window, value='尚未选择模板。')
        self.inspection_info = tk.StringVar(master=window, value='先选择一个已保存的工程 ZIP，再读取模块和文件范围。')
        self.plan_info = tk.StringVar(master=window, value='预览后可直接更新当前会话。' if session is not None else '预览后才可生成工程。原 ZIP 始终保留。')
        self._configure()
        self._render()
        self._publish_states()
        self._fit_size(window, 940, 680)
        if preference_error:
            self._log('上次库路径未能恢复：' + preference_error)
        for variable in (self.current, self.template_path, self.data_policy, self.settings_policy):
            variable.trace_add('write', lambda *args: self._invalidate())
        self.search.trace_add('write', lambda *args: self._filter())
        self.author_filter.trace_add('write', self._author_changed)
        self.release_sort.trace_add('write', lambda *args: self._filter())
        self.repository.trace_add('write', lambda *args: self._repository_changed())
        for variable in (self.proxy_mode, self.proxy_host, self.proxy_port, self.proxy_username, self.proxy_password):
            variable.trace_add('write', lambda *args: self._proxy_changed())
        self._proxy_hint()
        for variable in (self.source, self.roots, self.include_examples, self.publish_destination, *self.metadata.values()):
            variable.trace_add('write', lambda *args: self._invalidate_publish())
        window.protocol('WM_DELETE_WINDOW', self.close)
        self._poll_after = window.after(100, self._poll)
        self._refresh_after = window.after(150, self._startup)

    def _startup(self):
        self._refresh_after = None
        if not self.alive or self.close_requested:
            return
        # Version checks have their own worker and cancellation; offline/local
        # use stays available while GitHub responds or times out.
        self._check_manager_update(automatic=True)
        self.refresh(automatic=True)

    def _configure(self):
        w = self.window
        # Window decorations use the Linux window manager's fonts, not Tk's.
        w.title('OMFIT Template Manager')
        width = min(1180, max(940, w.winfo_screenwidth() - 80))
        height = min(800, max(680, w.winfo_screenheight() - 100))
        w.geometry('{}x{}'.format(width, height))
        w.minsize(940, 680)
        # nametofont(root=...) requires Python 3.10; Font supports 3.9 and
        # still binds to this window's interpreter in an embedded OMFIT session.
        default = tkfont.Font(root=w, name='TkDefaultFont', exists=True).actual()
        available = set(tkfont.families(root=w))
        family = next((candidate for candidate in ('Noto Sans CJK SC', 'Source Han Sans SC',
                       'WenQuanYi Micro Hei', 'Noto Sans SC', 'WenQuanYi Zen Hei',
                       'Droid Sans Fallback', 'AR PL UMing CN') if candidate in available), default['family'])
        font = (family, default['size'] if default['size'] < 0 else max(10, default['size']))
        self._metrics_font = tkfont.Font(root=w, family=font[0], size=font[1])
        # On older Linux desktops the Latin default can fall back to much
        # taller CJK glyphs. Use Tk's actual Chinese face for layout metrics too.
        try:
            family = str(w.tk.call('font', 'actual', str(self._metrics_font), '-family', '中'))
            self._metrics_font.configure(family=family)
            font = (family, font[1])
        except tk.TclError:
            pass
        self.font = font
        self._line_gap = max(6, self._metrics_font.metrics('linespace') // 3)
        self._path_label_width = max(self._metrics_font.measure(text) for text in
            ('当前工程 ZIP', '输出工程 ZIP', '来源工程 ZIP', '选用模板包', '本地模板库', '共享目录（可选）')) + 12
        style = ttk.Style(w)
        if isinstance(w, tk.Tk) and 'clam' in style.theme_names():
            style.theme_use('clam')
        style.configure('TM.TFrame', background='#f4f6fa')
        style.configure('TM.TLabel', background='#f4f6fa', foreground='#17283d', font=font)
        style.configure('TM.Muted.TLabel', background='#f4f6fa', foreground='#53647a', font=font)
        style.configure('TM.Empty.TFrame', background='white')
        style.configure('TM.Empty.TLabel', background='white', foreground='#53647a', font=font)
        for name in ('TM.TLabel', 'TM.Muted.TLabel'):
            style.map(name, foreground=[('disabled', '#7a8492')], background=[('disabled', '#f4f6fa')])
        style.map('TM.TFrame', background=[('disabled', '#f4f6fa')])
        style.configure('TM.Title.TLabel', background='#f4f6fa', foreground='#143454', font=(font[0], 22, 'bold'))
        style.configure('TM.TButton', font=font, padding=(12, 7))
        style.configure('TM.TEntry', padding=(5, 4))
        style.configure('TM.TCombobox', padding=(5, 4))
        style.configure('TM.TCheckbutton', font=font, background='#f4f6fa')
        style.map('TM.TCheckbutton', foreground=[('disabled', '#7a8492')], background=[('disabled', '#f4f6fa')])
        for name in ('TM.TEntry', 'TM.TCombobox'):
            style.map(name, foreground=[('disabled', '#7a8492')], fieldbackground=[('disabled', '#eceff3')])
        style.configure('TM.Treeview', font=font, rowheight=max(30, self._metrics_font.metrics('linespace') + 8))
        style.configure('TM.Treeview.Heading', font=(font[0], font[1], 'bold'))
        style.configure('TM.TNotebook', background='#f4f6fa', tabmargins=(0, 6, 0, 0))
        style.configure('TM.TNotebook.Tab', font=font, padding=(18, 10))
        style.configure('TM.Horizontal.TProgressbar', background='#2476b8', troughcolor='#e1e7ef',
                        lightcolor='#2476b8', darkcolor='#2476b8', bordercolor='#b4c1d1')
        w.configure(background='#f4f6fa')

    def _frame(self, parent, **kwargs):
        return ttk.Frame(parent, style='TM.TFrame', **kwargs)

    def _fit_size(self, window, minimum_width, minimum_height):
        """Keep controls visible when Linux/OMFIT uses a larger display font."""
        window.update_idletasks()
        height = min(max(1, window.winfo_screenheight() - 80),
                     max(minimum_height, window.winfo_reqheight()))
        window.minsize(minimum_width, height)
        window.geometry('{}x{}'.format(max(minimum_width, window.winfo_width()),
                                        max(height, window.winfo_height())))

    def _label(self, parent, text='', variable=None, muted=False, **kwargs):
        # Explicit font overrides OMFIT's option database, so measured and
        # rendered widths agree even when *Font differs from ttk styles.
        kwargs.setdefault('font', self.font)
        if 'width' in kwargs:
            kwargs['width'] = max(kwargs['width'], self._text_width(text) + 2)
        label = ttk.Label(parent, text=text, textvariable=variable, style='TM.Muted.TLabel' if muted else 'TM.TLabel', **kwargs)
        if 'wraplength' in kwargs:
            parent.bind('<Configure>', lambda event: label.configure(wraplength=max(180, event.width - 32)), add='+')
        return label

    def _text_width(self, text):
        unit = max(1, self._metrics_font.measure('0'))
        return (self._metrics_font.measure(str(text)) + unit - 1) // unit

    def _text_area(self, parent, **kwargs):
        kwargs.setdefault('font', self.font)
        kwargs.setdefault('spacing1', self._line_gap // 2)
        kwargs.setdefault('spacing2', self._line_gap // 2)
        kwargs.setdefault('spacing3', self._line_gap)
        return tk.Text(parent, **kwargs)

    def _set_empty_hint(self, text):
        # Separate rows give CJK fallback glyphs real space; a newline in one
        # ttk.Label can use the Latin font's smaller baseline distance.
        for label in self.empty_hint.winfo_children():
            label.destroy()
        self.empty_hint_lines = []
        lines = text.splitlines()
        for index, line in enumerate(lines):
            label = ttk.Label(self.empty_hint, text=line, font=self.font, style='TM.Empty.TLabel',
                              justify='center', anchor='center', padding=(4, self._line_gap // 2))
            label.pack(fill='x', pady=(0, self._line_gap if index < len(lines) - 1 else 0))
            self.empty_hint_lines.append(label)
        self._layout_empty_hint()
        self.empty_hint.place(relx=.5, rely=.45, relwidth=.92, anchor='center')

    def _layout_empty_hint(self, event=None):
        width = max(80, int(self.library_table.winfo_width() * .92) - 16)
        for label in self.empty_hint_lines:
            label.configure(wraplength=width)

    def _button(self, parent, text, command):
        widget = ttk.Button(parent, text=text, command=command, style='TM.TButton', width=0)
        self.widgets.append((widget, 'normal'))
        return widget

    def _entry(self, parent, variable, width=None):
        widget = ttk.Entry(parent, textvariable=variable, font=self.font,
                           width=1 if width is None else width, style='TM.TEntry')
        self.widgets.append((widget, 'normal'))
        return widget

    def _combo(self, parent, variable, values):
        width = max(self._text_width(value) for value in values) + 2
        widget = ttk.Combobox(parent, textvariable=variable, values=values, state='readonly', width=width,
                              font=self.font, style='TM.TCombobox')
        widget.option_add('*' + str(widget).lstrip('.') + '*Listbox.font', self.font)
        self.widgets.append((widget, 'readonly'))
        return widget

    def _path_row(self, parent, label, variable, command):
        row = self._frame(parent)
        row.pack(fill='x', pady=5)
        row.columnconfigure(0, minsize=self._path_label_width)
        row.columnconfigure(1, weight=1)
        self._label(row, label).grid(row=0, column=0, sticky='w', padx=(0, 12))
        self._entry(row, variable, width=1).grid(row=0, column=1, sticky='ew', padx=(0, 8))
        self._button(row, '浏览…', command).grid(row=0, column=2)
        return row

    def _render(self):
        main = self._frame(self.window, padding=(22, 16))
        main.pack(fill='both', expand=True)
        header = self._frame(main)
        header.pack(fill='x')
        ttk.Label(header, text='OMFIT 模板管理', font=(self.font[0], 22, 'bold'), style='TM.Title.TLabel').pack(side='left')
        self.manager_update_button = self._button(header, '检查管理器更新', self._check_manager_update)
        self.manager_update_button.pack(side='right')
        self._label(main, variable=self.manager_version_info, muted=True, wraplength=1000).pack(fill='x', pady=(6, 0))
        self.tabs = ttk.Notebook(main, style='TM.TNotebook')
        self.tabs.pack(fill='both', expand=True, pady=(8, 10))
        self.pages = [self._frame(self.tabs, padding=16) for _ in range(4)]
        for page, title in zip(self.pages, ('1  GitHub 版本', '2  更新 / 切换', '3  发布模板', '4  设置与记录')):
            self.tabs.add(page, text=title)
        self._render_library(self.pages[0])
        self._render_update(self.pages[1])
        self._render_publish(self.pages[2])
        self._render_help(self.pages[3])
        footer = self._frame(main)
        footer.pack(side='bottom', fill='x', before=self.tabs)
        footer.columnconfigure(0, weight=1)
        status_label = self._label(footer, variable=self.status, wraplength=750)
        status_label.grid(row=0, column=0, sticky='w')
        self.progress = ttk.Progressbar(footer, length=180, mode='determinate', maximum=100,
                                        style='TM.Horizontal.TProgressbar')
        self.progress.grid(row=0, column=1, padx=10)
        self.cancel_button = ttk.Button(footer, text='取消操作', command=self.cancel.set, state='disabled',
                                        style='TM.TButton', width=0)
        self.cancel_button.grid(row=0, column=2)
        footer.bind('<Configure>', lambda event: status_label.configure(wraplength=max(100,
            event.width - self.progress.winfo_reqwidth() - self.cancel_button.winfo_reqwidth() - 20)))

    def _table(self, parent, columns, height=2):
        frame = self._frame(parent)
        frame.pack(fill='both', expand=True, pady=8)
        table = ttk.Treeview(frame, columns=[c[0] for c in columns], show='headings', selectmode='browse',
                             style='TM.Treeview', height=height)
        scrollbar = ttk.Scrollbar(frame, orient='vertical', command=table.yview)
        horizontal = ttk.Scrollbar(frame, orient='horizontal', command=table.xview)
        table.configure(yscrollcommand=scrollbar.set, xscrollcommand=horizontal.set)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        table.grid(row=0, column=0, sticky='nsew')
        scrollbar.grid(row=0, column=1, sticky='ns')
        horizontal.grid(row=1, column=0, sticky='ew')
        for key, label, width in columns:
            table.heading(key, text=label)
            minimum = max(65, self._metrics_font.measure(label) + 20)
            table.column(key, width=max(width, minimum), minwidth=minimum, stretch=(key in ('name', 'path')))
        flexible = next((key for key, _, _ in columns if key in ('name', 'path')), None)
        if flexible is not None:
            def fit_columns(event):
                fixed = sum(int(table.column(key, 'width')) for key, _, _ in columns if key != flexible)
                width = max(int(table.column(flexible, 'minwidth')), event.width - fixed - 4)
                if int(table.column(flexible, 'width')) != width:
                    table.column(flexible, width=width)
            table.bind('<Configure>', fit_columns, add='+')
        return table

    def _render_library(self, page):
        row = self._frame(page)
        row.pack(fill='x')
        self._label(row, 'GitHub 仓库', width=13).pack(side='left')
        self._entry(row, self.repository).pack(side='left', fill='x', expand=True, padx=(0, 8))
        self._button(row, '连接仓库', self._connect).pack(side='left', padx=(0, 8))
        self._button(row, '登录 GitHub', self._login).pack(side='left')
        network = self._frame(page)
        network.pack(fill='x', pady=(8, 0))
        self._label(network, '网络连接', width=13).pack(side='left')
        self._combo(network, self.proxy_mode, list(PROXY_MODES)).pack(side='left')
        self.proxy_settings_button = self._button(network, '代理设置…', self._proxy_settings)
        self.proxy_settings_button.pack(side='left', padx=8)
        self.proxy_test_button = self._button(network, '测试连接', self._test_proxy)
        self.proxy_test_button.pack(side='left')
        self._label(page, variable=self.proxy_info, muted=True, wraplength=1000).pack(fill='x', pady=(6, 0))
        self._label(page, variable=self.connection_info, muted=True, wraplength=1000).pack(fill='x', pady=(8, 4))
        row = self._frame(page)
        row.pack(fill='x', pady=(8, 0))
        self._combo(row, self.view_source, ['GitHub', '本地模板库', '共享模板库']).pack(side='left', padx=(0, 10))
        self._label(row, '作者').pack(side='left', padx=(0, 6))
        self.author_combo = self._combo(row, self.author_filter, ['全部作者'])
        self.author_combo.pack(side='left', fill='x', expand=True)
        row = self._frame(page)
        row.pack(fill='x', pady=(8, 0))
        self._label(row, '搜索').pack(side='left', padx=(0, 6))
        self._entry(row, self.search).pack(side='left', fill='x', expand=True)
        self._label(row, '排序').pack(side='left', padx=(10, 0))
        self._combo(row, self.release_sort, list(SORT_OPTIONS)).pack(side='left', padx=(10, 0))
        self._button(row, '刷新列表', self.refresh).pack(side='left', padx=(10, 0))
        self.view_source.trace_add('write', lambda *args: self.refresh())
        self.library_table = self._table(page, [('name', '模板', 260), ('author', '作者', 110),
            ('version', '版本', 100), ('examples', '示例', 95), ('size', '包大小', 100), ('date', '发布时间', 160)])
        self.library_table.heading('date', command=lambda: self.release_sort.set(next(iter(SORT_OPTIONS))))
        self.library_table.heading('version', command=self._toggle_version_sort)
        self.library_table.bind('<<TreeviewSelect>>', self._select_release)
        self.library_table.bind('<Double-1>', lambda event: self._use_selected())
        self.empty_hint = ttk.Frame(self.library_table, style='TM.Empty.TFrame')
        self._set_empty_hint('连接 GitHub 仓库，浏览团队模板版本。\n也可选择本地模板库使用已下载的版本。')
        self.library_table.bind('<Configure>', self._layout_empty_hint, add='+')
        info = self._label(page, variable=self.release_info, wraplength=1000, muted=True)
        actions = self._frame(page)
        actions.pack(side='bottom', fill='x', pady=(6, 0), before=self.library_table.master)
        info.pack(side='bottom', fill='x', pady=5, before=self.library_table.master)
        self.library_actions = {}
        for label, callback in [('拉取并使用 →', self._use_selected), ('在 GitHub 查看', self._browse_release),
                                ('导入包', self._import), ('导出包', self._export), ('上传本地包', self._upload_selected)]:
            button = self._button(actions, label, callback)
            button.pack(side='left', padx=(0, 8))
            self.library_actions[label] = button
        self._library_states()

    def _render_update(self, page):
        heading = self._frame(page)
        heading.pack(fill='x')
        self._label(heading, '预览变更 → 更新当前会话 → 界面自动刷新' if self.session is not None else
                    '预览变更 → 生成新工程 → 在 OMFIT 打开', muted=True).pack(side='left')
        if self.session is not None:
            self._label(page, '当前 OMFIT 工程：' + (self.current.get() or '未命名工程（尚未保存）'),
                        muted=True, wraplength=1000).pack(fill='x', pady=7)
        else:
            self._path_row(page, '当前工程 ZIP', self.current, lambda: self._choose_zip(self.current))
        self._path_row(page, '选用模板包', self.template_path, lambda: self._choose_zip(self.template_path, template=True))
        if self.session is None:
            self._path_row(page, '输出工程 ZIP', self.output, self._choose_output)
        row = self._frame(page)
        row.pack(fill='x', pady=7)
        data_label = self._label(row, '案例与结果')
        data_choice = self._combo(row, self.data_policy, list(DATA_OPTIONS))
        settings_label = self._label(row, '设置')
        settings_choice = self._combo(row, self.settings_policy, list(SETTING_OPTIONS))
        def layout_policies(event=None):
            needed = sum(widget.winfo_reqwidth() for widget in (data_label, data_choice, settings_label, settings_choice)) + 48
            stacked = row.winfo_width() < needed
            data_label.grid(row=0, column=0, sticky='w', padx=(0, 8), pady=3)
            data_choice.grid(row=0, column=1, sticky='w', pady=3)
            settings_label.grid(row=1 if stacked else 0, column=0 if stacked else 2,
                                sticky='w', padx=(0 if stacked else 24, 8), pady=3)
            settings_choice.grid(row=1 if stacked else 0, column=1 if stacked else 3, sticky='w', pady=3)
        row.bind('<Configure>', layout_policies)
        self._label(page, ('直接更新内存中的工程，保留选中的案例与结果；照常保存工程即可持久保存。'
                          '\n“切换到示例”会替换模板模块内的全部案例与结果。') if self.session is not None else
                    '“切换到示例”替换模板模块内的全部案例与结果；未保存的修改需先在 OMFIT 保存。',
                    muted=True, wraplength=1000).pack(fill='x')
        self.change_table = self._table(page, [('action', '变更', 85), ('path', '节点路径' if self.session else '文件路径', 710), ('size', '大小', 100)])
        summary = self._label(page, variable=self.plan_info, wraplength=1000)
        actions = self._frame(page)
        actions.pack(side='bottom', fill='x', before=self.change_table.master)
        summary.pack(side='bottom', fill='x', pady=5, before=self.change_table.master)
        self._button(actions, '预览变更', self._preview).pack(side='left', padx=(0, 10))
        self.apply_button = self._button(actions, '更新当前工程' if self.session is not None else '生成新工程', self._apply)
        self.apply_button.pack(side='left', padx=(0, 10))
        self.report_button = self._button(actions, '导出完整变更清单', self._save_report)
        self.report_button.pack(side='left')
        self.open_button = self._button(actions, '备份并在 OMFIT 打开', self._open_in_omfit)
        self.undo_button = None
        if self.session is not None:
            self.undo_button = self._button(actions, '撤销本次更新', self._undo_live)
            self.undo_button.pack(side='left', padx=(10, 0))
            self.undo_button.configure(state='normal' if self.session.can_undo_live() else 'disabled')
        self.open_button.configure(state='disabled')
        self.apply_button.configure(state='disabled')
        self.report_button.configure(state='disabled')

    def _render_publish(self, page):
        self._label(page, variable=self.publish_auth_info, wraplength=1000).pack(fill='x', pady=(0, 10))
        self.publish_content = self._frame(page)
        self.publish_content.pack(fill='both', expand=True)
        page = self.publish_content
        heading = self._frame(page)
        heading.pack(fill='x')
        self._label(heading, '每个开发者分别发布版本。默认只包含代码与设置。', muted=True).pack(side='left')
        if self.session is not None:
            self._button(heading, '保存当前 OMFIT 会话…', self._save_session).pack(side='right')
        self._path_row(page, '来源工程 ZIP', self.source, lambda: self._choose_zip(self.source))
        row = self._frame(page)
        row.pack(fill='x', pady=4)
        self._button(row, '读取工程范围', self._inspect).pack(side='left', padx=(0, 12))
        self._label(row, '模块（逗号分隔）').pack(side='left', padx=(0, 8))
        self._entry(row, self.roots).pack(side='left', fill='x', expand=True)
        form = self._frame(page)
        form.pack(fill='x', pady=10)
        form.columnconfigure(1, weight=1)
        form.columnconfigure(3, weight=1)
        for index, (key, label) in enumerate([('name', '显示名称'), ('id', '模板 ID'), ('author', '作者 ID'),
                                             ('version', '版本号'), ('description', '更新说明')]):
            row, column = divmod(index, 2)
            self._label(form, label).grid(row=row, column=column * 2, sticky='w', padx=(0, 10), pady=6)
            entry = self._entry(form, self.metadata[key])
            entry.grid(row=row, column=column * 2 + 1, sticky='ew',
                       padx=(0, 18), pady=6, columnspan=3 if index == 4 else 1)
            if key == 'author':
                self.author_entry = entry
        choices = self._frame(page)
        choices.pack(fill='x', pady=7)
        checkbox = ttk.Checkbutton(choices, text='包含所选模块的全部案例与结果，作为示例',
                                   variable=self.include_examples, style='TM.TCheckbutton')
        checkbox.pack(side='left', padx=(0, 25))
        self.widgets.append((checkbox, 'normal'))
        self._label(choices, '发布到').pack(side='left', padx=(0, 8))
        self._combo(choices, self.publish_destination, ['GitHub', '本地模板库']).pack(side='left')
        self._label(page, '默认只打包代码、模板输入和设置；示例建议来自单独准备的小型工程。', muted=True).pack(anchor='w', pady=(4, 12))
        self._label(page, variable=self.inspection_info, wraplength=1000, justify='left').pack(fill='x')
        bottom = self._frame(page)
        bottom.pack(side='bottom', fill='x', pady=(12, 0))
        self._label(bottom, variable=self.upload_info, wraplength=1000).pack(fill='x', pady=(0, 10))
        actions = self._frame(bottom)
        actions.pack(fill='x')
        self._button(actions, '准备模板包', self._publish).pack(side='left', padx=(0, 10))
        self.files_button = self._button(actions, '查看上传文件', self._show_package)
        self.files_button.pack(side='left', padx=(0, 10))
        self.upload_button = self._button(actions, '发布到 GitHub', self._upload)
        self.upload_button.pack(side='left')
        self.files_button.configure(state='disabled')
        self.upload_button.configure(state='disabled')

    def _render_help(self, page):
        self._path_row(page, '本地模板库', self.library, lambda: self._choose_dir(self.library))
        self._path_row(page, '共享目录（可选）', self.shared, lambda: self._choose_dir(self.shared))
        actions = self._frame(page)
        actions.pack(fill='x')
        self._button(actions, '读取当前工程的更新记录', self._history).pack(side='left')
        self._button(actions, '初始化 GitHub 空仓库', self._initialize_repository).pack(side='left', padx=10)
        self.log = self._text_area(page, wrap='word', background='#ffffff', foreground='#17283d',
                           relief='flat', padx=16, pady=14, height=5)
        scroll = ttk.Scrollbar(page, orient='vertical', command=self.log.yview)
        scroll.pack(side='right', fill='y', pady=(12, 0))
        self.log.configure(yscrollcommand=scroll.set)
        self.log.pack(fill='both', expand=True, pady=(12, 0))
        self._log('使用流程\n\n'
            '1. 打开后自动连接上次的 GitHub 仓库，同时检查管理器更新。登录按钮会打开 Linux 终端运行 gh auth login。\n'
            '2. 选择开发者和版本，“拉取并使用”会下载并校验模板，然后进入更新页。\n'
            '3. 内置管理器直接更新当前内存工程；外部管理器选择已保存的工程 ZIP。\n'
            '4. 默认保留当前设置，并补全新版新增项；模块身份与依赖说明随模板更新。\n'
            '5. 内置模式点击“更新当前工程”，界面自动刷新，照常保存即可；外部模式生成新的工程 ZIP。\n'
            '6. 发布时先准备模板包，查看文件清单与目标仓库，再发布到 GitHub Releases。\n\n'
            '范围说明\n\n'
            '支持自包含、未加密的 OMFIT 工程 ZIP，按顶层模块选择。更新要求模块名称匹配。\n'
            '代码范围：SCRIPTS / PLOTS / GUIS / LIB / TEMPLATES / WORKFLOWS / SOURCE / DOCS / TESTS，'
            '以及模块直属的 Python 脚本、help 与 license。其余内容按数据处理。\n'
            '保留结果时不自动删除旧子模块；结构不兼容会停止并给出原因。\n'
            'GitHub 版本使用 Release 附件分发。Git 分支合并和源码提交仍在原开发流程中完成。\n'
            '登录复用 gh 的当前账号；也支持启动 OMFIT 时已有的 GH_TOKEN / GITHUB_TOKEN。凭据不写入本工具配置或日志。\n'
            '已下载的模板保存在本地模板库，离线时可使用。共享目录也可作额外分发路径。\n'
            '读取与校验模板不会执行其代码。应用生成的工程在 OMFIT 中运行时，才使用该版本代码。\n'
            '发布页在未登录时禁用；作者 ID 自动使用经 GitHub 验证的当前账号。\n'
            'SHA-256 用于验证文件完整性。导入的既有模板仍保留原作者信息。\n')

    def _log(self, message):
        self.log.configure(state='normal')
        self.log.insert('end', message + '\n\n')
        self.log.see('end')
        self.log.configure(state='disabled')

    def _choose_dir(self, variable):
        chosen = filedialog.askdirectory(parent=self.window, initialdir=variable.get() or None)
        if chosen:
            variable.set(chosen)
            self._save_preferences()
            self.refresh()

    def _save_preferences(self):
        temporary = None
        try:
            self.preferences.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode='wb', prefix='.omfit-preferences-',
                                             dir=self.preferences.parent, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(json_bytes({'library': self.library.get().strip(), 'shared': self.shared.get().strip(),
                                         'current': self.current.get().strip(), 'repository': self.repository.get().strip(),
                                         'view_source': self.view_source.get(),
                                         'sort': SORT_OPTIONS.get(self.release_sort.get(), 'published'),
                                         'network': {'mode': PROXY_MODES.get(self.proxy_mode.get(), 'manual'),
                                                     'host': self.proxy_host.get().strip(), 'port': self.proxy_port.get().strip(),
                                                     'username': self.proxy_username.get().strip()}}))
            os.replace(temporary, self.preferences)
        except OSError as exc:
            self._log('库路径未保存：' + str(exc))
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()

    def _choose_zip(self, variable, template=False):
        chosen = filedialog.askopenfilename(parent=self.window,
            filetypes=[('OMFIT 模板', '*' + EXTENSION)] if template else [('OMFIT 工程 ZIP', '*.zip')])
        if chosen:
            variable.set(chosen)

    def _choose_output(self):
        chosen = filedialog.asksaveasfilename(parent=self.window, defaultextension='.zip', filetypes=[('OMFIT 工程 ZIP', '*.zip')],
                                             initialfile=Path(self.output.get()).name or 'OMFIT_updated.zip')
        if chosen:
            self.output.set(chosen)

    def _directory(self, shared=False):
        value = self.shared.get().strip() if shared else self.library.get().strip()
        if not value:
            raise TemplateError('请先选择共享模板库目录' if shared else '请先选择本地模板库目录')
        return Path(value).expanduser().resolve()

    def _error(self, exc):
        if isinstance(exc, GitHubError) and exc.status == 401:
            self._stop_login_check()
            self._set_github_login('')
        self.status.set(str(exc))
        self._log('错误：' + str(exc))
        messagebox.showerror('OMFIT Template Manager', str(exc), parent=self.window)

    def _set_busy(self, value):
        self.busy = value
        for widget, normal_state in self.widgets:
            widget.configure(state='disabled' if value else normal_state)
        self.cancel_button.configure(state='normal' if value else 'disabled')
        self.apply_button.configure(state='normal' if self.plan is not None and not value else 'disabled')
        self.report_button.configure(state='normal' if self.plan is not None and not value else 'disabled')
        self._publish_states()
        self.open_button.configure(state='normal' if self.session is not None and self.last_output and not value else 'disabled')
        if self.undo_button is not None:
            self.undo_button.configure(state='normal' if not value and self.session.can_undo_live() else 'disabled')
        self._library_states()

    def _library_states(self):
        selected = self.selected_release
        for label in ('拉取并使用 →', '导出包', '上传本地包'):
            enabled = bool(selected) and not self.busy
            if label != '拉取并使用 →' and selected and selected.get('remote'):
                enabled = False
            if label == '上传本地包' and not self.github_login:
                enabled = False
            self.library_actions[label].configure(state='normal' if enabled else 'disabled')

    def _publish_states(self):
        enabled = bool(self.github_login) and not self.busy
        def update(parent):
            for child in parent.winfo_children():
                if isinstance(child, ttk.Widget):
                    child.state(['!disabled' if enabled else 'disabled'])
                update(child)
        update(self.publish_content)
        self.author_entry.configure(state='readonly' if enabled else 'disabled')
        self.upload_button.configure(state='normal' if enabled and self.publish_plan is not None else 'disabled')
        self.files_button.configure(state='normal' if enabled and self.package_path is not None else 'disabled')
        self.publish_auth_info.set('已登录 GitHub：' + self.github_login + ' · 作者 ID 自动读取，无需填写。'
            if self.github_login else '未登录 · 发布模板暂不可用。请在“GitHub 版本”页登录；已有登录时点击“连接仓库”。')

    def _set_github_login(self, user):
        if user != self.github_login:
            self.github_login = user
            self._invalidate_publish()
        if self.metadata['author'].get() != user:
            self.metadata['author'].set(user)
        self._publish_states()
        self._library_states()

    def _require_publisher(self):
        if not self.github_login:
            raise TemplateError('请先在“GitHub 版本”页登录并确认账号，再发布模板')

    def _run(self, title, work, success, failure=None):
        if self.busy:
            return
        self.cancel.clear()
        self._show_progress(title)
        self._set_busy(True)

        def runner():
            try:
                result = work()
                self.events.put(('success', success, result))
            except Exception as exc:
                self.events.put(('error', exc, failure))
        threading.Thread(target=runner, name='omfit-template-worker', daemon=True).start()

    def _progress(self, label, done, total):
        self.events.put(('progress', label, done, total))

    def _show_progress(self, label, done=0, total=0):
        """Update Tk on the main thread; unknown work shows activity, not a percent."""
        if total:
            self.progress.stop()
            percent = max(0, min(100, 100 * done / total))
            self.progress.configure(mode='determinate', maximum=100, value=percent)
            self.status.set('{} · {:.1f}% · {} / {}'.format(label, percent, human_size(done), human_size(total)))
        else:
            if str(self.progress.cget('mode')) != 'indeterminate':
                self.progress.stop()
                self.progress.configure(mode='indeterminate', maximum=100, value=0)
                self.progress.start(60)
            self.status.set(label + (' · 已接收 ' + human_size(done) if done else ''))

    def _finish_progress(self, success=False):
        self.progress.stop()
        self.progress.configure(mode='determinate', maximum=100, value=100 if success else 0)

    def _poll(self):
        if not self.alive:
            return
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == 'manager-check':
                    self._automatic_manager_checked(*event[1:])
                elif event[0] == 'login-check':
                    if self.busy:
                        self.events.put(event)
                        break
                    self._login_checked(*event[1:])
                elif event[0] == 'progress':
                    _, label, done, total = event
                    if not self.close_requested:
                        self._show_progress(label, done, total)
                else:
                    self._finish_progress(success=event[0] == 'success')
                    self._set_busy(False)
                    if self.close_requested:
                        if (event[0] == 'error' and not isinstance(event[1], Cancelled)
                                and (len(event) < 3 or event[2] is None)):
                            self._error(event[1])
                        self.close()
                        return
                    if event[0] == 'success':
                        try:
                            event[1](event[2])
                            if not self.alive:
                                return
                        except Exception as exc:
                            self._finish_progress()
                            self._error(exc)
                    elif isinstance(event[1], Cancelled):
                        self.status.set(str(event[1]))
                    elif len(event) > 2 and event[2] is not None:
                        event[2](event[1])
                    else:
                        self._error(event[1])
        except queue.Empty:
            pass
        if self.alive:
            self._poll_after = self.window.after(100, self._poll)

    def refresh(self, automatic=False):
        if self.busy:
            return
        if self.view_source.get() == 'GitHub':
            self._connect(automatic=automatic)
            return
        try:
            directory = self._directory(self.view_source.get() == '共享模板库')
        except TemplateError as exc:
            self.status.set(str(exc))
            return
        self._run('正在读取模板库…', lambda: list_library(directory), self._loaded)

    def _selected_proxy(self):
        mode = PROXY_MODES.get(self.proxy_mode.get(), '')
        if mode == 'system':
            return None
        if mode == 'direct':
            return ''
        if mode == 'manual':
            return manual_proxy(self.proxy_host.get(), self.proxy_port.get(),
                                self.proxy_username.get().strip(), self.proxy_password.get())
        raise TemplateError('请选择网络连接方式')

    def _proxy_hint(self):
        try:
            self.proxy_info.set(connection_label(self._selected_proxy()) + ' · 点击“测试连接”验证 GitHub HTTPS。')
        except TemplateError as exc:
            self.proxy_info.set(str(exc))

    def _proxy_changed(self):
        self._proxy_hint()
        self.connection_info.set('网络设置已更改，请重新连接仓库。')
        self._invalidate_publish()
        if self.view_source.get() == 'GitHub':
            self.releases = []
            self._filter()

    def _test_proxy(self):
        if self.busy:
            return
        try:
            proxy = self._selected_proxy()
        except TemplateError as exc:
            self._error(exc)
            return
        self._save_preferences()
        self._run('正在测试 GitHub HTTPS 连接…',
                  lambda: GitHub(DEFAULT_REPOSITORY, token='', proxy=proxy, cancel=self.cancel).probe(),
                  lambda report: self.proxy_info.set('GitHub HTTPS 连接成功 · ' + report['connection']))

    def _proxy_settings(self):
        if self.busy:
            return
        if self.proxy_dialog is not None and self.proxy_dialog.winfo_exists():
            self.proxy_dialog.lift()
            return
        dialog = self.proxy_dialog = tk.Toplevel(self.window)
        dialog.title('GitHub Proxy Settings')
        dialog.geometry('780x420')
        dialog.minsize(720, 400)
        page = self._frame(dialog, padding=20)
        page.pack(fill='both', expand=True)
        row = self._frame(page)
        row.pack(fill='x', pady=(0, 12))
        self._label(row, '连接方式', width=13).pack(side='left')
        self._combo(row, self.proxy_mode, list(PROXY_MODES)).pack(side='left')
        self._label(page, '默认公共代理：47.102.120.146:18889，用户名和密码留空。',
                    muted=True, wraplength=680).pack(fill='x', pady=(0, 12))
        self._label(page, '手动 HTTP 代理（仅在手动模式下生效）').pack(anchor='w')
        for label, variable in (('主机', self.proxy_host), ('端口', self.proxy_port),
                                ('用户名', self.proxy_username), ('密码', self.proxy_password)):
            row = self._frame(page)
            row.pack(fill='x', pady=4)
            self._label(row, label, width=13).pack(side='left')
            entry = self._entry(row, variable)
            entry.pack(side='left', fill='x', expand=True)
            if variable is self.proxy_password:
                entry.configure(show='•')
        self._label(page, '密码仅在当前窗口内使用。外部浏览器仍使用浏览器自己的网络设置。',
                    muted=True, wraplength=740).pack(fill='x', pady=10)
        def close():
            if self.busy:
                return
            self._save_preferences()
            dialog.destroy()
            self.proxy_dialog = None
            self.widgets[:] = [(widget, normal) for widget, normal in self.widgets if widget.winfo_exists()]
        self._button(page, '保存并关闭', close).pack(side='bottom', anchor='e')
        dialog.protocol('WM_DELETE_WINDOW', close)
        dialog.transient(self.window)
        self._fit_size(dialog, 720, 400)

    def _repository_changed(self):
        self.connection_info.set('仓库已更改，请重新连接。')
        self._invalidate_publish()
        if self.view_source.get() == 'GitHub':
            self.releases = []
            self._filter()

    def _connect(self, automatic=False):
        if self.busy:
            return
        try:
            repo = repository(self.repository.get())
            proxy = self._selected_proxy()
        except TemplateError as exc:
            if automatic:
                self._automatic_connection_failed(exc)
            else:
                self.status.set(str(exc))
            return
        self._save_preferences()
        def work():
            client = GitHub(repo, cancel=self.cancel, progress=self._progress, proxy=proxy)
            return client.connect(), client.list_releases()
        def connected(result):
            info, releases = result
            self._stop_login_check()
            self._set_github_login(info['login'])
            self.connection_info.set('{} · {} · {} · 默认分支 {}'.format(info['repository'],
                '私有仓库' if info['private'] else '公开仓库',
                '登录账号 ' + info['login'] if info['login'] else '未登录，只读访问', info['default_branch']))
            # Switching the source must not start a second concurrent request.
            self.busy = True
            self.view_source.set('GitHub')
            self.busy = False
            self._loaded(releases)
            if not self.releases:
                self.status.set('仓库已连接，尚无模板 Release。可在“发布模板”页准备首个版本。')
            if info.get('empty'):
                self.status.set('仓库为空。登录后可在“设置与记录”页初始化，再发布首个模板版本。')
        self._run('正在连接 GitHub 并读取版本…', work, connected,
                  failure=self._automatic_connection_failed if automatic else None)

    def _automatic_connection_failed(self, exc):
        message = '自动连接仓库未完成：{}。可点击“连接仓库”重试，或使用本地模板库。'.format(exc)
        self.connection_info.set(message)
        self.status.set('自动连接未完成，可重试或使用本地模板。')
        self._log(message)

    def _login(self):
        if self.busy:
            return
        try:
            proxy = self._selected_proxy()
        except TemplateError as exc:
            self._error(exc)
            return
        self._save_preferences()
        self._stop_login_check()
        self._set_github_login('')
        def ready(executable):
            if self.cancel.is_set():
                self.status.set('已取消登录。')
                return
            login(proxy=proxy, executable=executable)
            self.status.set('已打开 GitHub 登录终端。完成浏览器授权后，将自动读取账号并启用发布页。')
            self._login_remaining = 120
            self._login_after = self.window.after(2500, self._check_login)
        self._run('正在准备 GitHub 登录，缺少 gh 时自动安装…',
                  lambda: ensure_cli(GitHub(CLI_REPOSITORY, token='', proxy=proxy,
                                           cancel=self.cancel, progress=self._progress)), ready)

    def _stop_login_check(self):
        self._login_generation += 1
        self._login_remaining = 0
        if self._login_after is not None:
            self.window.after_cancel(self._login_after)
            self._login_after = None

    def _check_login(self):
        self._login_after = None
        if not self.alive or not self._login_remaining:
            return
        if self.busy:
            self._login_after = self.window.after(2500, self._check_login)
            return
        generation = self._login_generation
        try:
            proxy = self._selected_proxy()
        except TemplateError as exc:
            self._login_checked(generation, '', exc)
            return
        def work():
            try:
                user = GitHub(DEFAULT_REPOSITORY, proxy=proxy).current_login()
                self.events.put(('login-check', generation, user, None))
            except Exception as exc:
                self.events.put(('login-check', generation, '', exc))
        threading.Thread(target=work, name='omfit-github-login-check', daemon=True).start()

    def _login_checked(self, generation, user, error):
        if generation != self._login_generation:
            return
        if error is not None:
            self._stop_login_check()
            self._set_github_login('')
            self.status.set('尚未确认登录，请完成授权后点击“连接仓库”。')
            self._log('登录状态检查：' + str(error))
        elif user:
            self._stop_login_check()
            self._set_github_login(user)
            self.connection_info.set('登录账号 ' + user + ' · 点击“连接仓库”读取模板版本与仓库信息。')
            self.status.set('已登录 GitHub：' + user + '。发布页已启用，作者 ID 已自动填入。')
        else:
            self._login_remaining -= 1
            if self._login_remaining:
                self._login_after = self.window.after(2500, self._check_login)
            else:
                self.status.set('尚未完成 GitHub 登录。完成授权后可点击“连接仓库”读取账号。')

    def _initialize_repository(self):
        if self.busy:
            return
        try:
            repo = repository(self.repository.get())
            proxy = self._selected_proxy()
        except TemplateError as exc:
            self._error(exc)
            return
        dialog = tk.Toplevel(self.window)
        dialog.title('Initialize GitHub Repository')
        dialog.geometry('850x600')
        self._label(dialog, '目标：' + repo + ' / README.md\n将创建下面的说明文件和首次提交。', wraplength=800).pack(fill='x', padx=15, pady=15)
        content = self._text_area(dialog, wrap='word', padx=15, pady=10)
        content.pack(fill='both', expand=True, padx=15)
        content.insert('1.0', INITIAL_README)
        content.configure(state='disabled')
        def confirmed():
            dialog.destroy()
            self._run('正在初始化 GitHub 空仓库…', lambda: GitHub(repo, cancel=self.cancel, proxy=proxy).initialize_empty(),
                      lambda url: (self._log('空仓库已初始化：' + url), self._connect()))
        ttk.Button(dialog, text='确认创建 README 和首次提交', command=confirmed, style='TM.TButton').pack(pady=15)
        dialog.transient(self.window)
        dialog.grab_set()

    def _browse_release(self):
        try:
            release = self.selected_release or {}
            url = release.get('url') or 'https://github.com/' + repository(self.repository.get()) + '/releases'
            webbrowser.open(url)
        except TemplateError as exc:
            self._error(exc)

    def _loaded(self, result):
        self.releases, errors = result
        self._filter()
        self.status.set('找到 {} 个版本。{}'.format(len(self.releases), '另有 {} 个包无法读取，详见记录。'.format(len(errors)) if errors else ''))
        if errors:
            self._log('\n'.join(errors))

    def _author_changed(self, *args):
        if not self._updating_authors:
            self._filter()

    def _filter(self):
        authors = sorted({str(item.get('author', '')) for item in self.releases if item.get('author')}, key=str.casefold)
        choices = ['全部作者'] + authors
        self.author_combo.configure(values=choices)
        if self.author_filter.get() not in choices:
            self._updating_authors = True
            try:
                self.author_filter.set('全部作者')
            finally:
                self._updating_authors = False
        author = self.author_filter.get()
        previous = self.selected_release
        self.releases = sort_releases(self.releases, SORT_OPTIONS.get(self.release_sort.get(), 'published'))
        self.library_table.delete(*self.library_table.get_children())
        self.selected_release = None
        self.release_info.set('选择一个版本可查看模块范围与更新说明；双击进入更新页。')
        query = self.search.get().strip().casefold()
        for index, release in enumerate(self.releases):
            if author != '全部作者' and release.get('author', '').casefold() != author.casefold():
                continue
            if query and query not in ' '.join(str(release.get(k, '')) for k in ('name', 'id', 'author', 'version')).casefold():
                continue
            self.library_table.insert('', 'end', iid=str(index), values=(release.get('name', release['id']), release['author'],
                release['version'], '待拉取确认' if release['examples'] is None else '包含示例' if release['examples'] else '无示例',
                human_size(release['archive_bytes']), release.get('created', '')[:16].replace('T', ' ')))
            if previous is not None and release == previous:
                self.library_table.selection_set(str(index))
                self.selected_release = release
        if self.library_table.get_children():
            self.empty_hint.place_forget()
        else:
            self._set_empty_hint('没有匹配的模板。\n请更换作者或调整搜索词。' if query or author != '全部作者' else
                '暂无模板版本。\n在“发布模板”页准备首个版本，或导入已有模板包。')
        self._library_states()

    def _toggle_version_sort(self):
        target = 'version_asc' if SORT_OPTIONS.get(self.release_sort.get()) == 'version' else 'version'
        self.release_sort.set(next(label for label, key in SORT_OPTIONS.items() if key == target))

    def _select_release(self, event=None):
        selected = self.library_table.selection()
        self.selected_release = self.releases[int(selected[0])] if selected else None
        if self.selected_release:
            r = self.selected_release
            self.release_info.set('{}  ·  模块：{}{}\n{}'.format(r['id'], ', '.join(r['roots']) or '拉取后确认',
                ' · GitHub 发布账号 ' + r['publisher'] if r.get('publisher') else '', str(r.get('description', ''))[:250]))
        self._library_states()

    def _require_selection(self):
        if not self.selected_release:
            raise TemplateError('请先在模板库中选择一个版本')
        return dict(self.selected_release)

    def _use_selected(self):
        if self.busy:
            return
        try:
            release = self._require_selection()
            if release.get('remote'):
                library = self._directory()
                proxy = self._selected_proxy()
                self._run('正在拉取所选 GitHub 版本…',
                    lambda: GitHub(release['repository'], cancel=self.cancel, progress=self._progress, proxy=proxy).pull(release, library),
                    self._use_path)
            else:
                self._use_path(release['path'])
        except TemplateError as exc:
            self._error(exc)

    def _use_path(self, path):
        with Template(path) as template:
            release = template.manifest
            self.template_path.set(path)
            if not release['examples']:
                self.data_policy.set(next(iter(DATA_OPTIONS)))
            if self.session is None and self.current.get():
                path = Path(self.current.get())
                self.output.set(str(path.with_name(path.stem + '__' + release['author'] + '_' + release['version'] + '.zip')))
            self.tabs.select(self.pages[1])

    def _transfer(self, source, directory):
        def work():
            with Template(source) as template:
                target = directory / release_name(template.manifest)
            return transfer(source, target, self.cancel, self._progress)
        self._run('正在校验并传输模板…', work, self._transferred)

    def _transferred(self, result):
        self._log('模板已写入：' + result)
        self.status.set('模板已写入：' + result)
        self.refresh()

    def _import(self):
        try:
            directory = self._directory()
            filename = filedialog.askopenfilename(parent=self.window, filetypes=[('OMFIT 模板', '*' + EXTENSION)])
            if filename:
                self._transfer(filename, directory)
        except TemplateError as exc:
            self._error(exc)

    def _export(self):
        try:
            release = self._require_selection()
            if release.get('remote'):
                raise TemplateError('请先“拉取并使用”，再从本地模板库导出')
            filename = filedialog.asksaveasfilename(parent=self.window, initialfile=release_name(release),
                defaultextension=EXTENSION, filetypes=[('OMFIT 模板', '*' + EXTENSION)])
            if filename:
                self._run('正在导出模板…', lambda: transfer(release['path'], filename, self.cancel, self._progress), self._transferred)
        except TemplateError as exc:
            self._error(exc)

    def _save_session(self):
        if self.session is None or self.busy:
            return
        path = filedialog.asksaveasfilename(parent=self.window, title='Save OMFIT Project As',
            initialfile='OMFIT_snapshot.zip', defaultextension='.zip', filetypes=[('OMFIT 工程 ZIP', '*.zip')])
        if not path:
            return
        self._set_busy(True)
        self.status.set('OMFIT 正在保存当前会话…')
        self.window.update_idletasks()
        try:
            saved = self.session.save_as(path)
            self.current.set(saved)
            self.source.set(saved)
            self.status.set('当前会话已保存：' + saved)
            self._log('OMFIT 当前会话另存为：' + saved)
        except Exception as exc:
            self._error(exc)
        finally:
            self._set_busy(False)

    def _open_in_omfit(self):
        if self.session is None or not self.last_output or self.busy:
            return
        target = self.last_output
        if not messagebox.askyesno('Open Updated OMFIT Project',
            '目标工程：' + target + '\n\n将先把当前 OMFIT 会话保存到目标旁的独立备份 ZIP，再打开此工程。继续？', parent=self.window):
            return
        self._set_busy(True)
        self.status.set('正在备份当前会话并在 OMFIT 打开工程…')
        self.window.update_idletasks()
        try:
            backup = self.session.backup_and_open(target)
            self.current.set(target)
            self.source.set(target)
            self.status.set('OMFIT 已打开更新后的工程。')
            self._log('已在 OMFIT 打开：' + target + '\n切换前的会话备份：' + backup)
        except Exception as exc:
            self._error(exc)
        finally:
            self._set_busy(False)

    def _invalidate(self):
        self.plan = None
        self.live_plan = None
        self.plan_info.set('选项已更改，请重新预览。' + ('将更新当前内存工程。' if self.session is not None else '原 ZIP 始终保留。'))
        self.apply_button.configure(state='disabled')
        self.report_button.configure(state='disabled')
        self.change_table.delete(*self.change_table.get_children())

    def _preview(self):
        self._invalidate()
        if self.session is not None:
            path = self.template_path.get().strip()
            if not path:
                self._error(TemplateError('请选择模板包'))
                return
            data, settings = DATA_OPTIONS[self.data_policy.get()], SETTING_OPTIONS[self.settings_policy.get()]
            self._run('正在校验模板并准备当前会话更新…',
                      lambda: Prepared(path, data, settings, cancel=self.cancel), self._live_prepared)
            return
        args = (self.current.get().strip(), self.template_path.get().strip(),
                DATA_OPTIONS[self.data_policy.get()], SETTING_OPTIONS[self.settings_policy.get()])
        if not args[0] or not args[1]:
            self._error(TemplateError('请选择当前工程 ZIP 和模板包'))
            return
        self._run('正在比较…', lambda: plan_update(*args, cancel=self.cancel, progress=self._progress), self._planned)

    def _planned(self, plan):
        self.plan = plan
        labels = {'add': '新增', 'replace': '更新', 'delete': '删除'}
        for change in plan['changes'][:1500]:
            self.change_table.insert('', 'end', values=(labels[change['action']], change['path'],
                                     '—' if plan.get('mode') == 'live' else human_size(change['bytes'])))
        counts = {action: sum(c['action'] == action for c in plan['changes']) for action in labels}
        self.plan_info.set('新增 {add} · 更新 {replace} · 删除 {delete} 个节点；直接在当前会话生效。'.format(**counts)
            if plan.get('mode') == 'live' else '新增 {add} · 更新 {replace} · 删除 {delete}；保留 {keep} 个文件，预计输出约 {size}。{tail}'.format(
            **counts, keep=plan['preserved_files'], size=human_size(plan['output_bytes_estimate']),
            tail='列表显示前 1500 项，可导出完整清单。' if len(plan['changes']) > 1500 else ''))
        scope = []
        for key, label in (('updated_modules', '更新模块'), ('added_modules', '新增模块')):
            if plan.get(key):
                scope.append(label + '：' + '、'.join(plan[key]))
        if scope:
            self.plan_info.set('；'.join(scope) + '\n' + self.plan_info.get())
        self.status.set('预览完成：{} / {} / {}'.format(plan['release']['author'], plan['release']['id'], plan['release']['version']))
        self._set_busy(False)

    def _apply(self):
        if self.plan is None:
            return
        if self.session is not None:
            self._apply_live()
            return
        path = self.output.get().strip()
        if not path:
            self._choose_output()
            path = self.output.get().strip()
        if not path:
            return
        plan = self.plan
        self._run('正在生成新工程…', lambda: apply_update(plan, path, self._progress, self.cancel), self._applied)

    def _applied(self, path):
        self.status.set('已生成新工程。' + ('可点击“备份并在 OMFIT 打开”。' if self.session else '请在 OMFIT 中打开此 ZIP。'))
        self._log('工程生成完成：' + path + '\n原工程（回退用）：' + self.current.get())
        messagebox.showinfo('New OMFIT Project Created', path + '\n\n请在 OMFIT 中打开此 ZIP。原工程已保留，可直接回退。', parent=self.window)
        self._invalidate()
        self.last_output = path
        self._set_busy(False)

    def _live_prepared(self, prepared):
        if self.cancel.is_set():
            return
        self.live_plan = self.session.preview_live(prepared)
        self._planned(self.live_plan.report())

    def _apply_live(self):
        if self.live_plan is None or self.busy:
            return
        self._set_busy(True)
        self.status.set('正在更新当前内存工程并刷新界面…')
        self.window.update_idletasks()
        try:
            report = self.session.apply_live(self.live_plan)
            self._invalidate()
            self.status.set('已更新当前工程至 ' + report['release']['version'] + '，已自动刷新界面。照常保存工程即可。')
            self._log(self.status.get() + '\n' + '、'.join(report['updated_modules']))
        except Exception as exc:
            self._invalidate()
            self._error(exc)
        finally:
            self._set_busy(False)

    def _undo_live(self):
        if self.busy or self.session is None:
            return
        self._set_busy(True)
        try:
            self.session.undo_live()
            self._invalidate()
            self.status.set('已撤销本次模板更新，恢复之前的代码和设置。')
            self._log(self.status.get())
        except Exception as exc:
            self._error(exc)
        finally:
            self._set_busy(False)

    def _save_report(self):
        if self.plan is None:
            return
        filename = filedialog.asksaveasfilename(parent=self.window, initialfile='template_changes.json', defaultextension='.json')
        if filename:
            try:
                with open(filename, 'xb') as stream:
                    stream.write(json_bytes(self.plan))
                self.status.set('变更清单已导出：' + filename)
            except OSError as exc:
                self._error(exc)

    def _inspect(self):
        if not self.github_login:
            self._error(TemplateError('请先登录 GitHub，再准备发布模板'))
            return
        source = self.source.get().strip()
        if not source:
            self._error(TemplateError('请选择来源工程 ZIP'))
            return
        self._run('正在读取工程范围…', lambda: inspect_project(source), self._inspected)

    def _inspected(self, result):
        self.roots.set(', '.join(result['available_roots']))
        self.inspection_info.set('可选模块：{}\n代码：{} / {}；设置：{} / {}；案例与结果：{} / {}。'.format(
            ', '.join(result['available_roots']), result['files'].get('code', 0), human_size(result['bytes'].get('code', 0)),
            result['files'].get('settings', 0), human_size(result['bytes'].get('settings', 0)),
            result['files'].get('data', 0), human_size(result['bytes'].get('data', 0))))
        self.status.set('工程范围已读取；请填写版本信息。')

    def _publish(self):
        try:
            self._require_publisher()
            source = self.source.get().strip()
            roots = sorted(set(x.strip() for x in self.roots.get().replace('，', ',').split(',') if x.strip()))
            metadata = {k: v.get().strip() for k, v in self.metadata.items()}
            metadata['author'] = self.github_login
            release_name(metadata)
            if not source or not roots:
                raise TemplateError('请选择来源工程并读取／填写模块范围')
            directory = self._directory()
            examples = self.include_examples.get()
            self._run('正在发布版本…', lambda: publish(source, directory, metadata, roots, examples,
                                                       self._progress, self.cancel), self._package_built)
        except TemplateError as exc:
            self._error(exc)

    def _published(self, path):
        self._log('版本已发布：' + path)
        self.status.set('版本已发布：' + Path(path).name)
        self.tabs.select(self.pages[0])
        self.view_source.set(self.publish_destination.get())
        self.refresh()

    def _invalidate_publish(self):
        self.publish_plan = None
        self.package_path = None
        self.upload_info.set('内容或目标已改变，请重新准备模板包。')
        self.upload_button.configure(state='disabled')
        self.files_button.configure(state='disabled')

    def _package_built(self, path):
        self.package_path = path
        self._log('模板包已准备：' + path)
        self._set_busy(False)
        if self.publish_destination.get() == 'GitHub':
            self._prepare_upload(path)
        else:
            self._published(path)

    def _upload_selected(self):
        try:
            self._require_publisher()
            release = self._require_selection()
            if release.get('remote'):
                raise TemplateError('请选择本地模板库中的包；GitHub 上已有的版本不能覆盖')
            self.publish_destination.set('GitHub')
            self.package_path = release['path']
            self.tabs.select(self.pages[2])
            self._prepare_upload(release['path'])
        except TemplateError as exc:
            self._error(exc)

    def _prepare_upload(self, path):
        try:
            self._require_publisher()
            repo = repository(self.repository.get())
            proxy = self._selected_proxy()
        except TemplateError as exc:
            self._error(exc)
            return
        def work():
            return GitHub(repo, cancel=self.cancel, progress=self._progress, proxy=proxy).prepare_publish(path)
        self._run('正在校验模板和 GitHub 发布目标…', work, self._prepared)

    def _prepared(self, plan):
        self._set_github_login(plan['login'])
        self.publish_plan = plan
        self.package_path = plan['path']
        metadata = plan['metadata']
        self.upload_info.set('目标：{}（{}） · 账号：{}\n版本：{} · {} · 模块：{} · {}'.format(
            plan['repository'], '私有' if plan['private'] else '公开', plan['login'], plan['tag'],
            human_size(plan['bytes']), ', '.join(metadata['roots']), '包含示例' if metadata['examples'] else '仅代码与设置'))
        self.status.set('模板包与发布目标已核对。可查看完整上传文件清单。')
        self._set_busy(False)

    def _show_package(self):
        if not self.package_path:
            return
        try:
            with Template(self.package_path) as template:
                manifest = template.manifest
                lines = ['模板包：' + self.package_path, '模块：' + ', '.join(manifest['roots']),
                         '案例与结果：' + ('包含' if manifest['examples'] else '不包含'), '']
                lines.extend('{}  {}  {}'.format(spec['kind'], human_size(spec['bytes']), name)
                             for name, spec in sorted(manifest['files'].items()))
            dialog = tk.Toplevel(self.window)
            dialog.title('Template Package Files')
            dialog.geometry('900x580')
            text = self._text_area(dialog, wrap='none', padx=12, pady=12)
            yscroll = ttk.Scrollbar(dialog, orient='vertical', command=text.yview)
            yscroll.pack(side='right', fill='y')
            xscroll = ttk.Scrollbar(dialog, orient='horizontal', command=text.xview)
            xscroll.pack(side='bottom', fill='x')
            text.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
            text.pack(fill='both', expand=True)
            text.insert('1.0', '\n'.join(lines))
            text.configure(state='disabled')
        except Exception as exc:
            self._error(exc)

    def _upload(self):
        if self.publish_plan is None or self.busy or not self.github_login:
            return
        plan = self.publish_plan
        if not messagebox.askyesno('Publish GitHub Release', self.upload_info.get()
            + '\n\n将创建 Release 并上传已准备的模板包。发布此版本？', parent=self.window):
            return
        try:
            proxy = self._selected_proxy()
        except TemplateError as exc:
            self._error(exc)
            return
        def work():
            return GitHub(plan['repository'], cancel=self.cancel, progress=self._progress, proxy=proxy).publish_release(plan)
        def uploaded(url):
            self.publish_plan = None
            self._set_busy(False)
            self._log('GitHub 版本已发布：' + url)
            self.status.set('GitHub 版本已发布。')
            self.tabs.select(self.pages[0])
            if self.view_source.get() != 'GitHub':
                self.view_source.set('GitHub')
            else:
                self.refresh()
        self._run('正在上传并发布 GitHub 版本…', work, uploaded)

    def _history(self):
        if self.session is not None:
            records = self.session.live_history()
            for record in records:
                release = record['release']
                self._log('{} · {} · {} / {} / {}'.format(record['completed_at'],
                    '撤销' if record.get('action') == 'undo' else '会话更新',
                    release['author'], release['id'], release['version']))
            self.status.set('当前会话有 {} 条模板更新记录。'.format(len(records)))
            return
        path = self.current.get().strip()
        if not path:
            self._error(TemplateError('请先在“更新 / 切换”页选择工程 ZIP'))
            return
        def loaded(records):
            self._log('工程更新记录：' + path)
            if not records:
                self._log('此工程尚无模板管理器记录。')
            for record in sorted(records, key=lambda r: r.get('completed_at', '')):
                release = record.get('release', {})
                self._log('{}\n{} / {} / {}\n原工程：{}\n案例策略：{}；设置策略：{}'.format(
                    record.get('completed_at', ''), release.get('author', ''), release.get('id', ''), release.get('version', ''),
                    record.get('current', ''), record.get('data_policy', ''), record.get('settings_policy', '')))
            self.status.set('已读取 {} 条更新记录。'.format(len(records)))
        self._run('正在读取更新记录…', lambda: read_history(path), loaded)

    def close(self):
        self._manager_auto_cancel.set()
        if self.busy:
            self.close_requested = True
            self.cancel.set()
            self.status.set('正在取消操作并清理临时文件…')
            return
        self.alive = False
        self.progress.stop()
        self._stop_login_check()
        self._save_preferences()
        for callback in (self._poll_after, self._refresh_after):
            if callback is None:
                continue
            try:
                self.window.after_cancel(callback)
            except tk.TclError:
                pass
        self.window.update_idletasks()
        self.window.destroy()


def open_manager(current_project='', library=None, preferences=None, session=None):
    """Reuse OMFIT's existing Tk interpreter; only standalone creates a root."""
    parent = tk._default_root
    if parent is not None:
        previous = getattr(parent, '_omfit_template_manager', None)
        if previous is not None and previous.alive and previous.window.winfo_exists():
            previous.window.deiconify()
            previous.window.lift()
            return previous
        window = tk.Toplevel(parent)
    else:
        window = tk.Tk(className='OMFITtemplates')
    manager = TemplateManager(window, current_project=current_project, library=library, preferences=preferences, session=session)
    if parent is not None:
        parent._omfit_template_manager = manager
    else:
        window.mainloop()
    return manager
