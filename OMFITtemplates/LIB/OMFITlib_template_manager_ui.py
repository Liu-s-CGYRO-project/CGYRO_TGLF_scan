"""Manager update dialog shared by standalone Tk and the OMFIT module."""
from builtins import len, str
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import webbrowser

from OMFITlib_template_archive import TemplateError
from OMFITlib_template_github import DEFAULT_REPOSITORY, GitHub
from OMFITlib_template_manager_update import check_manager_update, download_manager_package
from OMFITlib_template_versions import MANAGER_VERSION


class ManagerUpdateUI:
    def _check_manager_update(self):
        if self.busy:
            return
        try:
            proxy = self._selected_proxy()
        except TemplateError as exc:
            self._error(exc)
            return
        self._save_preferences()
        self._run('正在检查管理器自身更新…',
                  lambda: check_manager_update(GitHub(DEFAULT_REPOSITORY, token='', proxy=proxy, cancel=self.cancel)),
                  self._show_manager_update)

    def _close_manager_update(self):
        if self.busy:
            return
        if self.manager_update_dialog is not None:
            self.manager_update_dialog.destroy()
            self.manager_update_dialog = None
            self.widgets[:] = [(widget, state) for widget, state in self.widgets if widget.winfo_exists()]

    def _show_manager_update(self, result):
        self._close_manager_update()
        self.manager_update_result = result
        dialog = self.manager_update_dialog = tk.Toplevel(self.window)
        dialog.title('检查管理器更新')
        dialog.geometry('760x560')
        dialog.minsize(680, 480)
        dialog.transient(self.window)
        page = self._frame(dialog, padding=20)
        page.pack(fill='both', expand=True)
        if not result['latest']:
            summary = '更新源尚未发布独立的管理器版本。'
        elif result['available']:
            summary = '发现管理器新版本 ' + result['latest']
        elif result['latest'] == MANAGER_VERSION:
            summary = '当前管理器已是最新稳定版。'
        else:
            summary = '当前管理器版本高于已发布的稳定版。'
        self._label(page, summary, wraplength=700).pack(fill='x')
        self._label(page, '当前：' + result['current'] + '    最新稳定版：' + (result['latest'] or '暂无'),
                    muted=True).pack(anchor='w', pady=(8, 4))
        self._label(page, '管理器更新源：' + result['repository'] + '\n网络：' + self.proxy_info.get(),
                    muted=True, wraplength=700).pack(fill='x')
        self._label(page, '独立更新模板管理器。下载完成后按说明安装，再重新打开窗口；计算工程的更新仍在“更新 / 切换”页进行。',
                    muted=True, wraplength=700).pack(fill='x', pady=10)
        actions = self._frame(page)
        actions.pack(side='bottom', fill='x', pady=(12, 0))
        self.manager_download_buttons = {}
        for kind, label in (('omfit', '下载 OMFIT 模块'), ('linux', '下载 Linux 管理器')):
            if kind in result['packages']:
                button = self._button(actions, label, lambda selected=kind: self._download_manager_update(selected))
                button.pack(side='left', padx=(0, 8))
                self.manager_download_buttons[kind] = button
        self._button(actions, '关闭', self._close_manager_update).pack(side='right')
        self._button(page, '在 GitHub 查看发布说明', lambda: webbrowser.open(result['url'])).pack(side='bottom', anchor='w')
        if result['latest'] and len(result['packages']) != 2:
            self._label(page, '此版本部分安装包尚未上传完整或缺少校验值，请查看发布说明。',
                        muted=True, wraplength=700).pack(side='bottom', fill='x', pady=8)
        body = self._frame(page)
        body.pack(fill='both', expand=True, pady=8)
        notes = tk.Text(body, wrap='word', font=self.font, height=7, relief='flat', padx=12, pady=10)
        notes.pack(side='left', fill='both', expand=True)
        scroll = ttk.Scrollbar(body, command=notes.yview)
        scroll.pack(side='right', fill='y')
        notes.configure(yscrollcommand=scroll.set)
        notes.insert('1.0', result['notes'] or '暂无发布说明。')
        notes.configure(state='disabled')
        dialog.protocol('WM_DELETE_WINDOW', self._close_manager_update)
        self.status.set(summary)

    def _download_manager_update(self, kind):
        if self.busy:
            return
        try:
            package = self.manager_update_result['packages'][kind]
            proxy = self._selected_proxy()
            output = filedialog.asksaveasfilename(parent=self.manager_update_dialog,
                title='保存管理器安装包', initialfile=package['name'],
                filetypes=[('OMFIT 模块 ZIP', '*.zip')] if kind == 'omfit' else [('Linux 管理器', '*.tar.gz')])
            if not output:
                return
        except (TemplateError, KeyError) as exc:
            self._error(exc)
            return
        def downloaded(path):
            instruction = ('在 OMFIT 使用 Import module 导入此 ZIP，选择 OMFITtemplates；替换原管理模块后保存工程并重新打开管理器。'
                           if kind == 'omfit' else
                           '解压到新目录，运行其中的 start_manager.sh。已有模板库和代理偏好继续保存在原用户配置目录。')
            self.status.set('管理器安装包已下载并通过 SHA-256 校验。')
            messagebox.showinfo('管理器安装包已下载', str(path) + '\n\n' + instruction,
                                parent=self.manager_update_dialog or self.window)
        self._run('正在下载管理器安装包…',
            lambda: download_manager_package(GitHub(DEFAULT_REPOSITORY, token='', proxy=proxy,
                cancel=self.cancel, progress=self._progress), package, output), downloaded)
