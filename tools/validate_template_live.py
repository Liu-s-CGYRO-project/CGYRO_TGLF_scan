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
parser.add_argument('--previous-project', type=Path,
                    help='Released code-only ZIP supplying the already mounted GUI libraries')
args = parser.parse_args()
BASE = args.output.parent.resolve()
BASE.mkdir(parents=True, exist_ok=True)
REPO = Path(__file__).resolve().parents[1]
SOURCE = args.source.resolve()
library_paths = dict(layout='OMFITlib_gui_layout', context='OMFITlib_gui_context',
                     deferred='OMFITlib_gui_deferred', api='OMFITlib_gui_api')
# Native imports resolve only registered LIB nodes, not PYTHONPATH. Include
# the GUI dependency closure while keeping this fixture free of result data.
pending = list(library_paths.values())
while pending:
    library = pending.pop()
    source = (REPO / 'CGYRO_TGLF_scan/LIB' / (library + '.py')).read_text(encoding='utf-8')
    for node in ast.walk(ast.parse(source)):
        names = ([node.module] if isinstance(node, ast.ImportFrom) else
                 [alias.name for alias in node.names] if isinstance(node, ast.Import) else [])
        for name in names:
            if name and name.startswith('OMFITlib_') and name not in library_paths.values():
                library_paths[name] = name
                pending.append(name)
new_libraries = {key + '.py': (REPO / 'CGYRO_TGLF_scan/LIB' / (name + '.py')).read_bytes()
                 for key, name in library_paths.items()}
old_libraries = dict(new_libraries)
previous_version = None
if args.previous_project is not None:
    with zipfile.ZipFile(args.previous_project) as archive:
        previous_version = json.loads(archive.read('PROJECT_CONTENTS.json'))['version']
        for key, name in library_paths.items():
            old_libraries[key + '.py'] = archive.read('CGYRO_TGLF_scan/LIB/' + name + '.py')
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
['Demo']['LIB']['OMFITlib_gui_context'] <-:-:-> OMFITpythonTask <-:-:-> ./context.py <-:-:-> {}
['Demo']['LIB']['OMFITlib_gui_deferred'] <-:-:-> OMFITpythonTask <-:-:-> ./deferred.py <-:-:-> {}
['Demo']['LIB']['OMFITlib_gui_api'] <-:-:-> OMFITpythonTask <-:-:-> ./api.py <-:-:-> {}
['Demo']['GUIS'] <-:-:-> OMFITtree <-:-:->  <-:-:-> {}
['Demo']['GUIS']['main'] <-:-:-> OMFITpythonGUI <-:-:-> ./main.py <-:-:-> {}
['Demo']['SETTINGS'] <-:-:-> OMFITsettings <-:-:-> ./settings.json <-:-:-> {}
['Demo']['RUN_DB'] <-:-:-> OMFITtree <-:-:->  <-:-:-> {}
"""
    tree += ''.join("['Demo']['LIB']['" + name + "'] <-:-:-> OMFITpythonTask <-:-:-> ./" + key + '.py <-:-:-> {}\n'
                    for key, name in library_paths.items() if key not in ('layout', 'context', 'deferred', 'api'))
    def program(version):
        # The selected lazy tab is built before finish_gui_layout replaces the
        # previous instance retained on parentGUI. A simple label-only fixture
        # missed the 1.24.22 -> 1.24.23 missing-prune regression at this boundary.
        tabs = ('' if version == 1 else
                'from OMFITlib_gui_deferred import TabPages\n'
                'tabs = TabPages(OMFITx, {"scan": "扫描", "results": "结果"}, root["SETTINGS"], "page", '
                'lambda key: OMFITx.Label(key))\n'
                'OMFITx.Tab("")\n')
        return ('from OMFITlib_gui_layout import finish_gui_layout\nversion = ' + str(version) + '\n'
                'label = OMFITx.Label("当前版本 ' + str(version) + ' · 计算结果保留", align="left")\n'
                + tabs +
                'OMFITx.Button("运行当前代码", lambda: root["SETTINGS"].__setitem__("clicked", ' + str(version) + '))\n'
                'finish_gui_layout(label, OMFITx)\n')
    (directory / 'OMFITsave.txt').write_text(tree)
    (directory / 'settings.json').write_text(json.dumps({'MODULE': {'ID': 'Demo'}, 'PHYSICS': {'x': 99}}))
    (directory / 'main.py').write_text(program(1), encoding='utf-8')
    for name, data in old_libraries.items():
        (directory / name).write_bytes(data)
    current = LiveOMFIT()
    current._OMFITkeyName = 'OMFIT'
    current['Demo'] = factory(directory / 'OMFITsave.txt')['Demo']
    module = current['Demo']
    results = module['RUN_DB']
    results['unsaved'] = UnreadResult()
    current['Other'] = UnreadResult()
    old_file = module['GUIS']['main']
    window = tk.Tk()
    callback_errors = []
    window.report_callback_exception = lambda kind, error, trace: callback_errors.append(repr(error))
    window.geometry('900x700')
    ui = NativeWidgets(SOURCE, module, window, 14)
    # NativeWidgets wraps public widget functions; OMFITaux is session data.
    ui.OMFITaux = ui.namespace['OMFITaux']
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
            old_layout_has_prune = hasattr(ui.body._cgyro_gui_layout, 'prune')
            source_zip = directory / 'new.zip'
            with zipfile.ZipFile(source_zip, 'w', zipfile.ZIP_DEFLATED) as archive:
                archive.writestr('OMFITsave.txt', tree)
                archive.writestr('main.py', program(2))
                for name, data in new_libraries.items():
                    archive.writestr(name, data)
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
            assert controller.notebooks and not anchor_before.winfo_exists()
            assert not callback_errors, callback_errors
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
            assert not callback_errors, callback_errors
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
              lazy_tab_built_during_live_refresh=True, callback_errors=callback_errors,
              previous_project_version=previous_version, previous_layout_has_prune=old_layout_has_prune,
              previous_layout_sha256=hashlib.sha256(old_libraries['layout.py']).hexdigest(),
              project_save_or_load_called=False, complete_omfit_session_tested=False)
args.output.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2), flush=True)
