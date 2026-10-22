"""Real Tk regressions with OMFIT's unchanged widget and GUI update bodies.

The supplied OMFIT checkout provides GUI, Entry, _Entry, _Text, ComboBox and
the native Tk subclasses. Tree locations, session state, error reporting and
font preferences are small adapters; this is not a full OMFIT session test.
The optional IDLE syntax highlighter is disabled when that package is absent.
"""
import ast
from collections import OrderedDict
import copy
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch

import numpy as np

try:
    from idlelib.colorizer import ColorDelegator
    from idlelib.percolator import Percolator
except ImportError:
    # Native _Text does not enable highlighting; no colorizer methods are used.
    class Percolator:
        def __init__(self, widget):
            pass

    class ColorDelegator:
        pass

REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO.parents[2] / 'OMFIT-source-ASIPP_unstable/omfit'
sys.path.insert(0, str(REPO / 'CGYRO_TGLF_scan/LIB'))
import OMFITlib_gui_api as widgets


def native_definitions(path, names, namespace):
    definitions = [node for node in ast.parse(path.read_text(encoding='utf-8')).body
                   if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names]
    if {node.name for node in definitions} != set(names):
        raise AssertionError('Missing native definitions: ' + str(names))
    for node in definitions:
        node.decorator_list = []
    exec(compile(ast.Module(body=definitions, type_ignores=[]), str(path), 'exec'), namespace)


