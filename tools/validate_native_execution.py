"""Linux execution checks using OMFIT's unchanged importer/defaultVars bodies.

The source checkout supplies execGlobLoc, _defaultVars and SortedDict. Only the
outer Matplotlib preference-lock decorator is omitted. Script execution,
library lookup, injected pylab names and import-cache cleanup are native.
Project-file nodes, solver readers and the session host are adapters: this is
not a complete OMFIT process, save/reload acceptance test or solver validation.
"""
import argparse
import ast
from contextlib import contextmanager
import copy
import hashlib
import inspect
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch
import warnings

import numpy as np
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt

from validate_project_mapping import load_native_mapping
from omfit_mapping import treeify

REPO = Path(__file__).resolve().parents[1]
CG = REPO / 'CGYRO_TGLF_scan/CGYRO_scan'


def rows():
    for line in (REPO / 'OMFITsave.txt').read_text(encoding='utf-8').splitlines():
        fields = line.split(' <-:-:-> ')
        if len(fields) != 4 or not fields[0].startswith('['):
            continue
        node = ast.parse('root' + fields[0], mode='eval').body
        keys = []
        while isinstance(node, ast.Subscript):
            keys.insert(0, ast.literal_eval(node.slice))
            node = node.value
        yield tuple(keys), fields[1], fields[2]


def settings(path):
    def decode(value):
        if '__ndarray_tolist__' in value:
            return np.array(value['__ndarray_tolist__'], dtype=value['dtype']).reshape(value['shape'])
        return value
    return json.loads(path.read_text(encoding='utf-8'), object_hook=decode)


class NativeHost:
    def __init__(self, source):
        self.source = Path(source)
        self.factory, self.registry, self.mapping_evidence = load_native_mapping(self.source / 'omfit_classes/sortedDict.py')
        source = self.source / 'omfit_classes/omfit_python.py'
        raw = source.read_text(encoding='utf-8')
        nodes = [n for n in ast.parse(raw).body if isinstance(n, ast.FunctionDef) and n.name in ('execGlobLoc', '_defaultVars')]
        assert len(nodes) == 2
        self.evidence = {n.name: hashlib.sha256(ast.get_source_segment(raw, n).encode()).hexdigest() for n in nodes}
        for node in nodes:
            node.decorator_list = []
        pylab = {}
        exec('from pylab import *', pylab)
        class OMFITobject:
            pass
        class Task:
            def __init__(node, filename, root):
                node.filename, node.root = str(filename), root
            def run(node, **kwargs):
                return self.execute(Path(node.filename).read_text(encoding='utf-8'), node.root, user=kwargs)
            runNoGUI = run
            plot = run
        class Plot(Task):
            pass
        class Reader(self.factory):
            pass
        self.Task = Task
        self.gacode = ModuleType('omfit_classes.omfit_gacode')
        self.gacode.OMFITcgyro = type('OMFITcgyro', (Reader,), {})
        self.gacode.OMFITgyro = type('OMFITgyro', (Reader,), {})
        namespace = dict(__name__='native_execution_validation', all_pylab_imports=pylab,
                         np=np, pyplot=plt, sys=sys, inspect=inspect, contextmanager=contextmanager,
                         SortedDict=self.factory, OMFITtree=self.factory, OMFITobject=OMFITobject,
                         _OMFITpython=Task, OMFITpythonTask=Task, OMFITpythonPlot=Plot,
                         OMFITexception=RuntimeError, EndOMFITpython=type('EndOMFITpython', (Exception,), {}),
                         OMFITaux={'prun_process': []}, OMFITreloadedDict={}, SERVER=SimpleNamespace(),
                         printd=lambda *a, **kw: None, printe=print, printw=print)
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), 'exec'), namespace)
        self.executor = namespace['execGlobLoc']
        self.modules = {}
        saved = list(rows())
        with patch.dict(sys.modules, {'omfit_classes.utils_base': self.registry}):
            for keys, kind, ref in saved:
                if kind == 'OMFITmodule':
                    self.modules[keys] = self.factory({'LIB': self.factory()})
            for keys, kind, ref in saved:
                if not kind.startswith('OMFITpython'):
                    continue
                owner = max((m for m in self.modules if keys[:len(m)] == m), key=len)
                root = self.modules[owner]
                node = root
                for key in keys[len(owner):-1]:
                    node = node.setdefault(key, self.factory())
                node[keys[-1]] = Task(REPO / ref, root)
        self.cg = self.modules[('CGYRO_TGLF_scan', 'CGYRO_scan')]

    def execute(self, text, root=None, user=None, **inputs):
        inputs.update(root=root if root is not None else self.cg, rootName='test_root')
        with patch.dict(sys.modules, {'omfit_classes.utils_base': self.registry,
                                      'omfit_classes.omfit_gacode': self.gacode}):
            return self.executor(text, dict(user or {}), inputs, {}, {})

    def cg_fixture(self):
        root = self.cg
        root['SETTINGS'] = treeify(settings(CG / 'SettingsNamelist.txt'), self.factory)
        root['INPUTS'] = self.factory({'input.cgyro': self.factory({'N_SPECIES': 3})})
        root['OUTPUTS'] = self.factory({'do_not_replace': 42, 'NonLinear': self.factory()})
        root['OUTPUTScan'] = self.factory()
        root['SETTINGS']['PLOTS']['iflwphy'] = 0
        root['SETTINGS']['PLOTS']['1d']['para_eigen'] = []
        root['SETTINGS']['PLOTS']['2d']['para_x_eigen'] = []
        root['SETTINGS']['PLOTS']['nl']['case_plot'] = []
        root['SETTINGS']['SETUP']['idimrun'] = 1
        return root


