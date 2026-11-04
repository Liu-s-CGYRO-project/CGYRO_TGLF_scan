"""Native GUI.update must not traverse a project when opening the manager.

The OMFIT GUI body and Tk bindings are unchanged. The live session and remote
services are host boundaries; no project results or network are accessed.
"""
from contextlib import ExitStack
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_cgyro_storage  # Explicit opaque-reader adapters for native imports.
import test_gui_refresh_native as native
import OMFITlib_template_ui as manager_ui

SOURCE = native.SOURCE
REPO = Path(__file__).resolve().parents[1]


class ManagerEntryTests(unittest.TestCase):
    def setUp(self):
        self.scope = ExitStack()
        self.addCleanup(self.scope.close)
        self.scope.enter_context(patch.object(native, 'SOURCE', SOURCE))
        self.host = native.NativeTkRefreshTests()
        self.addCleanup(self.host.doCleanups)
        self.host.setUp()
        self.addCleanup(self.host.tearDown)
        self.temporary = self.scope.enter_context(tempfile.TemporaryDirectory())
        directory = Path(self.temporary)
        self.scope.enter_context(patch.object(manager_ui, 'preferences_path', return_value=directory/'preferences.json'))
        self.scope.enter_context(patch.object(manager_ui, 'legacy_preferences_path', return_value=directory/'legacy.json'))
        self.scope.enter_context(patch.object(manager_ui, 'default_library', return_value=directory/'library'))
        self.scope.enter_context(patch.object(manager_ui.TemplateManager, '_startup', lambda app: None))
        session = SimpleNamespace(project_path=lambda: '', can_undo_live=lambda: False)
        self.scope.enter_context(patch.dict('sys.modules', {'OMFITlib_template_session':
            SimpleNamespace(OMFITSession=lambda *args, **kw: session)}))
        self.managers = []
        self.addCleanup(self.close_managers)
        self.refreshes = []
        self.host.root.bind('<<update_treeGUI>>', lambda event: self.refreshes.append('project traversal'), add='+')
        self.source = (REPO / 'OMFITtemplates/GUIS/main.py').read_text(encoding='utf-8')

    def close_managers(self):
        for manager in self.managers:
            if manager.alive:
                manager.close()

    def open(self):
        def script(**kwargs):
            namespace = dict(OMFIT={}, OMFITx=self.host.api)
            exec(compile(self.source, 'OMFITtemplates/GUIS/main.py', 'exec'), namespace)
            self.managers.append(namespace['manager'])
        self.host.owner.pythonFile.__run__ = script
        self.host.owner.update()  # Runs the original native GUI.update body.
        return self.managers[-1]

    def test_raw_native_entry_omits_project_repaint_and_keeps_later_events(self):
        manager = self.open()
        self.assertEqual(self.refreshes, [], 'Opening the manager requested a full project traversal')
        self.assertEqual(manager.native_open_events['suppressed'], 1)
        self.host.root.update()
        self.assertFalse(manager.native_open_events['active'])
        self.assertFalse(manager.startup_notices)
        self.assertNotIn('尚无对应', manager.log.get('1.0', 'end'))
        manager._native_diagnostics()
        self.assertIn('尚无对应', manager.log.get('1.0', 'end'))
        self.assertIn('suppressed=1', manager.log.get('1.0', 'end'))
        self.assertIn('0 次拦截不表示错误', manager.log.get('1.0', 'end'))
        self.assertEqual(self.refreshes, [])
        self.host.root.event_generate('<<update_treeGUI>>')
        self.assertEqual(self.refreshes, ['project traversal'])
        manager.tabs.select(3)
        self.host.root.update()
        self.assertEqual(manager.tabs.index(manager.tabs.select()), 3)

    def test_business_event_during_open_is_preserved(self):
        original = manager_ui.open_manager
        def changed(**kwargs):
            manager = original(**kwargs)
            self.host.root.event_generate('<<update_treeGUI>>')
            return manager
        with patch.object(manager_ui, 'open_manager', side_effect=changed):
            manager = self.open()
        self.assertEqual(self.refreshes, ['project traversal'])
        self.assertEqual(manager.native_open_events['suppressed'], 1)

    def test_failed_native_entry_releases_temporary_bindings(self):
        before = self.host.root.bindtags()
        with patch.object(manager_ui, 'open_manager', side_effect=RuntimeError('open failed')):
            with self.assertRaisesRegex(RuntimeError, 'open failed'):
                self.open()
        self.host.root.update()
        self.assertEqual(self.host.root.bindtags(), before)
        self.host.root.event_generate('<<update_treeGUI>>')
        self.assertEqual(self.refreshes, ['project traversal'])

    def test_startup_notice_is_visible_once_without_changing_tabs_or_project(self):
        manager = self.open()
        self.host.root.update()
        tab = manager.tabs.select()
        message = '独立摘要锚点缺失：继续运行当前目录版本'
        before = len(manager.tabs.master.winfo_children())
        manager.show_startup_notice(message)
        manager.show_startup_notice(message)
        self.assertEqual(len(manager.tabs.master.winfo_children()), before + 1)
        self.assertEqual(manager.log.get('1.0', 'end').count(message), 1)
        self.assertEqual(manager.tabs.select(), tab)
        self.assertEqual(self.refreshes, [])


if __name__ == '__main__':
    unittest.main()
