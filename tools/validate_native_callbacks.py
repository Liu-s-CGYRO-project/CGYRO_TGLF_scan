"""Exercise saved GUI callbacks after OMFIT's native import hook is removed.

Use the unchanged execGlobLoc body and SortedDict class from the supplied source.
Widgets/session/file readers are adapters; figures and spectrum exports are real.
No project LIB directory is added to sys.path, and no solver is executed.
"""
import argparse
import ast
from contextlib import nullcontext
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from validate_native_execution import NativeHost, REPO, np, plt, treeify


def fixtures():
    # Reuse only fixture definitions, avoiding test_compare's filesystem imports.
    definitions = {'fixture', 'FakeUI', 'Notebook'}
    path = REPO / 'tests/test_compare.py'
    nodes = [node for node in ast.parse(path.read_text(encoding='utf-8')).body
             if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in definitions]
    assert len(nodes) == len(definitions)
    namespace = dict(np=np, plt=plt, ast=ast, copy=copy, nullcontext=nullcontext,
                     state=SimpleNamespace(initialize_settings=lambda root: None))
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), namespace)
    return namespace


class CallbackTests(unittest.TestCase):
    host = None

    def setUp(self):
        self.fixture = fixtures()
        self.addCleanup(plt.close, 'all')
        self.assertFalse(any(name.startswith('OMFITlib_') for name in sys.modules))
        self.assertNotIn(str(REPO / 'CGYRO_TGLF_scan/LIB'), sys.path)

    def assert_cleaned(self, importers):
        self.assertEqual(sys.meta_path, importers)
        self.assertFalse(any(name.startswith('OMFITlib_') for name in sys.modules))

    def page(self, mode='CGYRO_vs_CGYRO'):
        root = treeify(self.fixture['fixture'](mode), self.host.factory)
        root['LIB'] = self.host.modules[('CGYRO_TGLF_scan',)]['LIB']
        ui = self.fixture['FakeUI'](root)
        plots = []

        def plot(key):
            plots.append(key)
            path = REPO / ('CGYRO_TGLF_scan/PLOTS/' + key + '.py')
            return self.host.execute(path.read_text(encoding='utf-8'), root,
                                     FigureNotebook=self.fixture['Notebook'])

        for key in ('CGYRO_vs_CGYRO', 'CGYRO_vs_TGLF'):
            root['PLOTS'][key] = SimpleNamespace(plot=lambda key=key: plot(key))
        entry = REPO / 'CGYRO_TGLF_scan/GUIS/CGYRO_vs_TGLF.py'
        before = list(sys.meta_path)
        self.host.execute(entry.read_text(encoding='utf-8'), root, OMFITx=ui, OMFIT={})
        self.assert_cleaned(before)
        buttons = {args[0]: args[1] for _, kind, args, _ in ui.events if kind == 'Button'}
        return root, buttons, plots, before

    def test_four_modes_plot_and_check_after_gui_returns(self):
        for mode in ('CGYRO_vs_CGYRO', 'CGYRO_vs_TGLF', 'TGLF_vs_TGLF', 'TGLF_vs_CGYRO'):
            with self.subTest(mode=mode):
                root, buttons, plots, before = self.page(mode)
                self.assertEqual(buttons['检查选择']()['errors'], [])
                buttons['绘制所选数据']()
                self.assertEqual(len(plots), 1)
                self.assertTrue(plt.get_fignums())
                for number in plt.get_fignums():
                    plt.figure(number).canvas.draw()
                self.assert_cleaned(before)
                plt.close('all')

    def test_invalid_options_still_block_plot_after_gui_returns(self):
        root, buttons, plots, before = self.page()
        settings = root['SETTINGS']['PHYSICS']['CGYRO_vs_CGYRO']
        invalid = [dict(plot_mode='Plot single ky', single_ky_values='bad'),
                   dict(plot_mode='Plot eigen ball', eigen_ky_mode='single ky', eigen_ky_values=''),
                   dict(plot_mode='Plot γ/γ_ref', gamma_ref_value='nan'),
                   dict(plot_mode='Plot γ/γ_ref', gamma_ref_mode='single ky', gamma_ref_value='', gamma_ref_ky_values=''),
                   dict(plot_mode='unknown')]
        for values in invalid:
            with self.subTest(values=values):
                settings.update(values)
                self.assertTrue(buttons['检查选择']()['errors'])
                with self.assertRaises(ValueError):
                    buttons['绘制所选数据']()
                self.assertEqual(plots, [])
                self.assert_cleaned(before)

    def test_export_after_gui_returns_writes_raw_spectra_and_restores_flag(self):
        root, buttons, plots, before = self.page()
        callback = buttons['导出频率 / 增长率谱…']
        app = callback.__self__
        settings = root['SETTINGS']['PHYSICS']['CGYRO_vs_CGYRO']
        settings['linear_export_now'] = False
        with tempfile.TemporaryDirectory() as directory:
            app._select_export_directory = lambda *args: directory
            callback()
            files = list(Path(directory).glob('cgyro_spectra_*/omega_gamma_vs_ky__*.txt'))
            self.assertEqual(len(files), 2)
            first = np.loadtxt(files[0])
            self.assertEqual(first.shape, (4, 7))
            np.testing.assert_allclose(first[:, 0], [.1, .2, .4, .8])
        self.assertFalse(settings['linear_export_now'])
        self.assertEqual(plots, ['CGYRO_vs_CGYRO'])
        self.assert_cleaned(before)

    def test_cancelled_export_after_gui_returns_preserves_state(self):
        root, buttons, plots, before = self.page()
        callback = buttons['导出频率 / 增长率谱…']
        callback.__self__._select_export_directory = lambda *args: None
        callback()
        self.assertEqual(plots, [])
        self.assertFalse(root['SETTINGS']['PHYSICS']['CGYRO_vs_CGYRO']['linear_export_now'])
        self.assert_cleaned(before)

    def test_completed_multi_input_page_can_render_after_import_cleanup(self):
        root = treeify({'SETTINGS': {}, 'TGLF_CASES': {'case': {
            'enabled': True, 'label': 'completed case', 'source': 'input.gacode',
            'info': {'points': 3, 'ions': 1}, 'sha256': 'synthetic', 'radii': '', 'extra': '',
            'selected_run': 'run', 'runs': {'run': {'created': 'fixture', 'status': 'complete',
                'plan': {'coordinate': 'rho', 'radii': [.5], 'parameters': {}},
                'points': {'point': {'radius': .5, 'status': 'complete', 'selected_attempt': 'attempt',
                    'attempts': {'attempt': {'status': 'complete', 'workdir': '/fixture',
                        'result': {'gbflux': {'data': [('ion', 1., 2.)]}}}}}}}}}}}, self.host.factory)
        root['LIB'] = self.host.modules[('CGYRO_TGLF_scan',)]['LIB']
        ui = self.fixture['FakeUI'](root)
        before = list(sys.meta_path)
        out = self.host.execute('from OMFITlib_tglf_multi_ui import MultiInputUI\napp = MultiInputUI(root, OMFITx)\napp.render()',
                                root, OMFITx=ui)
        self.assert_cleaned(before)
        ui.events.clear()
        out['app'].render()
        labels = [args[0] for _, kind, args, _ in ui.events if kind == 'Label']
        self.assertTrue(any('ion | 1 | 2' in text for text in labels))
        self.assert_cleaned(before)


def validate(source):
    host = NativeHost(source)
    CallbackTests.host = host
    stream = io.StringIO()
    with patch.dict(sys.modules, {'omfit_classes.utils_base': host.registry}):
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(CallbackTests)
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    report = dict(tests=result.testsRun, failures=len(result.failures), errors=len(result.errors),
                  python=sys.version.split()[0], native_functions=host.evidence,
                  native_mapping=host.mapping_evidence, import_cleanup_checked=True,
                  project_lib_on_sys_path=False, real_matplotlib=True,
                  complete_omfit_session_tested=False, solver_executed=False)
    return report, stream.getvalue(), result.wasSuccessful()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('omfit_source', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report, log, passed = validate(args.omfit_source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    args.output.with_suffix('.log').write_text(log, encoding='utf-8')
    print(log)
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if passed else 1)
