"""Legacy GUI boundaries with opaque archived payloads and lazy tab hosts."""
import ast
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import OMFITlib_gui_api as api
import OMFITlib_gui_deferred as deferred
import OMFITlib_gui_layout as layout

BASE = Path(__file__).resolve().parents[1] / 'CGYRO_TGLF_scan/TGLF_scan'


class Opaque(dict):
    def __getitem__(self, key):
        raise AssertionError('An unselected payload was read: ' + str(key))
    def items(self):
        raise AssertionError('An unselected payload was traversed')
    def __deepcopy__(self, memo):
        raise AssertionError('An unselected payload was copied')


class UI:
    def __init__(self, namespace):
        self.ns, self.events = namespace, []
    def same_row(self):
        return nullcontext()
    def __getattr__(self, name):
        def record(*args, **kwargs):
            self.events.append((name, args, kwargs))
            if name in ('Entry', 'CheckBox', 'ComboBox') and 'default' in kwargs:
                paths = args[0] if isinstance(args[0], list) else [args[0]]
                defaults = kwargs['default'] if isinstance(args[0], list) else [kwargs['default']]
                for path, value in zip(paths, defaults):
                    node = ast.parse(path, mode='eval').body
                    parent = eval(compile(ast.Expression(node.value), '<location>', 'eval'), self.ns)
                    parent.setdefault(ast.literal_eval(node.slice), value)
            return SimpleNamespace(master=SimpleNamespace(pack_forget=lambda: None))
        return record


class SelectedPages:
    def __init__(self, ui, captions, state, key, render):
        self.render, self.state, self.key = render, state, key
        self.captions = captions
        ui.events.append(('Pages', (), dict(page=self)))
        self.select(state.get(key) if state.get(key) in captions else next(iter(captions)))
    def select(self, key):
        self.state[self.key] = key
        self.render(key)