class NativeExecutionTests(unittest.TestCase):
    host = None

    def setUp(self):
        self.addCleanup(plt.close, 'all')

    def reader(self):
        return self.host.execute('from OMFITlib_cgyro_read import *')

    def flux(self):
        return {'input.cgyro.gen': self.host.factory({'N_FIELD': 1, 'Z_1': 1, 'Z_2': 2, 'Z_3': -1}),
                'qlflux_ky': {name: np.array([[[1., 2.]], [[2., 3.]], [[3., 4.]]])
                              for name in ('particle', 'energy', 'momentum')}}

    def test_native_pylab_reproduces_old_generator_problem(self):
        out = self.host.execute('old = any(x is None for x in (1, 2))\nfrom builtins import any\nnew = any(x is None for x in (1, 2))')
        self.assertTrue(bool(out['old']))
        self.assertFalse(out['new'])

    def test_reader_flux_in_native_namespace_and_required_get_defaults(self):
        totals, raw, labels = self.reader()['ql_species_flux'](self.flux())
        np.testing.assert_allclose(totals['Gi'], [8, 0, 0])
        np.testing.assert_allclose(totals['Qi'], [5, 0, 0])
        np.testing.assert_allclose(totals['Ge'], [4, 0, 0])
        self.assertEqual(labels, ['ion_1', 'ion_2', 'electron'])
        self.assertEqual(raw['particle'].shape, (3, 3))

    def test_reader_rejects_nonfinite_and_inconsistent_channels(self):
        reader = self.reader()['ql_species_flux']
        case = self.flux()
        case['qlflux_ky']['energy'][0, 0, -1] = np.nan
        with self.assertRaisesRegex(ValueError, 'Nonfinite'):
            reader(case)
        case = self.flux()
        case['qlflux_ky']['energy'] = np.ones((2, 1, 2))
        with self.assertRaisesRegex(ValueError, 'dimensions'):
            reader(case)

    def test_frequency_uncertainty_preserves_negative_growth(self):
        readfreq = self.reader()['readfreq']
        mean, error = readfreq({'freq': {'omega': [[1., 3.]], 'gamma': [[-4., -2.]]}})
        np.testing.assert_allclose(mean, [2., -3.])
        np.testing.assert_allclose(error, [.5, 1/3])
        with self.assertRaises(ValueError):
            readfreq({'freq': {'omega': [[1.]], 'gamma': [[-2.]]}})

    def test_no_python_path_changes_or_leaked_reader_exports(self):
        path = list(sys.path)
        out = self.host.execute('import OMFITlib_cgyro_read as reader\nexports = reader.__all__')
        self.assertEqual(out['exports'], ['readfreq', 'ql_species_flux', 'readchi', 'getoutmsg', 'num2str_xj'])
        self.assertEqual(path, sys.path)
        self.assertNotIn('OMFITlib_cgyro_read', sys.modules)

    def test_library_uses_saved_omfit_file_each_time(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'reader.py'
            root = self.host.factory({'LIB': self.host.factory()})
            root['LIB']['OMFITlib_probe'] = self.host.Task(path, root)
            path.write_text('value = 1\n', encoding='utf-8')
            one = self.host.execute('from OMFITlib_probe import value', root)
            path.write_text('value = 2\n', encoding='utf-8')
            two = self.host.execute('from OMFITlib_probe import value', root)
            self.assertEqual((one['value'], two['value']), (1, 2))
            with self.assertRaisesRegex(RuntimeError, 'library files'):
                self.host.execute('import OMFITlib_probe')

    def test_legacy_saved_helper_entry_loads_registered_library(self):
        out = self.host.cg['PLOTS']['CGYROscan']['assist']['cgyro_read_xj'].run()
        self.assertEqual(out['num2str_xj'](.1, 5), '0.10000')

    def test_all_helper_blocks_accept_multiline_programs(self):
        count = 0
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'getglobal.py'
            path.write_text('def helper_function():\n    return root["marker"] + 1\nhelper_result = helper_function()\n', encoding='utf-8')
            for source in CG.rglob('*.py'):
                tree = ast.parse(source.read_text(encoding='utf-8'))
                for node in ast.walk(tree):
                    if not isinstance(node, ast.With) or '_helper_source' not in ast.unparse(node.items[0]):
                        continue
                    root = self.host.factory({'marker': count})
                    target = ast.unparse(node.items[0].context_expr.args[0].value)
                    keys = []
                    while target.startswith('root'):
                        expr = ast.parse(target, mode='eval').body
                        while isinstance(expr, ast.Subscript):
                            keys.insert(0, ast.literal_eval(expr.slice))
                            expr = expr.value
                        break
                    branch = root
                    for key in keys[:-1]:
                        branch = branch.setdefault(key, self.host.factory())
                    branch[keys[-1]] = self.host.Task(path, root)
                    program = ast.unparse(node)
                    result = self.host.execute(program, root)
                    self.assertEqual(result['helper_result'], count + 1, str(source))
                    count += 1
        self.assertEqual(count, 34)

    def test_registered_libraries_import_in_their_own_module(self):
        checked = []
        for owner, root in self.host.modules.items():
            for key in root['LIB']:
                with self.subTest(module=owner, library=key):
                    self.host.execute('import ' + key, root)
                    checked.append('/'.join(owner + ('LIB', key)))
        self.host.imported_libraries = checked

    def test_proxy_functions_survive_native_import_cleanup(self):
        from urllib import request
        root = self.host.modules[('OMFITtemplates',)]
        before = list(sys.meta_path)
        out = self.host.execute('from OMFITlib_template_proxy import relay_proxy, proxy_handler\n'
                                'from OMFITlib_template_github import GitHub', root)
        self.assertEqual(sys.meta_path, before)
        self.assertFalse(any(name.startswith('OMFITlib_') for name in sys.modules))
        url = 'http://omfit:native-test-only@127.0.0.1:32123'
        environment = self.host.factory({'OMFIT_GITHUB_RELAY_PORT': '32123', 'https_proxy': url})
        self.assertEqual(out['relay_proxy'](environment), url)
        handler = out['proxy_handler'](url)
        req = request.Request('https://api.github.com/rate_limit')
        handler.https_open(req)
        self.assertEqual(req.host, '127.0.0.1:32123')
        self.assertEqual(req._tunnel_host, 'api.github.com')
        self.assertTrue(req.get_header('Proxy-authorization').startswith('Basic '))
        client = out['GitHub']('team/demo', token='', proxy=url)
        self.assertNotIn('native-test-only', client.connection)

    def test_collectors_define_all_four_classes_inside_omfit(self):
        root = self.host.cg_fixture()
        cases = [('CGYROscan', 'collect.py', 'OMFITcgyro_eigen'),
                 ('CGYROscan', 'collect_gyro.py', 'OMFITgyro_eigen'),
                 ('CGYROalone', 'collect.py', 'OMFITcgyro_nonlin'),
                 ('CGYROalone', 'collect_gyro.py', 'OMFITgyro_nonlin')]
        self.host.collector_classes = {}
        for kind, key, name in cases:
            with self.subTest(collector=name):
                result = root['PLOTS'][kind]['assist'][key].run()
                self.assertIn(name, result)
                self.host.collector_classes[name] = result[name]
        self.assertEqual(root['OUTPUTS']['do_not_replace'], 42)

    def test_miller_method_from_private_archive_is_available_and_finite(self):
        self.test_collectors_define_all_four_classes_inside_omfit()
        for name, cls in self.host.collector_classes.items():
            obj = cls.__new__(cls)
            self.host.factory.__init__(obj)
            values = dict(Rmaj=3., rmin=.5, shift=0., kappa=1.5, skappa=.1, delta=.2,
                          sdelta=.1, q=2., shear=.8, betastar=.01, theta_p=np.linspace(-np.pi,np.pi,37),
                          n_theta_p=37, ky=np.array([0., .3]) if name.endswith('nonlin') else .3)
            for key, value in values.items():
                setattr(obj, key, value)
            with self.subTest(collector=name):
                obj.miller_wd_s()
                for key in ('Rs', 'Zs', 'q_loc', 's_loc', 'wd1', 'k_perp'):
                    self.assertTrue(np.all(np.isfinite(getattr(obj, key))), (name, key))

    def test_rice_explicit_parameters_survive_native_defaultvars(self):
        script = REPO / 'CGYRO_TGLF_scan/TGLF_scan/TGYRO/SCRIPTS/Rice_scaling.py'
        inputs = {'BT_EXP': 2., 'ne': np.array([3., 4.]), 'z_eff': np.array([1.5, 2.]), 'rmaj': np.array([3., 3.])}
        out = self.host.execute(script.read_text(encoding='utf-8'), input_gacode=inputs,
                                user=dict(beta_t=.02, qstar=3., ion_mass_amu=2., impurity_charge=6.))
        self.assertTrue(np.all(np.isfinite(out['vtor'])))
        with self.assertRaisesRegex(RuntimeError, 'Rice estimate requires'):
            self.host.execute(script.read_text(encoding='utf-8'), input_gacode=inputs)

    def test_linear_flux_plot_consumes_collector_cache(self):
        root = self.host.cg_fixture()
        root['SETTINGS']['PLOTS']['1d']['para_eigen'] = [1.]
        root['SETTINGS']['PLOTS']['ky_eigen'] = [.1]
        root['SETTINGS']['PLOTS']['idimplt'] = 0
        root['SETTINGS']['SETUP']['icgyro'] = 1
        invoked = []
        case = SimpleNamespace(flux_lin=7., k_perp_squal_ave=2., gamma=.3, theta_width=1.,
                               get_flux_lin=lambda: invoked.append('used'))
        para = root['SETTINGS']['PLOTS']['1d']['Para']
        digits = int(root['SETTINGS']['SETUP']['effnum'])
        key = para + '_' + format(1., '.' + str(digits) + 'f') + '~ky_' + format(.1, '.' + str(digits) + 'f')
        def collect():
            root['_PLOT_CACHE'][key] = case
        assist = root['PLOTS']['CGYROscan']['assist']
        original = assist['collect.py']
        try:
            assist['collect.py'] = SimpleNamespace(run=collect)
            out = root['PLOTS']['CGYROscan']['eigen']['flux_lin.py'].run()
            np.testing.assert_allclose(out['flux_lin_arr'], [[7.]])
            self.assertEqual(invoked, ['used'])
            self.assertEqual(root['OUTPUTS']['do_not_replace'], 42)
            self.assertNotIn('Linear', root['OUTPUTS'])
            for number in plt.get_fignums():
                plt.figure(number).canvas.draw()
        finally:
            assist['collect.py'] = original

    def test_qlgyro_missing_companion_modules_fails_before_input_mutation(self):
        path = REPO / 'CGYRO_TGLF_scan/TGLF_scan/TGYRO/SCRIPTS/omfit_qlgyro.py'
        root = self.host.factory({'INPUTS': self.host.factory({'unchanged': 42})})
        with self.assertRaisesRegex(RuntimeError, 'optional OMFIT module TGLF_GACODE'):
            self.host.execute(path.read_text(encoding='utf-8'), root)
        self.assertEqual(list(root['INPUTS'].items()), [('unchanged', 42)])

    def test_legacy_frequency_normalization_uses_generated_case_species(self):
        source = CG / 'PLOTS/CGYROscan/linCGYRO.py'
        tree = ast.parse(source.read_text(encoding='utf-8'))
        block = next(n for n in ast.walk(tree) if isinstance(n, ast.If) and ast.unparse(n.test) == 'unit_flag == 1'
                     and 'omega_a_to_cs' in ast.unparse(n))
        for kinetic in (0, 1):
            generated = self.host.factory({'BETAE_UNIT': .02, 'SAFETY_FACTOR': 2., 'ASPECT_RATIO': 3.,
                'AE_FLAG': 1 - kinetic, 'NI_OVER_NE': .8, 'MU': 1., 'NI_OVER_NE_2': .1, 'MU_2': .5})
            case = {'input.gyro.gen': generated, 'tagspec': ['i1', 'i2'] + (['e'] if kinetic else [])}
            out = self.host.execute(ast.unparse(block), unit_flag=1, setup={'icgyro': 0}, datanode=case,
                                    w=np.array([3., .5]), print=lambda *args: None)
            self.assertAlmostEqual(out['nimisum'], 1.2)
            self.assertEqual(out['Rmaj'], 3.)
            np.testing.assert_allclose(out['w'], np.array([3., .5]) / (np.sqrt(2/.02/1.2)/6))

    def test_transfer_profile_interpolation_has_explicit_scipy_support(self):
        source = REPO / 'CGYRO_TGLF_scan/Transfer_tool/PLOTS/view12.py'
        tree = ast.parse(source.read_text(encoding='utf-8'))
        # Execute the actual equilibrium processing prefix before current-profile IO.
        end = next(n for n in tree.body if isinstance(n, ast.If) and ast.unparse(n.test) == 'itrpltout == 1')
        prefix = ast.Module(body=tree.body[:tree.body.index(end)], type_ignores=[])
        root = self.host.factory({'INPUTS': self.host.factory({'gfile': {
            'SIMAG': 0., 'SIBRY': 1., 'QPSI': np.full(9, 2.), 'PPRIME': np.full(9, -2.)}})})
        out = self.host.execute(ast.unparse(prefix), root, plt=plt)
        np.testing.assert_allclose(out['rhot'], np.sqrt(np.linspace(0, 1, 9)))
        np.testing.assert_allclose(out['Pres'], 2*(1-np.linspace(0, 1, 9)))


def validate(source):
    host = NativeHost(source)
    NativeExecutionTests.host = host
    stream = io.StringIO()
    with warnings.catch_warnings(), patch.dict(sys.modules, {'omfit_classes.utils_base': host.registry}):
        warnings.simplefilter('ignore', (SyntaxWarning, DeprecationWarning))
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(NativeExecutionTests)
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    report = dict(python=sys.version.split()[0], numpy=np.__version__, omfit_source=str(source),
                  native_functions=host.evidence, native_mapping=host.mapping_evidence,
                  imported_libraries=getattr(host, 'imported_libraries', []),
                  tests=result.testsRun, failures=len(result.failures), errors=len(result.errors),
                  complete_omfit_session_tested=False, solver_executed=False)
    return report, stream.getvalue(), result.wasSuccessful()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('omfit_source', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    report, log, passed = validate(args.omfit_source)
    text = json.dumps(report, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(text.encode())
        args.output.with_suffix('.log').write_bytes(log.encode())
    print(log)
    print(text)
    raise SystemExit(0 if passed else 1)
