"""On-demand CGYRO task manager. No scheduler calls or persistent result cache.

Rows are keyed by full run_token, never by a table position/display job number.
Filtering and sorting cannot change the selected task's identity. The backend
revalidates the metadata revision after both modal confirmation dialogs.
"""
from builtins import (Exception, ValueError, any, bool, enumerate, len, max, min, set, sorted, str, zip)
import tkinter as tk
from tkinter import messagebox, ttk
from OMFITlib_cgyro_db import ensure_layout
from OMFITlib_cgyro_archive import case_parts
from OMFITlib_cgyro_present import case_caption
from OMFITlib_cgyro_task_catalog import task_catalog
from OMFITlib_cgyro_task_cleanup import preview_tasks
from OMFITlib_gui_fonts import configure_window_fonts, style_widget, unbind_callback


def task_case_caption(case_id):
    parts = case_parts(case_id)
    return ('nr=' + parts[0] + ' · ' if parts is not None else '') + case_caption(case_id)


def task_description(row):
    return '{} | {} | {} | 作业 {} | {}'.format(', '.join(row['servers']) or '未知服务器',
        ', '.join(row['runids']) or '未命名', ', '.join(task_case_caption(c) for c in row['cases']) or '未知案例',
        ', '.join(row['jobs']) or '尚未提交/未取得作业号', row['token'])


def deletion_prompt(report):
    rows = [task_description(row) for row in report['tasks']]
    rows += ['', '删除 {} 条任务记录、冻结输入和 {} 个归档计算点。'.format(len(report['tokens']), report['archived_points']),
             '未归档输出随任务解除引用；归档结果仅在勾选相应选项时解除引用。',
             '物理文件留到明确的存储整理时清理；共享文件仍有引用时始终保留。',
             '其他任务、参数及 ky 结果保留。服务器作业和文件保留，不执行 scancel。',
             '一次扫描及其自动重试作为一条任务；上面已列出该任务的全部作业号。',
             '已准备续算使用自身冻结输入，结果续算使用 RUN_DB 所选文件，不依赖此任务历史。',
             '只修改当前工程；已有 ZIP、服务器目录和 /tmp 文件不在本次删除范围。']
    if report['unknown_points_preserved']:
        rows.append('另有 {} 个身份不明的旧计算点保留，不按名称猜测删除。'.format(report['unknown_points_preserved']))
    return '\n'.join(rows)


def review_scope(title, text, parent=None, icon=None):
    """Scrollable first confirmation; keep its buttons visible on small VNC desktops."""
    window = tk.Toplevel(parent)
    window.withdraw()
    window.title(title)
    configure_window_fonts(window)
    width = max(420, min(920, window.winfo_screenwidth() - 100))
    height = max(280, min(620, window.winfo_screenheight() - 140))
    window.geometry('{}x{}'.format(width, height))
    window.columnconfigure(0, weight=1)
    window.rowconfigure(0, weight=1)
    contents = tk.Text(window, wrap='word', width=60, height=15)
    scroll = ttk.Scrollbar(window, orient=tk.VERTICAL, command=contents.yview)
    contents.configure(yscrollcommand=scroll.set)
    contents.insert('1.0', text)
    contents.configure(state='disabled')
    contents.grid(row=0, column=0, sticky='nsew', padx=(10, 0), pady=10)
    scroll.grid(row=0, column=1, sticky='ns', pady=10, padx=(0, 10))
    accepted = [False]
    def finish(allow=False):
        accepted[0] = allow
        window.destroy()
    buttons = ttk.Frame(window)
    buttons.grid(row=1, column=0, columnspan=2, sticky='ew', padx=10, pady=(0, 10))
    cancel = ttk.Button(buttons, text='取消', command=finish)
    cancel.pack(side=tk.RIGHT)
    ttk.Button(buttons, text='范围正确，继续确认', command=lambda: finish(True)).pack(side=tk.RIGHT, padx=8)
    window.protocol('WM_DELETE_WINDOW', finish)
    window.bind('<Escape>', lambda event: finish())
    window.deiconify()
    window.grab_set()
    cancel.focus_set()
    window.wait_window()
    return accepted[0]


def confirm_scope(parent, text, challenge, first=None, second=None):
    """Confirm twice by clicking; keep the preview credential internal."""
    first, second = first or review_scope, second or messagebox.askokcancel
    if not first('第 1 次确认：核对删除范围', text, parent=parent, icon='warning'):
        return None
    accepted = second('第 2 次确认：确认删除',
        '确认删除已核对的记录和结果？\n此操作无法撤销。',
        parent=parent, icon='warning', default='cancel')
    return challenge if accepted is True else None