class LegacyBoundaries(unittest.TestCase):
    def run_gui(self, relative, root, **kwargs):
        ns = dict(root=root, scratch={}, compoundGUI=True, input_gacode=None,
                  OMFITtree=dict, OMFITgacode=dict, is_int=lambda value: isinstance(value, int),
                  treeLocation=lambda obj: ['root'])
        ns.update(kwargs)
        ui = UI(ns)
        ns['OMFITx'] = ui
        ns['defaultVars'] = lambda **defaults: [ns.setdefault(key, value) for key, value in defaults.items()]
        with (patch.object(api, 'adapt', side_effect=lambda value: value),
              patch.object(deferred, 'deferred_section', return_value=None),
              patch.object(deferred, 'TabPages', SelectedPages),
              patch.object(layout, 'finish_gui_layout')):
            exec(compile((BASE / relative).read_text(encoding='utf-8'), str(BASE / relative), 'exec'), ns)
        return ui, ns

    def test_all_legacy_scalar_controls_are_explicitly_scoped(self):
        paths = [p for p in BASE.rglob('*') if p.is_file() and p.parent.name == 'GUIS'
                 and (p.suffix == '.py' or p.name == 'modifyGradientsGUI')]
        self.assertEqual(len(paths), 25)
        controls = 0
        for path in paths:
            source = path.read_text(encoding='utf-8')
            self.assertIn('adapt(OMFITx)', source, path)
            tree = ast.parse(source, feature_version=(3, 9))
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr in ('Entry', 'ComboBox', 'CheckBox', 'ListEditor')):
                    options = {key.arg: key.value for key in node.keywords}
                    self.assertIn('refresh_tree', options, (path, node.lineno))
                    if ast.literal_eval(options['refresh_tree']):
                        self.assertTrue(any(word in ast.get_source_segment(source, node)
                                            for word in ('reloadDVscan', 'reloadTGYRO', "['reset']", 'postcommand=load_project')))
                    controls += 1
        self.assertGreater(controls, 200)

    def test_empty_profile_preparation_does_not_reset_retained_scans(self):
        retained = Opaque(old_result='opaque')
        reset = Mock(side_effect=AssertionError('Rendering reset user results'))
        root = {'SETTINGS': {'PHYSICS': {}, 'GUI': {}}, 'scanResults': retained,
                'TGLF': {'SETTINGS': {'PHYSICS': {}}, 'GUIS': {'TGLF_GUI': 'input'}},
                'TGYRO': {'PROFILES_GEN': {'OUTPUTS': {}, 'GUIS': {'standaloneGUI': 'profiles'}}},
                'SCRIPTS': {'reset': reset}}
        ui, _ = self.run_gui('GUIS/tglf_scan_gui.py', root)
        self.assertIs(root['scanResults'], retained)
        reset.runNoGUI.assert_not_called()
        self.assertEqual([args[0] for kind, args, _ in ui.events if kind == 'CompoundGUI'], ['profiles'])

    def test_main_dv_lists_only_keys_and_builds_only_selected_tab(self):
        root = {'SETTINGS': {'PHYSICS': {'runs_label': 'old'}, 'GUI': {}},
                'TGLF_SCAN_DB': Opaque(old='opaque'),
                'TGYRO': {'PROFILES_GEN': {'OUTPUTS': {'input.gacode': Opaque()},
                    'GUIS': {'standaloneGUI': 'profiles', 'modifyIonsGUI': 'ions'}},
                    'INPUTS': {'input.tglf': Opaque()}},
                'TGLF': {'GUIS': {'TGLF_GUI': 'parameters'}}, 'GUIS': {'particleDandVgui': 'transport'},
                'SCRIPTS': {'reloadDVscan': Mock()}}
        ui, _ = self.run_gui('GUIS/main_DV_gui.py', root)
        self.assertEqual([args[0] for kind, args, _ in ui.events if kind == 'CompoundGUI'], ['profiles'])
        pages = next(options['page'] for kind, _, options in ui.events if kind == 'Pages')
        pages.select('ions')
        self.assertEqual([args[0] for kind, args, _ in ui.events if kind == 'CompoundGUI'], ['profiles', 'ions'])

    def test_native_scan_page_does_not_load_spectrum_for_ky_choice(self):
        physics = dict(single_Ti=False, scanParameter='SAT_RULE', scanParameterMin=.5, scanParameterMax=2.)
        root = {'FILES': {'input.tglf': {'NS': 0, 'SAT_RULE': 1}}, 'SETTINGS': {'PHYSICS': physics},
                'scanResults': Opaque(SAT_RULE='opaque'), 'PLOTS': {'plot_growthrate_scan': object()}}
        ui, _ = self.run_gui('TGLF/GUIS/scanGUI.py', root, show_constraints=False)
        controls = [(args, kwargs) for kind, args, kwargs in ui.events if kind == 'Entry']
        self.assertTrue(any("['plot_ky']" in args[0] and not kw['updateGUI'] for args, kw in controls))
        action = next(args[1] for kind, args, _ in ui.events if kind == 'Button' and args[0] == '绘制指定 ky 的增长率')
        with patch.object(api, 'plot_view', return_value=None) as plot:
            # The GUI imported its callable; replace that exact global boundary.
            action.__globals__['plot_view'] = plot
            action()
        plot.assert_called_once_with(root['PLOTS']['plot_growthrate_scan'], param='SAT_RULE')

    def test_quantity_selector_lists_names_without_loading_array_values(self):
        root = {'SETTINGS': {}}
        ui, _ = self.run_gui('GUIS/selection_GUI.py', root,
            dictionary_to_read=Opaque(D='unopened array', v='unopened array', __metadata='hidden'))
        choices = next(args[1] for kind, args, _ in ui.events if kind == 'ComboBox')
        self.assertEqual(choices, ['', 'D', 'v'])

    def test_native_parameter_tabs_do_not_build_hidden_constraints(self):
        root = {'FILES': {'input.tglf': {'USE_TRANSPORT_MODEL': True, 'NN_MAX_ERROR': -1., 'NS': 2}},
                'SETTINGS': {'GUI': {}}, 'GUIS': {'constraints_GUI': 'constraints'}}
        ui, _ = self.run_gui('TGLF/GUIS/TGLF_GUI.py', root, showButtons=False)
        self.assertFalse(any(kind == 'CompoundGUI' for kind, _, _ in ui.events))
        pages = next(options['page'] for kind, _, options in ui.events if kind == 'Pages')
        with patch.object(layout, 'finish_gui_layout'):
            pages.select('constraints')
        self.assertEqual([args[0] for kind, args, _ in ui.events if kind == 'CompoundGUI'], ['constraints'])

    def test_tgyro_navigation_does_not_touch_hidden_output_payloads(self):
        root = {'SETTINGS': {'EXPERIMENT': {'runid': 'old'}, 'GUI': {}}, 'RUN_DB': Opaque(old='opaque'),
                'OUTPUTS': Opaque(output='opaque', **{'input.gacode': 'opaque'}),
                'GUIS': {'Rungui': 'run', 'Plotgui': 'plot', 'D_and_v_gui': 'transport'},
                'SCRIPTS': {'reloadTGYRO': Mock()}}
        ui, _ = self.run_gui('TGYRO/GUIS/TGYROgui.py', root)
        self.assertEqual([args[0] for kind, args, _ in ui.events if kind == 'CompoundGUI'], ['run'])
        pages = next(options['page'] for kind, _, options in ui.events if kind == 'Pages')
        pages.select('plot')
        self.assertEqual([args[0] for kind, args, _ in ui.events if kind == 'CompoundGUI'], ['run', 'plot'])

    def test_tgyro_external_module_catalog_is_inspected_only_explicitly(self):
        project = Mock()
        project.info.return_value = {'modules': ['OMFITprofiles', 'unrelated']}
        scratch = dict(outside_module=True, profile_module_project='/fixture/old-project.zip')
        root = {'RUN_DB': {'old': Opaque()}, 'OUTPUTS': {}, 'SETTINGS': {'DEPENDENCIES': {}}}
        args = dict(OMFITproject=project, scratch=scratch, MainSettings={'SETUP': {'projectsDir': '/fixture'}},
                    profiles_module=None, ismodule=lambda *args: False)
        ui, _ = self.run_gui('TGYRO/GUIS/Plotgui.py', root, **args)
        project.info.assert_not_called()
        inspect = next(values[1] for kind, values, _ in ui.events
                       if kind == 'Button' and values[0] == '读取 / 刷新模块列表')
        inspect()
        project.info.assert_called_once_with(filename='/fixture/old-project.zip')
        ui, _ = self.run_gui('TGYRO/GUIS/Plotgui.py', root, **args)
        self.assertEqual(project.info.call_count, 1)
        self.assertTrue(any(kind == 'ComboBox' and values[1] == ['OMFITprofiles']
                            for kind, values, _ in ui.events))


if __name__ == '__main__':
    unittest.main()