class NativeTkRefreshTests(unittest.TestCase):
    def start_patch(self, patcher):
        result = patcher.start()
        self.addCleanup(patcher.stop)
        return result

    def setUp(self):
        if not (SOURCE / 'omfit_classes/OMFITx.py').is_file():
            self.skipTest('The supplied OMFIT source is required')
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest('A Tk desktop/display is required: ' + str(error))
        self.addCleanup(self.root.destroy)
        self.root.geometry('400x300+0+0')
        self.errors, self.updates, self.controls = [], [], {}
        self.inside_callback = False
        self.root.report_callback_exception = lambda kind, error, traceback: self.errors.append(error)
        background_error = self.root.register(lambda message: self.errors.append(('Tcl', message)))
        self.root.tk.call('proc', 'bgerror', 'message', background_error + ' $message')

        font_module = ModuleType('utils_widgets')
        font_module.OMFITfont = lambda *args, **kwargs: ('DejaVu Sans', 11)
        self.start_patch(patch.dict(sys.modules, {'utils_widgets': font_module}))
        self.start_patch(patch.object(widgets, 'style_widget'))

        tk_namespace = dict(tk=tk, ttk=ttk, _Combobox=ttk.Combobox,
                            Percolator=Percolator, ColorDelegator=ColorDelegator,
                            ctrlCmd=lambda: 'Control')
        native_definitions(SOURCE / 'utils_tk.py',
                           {'get_entry_fieldbackground', 'Combobox', '_ScrolledText'}, tk_namespace)
        self.start_patch(patch.object(tk, 'ScrolledText', tk_namespace['_ScrolledText'], create=True))

        self.api = ModuleType('native_gui_refresh_test')
        self.tree = {'mode': 'spectra', 'number': 12.0, 'text': 'old\ntext'}
        self.special = object()
        namespace = self.api.__dict__
        namespace.update(tk=tk, ttk=ttk, np=np, copy=copy, OrderedDict=OrderedDict,
                         SortedDict=dict, Combobox=tk_namespace['Combobox'],
                         special1=self.special, root=self.tree, rightClick='Button-3',
                         OMFITexception=ValueError, _GUIs={},
                         _aux={'same_row': None, 'packing': tk.TOP},
                         OMFITaux={'rootGUI': self.root, 'GUI': SimpleNamespace(lockSave=False)},
                         _absLocation=lambda value: value,
                         _for_each_collection=lambda value: (value, None),
                         _tk_ttk_process_kw=lambda kind, options: dict(options),
                         _ttk_tk_process_kw=lambda options: dict(options),
                         _setDefault=lambda location, default: (default, False),
                         Lock=lambda *args, **kwargs: False,
                         _helpButton=lambda *args: None, _urlButton=lambda *args: None,
                         _reveal=lambda *args: None, printe=lambda *args: None,
                         tolist=lambda value: list(np.atleast_1d(value)),
                         treeLocation=lambda value: ['test'])
        namespace['_eval'] = lambda location: eval(location, namespace)
        namespace['repr_eval'] = lambda location, preentry=None, collect=False: repr(
            preentry(eval(location, namespace)) if preentry else eval(location, namespace))
        namespace['manage_user_errors'] = lambda command, **kwargs: command()
        native_definitions(SOURCE / 'omfit_classes/OMFITx.py',
                           {'GUI', '_clearKids', '_clearClosedGUI', '_Entry', '_Text', 'Entry', 'ComboBox', 'Button'},
                           namespace)
        self.root.bind('<<update_treeGUI>>', lambda event: self.root.update_idletasks())
        self.root.bind('<<update_GUI>>', lambda event: self.global_update())
        self.owner = self.make_gui('owner')
        self.other = self.make_gui('other')
        self.root.update()
        self.updates.clear()

    def tearDown(self):
        if hasattr(self, 'errors'):
            self.assertEqual(self.errors, [])

    def make_gui(self, name):
        gui = self.api.GUI.__new__(self.api.GUI)
        gui.top = tk.Toplevel(self.root)
        gui.top.geometry('450x300')
        gui.kw, gui.notebooks, gui.locked = {}, {}, []
        gui.pythonFile = SimpleNamespace(__run__=lambda **kwargs: ttk.Label(
            self.api._aux['parentGUI'], text=name).pack())
        gui.relativeLocations = {'root': self.tree}
        self.api._GUIs[str(gui.top)] = gui
        native_update = gui.update

        def update():
            self.updates.append((name, self.inside_callback))
            native_update()

        gui.update = update
        gui.update()
        return gui

    def global_update(self):
        for gui in list(self.api._GUIs.values()):
            gui.update()

    def render(self, builder, adapt=widgets.adapt):
        def script(**kwargs):
            self.controls.clear()
            builder(adapt(self.api))
        self.owner.pythonFile.__run__ = script
        self.owner.update()
        self.root.update()
        self.updates.clear()
        # A different window was rendered last; callbacks must use ancestry.
        self.api._aux['topGUI'] = self.other.top

    def invoke(self, callback):
        self.inside_callback = True
        try:
            callback()
        finally:
            self.inside_callback = False

    def drain(self, milliseconds=30):
        finished = tk.BooleanVar(self.root, value=False)
        self.root.after(milliseconds, lambda: finished.set(True))
        self.root.wait_variable(finished)
        self.root.update_idletasks()

    def descendants(self, parent):
        for child in parent.winfo_children():
            yield child
            yield from self.descendants(child)

    def button(self, parent, caption):
        return next(child for child in self.descendants(parent)
                    if isinstance(child, ttk.Button) and str(child.cget('text')) == caption)

    def assert_owner_refresh(self):
        self.root.update_idletasks()
        self.assertEqual(self.updates, [])
        self.drain()
        self.assertEqual(self.updates, [('owner', False)])

    def test_native_combo_selection_and_reset_defer_only_owner(self):
        self.render(lambda api: self.controls.update(combo=api.ComboBox(
            "root['mode']", {'Spectra': 'spectra', 'Ballooning': 'ballooning'},
            updateGUI=True, default='spectra')))
        combo = self.controls['combo']
        combo.set('Ballooning')
        self.invoke(lambda: combo.event_generate('<<ComboboxSelected>>'))
        self.assertEqual(self.tree['mode'], 'ballooning')
        self.assert_owner_refresh()
        self.updates.clear()
        self.invoke(self.button(self.owner.top, '重置').invoke)
        self.assertEqual(self.tree['mode'], 'spectra')
        self.assert_owner_refresh()

    def test_native_entry_reset_stages_without_discarding_default(self):
        self.render(lambda api: self.controls.update(entry=api.Entry(
            "root['number']", default=6.0, updateGUI=True)))
        entry = self.controls['entry']
        self.invoke(self.button(self.owner.top, '重置').invoke)
        self.assertEqual(float(entry.get()), 6.0)
        self.assertEqual(self.tree['number'], 12.0)
        self.drain()
        self.assertEqual(self.updates, [])
        self.assertTrue(entry.winfo_exists())

    def test_native_button_refresh_leaves_no_deleted_widget_timer(self):
        clicked, unrelated = [], []
        self.render(lambda api: self.controls.update(button=api.Button(
            'Apply', lambda: clicked.append('applied'), updateGUI=True)))
        self.other.top.after(100, lambda: unrelated.append('other window timer'))
        self.invoke(self.controls['button'].invoke)
        self.assertEqual(clicked, ['applied'])
        self.assert_owner_refresh()
        # Native Button(updateGUI=False) queues a delayed re-enable callback.
        self.drain(300)
        self.assertEqual(unrelated, ['other window timer'])
        self.assertEqual(self.errors, [])

    def test_native_button_handles_redraw_inside_command_before_finally(self):
        self.render(lambda api: self.controls.update(button=api.Button(
            'Rebuild', self.owner.update, updateGUI=True)))
        original = self.controls['button']
        self.invoke(original.invoke)
        self.assertFalse(original.winfo_exists())
        self.assertEqual(self.updates, [('owner', True)])
        # Native finally tries to schedule its re-enable after old-button death.
        self.drain(300)
        self.assertEqual(self.updates, [('owner', True), ('owner', False)])
        self.assertEqual(self.errors, [])

    def apply_multiline(self, text):
        self.invoke(self.button(self.owner.top, '...').invoke)
        editor_top = next(child for child in self.descendants(self.owner.top)
                          if isinstance(child, tk.Toplevel))
        editor = next(child for child in self.descendants(editor_top)
                      if isinstance(child, tk.Text))
        editor.delete('1.0', tk.END)
        editor.insert('1.0', text)
        self.invoke(self.button(editor_top, 'Update').invoke)
        self.assertFalse(editor_top.winfo_exists())

    def test_native_multiline_preserves_normalization_and_private_helper(self):
        original_text = self.api._Text
        original_entry = self.api.Entry
        self.render(lambda api: self.controls.update(entry=api.Entry(
            "root['number']", multiline=True, norm=3.0, updateGUI=True)))
        self.assertEqual(float(self.controls['entry'].get()), 4.0)
        self.apply_multiline('7.0')
        self.assertEqual(self.tree['number'], 21.0)
        self.assert_owner_refresh()
        self.assertEqual(float(self.controls['entry'].get()), 7.0)
        self.assertIs(self.api._Text, original_text)
        self.assertIs(self.api.Entry, original_entry)
        self.assertIs(original_entry.__globals__['_Text'], original_text)

    def test_native_multiline_implicit_refresh_is_local_when_entry_flag_false(self):
        self.render(lambda api: self.controls.update(entry=api.Entry(
            "root['text']", updateGUI=False)))
        self.apply_multiline('new\ntext')
        self.assertEqual(self.tree['text'], 'new\ntext')
        self.assert_owner_refresh()

    def test_multiline_callback_survives_native_import_cache_cleanup(self):
        sys.path.insert(0, str(REPO / 'tools'))
        self.addCleanup(sys.path.remove, str(REPO / 'tools'))
        from validate_native_execution import NativeHost
        host = NativeHost(SOURCE)
        hooks = list(sys.meta_path)
        previous = {name: module for name, module in sys.modules.items()
                    if name.startswith('OMFITlib_')}
        self.addCleanup(sys.modules.update, previous)
        for name in previous:
            del sys.modules[name]
        imported = host.execute('from OMFITlib_gui_api import adapt',
                                host.modules[('CGYRO_TGLF_scan',)])
        adapt = imported['adapt']
        self.assertIsNot(adapt, widgets.adapt)
        self.assertEqual(sys.meta_path, hooks)
        self.assertFalse(any(name.startswith('OMFITlib_') for name in sys.modules))
        with patch.dict(adapt.__globals__, {'style_widget': lambda widget: None}):
            self.render(lambda api: self.controls.update(entry=api.Entry(
                "root['number']", multiline=True, norm=3.0, updateGUI=True)), adapt=adapt)
            self.apply_multiline('9.0')
            self.assertEqual(self.tree['number'], 27.0)
            self.assert_owner_refresh()
        self.assertEqual(sys.meta_path, hooks)
        self.assertFalse(any(name.startswith('OMFITlib_') for name in sys.modules))


if __name__ == '__main__':
    unittest.main(verbosity=2)
