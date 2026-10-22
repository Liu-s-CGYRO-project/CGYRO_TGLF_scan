"""Control refresh contracts with OMFIT's unchanged selection callback.

The scheduler is a small headless Tk adapter. It distinguishes timer events
from update_idletasks so a redraw cannot hide inside a native tree refresh.
When the supplied OMFIT source is available, commit/validation/event generation
use its actual ComboBox.update_tree_values body, rather than a second copy.
This is not a full desktop or solver test.
"""
import ast
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'CGYRO_TGLF_scan/LIB'))
import OMFITlib_gui_api as widgets

CORE = REPO.parents[2] / 'OMFIT-source-ASIPP_unstable/omfit/omfit_classes/OMFITx.py'


class Scheduler:
    def __init__(self):
        self.tasks = {}
        self.counter = 0

    def add(self, kind, callback):
        self.counter += 1
        token = 'after' + str(self.counter)
        self.tasks[token] = (kind, callback)
        return token

    def step(self, kind='timer'):
        for token, (task_kind, callback) in list(self.tasks.items()):
            if task_kind == kind and token in self.tasks:
                del self.tasks[token]
                callback()


class Widget:
    def __init__(self, name, loop, master=None):
        self.name, self.loop, self.master = name, loop, master
        self.children, self.bindings = [], {}
        self.exists = True
        if master is not None:
            master.children.append(self)

    def __str__(self):
        return self.name

    def winfo_children(self):
        return self.children[:]

    def winfo_class(self):
        return 'TCombobox'

    def winfo_exists(self):
        return self.exists

    def bind(self, event, callback, add=None):
        self.bindings.setdefault(event, []).append(callback)
        return str(len(self.bindings[event]))

    def after(self, milliseconds, callback):
        return self.loop.add('timer', callback)

    def after_idle(self, callback):
        return self.loop.add('idle', callback)

    def after_cancel(self, token):
        self.loop.tasks.pop(token, None)

    def destroy(self):
        self.exists = False
        for callback in self.bindings.get('<Destroy>', []):
            callback(SimpleNamespace(widget=self))


class NativeAPI:
    """Minimal host for the real native selection callback, without a Tk root."""
    def __init__(self, callback):
        self.callback = callback
        self.loop = Scheduler()
        self.top = Widget('.owner', self.loop)
        self.parent = Widget('.owner.page', self.loop, self.top)
        self.other = Widget('.other', self.loop)
        self.session = SimpleNamespace(lockSave=False)
        self.OMFITaux = {'GUI': self.session}
        self.updates, self.errors = [], []
        self.root = {'plot_mode': 'Plot 2D'}
        self.inside_selection = False
        self.on_update = None
        self.depth = self.max_depth = 0
        self.gui = SimpleNamespace(top=self.top, update=self.update)
        self.other_gui = SimpleNamespace(top=self.other, update=lambda: self.updates.append(('other', self.inside_selection)))
        self._GUIs = {str(self.top): self.gui, str(self.other): self.other_gui}
        # Deliberately stale global GUI context; ancestry must find the owner.
        self._aux = {'topGUI': self.other, 'parentGUI': self.parent}

    def update(self):
        self.depth += 1
        self.max_depth = max(self.depth, self.max_depth)
        try:
            self.updates.append(('owner', self.inside_selection))
            if self.on_update:
                self.on_update()
            self.loop.step('idle')
        finally:
            self.depth -= 1

    def event_generate(self, event):
        if event == '<<update_GUI>>':
            for gui in self._GUIs.values():
                gui.update()
        elif event == '<<update_treeGUI>>':
            self.loop.step('idle')

    def ComboBox(self, location, options, lbl=None, comment=None, updateGUI=False,
                 state='readonly', help='', postcommand=None, **kwargs):
        control = Widget('.owner.page.combo' + str(len(self.parent.children)), self.loop, self.parent)
        control.get = lambda: control.value
        control.value = next(iter(options))

        def manage(function, **unused):
            try:
                return function()
            except Exception as error:
                self.errors.append(error)

        namespace = dict(root=self.root, np=np, array=np.array, comboBox=control, options=options,
                         state=state, checkKeyPressed=lambda: (True, None),
                         escapeDescription=lambda value: value, printe=lambda *args: None,
                         manage_user_errors=manage, postcommand=postcommand,
                         OMFITaux={'rootGUI': self})
        namespace['_eval'] = lambda expression: eval(expression, namespace)
        exec(compile(ast.Module(body=[self.callback], type_ignores=[]), str(CORE), 'exec'), namespace)
        commit = namespace['update_tree_values']

        def select(value):
            control.value = value
            self.inside_selection = True
            try:
                commit(location, updateGUI)
            finally:
                self.inside_selection = False
        control.select = select
        return control


