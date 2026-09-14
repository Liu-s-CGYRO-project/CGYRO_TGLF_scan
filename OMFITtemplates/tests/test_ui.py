"""Actual Tk widgets and background actions, with file dialogs replaced in tests."""
from pathlib import Path
import sys
import tempfile
import time
import tkinter as tk
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'LIB'))
from OMFITlib_template_ui import TemplateManager, open_manager
from OMFITlib_template_service import publish
from OMFITlib_template_archive import Project
from test_templates import add_module, fixture


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

    def test_repair_from_ui_requires_no_template_and_keeps_current_project(self):
        self.app.template_path.set('')
        before = self.old.read_bytes()
        output = self.base / 'repaired.zip'
        with patch('OMFITlib_template_ui.filedialog.asksaveasfilename', return_value=str(output)), \
                patch('OMFITlib_template_ui.messagebox.showinfo'):
            self.app.repair_button.invoke()
            self.assertTrue(self.app.repair_button.instate(['disabled']))
            self.wait_idle()
        with Project(output) as result:
            result.require_entry_first()
            self.assertEqual(result.read('Demo/data/v1.npy'), b'UNTOUCHED-RESULT-' + b'\x01' * 4096)
        self.assertEqual(self.old.read_bytes(), before)
        self.assertEqual(self.app.current.get(), str(self.old))
        self.assertEqual(self.app.last_output, str(output))
        self.assertIsNone(self.app.plan)
        self.assertIn('ZIP 入口已修复', self.app.plan_info.get())

    def test_repair_save_dialog_cancel_does_not_start_work(self):
        with patch('OMFITlib_template_ui.filedialog.asksaveasfilename', return_value=''):
            self.app.repair_button.invoke()
        self.assertFalse(self.app.busy)
        self.assertIsNone(self.app.last_output)

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
        for widget in (self.app.apply_button, self.app.report_button, self.app.cancel_button, self.app.repair_button):
            self.assertTrue(widget.winfo_ismapped())
            self.assertLessEqual(widget.winfo_rooty() + widget.winfo_height(), bottom)
            self.assertLessEqual(widget.winfo_rootx() + widget.winfo_width(), self.root.winfo_rootx() + self.root.winfo_width())

    def test_github_connect_pull_and_use_from_real_widgets(self):
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
        self.assertEqual(self.app.template_path.get(), self.template)
        self.assertEqual(self.app.data_policy.get(), '保留当前案例与结果')

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


if __name__ == '__main__':
    unittest.main(verbosity=2)
