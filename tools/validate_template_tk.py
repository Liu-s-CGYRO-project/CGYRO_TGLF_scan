"""Exercise the manager with Tk patches taken directly from an OMFIT checkout.

Example on Linux:
    python3 tools/validate_template_tk.py /path/to/omfit/utils_tk.py

This checks native variable/window/text patches and the real module GUI entry.
The host OMFIT panel and default-font lookup are small adapters; it does not
initialize a complete OMFIT session or run any solver.
"""
import argparse
import ast
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / 'OMFITtemplates'
sys.path[:0] = [str(MODULE / 'LIB'), str(MODULE / 'tests')]
from OMFITlib_template_archive import Project
from OMFITlib_template_service import publish
import OMFITlib_template_ui as ui
from test_templates import fixture


def validate(source):
    source = Path(source).resolve()
    raw = source.read_text(encoding='utf-8')
    selected = ('get_entry_fieldbackground', 'Toplevel', 'Text', '_tkStringVar', '_tkBooleanVar')
    nodes = [node for node in ast.parse(raw).body
             if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in selected]
    assert {node.name for node in nodes} == set(selected)
    root = tk.Tk()
    root.withdraw()
    report = dict(omfit_tk_source=str(source), python=sys.version.split()[0],
                  tk=root.tk.call('package', 'require', 'Tk'),
                  native_patches={node.name: hashlib.sha256(ast.get_source_segment(raw, node).encode()).hexdigest()
                                  for node in nodes}, complete_omfit_session_tested=False)
    original_string, original_boolean = tk.StringVar, tk.BooleanVar
    original_toplevel, original_text = tk.Toplevel, tk.Text
    namespace = dict(tk=tk, ttk=ttk, _Toplevel=original_toplevel, _Text=original_text,
                     _orig_tkStringVar=original_string, _orig_tkBooleanVar=original_boolean,
                     OMFITaux={'rootGUI': root}, OMFITfont=lambda *args: 'TkDefaultFont', ctrlCmd=lambda: 'Control')
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), 'exec'), namespace)
    manager = None
    try:
        with tempfile.TemporaryDirectory(prefix='omfit-native-tk-') as folder, ExitStack() as context:
            folder = Path(folder)
            for attr, name in (('StringVar', '_tkStringVar'), ('BooleanVar', '_tkBooleanVar'),
                               ('Toplevel', 'Toplevel'), ('Text', 'Text')):
                context.enter_context(patch.object(tk, attr, namespace[name]))
            # Verify that the unchanged upstream factory reproduces the report.
            try:
                tk.StringVar(root, 'old positional call')
            except TypeError as error:
                assert 'positional' in str(error)
                report['original_error_reproduced'] = True
            else:
                raise AssertionError('OMFIT factory no longer has the reported positional-argument constraint')
            old, new = folder / 'old.zip', folder / 'new.zip'
            fixture(old, 1)
            fixture(new, 2)
            library = folder / 'library'
            template = publish(new, library, dict(id='native', name='Native Tk', author='test', version='2'), ['Demo'])
            context.enter_context(patch.object(ui, 'default_library', lambda: library))
            context.enter_context(patch.object(ui, 'preferences_path', lambda: folder / 'preferences.json'))
            errors = []
            context.enter_context(patch.object(ui.messagebox, 'showerror', side_effect=lambda title, message, **kw: errors.append(message)))
            context.enter_context(patch.object(ui.messagebox, 'showinfo'))
            buttons = []
            host = SimpleNamespace(TitleGUI=lambda *args, **kw: None, Label=lambda *args, **kw: None,
                                   Button=lambda title, command: buttons.append(command))
            entry = MODULE / 'GUIS/main.py'
            exec(compile(entry.read_text(encoding='utf-8'), str(entry), 'exec'),
                 {'OMFIT': SimpleNamespace(filename=str(old)), 'OMFITx': host})
            manager = root._omfit_template_manager
            assert manager.window.tk is root.tk
            assert isinstance(manager.window, namespace['Toplevel'])
            assert isinstance(manager.log, namespace['Text'])
            assert isinstance(manager.include_examples, original_boolean)
            assert manager.current.get() == str(old)
            assert len(manager.tabs.tabs()) == 4
            assert buttons[0]() is manager
            assert tk.StringVar is namespace['_tkStringVar']  # The manager must not undo OMFIT's patch.
            manager._proxy_settings()
            assert isinstance(manager.proxy_dialog, namespace['Toplevel'])
            assert manager.proxy_password._tk is root.tk
            manager.proxy_password.set('native-test-password')
            manager._save_preferences()
            assert 'native-test-password' not in manager.preferences.read_text(encoding='utf-8')
            close_proxy = next(widget for widget, _ in manager.widgets
                               if widget.winfo_class() == 'TButton' and widget.cget('text') == '保存并关闭')
            close_proxy.invoke()
            manager._set_busy(False)
            report['proxy_dialog_native_variables_and_private_password'] = True
            manager._show_manager_update(dict(current='1.4.0', latest='1.4.0', available=False,
                repository='Liu-s-CGYRO-project/CGYRO_TGLF_scan', notes='管理器独立更新',
                packages={}, url='https://github.com/Liu-s-CGYRO-project/CGYRO_TGLF_scan/releases'))
            assert isinstance(manager.manager_update_dialog, namespace['Toplevel'])
            assert manager.manager_update_dialog.tk is root.tk
            manager._close_manager_update()
            manager._set_busy(False)
            report['manager_update_dialog_native_patches'] = True
            assert manager.window.title() == 'OMFIT Template Manager'
            assert manager.window.title().isascii()
            assert manager.author_entry.instate(['disabled'])
            manager._set_github_login('native-test-author')
            assert manager.metadata['author'].get() == 'native-test-author'
            assert manager.author_entry.instate(['readonly', '!disabled'])
            manager._set_busy(True)
            manager._set_busy(False)
            assert manager.author_entry.instate(['readonly', '!disabled'])
            manager._set_github_login('')
            assert manager.author_entry.instate(['disabled'])
            report['ascii_window_title'] = True
            report['publish_login_gate_and_readonly_account'] = True

            def wait():
                deadline = time.monotonic() + 10
                while manager.busy and time.monotonic() < deadline:
                    root.update()
                    time.sleep(.01)
                assert not manager.busy, 'background action timed out'
                assert not errors, errors

            manager.template_path.set(template)
            manager._preview()
            wait()
            assert manager.plan is not None
            manager.settings_policy.set('使用模板设置')
            assert manager.plan is None  # Native Tk variable traces still fire.
            manager.settings_policy.set('保留当前设置，补全新增项')
            manager._preview()
            wait()
            output = folder / 'updated.zip'
            manager.output.set(str(output))
            manager._apply()
            wait()
            with Project(old) as before, Project(output) as after:
                after.require_entry_first()
                assert before.read('Demo/data/v1.npy') == after.read('Demo/data/v1.npy')
            report.update(real_module_gui_entry=True, native_patched_widgets=True, window_reused=True,
                          correct_master_and_initial_values=True, variable_traces=True,
                          preview_and_generate=True, result_bytes_preserved=True, root_zip_entry=True)
            manager.close()
            assert root.winfo_exists()
            report['parent_session_survives_close'] = True
    finally:
        if manager is not None and manager.alive:
            manager.close()
        root.update_idletasks()
        root.destroy()
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('omfit_tk_source', help='OMFIT checkout omfit/utils_tk.py')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    report = validate(args.omfit_tk_source)
    content = json.dumps(report, indent=2, ensure_ascii=False) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding='utf-8')
    print(content)