class DeferredRefreshTests(unittest.TestCase):
    def setUp(self):
        self.loop = Scheduler()
        self.top = Widget('.owner', self.loop)
        self.calls = []
        self.gui = SimpleNamespace(top=self.top, update=lambda: self.calls.append('owner'))
        self.registry = {str(self.top): self.gui}
        self.api = SimpleNamespace(OMFITaux={'GUI': SimpleNamespace(lockSave=False)})
        self.refresh = widgets._DeferredGUIRefresh(self.api, self.gui, self.registry)

    def test_not_run_during_native_idle_flush_and_coalesce_requests(self):
        for _ in range(20):
            self.refresh.request()
        self.loop.step('idle')
        self.assertEqual(self.calls, [])
        self.assertEqual(len(self.loop.tasks), 1)
        self.loop.step()
        self.assertEqual(self.calls, ['owner'])
        self.assertFalse(self.loop.tasks)

    def test_save_defers_redraw_and_leaves_other_events_available(self):
        self.api.OMFITaux['GUI'].lockSave = 'auto-save'
        self.refresh.request()
        self.loop.step()
        self.assertEqual(self.calls, [])
        self.top.after(1, lambda: self.calls.append('heartbeat'))
        self.loop.step()
        self.assertEqual(self.calls, ['heartbeat'])
        self.api.OMFITaux['GUI'].lockSave = False
        self.loop.step()
        self.assertEqual(self.calls, ['heartbeat', 'owner'])

    def test_close_cancels_only_owned_timer(self):
        unrelated = self.top.after(1, lambda: self.calls.append('unrelated'))
        self.refresh.request()
        self.top.destroy()
        self.assertEqual(list(self.loop.tasks), [unrelated])
        self.loop.step()
        self.assertEqual(self.calls, ['unrelated'])

    def test_stale_registry_entry_is_not_refreshed(self):
        self.refresh.request()
        self.registry[str(self.top)] = SimpleNamespace(update=lambda: self.calls.append('replacement'))
        self.loop.step()
        self.assertEqual(self.calls, [])

    def test_refresh_requested_during_redraw_runs_after_return(self):
        depth = []
        def update():
            depth.append(self.refresh.running)
            self.calls.append('owner')
            if len(self.calls) == 1:
                self.refresh.request()
                self.loop.step('idle')
                self.assertEqual(self.calls, ['owner'])
        self.gui.update = update
        self.refresh.request()
        self.loop.step()
        self.assertEqual(self.calls, ['owner'])
        self.loop.step()
        self.assertEqual(self.calls, ['owner', 'owner'])
        self.assertEqual(depth, [True, True])

    def test_error_does_not_leave_refresh_permanently_running(self):
        def fail():
            raise RuntimeError('render failed')
        self.gui.update = fail
        self.refresh.request()
        with self.assertRaisesRegex(RuntimeError, 'render failed'):
            self.loop.step()
        self.assertFalse(self.refresh.running)
        self.gui.update = lambda: self.calls.append('recovered')
        self.refresh.request()
        self.loop.step()
        self.assertEqual(self.calls, ['recovered'])


class NativeComboRefreshTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not CORE.is_file():
            raise unittest.SkipTest('The supplied OMFIT source is required for native callback checks')
        definition = next(node for node in ast.parse(CORE.read_text(encoding='utf-8')).body
                          if isinstance(node, ast.FunctionDef) and node.name == 'ComboBox')
        cls.callback = next(node for node in ast.walk(definition)
                            if isinstance(node, ast.FunctionDef) and node.name == 'update_tree_values')

    def setUp(self):
        self.host = NativeAPI(self.callback)
        self.tk_types = patch.object(widgets.tk, 'Misc', Widget)
        self.style = patch.object(widgets, 'style_widget')
        self.tk_types.start()
        self.style.start()
        self.addCleanup(self.tk_types.stop)
        self.addCleanup(self.style.stop)
        self.options = {'Spectra': 'Plot 2D', 'Ballooning': 'Plot eigen ball'}

    def test_native_baseline_refreshes_all_windows_inside_selection(self):
        combo = self.host.ComboBox("root['plot_mode']", self.options, updateGUI=True)
        combo.select('Ballooning')
        self.assertEqual(self.host.updates, [('owner', True), ('other', True)])

    def test_ballooning_commits_then_only_owner_refreshes_after_selection(self):
        combo = widgets.adapt(self.host).ComboBox("root['plot_mode']", self.options, updateGUI=True)
        combo.select('Ballooning')
        self.assertEqual(self.host.root['plot_mode'], 'Plot eigen ball')
        self.assertEqual(self.host.updates, [])
        self.host.loop.step()
        self.assertEqual(self.host.updates, [('owner', False)])

    def test_repeated_changes_share_one_refresh_and_keep_latest_value(self):
        combo = widgets.adapt(self.host).ComboBox("root['plot_mode']", self.options, updateGUI=True)
        for value in ('Ballooning', 'Spectra', 'Ballooning'):
            combo.select(value)
        self.assertEqual(len(self.host.loop.tasks), 1)
        self.host.loop.step()
        self.assertEqual(self.host.root['plot_mode'], 'Plot eigen ball')
        self.assertEqual(self.host.updates, [('owner', False)])

    def test_positional_arguments_preserve_native_postcommand(self):
        seen = []
        combo = widgets.adapt(self.host).ComboBox(
            "root['plot_mode']", self.options, None, None, True,
            postcommand=lambda location: seen.append((location, self.host.root['plot_mode'])))
        combo.select('Ballooning')
        self.assertEqual(seen, [("root['plot_mode']", 'Plot eigen ball')])
        self.assertEqual(self.host.updates, [])
        self.host.loop.step()
        self.assertEqual(self.host.updates, [('owner', False)])

    def test_native_postcommand_error_still_schedules_refresh(self):
        def fail(location):
            raise ValueError('native callback error')
        combo = widgets.adapt(self.host).ComboBox(
            "root['plot_mode']", self.options, updateGUI=True, postcommand=fail)
        combo.select('Ballooning')
        self.assertEqual(str(self.host.errors[0]), 'native callback error')
        self.host.loop.step()
        self.assertEqual(self.host.updates, [('owner', False)])

    def test_native_list_to_array_conversion_remains_intact(self):
        self.host.root['values'] = np.array([False, False])
        combo = widgets.adapt(self.host).ComboBox(
            "root['values']", {'scaled': [True, False]}, updateGUI=True)
        combo.select('scaled')
        self.assertIsInstance(self.host.root['values'], np.ndarray)
        np.testing.assert_array_equal(self.host.root['values'], [True, False])
        self.host.loop.step()
        self.assertEqual(self.host.updates, [('owner', False)])

    def test_unregistered_host_keeps_native_update_policy(self):
        self.host._GUIs = {}
        combo = widgets.adapt(self.host).ComboBox("root['plot_mode']", self.options, updateGUI=True)
        combo.select('Ballooning')
        self.assertEqual(self.host.root['plot_mode'], 'Plot eigen ball')
        self.assertEqual(self.host.loop.tasks, {})

    def test_direct_refresh_uses_captured_owner_not_last_rendered_window(self):
        ui = widgets.adapt(self.host)
        self.host._aux['parentGUI'] = self.host.other
        ui.UpdateGUI()
        self.assertEqual(self.host.updates, [])
        self.host.loop.step()
        self.assertEqual(self.host.updates, [('owner', False)])

    def test_explicit_target_refresh_is_deferred_and_does_not_touch_owner(self):
        ui = widgets.adapt(self.host)
        ui.UpdateGUI(top=self.host.other)
        self.assertEqual(self.host.updates, [])
        self.host.loop.step()
        self.assertEqual(self.host.updates, [('other', False)])

    def test_explicit_all_windows_policy_keeps_native_call(self):
        calls = []
        self.host.UpdateGUI = lambda top=None: calls.append(top)
        ui = widgets.adapt(self.host)
        ui.UpdateGUI(all_windows=True)
        self.assertEqual(calls, [None])
        self.assertEqual(self.host.loop.tasks, {})

    def test_control_construction_does_not_schedule_redraw(self):
        widgets.adapt(self.host).ComboBox("root['plot_mode']", self.options, updateGUI=True)
        self.assertEqual(self.host.loop.tasks, {})


if __name__ == '__main__':
    unittest.main(verbosity=2)
