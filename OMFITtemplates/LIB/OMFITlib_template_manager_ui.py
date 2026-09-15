"""Manager update dialog shared by standalone Tk and the OMFIT module."""
from builtins import len, str
from pathlib import Path
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import webbrowser

from OMFITlib_template_archive import TemplateError, human_size
from OMFITlib_template_github import DEFAULT_REPOSITORY, GitHub
from OMFITlib_template_manager_update import check_manager_update, download_manager_package
from OMFITlib_template_versions import MANAGER_VERSION
from OMFITlib_template_incremental import plan_incremental, install_incremental, activate_installation, restore_activation
from OMFITlib_template_service import Cancelled


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
        sources = self.session.manager_sources() if self.session is not None else {}
        module_dir = Path(__file__).resolve().parents[1]
        def check():
            client = GitHub(DEFAULT_REPOSITORY, token='', proxy=proxy, cancel=self.cancel)
            result = check_manager_update(client)
            if result['available'] and result.get('incremental'):
                try:
                    result['plan'] = plan_incremental(client, result, module_dir, sources)
                except Cancelled:
                    raise
                except TemplateError as exc:
                    result['incremental_error'] = str(exc)
            return result
        self._run('正在检查管理器自身更新并比较本地文件…', check, self._show_manager_update)

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
        dialog.title('OMFIT Template Manager Updates')
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
        self._label(page, '增量更新只下载变更文件，校验后安装并重新打开管理器。当前工程、计算结果和模板库保留；在 OMFIT 中正常保存工程即可保留更新。',
                    muted=True, wraplength=700).pack(fill='x', pady=10)
        plan = result.get('plan')
        self.manager_install_button = None
        if plan:
            self._label(page, '下载 {} 个变更文件（{}），复用 {} 个文件。'.format(
                len(plan['changed']), human_size(plan['download_bytes']), len(plan['reused'])), wraplength=700).pack(fill='x')
            self.manager_install_button = self._button(page, '安装增量更新并重新打开', self._install_manager_update)
            self.manager_install_button.pack(anchor='w', pady=(8, 0))
        elif result['available']:
            self._label(page, result.get('incremental_error') or '此版本未提供增量文件，请下载完整安装包。',
                        muted=True, wraplength=700).pack(fill='x')
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
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        notes = self._text_area(body, wrap='word', height=7, relief='flat', padx=12, pady=10)
        notes.grid(row=0, column=0, sticky='nsew')
        scroll = ttk.Scrollbar(body, command=notes.yview)
        scroll.grid(row=0, column=1, sticky='ns')
        notes.configure(yscrollcommand=scroll.set)
        changes = ('需要更新的文件：\n' + '\n'.join(plan['changed']) + '\n\n发布说明：\n') if plan else ''
        notes.insert('1.0', changes + (result['notes'] or '暂无发布说明。'))
        notes.configure(state='disabled')
        dialog.protocol('WM_DELETE_WINDOW', self._close_manager_update)
        self.status.set(summary)
        self._fit_size(dialog, 680, 480)

    def _install_manager_update(self):
        if self.busy or not self.manager_update_result.get('plan'):
            return
        plan = self.manager_update_result['plan']
        try:
            proxy = self._selected_proxy()
        except TemplateError as exc:
            self._error(exc)
            return
        def install():
            path = install_incremental(GitHub(DEFAULT_REPOSITORY, token='', proxy=proxy,
                cancel=self.cancel, progress=self._progress), plan)
            if self.session is None:
                result = subprocess.run([sys.executable, str(Path(path) / 'OMFITtemplates/launch.py'), '--check-ui'],
                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
                if result.returncode:
                    raise TemplateError('新版启动检查失败，当前版本保留：' + result.stderr.decode('utf-8', errors='replace')[-1000:])
            return path
        self._run('正在安装增量更新；当前版本保留…', install, self._manager_installed)

    def _manager_installed(self, path):
        if self.cancel.is_set():
            self.status.set('已取消版本切换，当前管理器继续运行。')
            return
        path = Path(path)
        self._save_preferences()
        if self.session is not None:
            session = self.session
            parent = self.window.master
            if parent is None:
                raise TemplateError('未找到 OMFIT 主窗口，当前模块保留，请从 OMFIT 重新打开管理器')
            previous = session.replace_manager(path / 'OMFITtemplates')
            self.close()
            def reopen():
                try:
                    session.reopen_manager()
                except Exception as exc:
                    session.restore_manager(previous)
                    messagebox.showerror('Manager Update', '新版管理器未能打开，已恢复原模块：' + str(exc), parent=parent)
                    session.reopen_manager()
            parent.after(100, reopen)
        else:
            previous = activate_installation(path)
            try:
                subprocess.Popen([sys.executable, str(path / 'OMFITtemplates/launch.py'),
                    '--library', self.library.get(), '--project', self.current.get()],
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            except OSError:
                restore_activation(previous)
                raise
            self.close()

    def _download_manager_update(self, kind):
        if self.busy:
            return
        try:
            package = self.manager_update_result['packages'][kind]
            proxy = self._selected_proxy()
            output = filedialog.asksaveasfilename(parent=self.manager_update_dialog,
                title='Save Manager Package', initialfile=package['name'],
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
            messagebox.showinfo('Manager Package Downloaded', str(path) + '\n\n' + instruction,
                                parent=self.manager_update_dialog or self.window)
        self._run('正在下载管理器安装包…',
            lambda: download_manager_package(GitHub(DEFAULT_REPOSITORY, token='', proxy=proxy,
                cancel=self.cancel, progress=self._progress), package, output), downloaded)