def confirm_deletion(parent, report, first=None, second=None):
    """Two independent cancellations; the backend still receives the bound preview."""
    return confirm_scope(parent, deletion_prompt(report), report['confirmation'], first, second)


class TaskManager:
    COLUMNS = ('jobs', 'server', 'run', 'case', 'scan', 'state', 'archived', 'retained', 'token')

    def __init__(self, parent, module, delete, factory=dict, on_changed=None):
        ensure_layout(module, factory)
        self.module, self.delete, self.on_changed = module, delete, on_changed
        self.rows, self.confirming = {}, False
        self.owner = parent.winfo_toplevel()
        # OMFIT rebuilds all children of its settings window. Keep this task
        # window at the interpreter root; an owner refresh must not destroy a
        # confirmation dialog halfway through a deletion transaction.
        self.window = tk.Toplevel(parent._root())
        self.window.transient(self.owner)
        self.owner_binding = self.owner.bind('<Destroy>', self._owner_closed, add='+')
        self.window.bind('<Destroy>', self._window_closed, add='+')
        self.window.withdraw()
        configure_window_fonts(self.window)
        self.window.title('CGYRO · 任务管理与删除')
        width = max(480, min(1200, self.window.winfo_screenwidth() - 80))
        height = max(320, min(740, self.window.winfo_screenheight() - 120))
        self.window.geometry('{}x{}'.format(width, height))
        self.window.minsize(min(width, 640), min(height, 380))
        self.window.columnconfigure(0, weight=1)
        self.window.rowconfigure(2, weight=1)
        self._build_controls(width)
        self.refresh()
        self.window.deiconify()

    def alive(self):
        try:
            return bool(self.window.winfo_exists())
        except tk.TclError:
            return False

    def _owner_closed(self, event):
        if event.widget is self.owner and self.alive():
            self.window.destroy()

    def _window_closed(self, event):
        if event.widget is self.window and self.owner_binding:
            try:
                unbind_callback(self.owner, '<Destroy>', self.owner_binding)
            except tk.TclError:
                pass
            self.owner_binding = None

    def _build_controls(self, width):
        ttk.Label(self.window, text='选择要删除的任务（Ctrl / Shift 多选）。未归档任务也在此列出。',
                  wraplength=width - 40).grid(row=0, column=0, sticky='ew', padx=10, pady=(10, 4))
        filters = ttk.Frame(self.window)
        filters.grid(row=1, column=0, sticky='ew', padx=10, pady=4)
        filters.columnconfigure(1, weight=1)
        ttk.Label(filters, text='查找作业号 / 半径 / 扫描参数').grid(row=0, column=0, padx=(0, 8))
        self.query = tk.StringVar(master=self.window)
        ttk.Entry(filters, textvariable=self.query).grid(row=0, column=1, sticky='ew')
        ttk.Button(filters, text='刷新任务', command=self.refresh).grid(row=0, column=2, padx=8)
        self.query.trace_add('write', lambda *args: self.filter_rows())
        self.delete_results = tk.BooleanVar(master=self.window, value=False)
        ttk.Checkbutton(filters, text='同时删除所选任务的归档结果引用', variable=self.delete_results).grid(
            row=1, column=0, columnspan=3, sticky='w', pady=(6, 0))
        self._build_table()
        self.detail = tk.StringVar(master=self.window, value='尚未选择任务。')
        ttk.Label(self.window, textvariable=self.detail, wraplength=width - 40).grid(
            row=3, column=0, sticky='ew', padx=10, pady=6)
        buttons = ttk.Frame(self.window)
        buttons.grid(row=4, column=0, sticky='ew', padx=10, pady=(0, 10))
        ttk.Button(buttons, text='全选当前列表', command=self.select_visible).pack(side=tk.LEFT)
        ttk.Button(buttons, text='清空选择', command=self.clear_selection).pack(side=tk.LEFT, padx=6)
        self.delete_button = ttk.Button(buttons, text='删除所选任务…', command=self.remove_selected, state='disabled')
        self.delete_button.pack(side=tk.RIGHT)
        ttk.Button(buttons, text='关闭', command=self.window.destroy).pack(side=tk.RIGHT, padx=8)

    def _build_table(self):
        frame = ttk.Frame(self.window)
        frame.grid(row=2, column=0, sticky='nsew', padx=10)
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        self.table = ttk.Treeview(frame, columns=self.COLUMNS, show='headings', selectmode='extended')
        headings = ('作业号（含重试）', '服务器', '结果集', '半径 / 离子', '扫描参数', '任务状态', '归档点', '未归档点', '完整任务标识')
        for name, caption in zip(self.COLUMNS, headings):
            self.table.heading(name, text=caption, command=lambda c=name: self.sort_rows(c))
            self.table.column(name, width=220 if name == 'token' else 150,
                              minwidth=80, stretch=name in ('scan', 'case', 'state'))
        vertical = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.table.yview)
        horizontal = ttk.Scrollbar(frame, orient=tk.HORIZONTAL, command=self.table.xview)
        self.table.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.table.grid(row=0, column=0, sticky='nsew')
        vertical.grid(row=0, column=1, sticky='ns')
        horizontal.grid(row=1, column=0, sticky='ew')
        self.table.bind('<<TreeviewSelect>>', lambda event: self.selection_changed())
        style_widget(self.table)
        self.sort_reverse = {}

    def refresh(self):
        # Explicit refresh rebuilds lightweight metadata once. Search reuses
        # those rows instead of formatting and recreating every Tcl item.
        for token in self.rows:
            self.table.delete(token)
        self.rows = {row['token']: row for row in task_catalog(self.module)}
        self.search_text = {}
        for token, row in self.rows.items():
            values = (', '.join(row['jobs']) or '未提交/未知', ', '.join(row['servers']) or '未知',
                ', '.join(row['runids']), ', '.join(task_case_caption(c) for c in row['cases']),
                ', '.join(row['scans']), ('本地操作中' if row['busy'] else
                ('已归档' if row['archived_points'] is None or row['archived_points'] else '未归档')) + ' / ' + ', '.join(row['statuses']),
                row['archived_points'] if row['archived_points'] is not None else '旧索引未计数', row['retained_points'], token)
            self.search_text[token] = ' '.join(str(v) for v in values).casefold()
            self.table.insert('', 'end', iid=token, values=values)
        self.filter_rows()

    def filter_rows(self):
        # Detached items keep their full task ID, but never a hidden selection.
        self.table.selection_remove(self.table.selection())
        query = self.query.get().strip().casefold()
        self.table.set_children('', *(token for token, text in self.search_text.items()
                                      if not query or query in text))
        self.selection_changed()

    def sort_rows(self, column):
        reverse = self.sort_reverse.get(column, False)
        def key(token):
            row = self.rows[token]
            return ((row['archived_points'] if row['archived_points'] is not None else -1) if column == 'archived' else row['retained_points'] if column == 'retained'
                    else str(self.table.set(token, column)).casefold())
        for index, token in enumerate(sorted(self.table.get_children(), key=key, reverse=reverse)):
            self.table.move(token, '', index)
        self.sort_reverse[column] = not reverse

    def selected_tokens(self):
        visible = set(self.table.get_children())
        return sorted(t for t in self.table.selection() if t in visible and t in self.rows)

    def select_visible(self):
        self.table.selection_set(self.table.get_children())
        self.selection_changed()

    def clear_selection(self):
        self.table.selection_remove(self.table.selection())
        self.selection_changed()

    def selection_changed(self):
        selected = self.selected_tokens()
        busy = any(self.rows[t]['busy'] for t in selected)
        self.delete_button.configure(state='normal' if selected and not busy and not self.confirming else 'disabled')
        self.detail.set(('已选 {} 条任务；删除前还需核对范围并再次确认。'.format(len(selected)) if selected else
                         '共 {} 条已知任务；没有自动选中任何任务。'.format(len(self.rows))) +
                        (' 所选任务有本地操作未结束，暂不能删除。' if busy else ''))

    def remove_selected(self):
        if self.confirming:
            return
        selected = self.selected_tokens()
        if not selected:
            return
        self.confirming = True
        self.selection_changed()
        try:
            report = preview_tasks(self.module, selected, delete_results=self.delete_results.get())
            challenge = confirm_deletion(self.window, report)
            if challenge is None:
                return
            if not self.alive() or self.selected_tokens() != selected:
                raise ValueError('任务选择已变化，请重新核对；未执行删除。')
            self.delete(selected, expected=report, confirmation=challenge)
            self.refresh()
            if self.on_changed is not None:
                self.on_changed()
            if self.alive():
                messagebox.showinfo('任务已删除', '所选任务已从当前工程移除，请另存工程。\n服务器作业和文件保留。', parent=self.window)
        except Exception as error:
            if self.alive():
                messagebox.showerror('未完成任务删除', str(error), parent=self.window)
        finally:
            self.confirming = False
            if self.alive():
                self.selection_changed()
