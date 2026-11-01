"""Native File callback boundaries with real Tk menus and guarded projects.

The supplied core provides callback/action bodies. No real project, result
file or scheduler is opened; tests fail if menu expansion requests them.
"""
import ast
import copy
from pathlib import Path
import sys
import tkinter as tk
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO.parents[2] / 'OMFIT-source-ASIPP_unstable/omfit'
sys.path.insert(0, str(REPO / 'tools'))
import repair_omfit_file_menu as repair


def native_method(source, name):
    tree = ast.parse(source)
    gui = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'OMFITgui')
    return next(node for node in gui.body if isinstance(node, ast.FunctionDef) and node.name == name)


def file_callback(source, menu, project, gui):
    method = native_method(source, 'dropdownMenu')
    for index, statement in enumerate(method.body):
        if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call):
            call = statement.value
            if (isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name)
                    and call.func.value.id == 'filemenu' and call.func.attr == 'config'
                    and any(keyword.arg == 'postcommand' for keyword in call.keywords)):
                callback = copy.deepcopy(method.body[index-1])
                break
    else:
        raise AssertionError('Native File callback not found')
    namespace = dict(tk=tk, filemenu=menu, OMFIT=project, self=gui,
                     os=SimpleNamespace(W_OK=2, access=Mock(side_effect=AssertionError('menu filesystem access'))))
    exec(compile(ast.Module(body=[callback], type_ignores=[]), '<native-file-menu>', 'exec'), namespace)
    return namespace['update']


class MetadataOnlyProject:
    filename = '/unavailable-nfs/project.zip'

    def __getattr__(self, name):
        raise AssertionError('Menu requested project data: ' + name)

    def __iter__(self):
        raise AssertionError('Menu traversed project data')


class FileMenuTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = (SOURCE / 'omfit_gui.py').read_bytes()
        cls.updated = repair.patched_source(cls.original)

    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.menu = tk.Menu(self.root, tearoff=False)
        self.commands = []
        names = ('New project', 'Open project...', 'Save project', 'Save project as...', 'Save remote copy of project...',
                 None, 'Compare to project...', None, 'New module...', 'Import module...', 'Reload modules...',
                 'Export modules...', None, 'Load regression script...')
        for name in names:
            if name is None:
                self.menu.add_separator()
            else:
                self.menu.add_command(label=name, command=lambda name=name: self.commands.append(name))
        self.gui = SimpleNamespace(filemenu=self.menu,
            force_selection=Mock(side_effect=AssertionError('Menu resolved tree selection')))
        self.project = MetadataOnlyProject()
        self.original_calls = []
        self.menu.configure(postcommand=lambda: self.original_calls.append('original'))
        self.original_post = str(self.menu.cget('postcommand'))

    def post(self):
        self.menu.tk.call(self.menu.cget('postcommand'))

    def test_unfixed_native_callback_reproduces_selection_resolution(self):
        with self.assertRaisesRegex(AssertionError, 'tree selection'):
            file_callback(self.original, self.menu, self.project, self.gui)()

    def test_unfixed_native_callback_traverses_project_even_with_selection_stubbed(self):
        self.gui.force_selection = lambda: None
        with self.assertRaisesRegex(AssertionError, 'moduleDict'):
            file_callback(self.original, self.menu, self.project, self.gui)()

    def test_patched_native_menu_reopens_without_project_or_filesystem_access(self):
        callback = file_callback(self.updated, self.menu, self.project, self.gui)
        for _ in range(100):
            callback()
        self.gui.force_selection.assert_not_called()
        self.assertEqual(self.menu.entrycget(2, 'state'), 'normal')

    def test_patched_native_save_state_follows_project_changes(self):
        callback = file_callback(self.updated, self.menu, self.project, self.gui)
        self.project.filename = ''
        callback()
        self.assertEqual(self.menu.entrycget(2, 'state'), 'disabled')
        self.project.filename = '/new/project.zip'
        callback()
        self.assertEqual(self.menu.entrycget(2, 'state'), 'normal')

    def test_live_install_is_bounded_and_preserves_action_commands(self):
        before = {i: self.menu.entrycget(i, 'command') for i in (0, 1, 2, 10, 11)}
        self.menu.entryconfigure(10, state='disabled')
        self.assertEqual(repair.install(self.gui, self.project), 'installed')
        for _ in range(100):
            self.post()
        self.assertEqual(self.original_calls, [])
        self.assertEqual(self.commands, [])
        for index, command in before.items():
            self.assertEqual(self.menu.entrycget(index, 'command'), command)
        self.menu.invoke(10)
        self.menu.invoke(11)
        self.menu.invoke(2)
        self.assertEqual(self.commands, ['Reload modules...', 'Export modules...', 'Save project'])

    def test_live_install_does_not_cache_save_state(self):
        repair.install(self.gui, self.project)
        self.post()
        self.project.filename = ''
        self.post()
        self.assertEqual(self.menu.entrycget(2, 'state'), 'disabled')

    def test_restore_removes_only_registered_callback_and_restores_states(self):
        self.menu.entryconfigure(11, state='disabled')
        repair.install(self.gui, self.project)
        registered = str(self.menu.cget('postcommand'))
        self.assertEqual(repair.restore(self.gui), 'restored')
        self.assertEqual(str(self.menu.cget('postcommand')), self.original_post)
        self.assertEqual(self.menu.entrycget(11, 'state'), 'disabled')
        self.assertFalse(self.menu.tk.call('info', 'commands', registered))
        self.post()
        self.assertEqual(self.original_calls, ['original'])

    def test_repeated_install_does_not_accumulate_tcl_callbacks(self):
        repair.install(self.gui, self.project)
        commands = list(self.menu._tclCommands)
        self.assertEqual(repair.install(self.gui, self.project), 'already_installed')
        self.assertEqual(self.menu._tclCommands, commands)
        repair.restore(self.gui)
        self.assertEqual(repair.restore(self.gui), 'not_installed')

    def test_restore_does_not_overwrite_later_callback(self):
        repair.install(self.gui, self.project)
        self.menu.configure(postcommand=lambda: None)
        later = str(self.menu.cget('postcommand'))
        with self.assertRaisesRegex(ValueError, 'changed after'):
            repair.restore(self.gui)
        self.assertEqual(str(self.menu.cget('postcommand')), later)

    def test_unknown_menu_is_unchanged(self):
        self.menu.entryconfigure(2, label='Other save implementation')
        with self.assertRaisesRegex(ValueError, 'Unrecognized'):
            repair.install(self.gui, self.project)
        self.assertEqual(str(self.menu.cget('postcommand')), self.original_post)

    def test_native_action_rejects_empty_module_list_before_creating_window(self):
        method = copy.deepcopy(native_method(self.updated, 'OMFITmodules'))
        messages = []
        namespace = dict(OMFIT=SimpleNamespace(moduleDict=Mock(return_value={})), printi=messages.append,
                         tk=SimpleNamespace(Toplevel=Mock(side_effect=AssertionError('empty dialog'))))
        exec(compile(ast.Module(body=[method], type_ignores=[]), '<native-module-action>', 'exec'), namespace)
        namespace['OMFITmodules'](SimpleNamespace(rootGUI=None), 'reload')
        namespace['OMFITmodules'](SimpleNamespace(rootGUI=None), 'export')
        self.assertEqual(len(messages), 2)
        self.assertEqual(namespace['OMFIT'].moduleDict.call_count, 2)

    def test_save_permission_and_all_other_actions_are_unchanged(self):
        for name in ('quickSave', 'saveOMFITas', 'loadOMFIT', 'force_selection'):
            self.assertEqual(ast.dump(native_method(self.original, name)), ast.dump(native_method(self.updated, name)))
        original = native_method(self.original, 'dropdownMenu')
        updated = native_method(self.updated, 'dropdownMenu')
        self.assertEqual(len(original.body), len(updated.body))
        changed = [i for i, (a, b) in enumerate(zip(original.body, updated.body)) if ast.dump(a) != ast.dump(b)]
        self.assertEqual(len(changed), 1)
        self.assertEqual(original.body[changed[0]].name, 'update')

    def test_patch_is_idempotent_python39_compatible_and_preserves_newlines(self):
        self.assertEqual(repair.patched_source(self.updated), self.updated)
        ast.parse(self.updated, feature_version=(3, 9))
        for newline in (b'\n', b'\r\n'):
            source = self.original.replace(b'\r\n', b'\n').replace(b'\n', newline)
            updated = repair.patched_source(source)
            self.assertEqual(b'\r\n' in updated, newline == b'\r\n')

    def test_upstream_callback_changes_are_not_silently_replaced(self):
        source = self.original.replace(b'if len(OMFIT.moduleDict()):', b'if False:')
        with self.assertRaisesRegex(ValueError, 'Unrecognized'):
            repair.patched_source(source)


if __name__ == '__main__':
    unittest.main()
