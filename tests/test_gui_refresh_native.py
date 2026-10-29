"""Real Tk regressions with OMFIT's unchanged widget and GUI update bodies.

The supplied OMFIT checkout provides GUI, Entry, _Entry, _Text, ComboBox and
the native Tk subclasses. Tree locations, session state, error reporting and
font preferences are small adapters; this is not a full OMFIT session test.
The optional IDLE syntax highlighter is disabled when that package is absent.
"""
import ast
from collections import OrderedDict
import copy
import datetime
import io
import os
from pathlib import Path
import sys
import tempfile
import time
from types import MethodType, ModuleType, SimpleNamespace
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
        self.start_patch(patch.object(widgets, 'style_checkbox'))

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
        namespace.update(tk=tk, ttk=ttk, sys=sys, np=np, copy=copy, OrderedDict=OrderedDict,
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
                           {'GUI', '_clearKids', '_clearClosedGUI', '_Entry', '_Text', 'Entry', 'ComboBox', 'Button', 'CheckBox'},
                           namespace)
        self.root.bind('<<update_treeGUI>>', lambda event: self.root.update_idletasks())
        self.root.bind('<<update_GUI>>', lambda event: self.global_update())
        self.owner = self.make_gui('owner')
        self.other = self.make_gui('other')
        self.root.update()
        self.updates.clear()

    def tearDown(self):
        if hasattr(self, 'errors'):
            # Native task completion queues root.update_idletasks at 100 ms.
            # In OMFIT this root remains alive; let it run before destroying
            # this per-test interpreter, and include its errors in assertions.
            self.drain(120)
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

    def submit_entry(self, entry):
        # Reuse the exact native Return binding through a virtual event. Key
        # events require window-manager focus, which another parallel Tk test
        # can steal between focus_force() and event_generate('<Return>').
        # The native callback ignores the event kind; its validation, write,
        # postcommand and tree/GUI notifications all run unchanged.
        binding = entry.bind('<Return>')
        self.assertTrue(binding)
        event = '<<TestNativeReturn>>'
        entry.bind(event, binding)
        try:
            self.invoke(lambda: entry.event_generate(event))
        finally:
            entry.unbind(event)

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

    def render_scoped(self, builder):
        """Real native controls inside a page with an independently drawn tab."""
        self.region_updates, self.region_widgets = [], {}
        def render(ui):
            content = self.api._aux['parentGUI']
            header = ttk.Label(content, text='Persistent header')
            header.pack()
            body = ttk.Frame(content)
            body.pack(fill='both', expand=True)
            self.region_widgets.update(header=header, body=body, ui=ui)
            def populate(section):
                for child in section.winfo_children():
                    child.destroy()
                previous = self.api._aux['parentGUI']
                self.api._aux['parentGUI'] = section
                try:
                    self.controls.clear()
                    builder(ui)
                finally:
                    self.api._aux['parentGUI'] = previous
            def build_page():
                for child in body.winfo_children():
                    child.destroy()
                section = ttk.Frame(body)
                section.pack(fill='both', expand=True)
                self.region_widgets['section'] = section
                def redraw_section():
                    self.region_updates.append(('section', self.inside_callback))
                    populate(section)
                section._cgyro_local_refresh = widgets._DeferredGUIRefresh(
                    self.api, self.owner, self.api._GUIs, section, redraw_section)
                populate(section)
            def redraw_page():
                self.region_updates.append(('page', self.inside_callback))
                build_page()
            refresh = widgets._DeferredGUIRefresh(self.api, self.owner, self.api._GUIs, body, redraw_page)
            body._cgyro_action_refresh = content._cgyro_action_refresh = refresh
            build_page()
        self.render(render)

    def test_native_action_refreshes_page_and_preserves_header_and_business_tree_event(self):
        tree_events, actions = [], []
        self.root.bind('<<update_treeGUI>>', lambda event: tree_events.append('tree'), add='+')
        self.render_scoped(lambda api: self.controls.update(button=api.Button(
            'Apply', lambda: actions.append('applied'), updateGUI=True)))
        header, section = self.region_widgets['header'], self.region_widgets['section']
        old = self.controls['button']
        tree_events.clear()
        self.invoke(old.invoke)
        self.assertEqual(actions, ['applied'])
        self.assertEqual(tree_events, ['tree'])
        self.assertEqual(self.region_updates, [])
        self.drain(300)
        self.assertEqual(self.region_updates, [('page', False)])
        self.assertEqual(self.updates, [])
        self.assertTrue(header.winfo_exists())
        self.assertFalse(section.winfo_exists())
        self.assertFalse(old.winfo_exists())

    def native_plot(self, runner):
        namespace = dict(os=os, OMFITaux=self.api.OMFITaux, _OMFITpython=object)
        native_definitions(SOURCE / 'omfit_classes/omfit_python.py', {'OMFITpythonPlot'}, namespace)
        cls = namespace['OMFITpythonPlot']
        script = cls.__new__(cls)
        script.__run__ = runner
        return script

    def native_task(self, runner):
        aux = self.api.OMFITaux
        aux.setdefault('pythonRunWindows', [])
        aux.setdefault('haltWindow', None)
        self.halt_kills = getattr(self, 'halt_kills', [])
        self.task_log = getattr(self, 'task_log', io.StringIO())
        namespace = dict(os=SimpleNamespace(getpid=os.getpid, kill=lambda *args: self.halt_kills.append(args)),
                         time=time, datetime=datetime, tk=tk, ttk=ttk, OMFITaux=aux,
                         _OMFITpython=object, OMFIT_is_in_debug_mode=False,
                         OMFIT={'MainSettings': {'SETUP': {'show_halt_window': False}}},
                         _streams={'HIST': self.task_log}, _update_alarm=[],
                         treeLocation=lambda script: ['test task'], tk_center=lambda *args: None,
                         printd=lambda *args, **kwargs: None)
        native_definitions(SOURCE / 'omfit_classes/omfit_python.py', {'OMFITpythonTask'}, namespace)
        cls = namespace['OMFITpythonTask']
        script = cls.__new__(cls)
        script.__run__ = MethodType(runner, script)
        return script

    def test_task_action_preserves_native_progress_cleanup_and_only_refreshes_owner_section(self):
        calls, frames, events = [], [], []
        self.root.bind('<<update_treeGUI>>', lambda event: events.append('tree'), add='+')
        def execute(receiver, **kwargs):
            self.assertIs(receiver, script)
            calls.append(kwargs)
            frames.extend(self.api.OMFITaux['pythonRunWindows'])
            self.assertTrue(all(frame.winfo_exists() for frame in frames))
            self.api.OMFITaux['haltWindow'] = 123456  # fake PID: kill is recorded, never executed
            return 'collected'
        script = self.native_task(execute)
        original = script._endGUI.__func__
        results = []
        self.render_scoped(lambda api: self.controls.update(button=api.Button(
            'Sync', lambda: results.append(widgets.task_action(script, selected=['job'])),
            updateGUI=True, refresh_scope='section', refresh_tree=False)))
        events.clear()
        self.invoke(self.controls['button'].invoke)
        self.drain(300)
        self.assertEqual(results, ['collected'])
        self.assertEqual(calls, [{'selected': ['job']}])
        self.assertEqual(self.region_updates, [('section', False)])
        self.assertEqual(self.updates, [])
        self.assertEqual(events, [])
        self.assertEqual(self.api.OMFITaux['pythonRunWindows'], [])
        self.assertIsNone(self.api.OMFITaux['haltWindow'])
        self.assertEqual(self.halt_kills, [(123456, 9)])
        self.assertTrue(all(not frame.winfo_exists() for frame in frames))
        self.assertIn('Done @ ', self.task_log.getvalue())
        self.assertIs(script._endGUI.__func__, original)
        self.assertIs(original.__globals__['OMFITaux'], self.api.OMFITaux)

    def test_task_action_nested_and_abort_restore_stack_without_global_notifications(self):
        events, depths = [], []
        self.root.bind('<<update_treeGUI>>', lambda event: events.append('tree'), add='+')
        def execute(receiver, **kwargs):
            depths.append(len(self.api.OMFITaux['pythonRunWindows']))
            if kwargs.get('abort'):
                raise KeyboardInterrupt('native Abort')
            return 'done'
        inner = self.native_task(execute)
        outer = self.native_task(lambda receiver, **kwargs: widgets.task_action(inner, **kwargs))
        self.assertEqual(widgets.task_action(outer), 'done')
        with self.assertRaisesRegex(KeyboardInterrupt, 'native Abort'):
            widgets.task_action(outer, abort=True)
        self.assertEqual(depths, [3, 3])
        self.assertEqual(self.api.OMFITaux['pythonRunWindows'], [])
        self.assertEqual(events, [])
        self.assertEqual(self.updates, [])
        self.assertEqual(self.task_log.getvalue().count('Done @ '), 1)

    def test_task_action_keeps_explicit_business_events_and_unrelated_native_runs(self):
        events = []
        self.root.bind('<<update_treeGUI>>', lambda event: events.append('tree'), add='+')
        script = self.native_task(lambda receiver, **kwargs:
                                 self.api.OMFITaux['rootGUI'].event_generate('<<update_treeGUI>>'))
        widgets.task_action(script)
        self.assertEqual(events, ['tree'])
        self.assertEqual(self.updates, [])
        script.run()  # A caller outside our scoped GUI keeps native notifications.
        self.assertEqual(events, ['tree', 'tree', 'tree', 'tree', 'tree'])
        self.assertEqual({name for name, _ in self.updates}, {'owner', 'other'})
        callback = SimpleNamespace(run=lambda **kwargs: kwargs)
        self.assertEqual(widgets.task_action(callback, selected=['point']), {'selected': ['point']})

    def test_task_action_preserves_custom_runner_receiver_and_super(self):
        task = self.native_task(lambda receiver, **kwargs: kwargs)
        class CustomTask(type(task)):
            def run(self, **kwargs):
                return super().run(**kwargs)
        custom = CustomTask.__new__(CustomTask)
        custom.__run__ = MethodType(lambda receiver, **kwargs: (receiver, kwargs), custom)
        self.assertEqual(widgets.task_action(custom, value=3), (custom, {'value': 3}))
        self.assertEqual(self.api.OMFITaux['pythonRunWindows'], [])

    def test_view_gui_preserves_native_single_instance_context_and_business_events(self):
        calls, events, cleared = [], [], []
        self.root.bind('<<update_treeGUI>>', lambda event: events.append('tree'), add='+')
        cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as directory:
            def launch(script, locations, **kwargs):
                calls.append((locations, kwargs))
                os.chdir(directory)
                if kwargs.get('changed'):
                    self.api.OMFITaux['rootGUI'].event_generate('<<update_treeGUI>>')
                if kwargs.get('fail'):
                    raise ValueError('construction failed')
            api = SimpleNamespace(_GUIs={}, GUI=launch, _clearClosedGUI=cleared.append)
            namespace = dict(os=os, OMFITaux=self.api.OMFITaux, OMFITx=api,
                             _OMFITpython=object, relativeLocations=lambda script: {'root': 'selected'})
            native_definitions(SOURCE / 'omfit_classes/omfit_python.py', {'OMFITpythonGUI'}, namespace)
            cls = namespace['OMFITpythonGUI']
            script = cls.__new__(cls)
            original = script.run.__func__
            api._GUIs['existing'] = SimpleNamespace(pythonFile=script, top='existing')
            widgets.gui_view(script, page='plot')
            self.assertEqual(cleared, ['existing'])
            self.assertEqual(calls[-1], ({'root': 'selected'}, {'page': 'plot'}))
            self.assertEqual(events, [])
            self.assertEqual(os.getcwd(), cwd)
            with self.assertRaisesRegex(ValueError, 'construction failed'):
                widgets.gui_view(script, singleGUIinstance=False, _relLoc={'root': 'explicit'}, fail=True)
            self.assertEqual(cleared, ['existing'])
            self.assertEqual(calls[-1][0], {'root': 'explicit'})
            self.assertEqual(os.getcwd(), cwd)
            widgets.gui_view(script, changed=True)
            self.assertEqual(events, ['tree'])
            script.run()
            self.assertEqual(events, ['tree', 'tree'])
            self.assertIs(script.run.__func__, original)
            self.assertIs(original.__globals__['OMFITaux']['rootGUI'], self.root)

    def raw_view(self, build):
        """Use both real native launcher layers, as a tree double-click does."""
        self.api.OMFIT = {'MainSettings': {'SETUP': {'GUIs_on_top': False}}}
        self.api.tk_center = lambda *args, **kwargs: None
        namespace = dict(os=os, OMFITaux=self.api.OMFITaux, OMFITx=self.api,
                         _OMFITpython=object, relativeLocations=lambda script: {'root': self.tree})
        native_definitions(SOURCE / 'omfit_classes/omfit_python.py', {'OMFITpythonGUI'}, namespace)
        cls = namespace['OMFITpythonGUI']
        script = cls.__new__(cls)
        script.__run__ = lambda **kwargs: build(self.api)
        return script

    def test_raw_double_click_omits_two_tree_repaints_without_loading_result_expressions(self):
        loads = []
        self.root.bind('<<update_treeGUI>>', lambda event: loads.append('result expressions'), add='+')
        tags, binding = self.root.bindtags(), self.root.bind('<<update_treeGUI>>')
        original = self.api.GUI.update
        def build(api):
            widgets.begin_view_open(api)
            ttk.Label(api._aux['parentGUI'], text='Ready').pack()
        script = self.raw_view(build)
        script()  # No gui_view wrapper: exercise the user's actual entry point.
        self.assertEqual(loads, [])
        self.assertIs(self.api.GUI.update, original)
        self.root.update()
        self.assertEqual(self.root.bindtags(), tags)
        self.assertEqual(self.root.bind('<<update_treeGUI>>'), binding)
        self.root.event_generate('<<update_treeGUI>>')
        self.assertEqual(loads, ['result expressions'])

    def test_open_filter_keeps_business_events_and_other_native_windows(self):
        events = []
        self.root.bind('<<update_treeGUI>>', lambda event: events.append('tree'), add='+')
        other = self.raw_view(lambda api: ttk.Label(api._aux['parentGUI'], text='other').pack())
        def build(api):
            widgets.begin_view_open(api)
            widgets.begin_view_open(api)  # One filter even if requested twice.
            ttk.Label(api._aux['parentGUI'], text='main').pack()
            self.root.event_generate('<<update_treeGUI>>')
            other(singleGUIinstance=False)
        self.raw_view(build)()
        self.assertEqual(events, ['tree', 'tree', 'tree'])
        self.root.update()
        self.assertFalse(any(str(tag).startswith('CGYROViewOpen') for tag in self.root.bindtags()))

    def test_failed_open_cleans_filter_and_preserves_original_exception(self):
        tags = self.root.bindtags()
        def build(api):
            widgets.begin_view_open(api)
            raise ValueError('construction failed')
        with self.assertRaisesRegex(ValueError, 'construction failed'):
            self.raw_view(build)()
        self.root.update()
        self.assertEqual(self.root.bindtags(), tags)

    def test_native_compare_plot_button_avoids_both_tree_repaints_and_preserves_idle_draw(self):
        events, calls, draws = [], [], []
        self.root.bind('<<update_treeGUI>>', lambda event: events.append('tree'), add='+')
        script = self.native_plot(lambda **kwargs: calls.append(kwargs))
        original = script.plot.__func__
        namespace = dict(CaseSelection=object, plot_view=widgets.plot_view, comparison_issues=lambda *args: [])
        native_definitions(REPO / 'CGYRO_TGLF_scan/LIB/OMFITlib_compare_ui.py', {'ComparisonUI'}, namespace)
        view = namespace['ComparisonUI'].__new__(namespace['ComparisonUI'])
        view.mode = 'CGYRO_vs_CGYRO'
        view.root = {'SETTINGS': {'PHYSICS': {}}, 'PLOTS': {'CGYRO_vs_CGYRO': script}}
        view._assert_selection = lambda: None
        self.render_scoped(lambda api: self.controls.update(button=api.Button(
            'Plot', view._plot, refresh_tree=False)))
        events.clear()  # Opening the native GUI itself legitimately refreshes the tree.
        self.root.after_idle(lambda: draws.append('canvas drawn'))
        self.invoke(self.controls['button'].invoke)
        self.assertEqual(calls, [{'noGUI': True}])
        self.assertEqual(draws, ['canvas drawn'])
        self.assertEqual(events, [])
        self.assertEqual(self.region_updates, [])
        self.assertIs(script.plot.__func__, original)
        self.assertIs(original.__globals__['OMFITaux']['rootGUI'], self.root)
        self.drain(300)
        self.assertFalse(self.controls['button'].instate(['disabled']))

    def test_plot_view_runs_task_registered_plot_with_selected_arguments_without_refresh(self):
        events, calls, draws = [], [], []
        self.root.bind('<<update_treeGUI>>', lambda event: events.append('tree'), add='+')
        record = {'points': {'p000003': {'status': 'complete'}}}
        def execute(receiver, **kwargs):
            self.assertIs(receiver, script)
            calls.append(kwargs)
            return 'selected spectrum'
        script = self.native_task(execute)
        self.assertFalse(hasattr(script, 'plot'))
        results = []
        self.render_scoped(lambda api: self.controls.update(button=api.Button(
            'TGLF spectrum', lambda: results.append(widgets.plot_view(script, record=record, point_id='p000003')),
            refresh_tree=False)))
        events.clear()
        self.root.after_idle(lambda: draws.append('canvas drawn'))
        self.invoke(self.controls['button'].invoke)
        self.drain(300)
        self.assertEqual(results, ['selected spectrum'])
        self.assertEqual(calls, [{'record': record, 'point_id': 'p000003'}])
        self.assertIs(calls[0]['record'], record)
        self.assertEqual(draws, ['canvas drawn'])
        self.assertEqual(events, [])
        self.assertEqual(self.updates, [])
        self.assertEqual(self.region_updates, [])
        self.assertEqual(self.api.OMFITaux['pythonRunWindows'], [])
        self.assertFalse(self.controls['button'].instate(['disabled']))

    def test_plot_view_task_failure_keeps_error_and_cleans_native_progress(self):
        events = []
        self.root.bind('<<update_treeGUI>>', lambda event: events.append('tree'), add='+')
        def execute(receiver, **kwargs):
            self.assertEqual(kwargs, {'record': 'chosen', 'point_id': 'p000003'})
            raise ValueError('Selected point files are incomplete')
        script = self.native_task(execute)
        with self.assertRaisesRegex(ValueError, 'Selected point files are incomplete'):
            widgets.plot_view(script, record='chosen', point_id='p000003')
        self.assertEqual(events, [])
        self.assertEqual(self.updates, [])
        self.assertEqual(self.api.OMFITaux['pythonRunWindows'], [])
        self.assertNotIn('Done @ ', self.task_log.getvalue())

    def test_plot_view_task_preserves_explicit_no_gui_and_business_notifications(self):
        events = []
        self.root.bind('<<update_treeGUI>>', lambda event: events.append('tree'), add='+')
        def execute(receiver, **kwargs):
            self.assertEqual(kwargs, {'noGUI': True, 'point_id': 'p000003'})
            self.assertEqual(self.api.OMFITaux['pythonRunWindows'], [None, None])
            self.api.OMFITaux['rootGUI'].event_generate('<<update_treeGUI>>')
            return kwargs['point_id']
        script = self.native_task(execute)
        self.assertEqual(widgets.plot_view(script, noGUI=True, point_id='p000003'), 'p000003')
        self.assertEqual(events, ['tree'])
        self.assertEqual(self.updates, [])
        self.assertEqual(self.api.OMFITaux['pythonRunWindows'], [])

    def test_view_plot_restores_directory_return_value_and_error_without_changing_native_method(self):
        events, calls = [], []
        self.root.bind('<<update_treeGUI>>', lambda event: events.append('tree'), add='+')
        cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as directory:
            def run(**kwargs):
                calls.append(kwargs)
                os.chdir(directory)
                if kwargs.get('fail'):
                    raise ValueError('selected result unavailable')
                return 'figure'
            script = self.native_plot(run)
            self.assertEqual(widgets.plot_view(script, point_ids=['p000003']), 'figure')
            self.assertEqual(os.getcwd(), cwd)
            with self.assertRaisesRegex(ValueError, 'selected result unavailable'):
                widgets.plot_view(script, fail=True)
            self.assertEqual(os.getcwd(), cwd)
            self.assertEqual(events, [])
            self.assertEqual(calls[0], {'point_ids': ['p000003'], 'noGUI': True})
            # A native invocation outside this view still notifies the tree.
            self.assertEqual(script.plot(), 'figure')
            self.assertEqual(events, ['tree'])
            self.assertEqual(os.getcwd(), cwd)

    def test_view_button_error_reenables_and_does_not_suppress_business_notifications(self):
        events, errors = [], []
        self.root.bind('<<update_treeGUI>>', lambda event: events.append('tree'), add='+')
        def run(**kwargs):
            # Deliberate business notifications inside a user script survive.
            self.api.OMFITaux['rootGUI'].event_generate('<<update_treeGUI>>')
            raise ValueError('plot failed')
        script = self.native_plot(run)
        def manage(command, **kwargs):
            try:
                return command()
            except ValueError as error:
                errors.append(str(error))
        self.api.manage_user_errors = manage
        self.render_scoped(lambda api: self.controls.update(button=api.Button(
            'Plot', lambda: widgets.plot_view(script), refresh_tree=False)))
        events.clear()
        self.invoke(self.controls['button'].invoke)
        self.assertEqual(errors, ['plot failed'])
        self.assertEqual(events, ['tree'])
        self.drain(300)
        self.assertFalse(self.controls['button'].instate(['disabled']))
        self.assertIs(self.api.Button.__globals__['OMFITaux']['rootGUI'], self.root)

    def test_view_button_still_refreshes_requested_section_and_disabled_button_stays_disabled(self):
        calls, events = [], []
        self.root.bind('<<update_treeGUI>>', lambda event: events.append('tree'), add='+')
        def build(api):
            self.controls['button'] = api.Button('Check', lambda: calls.append('checked'), updateGUI=True,
                                                 refresh_scope='section', refresh_tree=False)
            self.controls['disabled'] = api.Button('Disabled', lambda: calls.append('unexpected'),
                                                   state='disabled', refresh_tree=False)
        self.render_scoped(build)
        events.clear()
        self.invoke(self.controls['disabled'].invoke)
        self.assertEqual(calls, [])
        self.invoke(self.controls['button'].invoke)
        self.drain(300)
        self.assertEqual(calls, ['checked'])
        self.assertEqual(self.region_updates, [('section', False)])
        self.assertEqual(events, [])

    def test_nested_view_plots_and_non_native_plot_callbacks_keep_arguments_and_returns(self):
        events, calls = [], []
        self.root.bind('<<update_treeGUI>>', lambda event: events.append('tree'), add='+')
        inner = self.native_plot(lambda **kwargs: calls.append(kwargs) or 'nested figure')
        outer = self.native_plot(lambda **kwargs: widgets.plot_view(inner, point_ids=['chosen']))
        self.assertEqual(widgets.plot_view(outer), 'nested figure')
        self.assertEqual(calls, [{'point_ids': ['chosen'], 'noGUI': True}])
        self.assertEqual(events, [])
        callback = SimpleNamespace(plot=lambda **kwargs: kwargs)
        self.assertEqual(widgets.plot_view(callback, point_ids=['chosen']), {'point_ids': ['chosen']})

    def test_native_field_and_reset_refresh_only_nearest_section(self):
        self.render_scoped(lambda api: self.controls.update(combo=api.ComboBox(
            "root['mode']", {'Spectra': 'spectra', 'Ballooning': 'ballooning'},
            updateGUI=True, default='spectra')))
        body, section = self.region_widgets['body'], self.region_widgets['section']
        combo = self.controls['combo']
        combo.set('Ballooning')
        self.invoke(lambda: combo.event_generate('<<ComboboxSelected>>'))
        self.drain()
        self.assertEqual(self.tree['mode'], 'ballooning')
        self.invoke(self.button(section, '重置').invoke)
        self.drain()
        self.assertEqual(self.tree['mode'], 'spectra')
        self.assertEqual(self.region_updates, [('section', False), ('section', False)])
        self.assertEqual(self.updates, [])
        self.assertTrue(body.winfo_exists() and section.winfo_exists())

    def test_view_checkbox_and_reset_keep_value_postcommand_and_local_refresh_without_tree_repaint(self):
        self.tree['visible'] = False
        tree_events, post = [], []
        self.root.bind('<<update_treeGUI>>', lambda event: tree_events.append('tree'), add='+')
        original = self.api.CheckBox
        self.render_scoped(lambda ui: self.controls.update(check=ui.view_only().CheckBox(
            "root['visible']", 'Visible', default=False, updateGUI=True,
            postcommand=lambda location: post.append(location))[0]))
        tree_events.clear()
        self.invoke(lambda: self.controls['check'].event_generate('<ButtonRelease-1>'))
        self.assertTrue(self.tree['visible'])
        self.assertEqual(post, ["root['visible']"])
        self.assertEqual(tree_events, [])
        self.drain()
        self.assertEqual(self.region_updates, [('section', False)])
        self.invoke(self.button(self.region_widgets['section'], '重置').invoke)
        self.drain()
        self.assertFalse(self.tree['visible'])
        self.assertEqual(post, ["root['visible']", "root['visible']"])
        self.assertEqual(tree_events, [])
        self.assertEqual(self.region_updates, [('section', False), ('section', False)])
        self.assertIs(self.api.CheckBox, original)
        self.assertIs(self.api.CheckBox.__globals__['OMFITaux']['rootGUI'], self.root)

    def test_view_entry_combobox_and_multiline_do_not_capture_normal_control_events(self):
        events, post = [], []
        self.root.bind('<<update_treeGUI>>', lambda event: events.append('tree'), add='+')
        def build(ui):
            view = ui.view_only()
            self.assertIs(view.view_only(), view)
            self.controls['normal'] = ui.Entry("root['number']", updateGUI=False)
            self.controls['entry'] = view.Entry("root['number']", updateGUI=True,
                                                postcommand=lambda location: post.append(location))
            self.controls['combo'] = view.ComboBox("root['mode']", ['spectra', 'ballooning'], updateGUI=True)
        self.render_scoped(build)
        events.clear()
        entry = self.controls['entry']
        entry.delete(0, tk.END)
        entry.insert(0, '18.0')
        self.submit_entry(entry)
        self.assertEqual(self.tree['number'], 18.0)
        self.assertEqual(post, ["root['number']"])
        self.assertEqual(events, [])
        self.drain()
        combo = self.controls['combo']
        combo.set('ballooning')
        self.invoke(lambda: combo.event_generate('<<ComboboxSelected>>'))
        self.drain()
        self.assertEqual(self.tree['mode'], 'ballooning')
        self.assertEqual(events, [])
        normal = self.controls['normal']
        normal.delete(0, tk.END)
        normal.insert(0, '24.0')
        self.submit_entry(normal)
        self.assertEqual(self.tree['number'], 24.0)
        self.assertEqual(events, ['tree'])
        self.render(lambda ui: self.controls.update(entry=ui.view_only().Entry(
            "root['number']", multiline=True, norm=3.0, updateGUI=True)))
        events.clear()
        self.apply_multiline('9.0')
        self.assertEqual(self.tree['number'], 27.0)
        self.assertEqual(events, [])
        self.assert_owner_refresh()

    def test_view_fields_keep_native_locks_and_unrelated_events(self):
        self.tree['visible'] = False
        self.api.Lock = lambda *args, **kwargs: True
        self.render(lambda ui: self.controls.update(
            check=ui.view_only().CheckBox("root['visible']", 'Locked', default=False)[0],
            entry=ui.view_only().Entry("root['number']")))
        self.assertTrue(self.controls['check'].instate(['disabled']))
        self.assertTrue(self.controls['entry'].instate(['disabled']))
        self.controls['check'].event_generate('<ButtonRelease-1>')
        self.assertFalse(self.tree['visible'])
        other = []
        self.root.bind('<<view_ready>>', lambda event: other.append('ready'))
        proxy = widgets._ViewRootEvents(self.root)
        proxy.event_generate('<<view_ready>>')
        self.assertEqual(other, ['ready'])
        self.assertEqual(proxy.winfo_exists(), self.root.winfo_exists())

    def test_parameter_fields_opt_out_of_tree_paint_without_losing_native_edits(self):
        events, post = [], []
        self.root.bind('<<update_treeGUI>>', lambda event: events.append('tree'), add='+')
        def build(ui):
            # Both orders share one refresh scope: a cached ordinary Entry
            # constructor must not leak its event destination into this field.
            self.controls['ordinary'] = ui.Entry("root['number']", updateGUI=False)
            self.controls['parameter'] = ui.Entry("root['number']", updateGUI=False, refresh_tree=False,
                postcommand=lambda location: post.append(location))
            self.controls['boolean'] = ui.ComboBox("root['mode']", ['spectra', 'ballooning'],
                updateGUI=False, refresh_tree=False)
        self.render_scoped(build)
        events.clear()
        entry = self.controls['parameter']
        entry.delete(0, tk.END)
        entry.insert(0, '9.5')
        self.submit_entry(entry)
        self.drain()
        self.assertEqual(self.tree['number'], 9.5)
        self.assertEqual(post, ["root['number']"])
        combo = self.controls['boolean']
        combo.set('ballooning')
        combo.event_generate('<<ComboboxSelected>>')
        self.drain()
        self.assertEqual(self.tree['mode'], 'ballooning')
        self.assertEqual(events, [])
        self.assertEqual(self.region_updates, [])
        self.assertEqual(self.updates, [])
        self.submit_entry(self.controls['ordinary'])
        self.assertEqual(events, ['tree'])
        self.render(lambda ui: self.controls.update(entry=ui.Entry("root['number']", multiline=True,
            refresh_tree=False, updateGUI=True, norm=2.)))
        events.clear()
        self.apply_multiline('4.5')
        self.assertEqual(self.tree['number'], 9.)
        self.assertEqual(events, [])
        self.assert_owner_refresh()

    def test_normal_physical_checkbox_still_notifies_tree(self):
        self.tree['visible'] = False
        events = []
        self.root.bind('<<update_treeGUI>>', lambda event: events.append('tree'), add='+')
        self.render(lambda ui: self.controls.update(check=ui.CheckBox("root['visible']", 'Physics')[0]))
        events.clear()
        self.invoke(lambda: self.controls['check'].event_generate('<ButtonRelease-1>'))
        self.assertTrue(self.tree['visible'])
        self.assertEqual(events, ['tree'])

    def test_native_view_button_can_request_section_and_reload_can_request_window(self):
        def build(api):
            self.controls['view'] = api.Button('Preview', lambda: None, updateGUI=True, refresh_scope='section')
            self.controls['reload'] = api.Button('Reload', lambda: None, updateGUI=True, refresh_scope='window')
        self.render_scoped(build)
        self.invoke(self.controls['view'].invoke)
        self.drain(300)
        self.assertEqual(self.region_updates, [('section', False)])
        self.assertEqual(self.updates, [])
        self.invoke(self.controls['reload'].invoke)
        self.assert_owner_refresh()

    def test_page_refresh_coalesces_waits_for_save_and_stops_after_close(self):
        self.render_scoped(lambda api: self.controls.update(button=api.Button('Apply', lambda: None, updateGUI=True)))
        ui = self.region_widgets['ui']
        self.api.OMFITaux['GUI'].lockSave = True
        self.invoke(self.controls['button'].invoke)
        ui.UpdateGUI()
        ui.UpdateGUI()
        self.drain(30)
        self.assertEqual(self.region_updates, [])
        self.assertEqual(self.updates, [])
        self.api.OMFITaux['GUI'].lockSave = False
        self.drain(150)
        self.assertEqual(self.region_updates, [('page', False)])
        ui.UpdateGUI()
        self.owner.top.destroy()
        self.drain(150)
        self.assertEqual(self.region_updates, [('page', False)])
        self.assertEqual(self.updates, [])

    def test_captured_dialog_callback_never_uses_last_constructed_window(self):
        def build(api):
            self.controls['changed'] = api.refresh_callback(scope='section')
        self.render_scoped(build)
        changed = self.controls['changed']
        self.api._aux['parentGUI'] = self.other.top
        self.invoke(changed)
        self.drain()
        self.assertEqual(self.region_updates, [('section', False)])
        self.assertEqual(self.updates, [])
        self.region_widgets['ui'].UpdateGUI()
        self.drain()
        self.assertEqual(self.region_updates, [('section', False), ('page', False)])
        self.assertEqual(self.updates, [])
        self.invoke(changed)  # An old dialog cannot redraw the replacement section.
        self.drain()
        self.assertEqual(self.region_updates, [('section', False), ('page', False)])

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

    def test_radius_cleanup_selector_uses_unchanged_native_combobox_options_signature(self):
        # Compile the actual page class without importing solver/UI modules.
        # Its native control call must work with OMFITx, not just a permissive
        # headless recorder that accepts arbitrary positional/keyword values.
        from OMFITlib_gui_deferred import deferred_section
        namespace = dict(tk=tk, deferred_section=deferred_section,
                         radius_choices=lambda node: {'Jet | nr=11 | rho=0.99': {}})
        native_definitions(REPO / 'CGYRO_TGLF_scan/LIB/OMFITlib_workbench_cgyro_ui.py',
                           {'CgyroPage'}, namespace)
        self.tree.update(cgyro_cleanup_open=True, cgyro_cleanup_radius='')
        view = namespace['CgyroPage']()
        view.settings, view.prefix = self.tree, 'root'
        view.open_cgyro_task_manager = view.confirm_cgyro_radius_cleanup = lambda: None
        def render(api):
            view.ui = api
            view.render_cgyro_cleanup({})
        self.render(render)
        combos = [w for w in self.descendants(self.owner.top) if isinstance(w, ttk.Combobox)]
        self.assertEqual(len(combos), 1)
        self.assertIn('Jet | nr=11 | rho=0.99', str(combos[0].cget('values')))
        self.assertEqual(self.errors, [])

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
