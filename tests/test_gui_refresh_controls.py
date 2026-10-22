"""Exercise native control callbacks against the project's refresh adapter.

The source callback bodies come from the supplied OMFIT checkout. The small
headless host supplies Tk values and scheduling, without copying their tree
write, postcommand, validation, reset, or error-handling implementations.
"""
import ast
import copy
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from test_gui_refresh import CORE, NativeAPI, Widget, widgets


class Variable:
    def __init__(self, master=None, value=None):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class Control(Widget):
    def __init__(self, name, loop, master=None):
        super().__init__(name, loop, master)
        self.options, self.states = {}, set()

    def configure(self, **kwargs):
        self.options.update(kwargs)

    config = configure

    def state(self, values):
        for value in values:
            if value.startswith('!'):
                self.states.discard(value[1:])
            else:
                self.states.add(value)

    def instate(self, values):
        return all(value in self.states for value in values)

    def focus_set(self):
        pass

    def grab_set(self):
        pass

    def grab_release(self):
        pass

    def event_generate(self, event):
        for callback in self.bindings.get(event, []):
            callback(SimpleNamespace(widget=self))

    def pack(self, **kwargs):
        pass


class NativeControls(NativeAPI):
    def __init__(self, definitions):
        super().__init__(None)
        self.definitions = definitions
        self.tree_events = 0
        self.parent.update_idletasks = lambda: self.loop.step('idle')
        self.callback = next(node for node in ast.walk(definitions['ComboBox'])
                             if isinstance(node, ast.FunctionDef) and node.name == 'update_tree_values')

    def event_generate(self, event):
        if event == '<<update_treeGUI>>':
            self.tree_events += 1
        super().event_generate(event)

    def _absLocation(self, location):
        if isinstance(location, str) and location.startswith('scratch['):
            return "root['scratch']" + location[len('scratch'):]
        return location

    def _eval(self, expression):
        return eval(expression, {'root': self.root, 'np': np})

    @staticmethod
    def tolist(value):
        return value if isinstance(value, list) else [value]

    def namespace(self, **values):
        def manage(function, **unused):
            try:
                return function()
            except Exception as error:
                self.errors.append(error)
        namespace = dict(root=self.root, np=np, os=os,
                         tk=SimpleNamespace(DISABLED='disabled', NORMAL='normal', END='end'),
                         _aux=self._aux, _absLocation=self._absLocation,
                         _clearClosedGUI=self.close, tolist=self.tolist,
                         manage_user_errors=manage, printe=lambda *args: None,
                         OMFITaux={'rootGUI': self})
        namespace.update(values)
        namespace['repr_eval'] = lambda location, *args, **kwargs: repr(eval(location, namespace))
        return namespace

    def compile_callbacks(self, owner, names, namespace):
        nodes = [next(node for node in ast.walk(self.definitions[owner])
                      if isinstance(node, ast.FunctionDef) and node.name == name)
                 for name in names]
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(CORE), 'exec'), namespace)

    def invoke(self, function, *args):
        self.inside_selection = True
        try:
            return function(*args)
        finally:
            self.inside_selection = False

    def close(self, top):
        self._GUIs.pop(str(top), None)
        top.destroy()

    def control(self, suffix):
        return Control('.owner.page.' + suffix + str(len(self.parent.children)), self.loop, self.parent)

    def ComboBox(self, location, options, lbl=None, comment=None, updateGUI=False,
                 state='readonly', help='', postcommand=None, **kwargs):
        if not isinstance(options, dict):
            options = {str(value): value for value in options}
        self.last_combo = super().ComboBox(location, options, lbl, comment, updateGUI,
                                          state, help, postcommand, **kwargs)
        return self.last_combo

    def install_helpers(self):
        """Install actual native helper definitions with a headless widget host."""
        class ModuleTree(dict):
            def moduleDict(self):
                return {"['first']": {'ID': 'profiles'}, "['second']": {'ID': 'profiles'}}

        self.root = ModuleTree(self.root)
        self.root.update(scratch={'objectPicker_test': ''}, first={}, second={})
        self._aux['topGUI'] = self.top
        self._aux['harvest'] = {}
        self.gui.pythonFile = object()

        def parse_location(expression):
            node = ast.parse(expression, mode='eval').body
            parts = []
            while isinstance(node, ast.Subscript):
                parts.insert(0, ast.literal_eval(node.slice))
                node = node.value
            return [node.id] + parts

        def build_location(parts):
            return parts[0] + ''.join('[{!r}]'.format(part) for part in parts[1:])

        def frame(master, **kwargs):
            result = Control(str(master) + '.child' + str(len(master.children)), self.loop, master)
            result.configure(**kwargs)
            return result

        namespace = self.namespace(
            copy=copy, OMFIT=self.root, OMFITobject=type('OMFITobject', (), {}),
            OMFITmodule=type('OMFITmodule', (), {}), OMFITexpression=type('OMFITexpression', (), {}),
            OMFITsrc='', _GUIs=self._GUIs, parseLocation=parse_location, buildLocation=build_location,
            omfit_hash=lambda *args: 'test', relativeLocations=lambda node: {'root': self.root, 'rootName': 'root'},
            treeLocation=lambda node: ['root'], is_none=lambda value: value is None,
            evalExpr=lambda value: value, ttk=SimpleNamespace(Frame=frame, Button=frame),
            Button=self.Button, FilePicker=self.FilePicker, ComboBox=self.ComboBox, Entry=self.Entry)
        namespace['tk'] = SimpleNamespace(TOP='top', NO=False, YES=True, X='x', LEFT='left', BOTH='both',
                                          NONE='none', NORMAL='normal', PhotoImage=lambda **kwargs: object())
        for name in ('ObjectPicker', 'ModulePicker', 'ShotTimeDevice'):
            node = copy.deepcopy(self.definitions[name])
            node.decorator_list = []
            exec(compile(ast.Module(body=[node], type_ignores=[]), str(CORE), 'exec'), namespace)
            setattr(self, name, namespace[name])
        return namespace

    def CheckBox(self, location, lbl=None, comment=None, useInt=False, mapFalseTrue=None,
                 updateGUI=False, help='', postcommand=None, default=False, **kwargs):
        locations = self.tolist(location)
        mapping = mapFalseTrue or ([0, 1] if useInt else [False, True])
        inverse = {repr(mapping[0]): False, repr(mapping[1]): True}
        controls = [self.control('check') for _ in locations]
        for control, path in zip(controls, locations):
            actual = inverse.get(repr(self._eval(path)), None)
            control.state(['selected'] if actual else [])
            if actual is None:
                control.state(['alternate'])
        namespace = self.namespace(location=locations, mapFalseTrue=mapping,
                                   invMapFalseTrue=inverse, e=controls, default=default,
                                   postcommand=postcommand, updateGUI=updateGUI)
        self.compile_callbacks('CheckBox', ['update_tree_values', 'writeToEntry'], namespace)
        for index, control in enumerate(controls):
            control.click = lambda index=index: self.invoke(
                namespace['update_tree_values'], locations, updateGUI, index)
            control.reset = lambda: self.invoke(namespace['writeToEntry'])
        return controls

    def Entry(self, location, lbl=None, comment=None, updateGUI=False, help='',
              preentry=None, postcommand=None, check=None, multiline=False, norm=None,
              default=0, delete_if_default=False, **kwargs):
        control = self.control('entry')
        value = Variable(value=repr(self._eval(location)))
        control.validation = (True, None)
        namespace = self.namespace(location=location, value=value, e=control,
                                   oldValueRepr={'val': value.get()}, preentry=preentry,
                                   postcommand=postcommand, collect=False, default=default,
                                   checkKeyPressed=lambda: control.validation, norm=norm)
        # Execute the native normalization block, which replaces postcommand.
        normalize = next(node for node in self.definitions['Entry'].body
                         if isinstance(node, ast.If) and isinstance(node.test, ast.Compare)
                         and isinstance(node.test.left, ast.Name) and node.test.left.id == 'norm')
        exec(compile(ast.Module(body=[normalize], type_ignores=[]), str(CORE), 'exec'), namespace)
        self.compile_callbacks('_Entry', ['set_location', 'update_tree_values'], namespace)
        self.compile_callbacks('Entry', ['writeToEntry'], namespace)
        control.value = value
        control.commit = lambda: self.invoke(namespace['update_tree_values'], location, updateGUI)
        control.reset = lambda: self.invoke(namespace['writeToEntry'])
        return control

    def FilePicker(self, location, lbl=None, comment=None, updateGUI=False,
                   help='', postcommand=None, **kwargs):
        control = self.control('file')
        value = Variable(value=repr(self._eval(location)))
        namespace = self.namespace(location=location, e=control, value=value,
                                   postcommand=postcommand, updateGUI=updateGUI)
        self.compile_callbacks('FilePicker', ['processFilename'], namespace)
        control.value = value
        control.choose = lambda filename: self.invoke(namespace['processFilename'], filename)
        return control

    def Button(self, lbl, command, help='', url='', closeGUI=False, updateGUI=False, **kwargs):
        control = self.control('button')
        namespace = self.namespace(command=command, closeGUI=closeGUI)
        self.compile_callbacks('Button', ['buttonClick'], namespace)
        # Execute the native string command resolution and close wrapper.
        setup = [node for node in self.definitions['Button'].body
                 if isinstance(node, ast.If) and
                 (isinstance(node.test, ast.Call) and isinstance(node.test.func, ast.Name)
                  and node.test.func.id == 'isinstance' or
                  isinstance(node.test, ast.Name) and node.test.id == 'closeGUI')]
        exec(compile(ast.Module(body=setup, type_ignores=[]), str(CORE), 'exec'), namespace)
        control.invoke = lambda: self.invoke(
            namespace['buttonClick'], control,
            lambda: namespace['manage_user_errors'](namespace['command'], reportUsersErrorByEmail=True),
            updateGUI)
        return control


class NativeControlRefreshTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not CORE.is_file():
            raise unittest.SkipTest('The supplied OMFIT source is required for native callback checks')
        cls.definitions = {node.name: node for node in ast.parse(CORE.read_text(encoding='utf-8')).body
                           if isinstance(node, ast.FunctionDef)}

    def setUp(self):
        self.host = NativeControls(self.definitions)
        self.api = widgets.adapt(self.host)
        for target, attribute, value in ((widgets.tk, 'Misc', Widget),
                                         (widgets.tk, 'BooleanVar', Variable),
                                         (widgets, 'style_widget', lambda widget: None),
                                         (widgets, 'style_checkbox', lambda widget: None)):
            patcher = patch.object(target, attribute, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def assert_owner_refresh(self):
        self.assertEqual(self.host.updates, [])
        self.host.loop.step('idle')
        self.assertEqual(self.host.updates, [])
        self.host.loop.step()
        self.assertEqual(self.host.updates, [('owner', False)])

    def test_checkbox_mapped_value_commits_before_postcommand_and_local_redraw(self):
        self.host.root['enabled'] = 'off'
        seen = []
        check = self.api.CheckBox("root['enabled']", mapFalseTrue=['off', 'on'], updateGUI=True,
                                  postcommand=lambda location: seen.append((location, self.host.root['enabled'])))[0]
        check.click()
        self.assertEqual(seen, [("root['enabled']", 'on')])
        self.assertEqual(self.host.tree_events, 1)
        self.assert_owner_refresh()

    def test_checkbox_invalid_mapped_value_moves_to_true(self):
        self.host.root['enabled'] = 'unexpected'
        check = self.api.CheckBox("root['enabled']", mapFalseTrue=['off', 'on'], updateGUI=True)[0]
        self.assertTrue(check.instate(['alternate']))
        check.click()
        self.assertEqual(self.host.root['enabled'], 'on')
        self.assert_owner_refresh()

    def test_checkbox_group_reset_commits_once_and_preserves_location_list(self):
        self.host.root.update(left=0, right=1)
        paths = ["root['left']", "root['right']"]
        seen = []
        check = self.api.CheckBox(paths, ['Left', 'Right'], useInt=True, default=[1, 0],
                                  updateGUI=True, postcommand=lambda location: seen.append(location))[0]
        check.reset()
        self.assertEqual((self.host.root['left'], self.host.root['right']), (1, 0))
        self.assertEqual(seen, [paths])
        self.assert_owner_refresh()

    def test_checkbox_without_refresh_still_commits(self):
        self.host.root['enabled'] = False
        self.api.CheckBox("root['enabled']", updateGUI=False)[0].click()
        self.assertIs(self.host.root['enabled'], True)
        self.assertEqual(self.host.tree_events, 1)
        self.assertFalse(self.host.loop.tasks)
        self.assertEqual(self.host.updates, [])

    def test_entry_valid_commit_preserves_postcommand_and_array_conversion(self):
        self.host.root['values'] = np.array([1, 2])
        seen = []
        entry = self.api.Entry("root['values']", updateGUI=True,
                               postcommand=lambda location: seen.append(location))
        entry.value.set('[3, 4]')
        entry.commit()
        self.assertIsInstance(self.host.root['values'], np.ndarray)
        np.testing.assert_array_equal(self.host.root['values'], [3, 4])
        self.assertEqual(seen, ["root['values']"])
        self.assert_owner_refresh()

    def test_entry_invalid_input_does_not_commit_or_schedule_redraw(self):
        self.host.root['number'] = 5
        seen = []
        entry = self.api.Entry("root['number']", updateGUI=True, postcommand=lambda location: seen.append(location))
        for invalid in ((False, None), (None, None), (None, 'int')):
            with self.subTest(validation=invalid):
                entry.validation = invalid
                entry.value.set('not valid')
                entry.commit()
                self.assertEqual(self.host.root['number'], 5)
                self.assertEqual(seen, [])
                self.assertEqual(self.host.tree_events, 0)
                self.assertFalse(self.host.loop.tasks)

    def test_entry_reset_stages_default_until_enter(self):
        self.host.root['number'] = 5
        seen = []
        entry = self.api.Entry("root['number']", default=12, updateGUI=True,
                               postcommand=lambda location: seen.append(location))
        entry.reset()
        self.assertEqual(entry.value.get(), '12')
        self.assertEqual(self.host.root['number'], 5)
        self.assertEqual(seen, [])
        self.assertFalse(self.host.loop.tasks)
        entry.commit()
        self.assertEqual(self.host.root['number'], 12)
        self.assertEqual(seen, ["root['number']"])
        self.assert_owner_refresh()

    def test_entry_norm_keeps_native_override_and_refreshes(self):
        self.host.root['number'] = 8
        seen = []
        entry = self.api.Entry("root['number']", norm=10, updateGUI=True,
                               postcommand=lambda location: seen.append(location))
        entry.value.set('2')
        entry.commit()
        self.assertEqual(self.host.root['number'], 20)
        self.assertEqual(seen, [])  # Native norm replaces the caller's postcommand.
        self.assert_owner_refresh()

    def test_filepicker_preserves_remote_tuple_and_postcommand_order(self):
        self.host.root['file'] = ''
        selected = ('/tmp/input.gacode', 'cluster', 'gateway')
        seen = []
        picker = self.api.FilePicker("root['file']", updateGUI=True, transferRemoteFile=None,
                                     postcommand=lambda location: seen.append((location, self.host.root['file'])))
        picker.choose(selected)
        self.assertEqual(seen, [("root['file']", selected)])
        self.assertEqual(picker.value.get(), repr(selected))
        self.assert_owner_refresh()

    def test_filepicker_postcommand_failure_still_refreshes_committed_value(self):
        self.host.root['file'] = ''
        def fail(location):
            raise ValueError('cannot load selected input')
        picker = self.api.FilePicker("root['file']", updateGUI=True, postcommand=fail)
        picker.choose('/tmp/input.gacode')
        self.assertEqual(self.host.root['file'], '/tmp/input.gacode')
        self.assertEqual(str(self.host.errors[0]), 'cannot load selected input')
        self.assert_owner_refresh()

    def test_button_string_command_and_positional_refresh_preserve_native_call(self):
        seen = []
        self.host.root['action'] = lambda: seen.append('called')
        button = self.api.Button('Apply', "root['action']", '', '', False, True)
        button.invoke()
        self.assertEqual(seen, ['called'])
        self.assertEqual(button.options['state'], 'disabled')
        self.assert_owner_refresh()
        self.assertEqual(button.options['state'], 'normal')

    def test_button_error_keeps_native_error_handling_and_deferred_refresh(self):
        def fail():
            raise ValueError('button failed')
        button = self.api.Button('Apply', fail, updateGUI=True)
        button.invoke()
        self.assertEqual(str(self.host.errors[0]), 'button failed')
        self.assertEqual(self.host.tree_events, 1)
        self.assert_owner_refresh()

    def test_button_close_does_not_redraw_closed_or_other_window(self):
        self.host._aux['topGUI'] = self.host.top
        seen = []
        button = self.api.Button('Close', lambda: seen.append('called'), closeGUI=True, updateGUI=True)
        button.invoke()
        self.assertEqual(seen, ['called'])
        self.assertFalse(self.host.top.winfo_exists())
        self.assertNotIn(str(self.host.top), self.host._GUIs)
        self.host.loop.step()
        self.assertEqual(self.host.updates, [])

    def test_button_without_gui_refresh_reenables_after_native_delay(self):
        button = self.api.Button('Apply', lambda: None)
        button.invoke()
        self.assertEqual(button.options['state'], 'disabled')
        self.assertEqual(self.host.tree_events, 1)
        self.host.loop.step()
        self.assertEqual(button.options['state'], 'normal')
        self.assertEqual(self.host.updates, [])

    def test_objectpicker_load_uses_native_conversion_and_owner_refresh(self):
        namespace = self.host.install_helpers()
        original_picker = namespace['FilePicker']
        seen = []
        picker = self.api.ObjectPicker(
            "root['payload']", 'Input', objectType=lambda filename: {'filename': filename},
            postcommand=lambda location: seen.append(location))
        self.assertFalse(self.host.loop.tasks, 'Constructing a helper must not request redraw')
        picker.choose('/tmp/input.tglf')
        self.assertEqual(self.host.root['payload'], {'filename': '/tmp/input.tglf'})
        self.assertEqual(seen, ["root['payload']"])
        self.assertIs(namespace['FilePicker'], original_picker, 'Native globals must remain untouched')
        self.assert_owner_refresh()

    def test_objectpicker_unset_keeps_native_callback_and_localizes_hardcoded_true(self):
        namespace = self.host.install_helpers()
        original_button = namespace['Button']
        self.host.root['payload'] = {'original': True}
        seen = []
        button = self.api.ObjectPicker("root['payload']", 'Input',
                                       unset_postcommand=lambda location: seen.append(location))
        self.assertFalse(self.host.loop.tasks, 'Constructing a helper must not request redraw')
        button.invoke()
        self.assertNotIn('payload', self.host.root)
        self.assertEqual(seen, ["root['payload']"])
        self.assertIs(namespace['Button'], original_button)
        self.assert_owner_refresh()

    def test_modulepicker_selection_defers_internal_native_combobox_refresh(self):
        namespace = self.host.install_helpers()
        original_combo = namespace['ComboBox']
        self.host.root['selection'] = "OMFIT['first']"
        seen = []
        combo = self.api.ModulePicker("root['selection']", modules=['profiles'], updateGUI=True,
                                      postcommand=lambda location: seen.append(location))
        self.assertFalse(self.host.loop.tasks, 'Constructing a helper must not request redraw')
        combo.select("[profiles] -- OMFIT['second']")
        self.assertEqual(self.host.root['selection'], "OMFIT['second']")
        self.assertEqual(seen, ["root['selection']"])
        self.assertIs(namespace['ComboBox'], original_combo)
        self.assert_owner_refresh()

    def test_shot_time_device_preserves_cross_window_mainsettings_sync(self):
        self.host.install_helpers()
        experiment = dict(device='EAST', shot=1, time=100, runid='',
                          shots=np.array([1]), times=np.array([100]))
        self.host.root['SETTINGS'] = {'EXPERIMENT': copy.deepcopy(experiment), 'MODULE': {'ID': 'TRXPL'}}
        self.host.root['MainSettings'] = {'EXPERIMENT': copy.deepcopy(experiment)}
        self.api.ShotTimeDevice(showDevice=['EAST', 'DIII-D'], showShot=False,
                                showTime=False, stopIfNotSet=False)
        self.assertFalse(self.host.loop.tasks)
        self.host.last_combo.select('DIII-D')
        self.assertEqual(self.host.root['SETTINGS']['EXPERIMENT']['device'], 'DIII-D')
        self.assertEqual(self.host.root['MainSettings']['EXPERIMENT']['device'], 'DIII-D')
        # This native helper writes shared MainSettings and intentionally keeps
        # its cross-window refresh; localizing its fields would leave peers stale.
        self.assertEqual(self.host.updates, [('owner', True), ('other', True)])


if __name__ == '__main__':
    unittest.main(verbosity=2)
