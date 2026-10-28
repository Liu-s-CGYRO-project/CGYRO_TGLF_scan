"""Compact, data-aware tabs for all Transfer_tool plot entries."""
from OMFITlib_gui_fonts import configure_window_fonts, style_widget
from builtins import dict, float, isinstance, len, list, min, str, tuple, zip
import tkinter as tk
from tkinter import ttk
from OMFITlib_gui_layout import finish_gui_layout, section_group
from OMFITlib_gui_deferred import TabPages
from OMFITlib_gui_api import plot_view
from OMFITlib_transfer_plot_data import (CATALOG, GROUPS, data_issues, initialize,
                                        parameter_rows, profile_choices)


class TransferPlotsUI:
    def __init__(self, root, ui, readers=None):
        self.root, self.ui = root, ui
        self.readers = readers or {}
        self.settings = initialize(root)
        self.prefix = "root['SETTINGS']['PLOT_OPTIONS']"

    def render(self):
        ui = self.ui
        ui.TitleGUI('Transfer_tool · 剖面绘图')
        anchor = ui.Label('选择数据与绘图内容', align='left')
        choices = profile_choices(self.root)
        if choices:
            ui.ComboBox(self.prefix + "['profile']", choices, '剖面', state='readonly', updateGUI=True, refresh_tree=False)
        else:
            ui.Label('载入或生成 input.gacode 后，可查看剖面和粒子。', align='left')
        with ui.same_row():
            ui.Entry(self.prefix + "['minimum']", '起始半径', width=10, updateGUI=False, refresh_tree=False)
            ui.Entry(self.prefix + "['maximum']", '结束半径', width=10, updateGUI=False, refresh_tree=False)
        ui.Entry(self.prefix + "['ky']", '估算 ky ρs', width=10, updateGUI=False, refresh_tree=False,
                 help='用于 MTM、KBM / BAE 及归一化图的模数与频移换算。')
        self.pages = TabPages(ui, GROUPS, self.settings, 'page',
                              lambda group: self.render_group(group, anchor))
        finish_gui_layout(anchor, ui, compact=True, fit_tabs=True)

    def render_group(self, group, anchor):
        ui = self.ui
        if group == 'estimates':
            ui.Label('解析模型估算，与求解器的稳定性结果分别查看。', align='left')
        elif group == 'transport' and self.readers:
            with section_group(ui, '补充数据'):
                for key, caption in (('gEQDSK', '平衡文件'), ('statefile', 'statefile'),
                                     ('trpltout.nc', 'trpltout.nc'), ('input.profiles', 'input.profiles')):
                    field = 'file_' + key
                    self.settings.setdefault(field, '')
                    ui.FilePicker(self.prefix + '[{!r}]'.format(field), caption, default='',
                                  transferRemoteFile=None, updateGUI=True,
                                  postcommand=lambda location=None, key=key: self.load_auxiliary(key))
        for name, (category, title, description) in CATALOG.items():
            if category != group:
                continue
            # Native file membership checks can parse an entire profile/result.
            # Opening a tab only builds its controls, without inspecting data.
            # draw()/show_parameters() validate only the requested plot.
            with section_group(ui, title):
                ui.Label(description, align='left', wraplength=600)
                callback = (lambda: self.show_parameters(anchor)) if name == 'printinfo' else (
                    lambda name=name: plot_view(self.root['PLOTS'][name + '.py']))
                ui.Button('查看参数表' if name == 'printinfo' else '绘制' + title,
                          callback, updateGUI=False, refresh_tree=False)

    def load_auxiliary(self, key):
        field = 'file_' + key
        selection = self.settings.get(field, '')
        if not selection:
            return
        if isinstance(selection, (tuple, list)):
            if len(selection) != 3:
                raise ValueError('请选择有效的文件地址')
            filename, server, tunnel = selection
        else:
            filename, server, tunnel = selection, 'localhost', ''
        incoming = self.readers[key](str(filename), server=str(server or 'localhost'), tunnel=str(tunnel or ''))
        incoming.keys()
        self.root['INPUTS'][key] = incoming
        self.settings[field] = str(filename)

    def show_parameters(self, anchor):
        issues = data_issues(self.root, 'printinfo')
        if issues:
            raise ValueError('；'.join(issues))
        values = parameter_rows(self.root)
        window = tk.Toplevel(anchor.winfo_toplevel())
        configure_window_fonts(window)
        window.title('Transfer_tool · 局部参数')
        columns = ('nr', 'rho', 'a/LTi', 'a/LTe', 'a/Lne', 'shear', 'q', 'beta_e', 'nu', 'alpha')
        frame = ttk.Frame(window, padding=8)
        frame.pack(fill=tk.BOTH, expand=True)
        table = ttk.Treeview(frame, columns=columns, show='headings', height=min(len(values), 12))
        style_widget(table)
        for key in columns:
            table.heading(key, text=key)
            table.column(key, width=90 if key != 'nr' else 50, minwidth=45, stretch=False)
        for row in values:
            table.insert('', 'end', values=[str(row[0])] + ['{:.6g}'.format(float(value)) for value in row[1:]])
        y = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=table.yview)
        x = ttk.Scrollbar(frame, orient=tk.HORIZONTAL, command=table.xview)
        table.configure(yscrollcommand=y.set, xscrollcommand=x.set)
        table.grid(row=0, column=0, sticky='nsew')
        y.grid(row=0, column=1, sticky='ns')
        x.grid(row=1, column=0, sticky='ew')
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        ttk.Button(window, text='关闭', command=window.destroy).pack(pady=(0, 8))
        window.update_idletasks()
        width = min(window.winfo_reqwidth(), int(window.winfo_screenwidth() * 0.9))
        height = min(window.winfo_reqheight(), int(window.winfo_screenheight() * 0.8))
        window.geometry('{}x{}'.format(width, height))
