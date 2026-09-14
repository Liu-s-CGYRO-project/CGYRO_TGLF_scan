"""Exercise saved tree branches and newly created records with OMFIT's API."""
import ast
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import warnings

import matplotlib.pyplot as plt
import numpy as np

from omfit_mapping import OMFITMapping, treeify
import test_project as dashboard
import test_tglf_multi as multi
import test_compare as compare


class NativeProjectTest(dashboard.ProjectTest):
    tree_factory = OMFITMapping


class NativeMultiInputTest(multi.TestMultiInput):
    tree_factory = OMFITMapping


class NativeIntegrationTest(unittest.TestCase):
    tree_factory = OMFITMapping

    def tree(self, value):
        return treeify(value, self.tree_factory)

    def setUp(self):
        self.addCleanup(plt.close, 'all')

    def test_original_get_and_update_errors_are_reproduced(self):
        root = self.tree({'INPUTS': {}})
        with self.assertRaisesRegex(TypeError, 'default'):
            root.get('INPUTS', {}).get('input.cgyro')
        with self.assertRaises(TypeError):
            root.update(status='ready')

    def test_real_main_entry_renders_saved_histories_and_pending_choice(self):
        root = self.tree(dashboard.fixture())
        actions = dashboard.project.ProjectActions(root, self.tree_factory)
        root['TGLF_scan']['TGLF']['FILES'] = self.tree({'input.tglf': dashboard.tglf(), 'result': [42]})
        actions.propose_tglf(self.tree(dict(dashboard.tglf(), SAT_RULE=2)), 'candidate')
        root['CGYRO_scan']['RUN_MANIFEST'] = self.tree({'status': 'submitted', 'points': ['a'], 'workDir': '/tmp/run'})
        root['TGLF_CASES'] = self.tree({'saved': {'enabled': True, 'label': 'saved', 'selected_run': 'r1',
                                                'runs': {'r1': {'status': 'complete'}}}})
        actions._record('old error', status='failed', error='saved message', previous_inputs=self.tree({'input': [7]}))
        entry = dashboard.REPO / 'CGYRO_TGLF_scan/GUIS/main.py'
        session = self.tree({'OMFITtemplates': {'GUIS': {'main': SimpleNamespace(run=Mock())}}})
        for page in dashboard.project.PAGES.values():
            with self.subTest(page=page):
                actions.settings['page'] = page
                ui = dashboard.UI(root)
                exec(compile(entry.read_text(encoding='utf-8'), str(entry), 'exec'),
                     dict(root=root, OMFITtree=self.tree_factory, OMFITgacode=Mock(), OMFIT=session,
                          OMFITx=ui, SERVER=SimpleNamespace(listServers=lambda: {'localhost': {}}), OMFITworkDir=Mock()))
                self.assertTrue(ui.events)
        self.assertEqual(dashboard.project.summary(root)['multi_selected'], 1)
        self.assertEqual(root['TGLF_scan']['TGLF']['FILES']['result'], [42])
        self.assertEqual(len(dashboard.project.pending_inputs(root)), 1)
        session['OMFITtemplates']['GUIS']['main'].run.assert_not_called()

    def test_valid_native_runtime_fields_are_not_silently_treated_as_missing(self):
        root = self.tree(dashboard.fixture())
        remote = root['CGYRO_scan']['SETTINGS']['REMOTE_SETUP']
        remote['serverPicker'] = 'cluster'
        for scheduler in ('slurm', 'pbs'):
            remote['cluster'] = self.tree(dict(scheduler=scheduler, server='cluster.example', workDir='/scratch/run',
                executable='cgyro -e . -n 4', environment='source /chosen/setup', queue='debug', w='00:30:00',
                nodes=1, ppn=4, ntasks_per_node=4, array_parallel=2))
            self.assertEqual(dashboard.project.runtime_issues(root, 'cgyro'), [])
            remote['cluster']['nodes'] = 0
            self.assertIn('nodes必须为正整数', dashboard.project.runtime_issues(root, 'cgyro'))
        for name in ('transfer', 'tglf', 'tgyro', 'profiles'):
            node = dashboard.project.module(root, name)
            node['SETTINGS']['REMOTE_SETUP']['server'] = 'localhost'
            node['SETTINGS']['SETUP']['executable'] = 'chosen-command'
            self.assertEqual(dashboard.project.runtime_issues(root, name), [])

    def test_input_lookup_keeps_lazy_loading_and_explicit_default(self):
        factory = self.tree_factory
        class LazyInput(factory):
            def load(self):
                self['input.cgyro'] = dashboard.cgyro()
        inputs = LazyInput()
        inputs.dynaLoad = True
        # The lightweight fixture has no lazy loader; this fallback exercises
        # the same mapping access. The native validation uses real decorators.
        if factory is OMFITMapping:
            inputs.load()
        root = self.tree(dashboard.fixture())
        root['CGYRO_scan']['INPUTS'] = inputs
        issues = dashboard.project.cgyro_input_issues(root)
        self.assertIn('准备尚未确认', issues[0])
        self.assertIn('input.cgyro', inputs)

    def test_comparison_pages_and_spectra_read_nested_native_trees(self):
        for mode in ('CGYRO_vs_TGLF', 'TGLF_vs_CGYRO', 'TGLF_vs_TGLF', 'CGYRO_vs_CGYRO'):
            with self.subTest(mode=mode):
                root = self.tree(compare.fixture(mode))
                if mode == 'TGLF_vs_TGLF':
                    root['SETTINGS']['PHYSICS'][mode]['plot']['show_flux_spectra'] = False
                ui = compare.FakeUI(root)
                compare.modules['ui'].ComparisonUI(root, ui).render()
                compare.Notebook.figures = []
                with patch.object(compare.modules['dispatch'], 'FigureNotebook', compare.Notebook, create=True), \
                     patch.object(compare.modules['cgyro'], 'FigureNotebook', compare.Notebook, create=True), \
                     patch.object(compare.modules['tglf'], 'FigureNotebook', compare.Notebook, create=True):
                    if mode == 'CGYRO_vs_CGYRO':
                        compare.modules['cgyro'].run_plot(root)
                    else:
                        compare.modules['dispatch'].run_plot(root)
                self.assertTrue(compare.Notebook.figures)
                for figure in compare.Notebook.figures:
                    figure.canvas.draw()
                    self.assertTrue(any(axis.lines for axis in figure.axes))
                plt.close('all')

    def test_saved_cache_provenance_reuses_only_matching_solver_and_input(self):
        source = dashboard.REPO / 'CGYRO_TGLF_scan/TGLF_scan/TGLF/LIB/OMFITlib_tglf_cache.py'
        spec = importlib.util.spec_from_file_location('native_cache_test', source)
        cache = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cache)
        old = self.tree({'reusable': True, 'sha256': 'input-a', 'solver_sha256': 'solver-a'})
        current = self.tree(dict(old))
        results, spectra = self.tree({'r': {'saved': np.array([42.])}}), self.tree({'r': {'saved': [7]}})
        records = self.tree({'r': old})
        cache.prepare(results, spectra, 'r', records, current, self.tree_factory)
        np.testing.assert_array_equal(results['r']['saved'], [42.])
        current = self.tree(dict(current))
        current['solver_sha256'] = 'solver-b'
        self.assertFalse(cache.matches(old, current))
        cache.prepare(results, spectra, 'r', records, current, self.tree_factory)
        self.assertEqual(results['r'], {})
        self.assertEqual(spectra['r'], {})

    def test_mapping_call_contract_across_project_sources(self):
        violations = []
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', SyntaxWarning)
            warnings.filterwarnings('ignore', message='invalid escape sequence', category=DeprecationWarning)
            for path in (dashboard.REPO / 'CGYRO_TGLF_scan').rglob('*.py'):
                for call in ast.walk(ast.parse(path.read_text(encoding='utf-8-sig'))):
                    if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Attribute):
                        continue
                    name = ast.unparse(call.func.value)
                    # Tk Listbox.get(index) is a widget API, not a mapping.
                    if path.name == 'OMFITlib_compare_widgets.py' and name == 'box':
                        continue
                    if call.func.attr in ('get', 'setdefault') and len(call.args) == 1 and not call.keywords:
                        violations.append((str(path), call.lineno, 'missing default'))
                    if call.func.attr == 'update' and call.keywords:
                        # STATUS is an explicitly constructed builtin dict.
                        if path.name != 'OMFITlib_project_ui.py' or name != 'STATUS':
                            violations.append((str(path), call.lineno, 'keyword update'))
        self.assertEqual(violations, [])


if __name__ == '__main__':
    unittest.main()
