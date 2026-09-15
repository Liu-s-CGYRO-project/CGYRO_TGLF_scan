"""Invoke native Entry / _Text / Lock callbacks with two real Linux Tk windows.

Widget function bodies are unchanged. Tree-location and ScrolledText hosts are
small adapters, so this is not a complete OMFIT process.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import sys
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace
from unittest.mock import patch

from validate_compare_layout import NativeWidgets, screenshot
from validate_native_execution import NativeHost


def validate(source, output):
    output.mkdir(parents=True, exist_ok=True)
    host = NativeHost(source)
    imported = host.execute('from OMFITlib_gui_layout import finish_gui_layout',
                            host.modules[('CGYRO_TGLF_scan',)])
    layout = imported['finish_gui_layout']
    main = tk.Tk()
    main.withdraw()
    first, second = tk.Toplevel(main), tk.Toplevel(main)
    first.geometry('840x450')
    tree = {'first': {'value': [1, 2]}, 'second': {'value': [9, 10]}}
    ui = NativeWidgets(source, tree['first'], first, 14)
    ns, aux = ui.namespace, ui.aux
    native_source = Path(source) / 'omfit_classes/OMFITx.py'
    raw = native_source.read_text(encoding='utf-8')
    wanted = {'_Text', '_absLocation', 'Lock'}
    nodes = [node for node in ast.parse(raw).body if isinstance(node, ast.FunctionDef) and node.name in wanted]
    evidence = {node.name: hashlib.sha256(ast.get_source_segment(raw, node).encode()).hexdigest() for node in nodes}
    for node in nodes:
        node.decorator_list = []
    ns.update(OMFIT=tree, _ttk_tk_process_kw=lambda kw: dict(kw),
              relativeLocations=lambda script: {'rootName': script.location},
              absLocation=lambda location, base, **kw: base['rootName'] + location[4:] if location.startswith('root[') else location)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(native_source), 'exec'), ns)
    class Text(tk.Text):
        def set(self, value):
            self.delete('1.0', 'end')
            self.insert('1.0', value)
        def get(self, *args):
            return super().get(*(args or ('1.0', 'end-1c')))
    a = SimpleNamespace(top=first, parentGUI=ui.body, pythonFile=SimpleNamespace(location="OMFIT['first']"), notebooks={}, locked=[])
    b = SimpleNamespace(top=second, parentGUI=ttk.Frame(second), pythonFile=SimpleNamespace(location="OMFIT['second']"), notebooks={}, locked=["OMFIT['first']['value']"])
    ns['_GUIs'].update({str(first): a, str(second): b})
    errors = []
    main.report_callback_exception = lambda typ, exc, tb: errors.append(exc)
    try:
        with patch.object(tk, 'ScrolledText', Text, create=True), patch.dict(sys.modules, {'utils_widgets': ui.helpers}):
            intro = ui.Label('共用环境脚本 · 原生多行编辑', align='left')
            entry = ui.Entry("root['value']", '参数列表', multiline=True)
            button = next(item for item in entry.master.winfo_children() if item.winfo_class() == 'TButton' and item.cget('text') == '...')
            # Reproduce the reported exception before applying our scoped binding.
            aux.update(topGUI=second, parentGUI=b.parentGUI)
            del ns['_GUIs'][str(second)]
            second.destroy()
            button.invoke()
            assert len(errors) == 1 and isinstance(errors[0], KeyError), errors
            for widget in list(entry.master.winfo_children()):
                if widget.winfo_class() == 'Toplevel':
                    widget.destroy()
            errors.clear()
            layout(intro, ui)
            bound = str(button.cget('command'))
            layout(intro, ui)
            assert str(button.cget('command')) == bound, 'Callback wrapped twice'
            button.invoke()
            assert not errors, errors
            dialog = next(widget for widget in entry.master.winfo_children() if widget.winfo_class() == 'Toplevel')
            editor = next(widget for widget in dialog.winfo_children() if widget.winfo_class() == 'Text')
            assert str(editor.cget('state')) == 'normal'
            editor.set('[3, 4]')
            frame = next(widget for widget in dialog.winfo_children() if widget.winfo_class() == 'TFrame')
            apply = next(widget for widget in frame.winfo_children() if widget.winfo_class() == 'TButton')
            assert apply.cget('text') == '应用'
            apply.invoke()
            assert tree['first']['value'] == [3, 4] and tree['second']['value'] == [9, 10]
            # A different live GUI may have its own lock state. Its locks must
            # never disable this editor, and its context is restored afterward.
            third = tk.Toplevel(main)
            c = SimpleNamespace(top=third, parentGUI=ttk.Frame(third), pythonFile=b.pythonFile, notebooks={}, locked=["OMFIT['first']['value']"])
            ns['_GUIs'][str(third)] = c
            aux.update(topGUI=third, parentGUI=c.parentGUI)
            button.invoke()
            assert aux['topGUI'] is third
            dialog = next(widget for widget in entry.master.winfo_children() if widget.winfo_class() == 'Toplevel')
            editor = next(widget for widget in dialog.winfo_children() if widget.winfo_class() == 'Text')
            assert editor.cget('state') == 'normal'
            dialog.destroy()
            a.locked.append("OMFIT['first']['value']")
            button.invoke()
            dialog = next(widget for widget in entry.master.winfo_children() if widget.winfo_class() == 'Toplevel')
            editor = next(widget for widget in dialog.winfo_children() if widget.winfo_class() == 'Text')
            assert editor.cget('state') == 'disabled'
            assert not errors, errors
            first.update()
            screenshot(first, output / 'native-editor-owner.png')
            dialog.destroy()
            opened = []
            def open_native_submodule():
                child = tk.Toplevel(main)
                body = ttk.Frame(child)
                body.pack()
                controller = SimpleNamespace(top=child, parentGUI=body, pythonFile=b.pythonFile, notebooks={}, locked=[])
                ns['_GUIs'][str(child)] = controller
                aux.update(topGUI=child, parentGUI=body)
                entry = ui.Entry("root['value']", '子模块参数', multiline=True)
                opened.append(next(item for item in entry.master.winfo_children()
                    if item.winfo_class() == 'TButton' and item.cget('text') == '...'))
            child_button = ttk.Button(ui.body, text='打开子模块', command=open_native_submodule)
            child_button.pack()
            layout(intro, ui)
            child_button.invoke()
            del ns['_GUIs'][str(third)]
            third.destroy()
            aux.update(topGUI=third, parentGUI=c.parentGUI)
            opened[0].invoke()
            assert not errors, errors
    finally:
        main.destroy()
    report = dict(reproduced_original_KeyError=True, closed_window_callback_fixed=True,
        live_other_window_context_restored=True, owning_window_locks_respected=True,
        edited_correct_module_only=True, localized_native_editor=True, duplicate_wrapping_prevented=True,
        opened_submodule_callback_scoped=True,
        native_bodies=evidence, complete_omfit_session_tested=False)
    (output / 'gui-context.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    validate(args.source, args.output)
