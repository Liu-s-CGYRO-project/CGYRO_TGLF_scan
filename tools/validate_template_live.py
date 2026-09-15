"""Native SortedDict/importer/GUI.update checks with file-node host adapters."""
import ast
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace, MethodType
from unittest.mock import patch
import zipfile

import argparse
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('source', type=Path)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
BASE = args.output.parent.resolve()
BASE.mkdir(parents=True, exist_ok=True)
REPO = Path(__file__).resolve().parents[1]
SOURCE = args.source.resolve()
sys.path.insert(0, str(REPO / 'tools'))
from validate_native_execution import NativeHost, treeify
from validate_compare_layout import NativeWidgets, screenshot

host = NativeHost(SOURCE)
api = host.execute('from OMFITlib_template_live import Prepared\nfrom OMFITlib_template_session import OMFITSession\n'
                   'from OMFITlib_template_service import publish\nfrom OMFITlib_template_archive import parse_tree',
                   host.modules[('OMFITtemplates',)])
OMFITmodule = type('OMFITmodule', (host.factory,), {})
class UnreadResult:
    def __deepcopy__(self, memo):
        raise AssertionError('Result copied')
    def read(self):
        raise AssertionError('Result read')
class OMFITpythonTask(host.Task):
    def __init__(self, path):
        self.filename = str(path)
    def read(self):
        return Path(self.filename).read_text(encoding='utf-8')
    def run(self, **kwargs):
        parent = self._OMFITparent
        while not isinstance(parent, OMFITmodule):
            parent = parent._OMFITparent
        out = host.execute(self.read(), parent, OMFITx=ui, **kwargs)
        events.append(out.get('version', None))
        return out
    __run__ = run
class LiveOMFIT(host.factory):
    filename = 'existing-project.zip'
    def load(self, *a, **kw):
        raise AssertionError('Project reloaded')
    save = saveas = load

def factory(entry, **kw):
    entry = Path(entry)
    root = host.factory()
    for row in api['parse_tree'](entry.read_bytes()):
        parent = root
        for key in row.keys[:-1]:
            parent = parent[key]
        if row.kind == 'OMFITmodule':
            value = OMFITmodule()
        elif row.kind == 'OMFITsettings':
            value = treeify(json.loads((entry.parent / row.ref).read_bytes()), host.factory)
        elif row.kind.startswith('OMFITpython'):
            value = OMFITpythonTask(entry.parent / row.ref)
        else:
            assert row.kind == 'OMFITtree'
            value = host.factory()
        parent[row.keys[-1]] = value
    return root

