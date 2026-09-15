"""Actual Tk widgets and background actions, with file dialogs replaced in tests."""
from contextlib import contextmanager
import os
import json
import threading
from pathlib import Path
import sys
import tempfile
import time
import tkinter as tk
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'LIB'))
from OMFITlib_template_ui import TemplateManager, open_manager
from OMFITlib_template_service import Cancelled, publish
from test_templates import add_module, fixture


@contextmanager
def omfit_variable_interceptors():
    """Desktop branch of omfit/utils_tk.py's name=None, **kw factories.

    Unlike standard tkinter classes, OMFIT exposes one positional argument
    (name), forwarding master and value only through keyword arguments.
    Keep the real Tk variables so widget bindings and traces are exercised.
    """
    original_string, original_boolean = tk.StringVar, tk.BooleanVar
    created = []

    def _tkStringVar(name=None, **kw):
        result = original_string(name=name, **kw)
        created.append((result, kw))
        return result

    def _tkBooleanVar(name=None, **kw):
        result = original_boolean(name=name, **kw)
        created.append((result, kw))
        return result

    with patch.object(tk, 'StringVar', _tkStringVar), patch.object(tk, 'BooleanVar', _tkBooleanVar):
        yield created


class UITest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.old, self.new = self.base / 'old.zip', self.base / 'new.zip'
        fixture(self.old, 1)
        fixture(self.new, 2)
        self.library = self.base / 'library'
        self.template = publish(self.new, self.library,
            dict(id='test', name='测试', author='local', version='2', description=''), ['Demo'])
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.destroy)
        self.errors = []
        self.dialogs = patch('OMFITlib_template_ui.messagebox.showerror', side_effect=lambda title, text, **kw: self.errors.append(text))
        self.dialogs.start()
        self.addCleanup(self.dialogs.stop)
        self.app = TemplateManager(self.root, str(self.old), self.library, self.base / 'preferences.json')
        self.pump(.25)
        self.wait_idle()

    def destroy(self):
        if self.app.alive:
            self.app.close()

    def pump(self, seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.root.update()
            time.sleep(.01)

    def wait_idle(self):
        deadline = time.monotonic() + 10
        while self.app.busy and time.monotonic() < deadline:
            self.pump(.02)
        self.assertFalse(self.app.busy, 'background action timed out')
        self.assertFalse(self.errors, self.errors)

    def select(self):
        children = self.app.library_table.get_children()
        self.assertEqual(len(children), 1)
        self.app.library_table.selection_set(children[0])
        self.app._select_release()
        self.app._use_selected()

    def test_four_pages_and_real_library(self):
        self.assertEqual(len(self.app.tabs.tabs()), 4)
        self.select()
        self.assertEqual(self.app.template_path.get(), self.template)
        self.assertTrue(self.app.apply_button.instate(['disabled']))

    def test_window_opens_with_python39_named_font_api(self):
        from tkinter import font as tkfont
        child = tk.Toplevel(self.root)
        self.addCleanup(lambda: child.destroy() if child.winfo_exists() else None)
        # Python 3.9 accepts only the name; 3.10 added the root argument.
        def legacy_nametofont(name):
            return tkfont.Font(name=name, exists=True)
        with patch('OMFITlib_template_ui.tkfont.nametofont', legacy_nametofont):
            manager = TemplateManager(child, library=self.library, preferences=self.base / 'legacy-font.json')
        self.addCleanup(lambda: manager.close() if manager.alive else None)
        self.assertEqual(len(manager.tabs.tabs()), 4)
        self.assertGreater(manager._metrics_font.measure('模板管理'), 0)

    def test_font_uses_target_interpreter_without_changing_default_font(self):
        from tkinter import font as tkfont
        other = tk.Tk()
        other.withdraw()
        def destroy_other():
            try:
                other.destroy()
            except tk.TclError:
                pass  # manager.close() already destroyed this interpreter.
        self.addCleanup(destroy_other)
        primary = tkfont.Font(root=self.root, name='TkDefaultFont', exists=True)
        before = primary.actual()
        target = tkfont.Font(root=other, name='TkDefaultFont', exists=True)
        target.configure(size=19)
        manager = TemplateManager(other, library=self.library, preferences=self.base / 'other-font.json')
        self.addCleanup(lambda: manager.close() if manager.alive else None)
        self.assertEqual(manager.font[1], 19)
        self.assertEqual(primary.actual(), before)
        self.assertIn('TkDefaultFont', tkfont.names(root=other))

    def test_preview_then_apply_from_ui(self):
        self.select()
        self.app._preview()
        self.assertTrue(self.app.busy)
        self.assertTrue(self.app.apply_button.instate(['disabled']))
        self.wait_idle()
        self.assertIsNotNone(self.app.plan)
        self.assertFalse(self.app.apply_button.instate(['disabled']))
        target = self.base / 'result.zip'
        self.app.output.set(str(target))
        with patch('OMFITlib_template_ui.messagebox.showinfo'):
            self.app._apply()
            self.wait_idle()
        self.assertTrue(target.exists())
        self.assertIsNone(self.app.plan)

    def test_preview_distinguishes_added_and_updated_modules(self):
        add_module(self.new)
        package = publish(self.new, self.library,
            dict(id='with-added', name='新增模块', author='local', version='3', description=''), ['Demo', 'Added'])
        self.app.template_path.set(package)
        self.app._preview()
        self.wait_idle()
        self.assertIn('更新模块：Demo', self.app.plan_info.get())
        self.assertIn('新增模块：Added', self.app.plan_info.get())
        self.assertFalse(self.app.apply_button.instate(['disabled']))
        self.app.output.set(str(self.base / 'with-added.zip'))
        with patch('OMFITlib_template_ui.messagebox.showinfo'):
            self.app._apply()
            self.wait_idle()
        self.assertTrue((self.base / 'with-added.zip').is_file())

    def test_changed_options_invalidate_preview(self):
        self.select()
        self.app._preview()
        self.wait_idle()
        self.app.settings_policy.set('使用模板设置')
        self.assertIsNone(self.app.plan)
        self.assertTrue(self.app.apply_button.instate(['disabled']))
        self.assertFalse(self.app.change_table.get_children())

    def test_publish_from_ui(self):
        self.app.source.set(str(self.new))
        self.app._inspect()
        self.wait_idle()
        self.app.roots.set('Demo')
        for key, value in dict(id='ui', name='界面发布', author='local', version='1', description='UI regression').items():
            self.app.metadata[key].set(value)
        self.app._publish()
        self.wait_idle()
        self.assertTrue((self.library / 'local__ui__1.omfittpl.zip').exists())

    def test_search_filters_without_changing_files(self):
        self.app.search.set('missing')
        self.assertFalse(self.app.library_table.get_children())
        self.app.search.set('local')
        self.assertEqual(len(self.app.library_table.get_children()), 1)

    def test_screenshot_sorting_and_selected_release_survive_order_change(self):
        from OMFITlib_template_versions import SORT_OPTIONS
        rows = [dict(id='scan', name='扫描', author='alice', version=version, examples=False,
                     archive_bytes=100, roots=[], created='2026-09-14T' + time + ':00Z')
                for version, time in [('2026.09.14.4', '05:16'), ('1.1.1', '09:19'), ('1.0.0', '06:21')]]
        self.app._loaded((rows, []))
        def versions():
            return [self.app.library_table.item(item, 'values')[2] for item in self.app.library_table.get_children()]
        self.assertEqual(versions(), ['1.1.1', '1.0.0', '2026.09.14.4'])
        self.app.library_table.selection_set('0')
        self.app._select_release()
        self.app.release_sort.set(next(label for label, key in SORT_OPTIONS.items() if key == 'version_asc'))
        self.pump(.02)
        self.assertEqual(versions(), ['2026.09.14.4', '1.0.0', '1.1.1'])
        self.assertEqual(self.app.selected_release['version'], '1.1.1')
        self.assertEqual(self.app._require_selection()['version'], '1.1.1')

    def test_manager_check_is_independent_and_uses_the_active_proxy(self):
        from OMFITlib_template_github import DEFAULT_REPOSITORY
        route = 'http://127.0.0.1:32123'
        self.app.proxy_mode.set('手动 HTTP 代理')
        self.app.proxy_host.set('127.0.0.1')
        self.app.proxy_port.set('32123')
        self.app.proxy_username.set('')
        self.app.repository.set('other/template-repository')
        before = self.old.read_bytes(), self.app.current.get(), self.app.template_path.get()
        report = dict(current='1.4.0', latest='1.5.0', available=True, repository=DEFAULT_REPOSITORY,
                      packages={}, notes='更新说明', url='https://github.com/' + DEFAULT_REPOSITORY + '/releases')
        with patch('OMFITlib_template_manager_ui.GitHub') as client, \
                patch('OMFITlib_template_manager_ui.check_manager_update', return_value=report):
            self.app.manager_update_button.invoke()
            self.wait_idle()
        self.assertEqual(client.call_args.args[0], DEFAULT_REPOSITORY)
        self.assertEqual(client.call_args.kwargs['proxy'], route)
        self.assertEqual(client.call_args.kwargs['token'], '')
        self.assertIn('1.5.0', self.app.status.get())
        self.assertEqual(before, (self.old.read_bytes(), self.app.current.get(), self.app.template_path.get()))
        self.assertIs(self.app.manager_update_dialog.tk, self.root.tk)
        self.app._close_manager_update()
        self.app._set_busy(True)
        self.app._set_busy(False)
        self.assertIsNone(self.app.manager_update_dialog)

    def test_manager_download_keeps_current_project_and_reports_installation(self):
        from OMFITlib_template_github import DEFAULT_REPOSITORY
        self.app.proxy_mode.set('不使用代理')
        package = dict(name='OMFIT_template_manager_1.5.0.omfit.zip')
        report = dict(current='1.4.0', latest='1.5.0', available=True, repository=DEFAULT_REPOSITORY,
                      packages={'omfit': package}, notes='修复', url='https://github.com/' + DEFAULT_REPOSITORY + '/releases')
        self.app._show_manager_update(report)
        output = str(self.base / package['name'])
        with patch('OMFITlib_template_manager_ui.filedialog.asksaveasfilename', return_value=output), \
                patch('OMFITlib_template_manager_ui.download_manager_package', return_value=output) as download, \
                patch('OMFITlib_template_manager_ui.messagebox.showinfo') as info:
            self.app.manager_download_buttons['omfit'].invoke()
            self.wait_idle()
        download.assert_called_once()
        self.assertEqual(download.call_args.args[1:], (package, output))
        self.assertIn('Import module', info.call_args.args[1])
        self.assertEqual(self.app.current.get(), str(self.old))
        self.assertIsNone(self.app.last_output)

    def test_omfit_window_reuses_existing_tk(self):
        manager = open_manager(str(self.old), self.library, self.base / 'preferences.json')
        self.assertIsNot(manager.window, self.root)
        self.assertIs(open_manager(), manager)
        self.assertIs(tk._default_root, self.root)
        manager.close()

    def test_library_paths_are_remembered(self):
        self.app.shared.set(str(self.base / 'shared'))
        self.app._save_preferences()
        child = tk.Toplevel(self.root)
        manager = TemplateManager(child, preferences=self.base / 'preferences.json')
        self.assertEqual(manager.library.get(), str(self.library))
        self.assertEqual(manager.shared.get(), str(self.base / 'shared'))
        manager.close()

    def test_controls_visible_at_minimum_window_size(self):
        self.root.deiconify()
        self.root.geometry('940x680')
        self.app.tabs.select(self.app.pages[1])
        self.pump(.15)
        bottom = self.root.winfo_rooty() + self.root.winfo_height()
        for widget in (self.app.apply_button, self.app.report_button, self.app.cancel_button):
            self.assertTrue(widget.winfo_ismapped())
            self.assertLessEqual(widget.winfo_rooty() + widget.winfo_height(), bottom)

    def test_github_connect_pull_and_use_from_real_widgets(self):
        route = 'http://omfit:fixture-secret@127.0.0.1:32123'
        self.app.proxy_host.set('127.0.0.1')
        self.app.proxy_port.set('32123')
        self.app.proxy_username.set('omfit')
        self.app.proxy_password.set('fixture-secret')
        self.app.repository.set('team/demo')
        remote = dict(id='test', name='测试', author='local', version='2', roots=['Demo'], examples=False,
                      archive_bytes=1024, repository='team/demo', remote=True, asset_id=17, publisher='developer')
        with patch('OMFITlib_template_ui.GitHub') as client:
            client.return_value.connect.return_value = dict(repository='team/demo', private=False,
                login='developer', default_branch='main', empty=False)
            client.return_value.list_releases.return_value = ([remote], [])
            client.return_value.pull.return_value = self.template
            self.app._connect()
            self.wait_idle()
            self.assertEqual(self.app.view_source.get(), 'GitHub')
            self.app.library_table.selection_set(self.app.library_table.get_children()[0])
            self.app._select_release()
            self.app._use_selected()
            self.wait_idle()
            client.return_value.pull.assert_called_once()
            self.assertTrue(all(call.kwargs['proxy'] == route for call in client.call_args_list))
        self.assertEqual(self.app.template_path.get(), self.template)
        self.assertEqual(self.app.data_policy.get(), '保留当前案例与结果')

    def test_retired_relay_preferences_migrate_in_real_gui_and_save(self):
        self.assertEqual(self.app._selected_proxy(), 'http://47.102.120.146:18889')
        path = self.base / 'old-preferences.json'
        path.write_text(json.dumps({'network': {'mode': 'relay', 'host': '127.0.0.1', 'port': '32123',
            'username': 'omfit', 'script': '/old/relay.sh'}, 'repository': 'team/demo'}))
        child = tk.Toplevel(self.root)
        manager = TemplateManager(child, preferences=path)
        try:
            self.assertEqual(manager.repository.get(), 'team/demo')
            self.assertEqual(manager._selected_proxy(), 'http://47.102.120.146:18889')
            self.assertEqual(manager.proxy_username.get(), '')
            manager._save_preferences()
            saved = json.loads(path.read_text())['network']
            self.assertEqual(saved['mode'], 'manual')
            self.assertNotIn('script', saved)
            self.assertFalse(hasattr(manager, 'relay_script'))
        finally:
            manager.close()

    def test_proxy_probe_login_and_upload_share_the_selected_route(self):
        route = 'http://omfit:fixture-secret@127.0.0.1:32123'
        self.app.proxy_host.set('127.0.0.1')
        self.app.proxy_port.set('32123')
        self.app.proxy_username.set('omfit')
        self.app.proxy_password.set('fixture-secret')
        plan = dict(repository='team/demo', private=False, login='dev', tag='tag', bytes=1,
                    path=self.template, metadata=dict(roots=['Demo'], examples=False))
        with patch('OMFITlib_template_ui.GitHub') as client, patch('OMFITlib_template_ui.login') as login, \
                patch('OMFITlib_template_ui.messagebox.askyesno', return_value=True), patch.object(self.app, '_connect'), \
                patch('OMFITlib_template_ui.ensure_cli', return_value='/fixture/gh'):
            client.return_value.probe.return_value = dict(connection='HTTP 代理 127.0.0.1:32123')
            client.return_value.prepare_publish.return_value = plan
            client.return_value.publish_release.return_value = 'https://github.com/team/demo/releases/tag/tag'
            self.app._test_proxy()
            self.wait_idle()
            self.app._login()
            self.wait_idle()
            login.assert_called_once_with(proxy=route, executable='/fixture/gh')
            self.app._prepare_upload(self.template)
            self.wait_idle()
            self.app._upload()
            self.wait_idle()
            client.return_value.publish_release.assert_called_once_with(plan)
            self.assertTrue(all(call.kwargs['proxy'] == route for call in client.call_args_list))

    def test_proxy_preferences_do_not_store_password(self):
        self.app.proxy_mode.set('手动 HTTP 代理')
        self.app.proxy_port.set('32123')
        self.app.proxy_password.set('private-test-password')
        self.app._save_preferences()
        content = (self.base / 'preferences.json').read_text()
        self.assertNotIn('private-test', content)
        child = tk.Toplevel(self.root)
        manager = TemplateManager(child, preferences=self.base / 'preferences.json')
        self.assertEqual(manager.proxy_port.get(), '32123')
        self.assertEqual(manager.proxy_password.get(), '')
        manager.close()

    def test_proxy_dialog_widgets_survive_close_and_background_state_changes(self):
        self.root.deiconify()
        self.root.geometry('940x680')
        self.app.tabs.select(self.app.pages[0])
        self.app._proxy_settings()
        self.pump(.2)
        dialog = self.app.proxy_dialog
        for parent in (self.root, dialog):
            left, top = parent.winfo_rootx(), parent.winfo_rooty()
            right, bottom = left + parent.winfo_width(), top + parent.winfo_height()
            def check(widget):
                for child in widget.winfo_children():
                    if child.winfo_class() == 'Toplevel':
                        continue
                    if child.winfo_ismapped() and child.winfo_class() in ('TButton', 'TEntry', 'TCombobox'):
                        self.assertGreaterEqual(child.winfo_rootx(), left)
                        self.assertGreaterEqual(child.winfo_rooty(), top)
                        self.assertLessEqual(child.winfo_rootx() + child.winfo_width(), right)
                        self.assertLessEqual(child.winfo_rooty() + child.winfo_height(), bottom)
                    check(child)
            check(parent)
        close = next(widget for widget, _ in self.app.widgets
                     if widget.winfo_class() == 'TButton' and widget.cget('text') == '保存并关闭')
        close.invoke()
        self.assertIsNone(self.app.proxy_dialog)
        self.app._set_busy(True)
        self.app._set_busy(False)
        self.app._proxy_settings()
        self.assertTrue(self.app.proxy_dialog.winfo_exists())

    def test_login_installs_in_background_then_opens_login_with_current_proxy(self):
        entered, release = threading.Event(), threading.Event()
        before = dict(os.environ)
        def install(client):
            self.assertEqual(client.repo, 'cli/cli')
            self.assertEqual(client._token, '')
            self.assertEqual(client.connection, 'HTTP 代理 47.102.120.146:18889')
            client.progress('正在下载 GitHub CLI', 5, 10)
            entered.set()
            self.assertTrue(release.wait(5))
            return '/fixture/gh'
        with patch('OMFITlib_template_ui.ensure_cli', side_effect=install) as prepare, \
                patch('OMFITlib_template_ui.login') as login:
            self.app._login()
            try:
                self.assertTrue(entered.wait(2))
                self.pump(.15)
                self.assertTrue(self.app.busy)
                self.assertIn('正在下载 GitHub CLI', self.app.status.get())
                login.assert_not_called()
                self.app._login()
                prepare.assert_called_once()
            finally:
                release.set()
            self.wait_idle()
            login.assert_called_once_with(proxy='http://47.102.120.146:18889', executable='/fixture/gh')
        self.assertEqual(dict(os.environ), before)

    def test_cancelled_install_does_not_launch_login(self):
        with patch('OMFITlib_template_ui.ensure_cli', side_effect=Cancelled('安装已取消')), \
                patch('OMFITlib_template_ui.login') as login:
            self.app._login()
            self.wait_idle()
            login.assert_not_called()
        self.assertFalse(self.errors)
        self.assertIn('取消', self.app.status.get())

    def test_upload_requires_prepared_plan_and_user_click(self):
        self.app.repository.set('team/demo')
        plan = dict(repository='team/demo', private=False, login='developer', tag='omfit/local/test/2',
                    bytes=1024, path=self.template, metadata=dict(roots=['Demo'], examples=False))
        self.app._prepared(plan)
        self.assertFalse(self.app.upload_button.instate(['disabled']))
        with patch('OMFITlib_template_ui.GitHub') as client, patch('OMFITlib_template_ui.messagebox.askyesno', return_value=False):
            self.app._upload()
            client.assert_not_called()
        self.app.metadata['description'].set('edited after preview')
        self.assertIsNone(self.app.publish_plan)
        self.assertTrue(self.app.upload_button.instate(['disabled']))

    def test_repository_change_invalidates_remote_list_and_publish_target(self):
        self.app._prepared(dict(repository='team/demo', private=False, login='dev', tag='tag', bytes=1,
            path=self.template, metadata=dict(roots=['Demo'], examples=False)))
        self.app.repository.set('other/repo')
        self.assertIsNone(self.app.publish_plan)
        self.assertIn('重新连接', self.app.connection_info.get())

    def test_native_session_save_and_open_run_on_tk_thread(self):
        from unittest.mock import Mock
        self.app.session = Mock()
        snapshot = str(self.base / 'snapshot.zip')
        self.app.session.save_as.return_value = snapshot
        with patch('OMFITlib_template_ui.filedialog.asksaveasfilename', return_value=snapshot):
            self.app._save_session()
        self.assertEqual(self.app.current.get(), snapshot)
        self.assertEqual(self.app.source.get(), snapshot)
        self.app.last_output = str(self.new)
        self.app.session.backup_and_open.return_value = snapshot
        with patch('OMFITlib_template_ui.messagebox.askyesno', return_value=True):
            self.app._open_in_omfit()
        self.app.session.backup_and_open.assert_called_once_with(str(self.new))
        self.assertEqual(self.app.current.get(), str(self.new))

    def test_publish_controls_visible_in_omfit_minimum_window(self):
        from unittest.mock import Mock
        child = tk.Toplevel(self.root)
        session = Mock()
        session.project_path.return_value = str(self.old)
        manager = TemplateManager(child, library=self.library, preferences=self.base / 'native.json', session=session)
        self.addCleanup(lambda: manager.close() if manager.alive else None)
        child.geometry('940x680')
        manager.tabs.select(manager.pages[2])
        self.pump(.3)
        bottom = child.winfo_rooty() + child.winfo_height()
        for widget in (manager.upload_button, manager.files_button, manager.cancel_button):
            self.assertTrue(widget.winfo_ismapped())
            self.assertLessEqual(widget.winfo_rooty() + widget.winfo_height(), bottom)

    def test_new_omfit_session_does_not_reuse_other_project_preference(self):
        from unittest.mock import Mock
        self.app._save_preferences()
        child = tk.Toplevel(self.root)
        session = Mock()
        session.project_path.return_value = ''
        manager = TemplateManager(child, preferences=self.base / 'preferences.json', session=session)
        self.assertEqual(manager.current.get(), '')
        manager.close()

    def test_omfit_variable_factories_open_preview_and_generate_project(self):
        from types import SimpleNamespace
        from OMFITlib_template_archive import Project
        from OMFITlib_template_session import OMFITSession
        with omfit_variable_interceptors() as created:
            manager = open_manager(library=self.library, preferences=self.base / 'omfit-vars.json',
                                   session=OMFITSession(SimpleNamespace(filename=str(self.old))))
            self.addCleanup(lambda: manager.close() if manager.alive else None)
            self.assertGreater(len(created), 20)
            self.assertEqual(len({str(variable) for variable, _ in created}), len(created))
            for variable, keywords in created:
                self.assertIs(keywords['master'], manager.window)
                self.assertIs(variable._tk, manager.window.tk)
                self.assertIn('value', keywords)
            self.assertEqual(manager.current.get(), str(self.old))
            self.assertEqual(manager.library.get(), str(self.library))
            self.assertFalse(manager.include_examples.get())
            manager.include_examples.set(True)
            self.assertTrue(manager.include_examples.get())
            manager.metadata['name'].set('Independent name')
            self.assertEqual(manager.metadata['author'].get(), '')
            manager.template_path.set(self.template)
            manager._preview()
            deadline = time.monotonic() + 10
            while manager.busy and time.monotonic() < deadline:
                self.pump(.02)
            self.assertFalse(manager.busy)
            self.assertFalse(self.errors, self.errors)
            self.assertIsNotNone(manager.plan)
            target = self.base / 'omfit-vars-updated.zip'
            manager.output.set(str(target))
            with patch('OMFITlib_template_ui.messagebox.showinfo'):
                manager._apply()
                deadline = time.monotonic() + 10
                while manager.busy and time.monotonic() < deadline:
                    self.pump(.02)
            self.assertFalse(manager.busy)
            self.assertFalse(self.errors, self.errors)
            with Project(self.old) as source, Project(target) as result:
                result.require_entry_first()
                self.assertEqual(source.read('Demo/data/v1.npy'), result.read('Demo/data/v1.npy'))
            self.assertIsNone(manager.plan)
            manager.close()
        self.assertTrue(self.root.winfo_exists())

    def test_omfit_variable_factories_bind_to_target_interpreter(self):
        other = tk.Tk()
        other.withdraw()
        self.addCleanup(other.destroy)
        child = tk.Toplevel(other)
        with omfit_variable_interceptors() as created:
            manager = TemplateManager(child, library=self.library, preferences=self.base / 'other-vars.json')
            self.addCleanup(lambda: manager.close() if manager.alive else None)
            for variable, _ in created:
                self.assertIs(variable._tk, other.tk)
                self.assertIsNot(variable._tk, self.root.tk)
            manager.search.set('second interpreter')
            self.assertEqual(other.getvar(str(manager.search)), 'second interpreter')
            self.assertEqual(self.app.search.get(), '')
            manager.close()


if __name__ == '__main__':
    unittest.main(verbosity=2)
