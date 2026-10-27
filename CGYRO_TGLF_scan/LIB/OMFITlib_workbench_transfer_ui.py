"""Transfer page and draft input editor. Saving is delegated to ProjectActions after digest validation.

Public methods remain inherited by ProjectUI for saved GUIs and callbacks.
Keep OMFITlib imports at module scope: native GUI execution clears its import hook.
"""
from OMFITlib_gui_fonts import configure_window_fonts, gui_font, style_widget
from builtins import dict, isinstance, len, min, next, str, sum
from collections import OrderedDict
import tkinter as tk
from tkinter import ttk
from OMFITlib_transfer_workflow import loaded_file
from OMFITlib_gui_deferred import TabPages
from OMFITlib_project import MODULES, location, module, input_digest, read, transfer_generated_rows, transfer_parameter_value


class TransferPage:
    """Page mixin; state belongs to the host, never to a module singleton."""
    def render_transfer(self):
        renderers = dict(run=self.transfer_run,
            files=lambda: self.transfer_files(transfer_generated_rows(self.root)),
            plots=lambda: self.compound(('Transfer_tool', 'GUIS', 'plots')),
            convert=lambda: self.compound(('Transfer_tool', 'GUIS', 'convert')),
            advanced=self.transfer_advanced)
        self.transfer_pages = TabPages(self.ui, OrderedDict([
            ('run', 'Transfer_tool 运行'), ('files', '生成文件'), ('plots', '剖面绘图'),
            ('convert', '局部输入互转'), ('advanced', '高级设置')]),
            self.settings, 'transfer_tab', lambda page: renderers[page]())

    def transfer_run(self):
        self.compound(('Transfer_tool', 'GUIS', 'transfer'), show_run_button=False)
        self.run_controls('transfer')
        files = transfer_generated_rows(self.root)
        ready = next((row for row in files if 'cgyro' in row['paths']), None)
        if ready is not None:
            self.nav('设置 CGYRO 扫描', 'cgyro', cgyro_source_mode=ready['mode'])

    def transfer_advanced(self):
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
        configure_window_fonts(window)
        window.title('生成输入 · ' + caption)
        width = min(720, window.winfo_screenwidth() - 64)
        height = min(840, window.winfo_screenheight() - 100)
        window.geometry('{}x{}'.format(width, height))
        ttk.Label(window, text=caption, anchor='w').pack(fill=tk.X, padx=10, pady=(10, 6))
        frame = ttk.Frame(window)
        frame.pack(fill=tk.BOTH, expand=True, padx=10)
        style = ttk.Style(window)
        preview_font = gui_font(window, style.lookup('Treeview', 'font') or 'TkDefaultFont')
        style_name = 'TransferPreview' + str(window).replace('.', '_') + '.Treeview'
        style.configure(style_name, font=preview_font, rowheight=preview_font.metrics('linespace') + 8)
        table = ttk.Treeview(frame, columns=('parameter', 'value'), show='headings', style=style_name)
        style_widget(table)
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
        table.tag_configure('changed', background='#eeeeee')
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