events = []
with tempfile.TemporaryDirectory(prefix='native-live-check-') as directory, patch.dict(sys.modules, {'omfit_classes.utils_base': host.registry}):
    directory = Path(directory)
    tree = """['Demo'] <-:-:-> OMFITmodule <-:-:->  <-:-:-> {}
['Demo']['LIB'] <-:-:-> OMFITtree <-:-:->  <-:-:-> {}
['Demo']['LIB']['OMFITlib_gui_layout'] <-:-:-> OMFITpythonTask <-:-:-> ./layout.py <-:-:-> {}
['Demo']['GUIS'] <-:-:-> OMFITtree <-:-:->  <-:-:-> {}
['Demo']['GUIS']['main'] <-:-:-> OMFITpythonGUI <-:-:-> ./main.py <-:-:-> {}
['Demo']['SETTINGS'] <-:-:-> OMFITsettings <-:-:-> ./settings.json <-:-:-> {}
['Demo']['RUN_DB'] <-:-:-> OMFITtree <-:-:->  <-:-:-> {}
"""
    def program(version):
        return ('from OMFITlib_gui_layout import finish_gui_layout\nversion = ' + str(version) + '\n'
                'label = OMFITx.Label("当前版本 ' + str(version) + ' · 计算结果保留", align="left")\n'
                'OMFITx.Button("运行当前代码", lambda: root["SETTINGS"].__setitem__("clicked", ' + str(version) + '))\n'
                'finish_gui_layout(label)\n')
    (directory / 'OMFITsave.txt').write_text(tree)
    (directory / 'settings.json').write_text(json.dumps({'MODULE': {'ID': 'Demo'}, 'PHYSICS': {'x': 99}}))
    (directory / 'main.py').write_text(program(1), encoding='utf-8')
    (directory / 'layout.py').write_bytes((REPO / 'CGYRO_TGLF_scan/LIB/OMFITlib_gui_layout.py').read_bytes())
    current = LiveOMFIT()
    current._OMFITkeyName = 'OMFIT'
    current['Demo'] = factory(directory / 'OMFITsave.txt')['Demo']
    module = current['Demo']
    results = module['RUN_DB']
    results['unsaved'] = UnreadResult()
    current['Other'] = UnreadResult()
    old_file = module['GUIS']['main']
    window = tk.Tk()
    window.geometry('900x700')
    ui = NativeWidgets(SOURCE, module, window, 14)
    native_text = (SOURCE / 'omfit_classes/OMFITx.py').read_text(encoding='utf-8')
    cls = next(n for n in ast.parse(native_text).body if isinstance(n, ast.ClassDef) and n.name == 'GUI')
    node = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'update')
    native_sha = hashlib.sha256(ast.get_source_segment(native_text, node).encode()).hexdigest()
    ns = ui.namespace
    ns['_clearKids'] = lambda parent: [child.destroy() for child in parent.winfo_children()]
    ns['_clearClosedGUI'] = lambda top: top.destroy()
    exec(compile(ast.Module(body=[node], type_ignores=[]), '<native-GUI.update>', 'exec'), ns)
    controller = SimpleNamespace(top=window, pythonFile=old_file, kw={}, notebooks={},
        parentGUI=ui.body, prefFrame=ttk.Frame(window), canvas=ui.canvas,
        taskGUIframeInterior=ui.body, interior_id=ui.canvas.find_all()[0],
        yscrollbar=next(w for w in window.winfo_children() if w.winfo_class() == 'TScrollbar'))
    controller.update = MethodType(ns['update'], controller)
    ns['_GUIs'][str(window)] = controller
    gui_api = SimpleNamespace(_GUIs=ns['_GUIs'], OMFITaux={'rootGUI': window}, _clearClosedGUI=ns['_clearClosedGUI'])
    session = api['OMFITSession'](current, tree_factory=factory, gui_api=gui_api)
    try:
        with patch.dict(sys.modules, {'utils_widgets': ui.helpers}):
            controller.update()
            ui.settle()
            anchor_before = ui.body._cgyro_gui_layout.anchor
            del ui.body._cgyro_gui_layout.anchor  # Upgrade from the pre-refresh layout helper.
            source_zip = directory / 'new.zip'
            with zipfile.ZipFile(source_zip, 'w', zipfile.ZIP_DEFLATED) as archive:
                archive.writestr('OMFITsave.txt', tree)
                archive.writestr('main.py', program(2))
                archive.writestr('layout.py', (directory / 'layout.py').read_bytes())
                archive.writestr('settings.json', json.dumps({'MODULE': {'ID': 'Demo'}, 'PHYSICS': {'x': 2, 'added': 4}}))
            template = api['publish'](source_zip, directory / 'library', dict(id='demo', name='Demo', author='test', version='2'), ['Demo'])
            plan = session.preview_live(api['Prepared'](template))
            top_id = window.winfo_id()
            session.apply_live(plan)
            ui.settle()
            assert window.winfo_id() == top_id
            assert current['Demo'] is module and module['RUN_DB'] is results
            assert module['SETTINGS']['PHYSICS']['x'] == 99
            assert module['SETTINGS']['PHYSICS']['added'] == 4
            assert controller.pythonFile is module['GUIS']['main'] and controller.pythonFile is not old_file
            assert ui.body._cgyro_gui_layout.anchor is not anchor_before
            for child in ui.body.winfo_children():
                for widget in child.winfo_children():
                    if widget.winfo_class() == 'TButton' and widget.cget('text') == '运行当前代码':
                        widget.invoke()
            assert module['SETTINGS']['clicked'] == 2
            assert not any(name.startswith('OMFITlib_') for name in sys.modules)
            screenshot(window, BASE / 'native-live-after.png')
            session.undo_live()
            ui.settle()
            assert controller.pythonFile is old_file and module['RUN_DB'] is results
            assert current.filename == 'existing-project.zip'
    finally:
        try:
            for callback in window.tk.call('after', 'info'):
                window.tk.call('after', 'cancel', callback)
            window.destroy()
        except tk.TclError:
            pass
report = dict(native_GUI_update_sha256=native_sha, native_SortedDict=True, native_import_cleanup=True,
              same_TopLevel=True, old_module_and_result_identity_preserved=True,
              new_button_callback_used=True, layout_reapplied_on_redraw=True, undo=True,
              project_save_or_load_called=False, complete_omfit_session_tested=False)
args.output.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2), flush=True)
