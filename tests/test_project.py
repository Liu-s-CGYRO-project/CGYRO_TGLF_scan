"""Dependency gates, explicit overwrite choices, and native-UI bindings."""
import ast
import copy
from contextlib import nullcontext
import json
import numpy as np
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'CGYRO_TGLF_scan/LIB'))
sys.path.insert(0, str(REPO / 'OMFITtemplates/LIB'))
from OMFITlib_template_archive import parse_tree
import OMFITlib_project as project
from OMFITlib_project_ui import ProjectUI


def fixture():
    root = {}
    for row in parse_tree((REPO / 'CGYRO_TGLF_scan/OMFITsave.txt').read_bytes()):
        if '__SETTINGS_AT_IMPORT__' in row.keys:
            continue
        parent = root
        for key in row.keys[:-1]:
            parent = parent.setdefault(key, {})
        key = row.keys[-1]
        if row.kind == 'OMFITsettings':
            parent[key] = json.loads((REPO / 'CGYRO_TGLF_scan' / row.ref).read_bytes())
        elif row.kind in ('OMFITmodule', 'OMFITtree') or key == 'FILES':
            parent.setdefault(key, {})
        elif row.kind in ('OMFITpythonGUI', 'OMFITpythonTask'):
            parent[key] = SimpleNamespace(run=Mock(), plot=Mock())
    return root


def cgyro():
    return dict(N_SPECIES=2, N_RADIAL=16, N_THETA=24, Q=2., RMIN=.5, RMAJ=3.)


def tglf():
    return dict(NS=2, KY=.3, SAT_RULE=0, USE_BPER=False, RLTS_1=3.)


def resolve_path(root, path):
    node = ast.parse(path, mode='eval').body
    keys = []
    while isinstance(node, ast.Subscript):
        keys.insert(0, ast.literal_eval(node.slice))
        node = node.value
    assert isinstance(node, ast.Name) and node.id == 'root'
    for key in keys[:-1]:
        root = root[key]
    return root, keys[-1]


class UI:
    def __init__(self, root):
        self.root, self.events = root, []
    def same_row(self):
        return nullcontext()
    def __getattr__(self, name):
        def record(*args, **kwargs):
            if name in ('Entry', 'ComboBox', 'CheckBox', 'FilePicker'):
                parent, key = resolve_path(self.root, args[0])
                parent.setdefault(key, copy.deepcopy(kwargs.get('default')))
            self.events.append((name, args, kwargs))
        return record
    def button(self, label):
        return next((args[1], kwargs) for name, args, kwargs in self.events if name == 'Button' and args[0] == label)


class ProjectTest(unittest.TestCase):
    def setUp(self):
        self.root = fixture()
        self.actions = project.ProjectActions(self.root)
        self.cg = self.root['CGYRO_scan']
        self.tg = self.root['TGLF_scan']['TGLF']
        self.transfer = self.root['Transfer_tool']

    def configure(self, name='cgyro'):
        node = project.module(self.root, name)
        remote = node['SETTINGS']['REMOTE_SETUP']
        remote.update(serverPicker='localhost', server='localhost', tunnel='', workDir='/tmp/test')
        if name == 'cgyro':
            remote['localhost'] = dict(scheduler='local', environment='source /chosen/setup', executable='cgyro -e . -n 1')
        else:
            node['SETTINGS']['SETUP']['executable'] = 'tglf -e .'

    def send(self, name='cgyro'):
        self.transfer['Transfer_file']['input.' + name] = cgyro() if name == 'cgyro' else tglf()
        source = ('Transfer_tool', 'Transfer_file', 'input.' + name)
        self.actions.settings['transfer_source'] = json.dumps(source)
        self.actions.handoff(name)

    def pending(self):
        return next(iter(project.pending_inputs(self.root).items()))

    def render(self, page, name=None):
        self.actions.settings['page'] = page
        if name:
            self.actions.settings['runtime_module'] = name
        ui = UI(self.root)
        ProjectUI(self.actions, ui, servers=['localhost', 'cluster']).render()
        return ui

    def test_all_pages_render_empty_project_without_running_any_task(self):
        self.root['TGLF_scan']['scanResults_spectra'] = {'existing': {}}
        for page in project.PAGES.values():
            self.render(page)
        self.assertEqual(self.root['TGLF_scan']['scanResults_spectra'], {'existing': {}})
        self.assertEqual(self.root['PROJECT_STATE'], {})
        def verify(node):
            if isinstance(node, dict):
                for child in node.values():
                    verify(child)
            elif isinstance(node, SimpleNamespace):
                node.run.assert_not_called()
        verify(self.root)

    def test_every_runtime_module_renders_with_missing_config(self):
        for name in project.MODULES:
            self.render('run', name)

    def test_existing_cgyro_file_cannot_bypass_transfer(self):
        self.configure()
        self.cg['INPUTS']['input.cgyro'] = cgyro()
        self.assertTrue(project.cgyro_input_issues(self.root))
        with self.assertRaisesRegex(ValueError, 'Transfer'):
            self.actions.run_cgyro()
        self.cg['SCRIPTS']['runCGYRO.py'].run.assert_not_called()

    def test_successful_handoff_is_independent_and_preserves_previous_input(self):
        old = cgyro(); old['Q'] = 9.
        self.cg['INPUTS']['input.cgyro'] = old
        self.send()
        self.assertEqual(project.cgyro_input_issues(self.root), [])
        self.assertIsNot(self.cg['INPUTS']['input.cgyro'], self.transfer['Transfer_file']['input.cgyro'])
        records = self.root['PROJECT_STATE']['activity'].values()
        self.assertEqual(next(iter(records))['previous_inputs']["root['CGYRO_scan']['INPUTS']['input.cgyro']"]['Q'], 9.)

    def test_change_to_transfer_source_blocks_cgyro_again(self):
        self.send(); self.configure()
        self.transfer['Transfer_file']['input.cgyro']['Q'] = 3.
        with self.assertRaisesRegex(ValueError, 'Transfer 输入已经变化'):
            self.actions.run_cgyro()

    def test_change_to_upstream_profile_invalidates_cgyro_handoff(self):
        self.transfer['Transfer_file']['input.gacode'] = {'rho': [0., .5, 1.]}
        self.send()
        self.transfer['Transfer_file']['input.gacode']['rho'][1] = .4
        self.assertIn('上游剖面', project.cgyro_input_issues(self.root)[0])

    def test_change_to_cgyro_destination_blocks_running(self):
        self.send()
        self.cg['INPUTS']['input.cgyro']['N_THETA'] = 32
        self.assertIn('CGYRO 输入已经变化', project.cgyro_input_issues(self.root)[0])

    def test_import_existing_cgyro_file_goes_through_transfer(self):
        self.actions.readers['cgyro'] = lambda filename: cgyro()
        self.actions.settings['cgyro_file'] = '/synthetic/input.cgyro'
        self.actions.import_input('cgyro')
        self.assertIn('input.cgyro', self.transfer['Transfer_file'])
        self.assertNotIn('input.cgyro', self.cg['INPUTS'])
        self.assertEqual(self.actions.settings['page'], 'transfer')

    def test_invalid_import_does_not_replace_input(self):
        self.cg['INPUTS']['input.cgyro'] = cgyro()
        self.actions.readers['cgyro'] = lambda filename: {'N_SPECIES': 0}
        self.actions.settings['cgyro_file'] = '/synthetic/invalid'
        with self.assertRaises(ValueError):
            self.actions.import_input('cgyro')
        self.assertEqual(self.cg['INPUTS']['input.cgyro'], cgyro())

    def test_wrong_transfer_file_type_cannot_replace_cgyro(self):
        self.transfer['Transfer_file']['input.tglf'] = tglf()
        self.actions.settings['transfer_source'] = json.dumps(['Transfer_tool', 'Transfer_file', 'input.tglf'])
        with self.assertRaises(ValueError):
            self.actions.handoff('cgyro')
        self.assertNotIn('input.cgyro', self.cg['INPUTS'])

    def test_run_rechecks_and_restores_run_flag(self):
        self.send(); self.configure()
        setup = self.cg['SETTINGS']['SETUP']; setup['irun'] = 0
        self.cg['SCRIPTS']['runCGYRO.py'].run.side_effect = lambda: self.assertEqual(setup['irun'], 1)
        self.actions.run_cgyro()
        self.assertEqual(setup['irun'], 0)

    def test_prepare_exception_restores_flag_and_records_failure(self):
        self.send(); self.configure()
        setup = self.cg['SETTINGS']['SETUP']; setup['irun'] = 1
        def fail(**kwargs):
            self.assertEqual(setup['irun'], 0)
            self.assertEqual(kwargs['scan_dimensions'], 1)
            raise RuntimeError('test failure')
        self.cg['SCRIPTS']['subscan_lin.py'].run.side_effect = fail
        with self.assertRaises(RuntimeError):
            self.actions.run_cgyro(prepare=True)
        self.assertEqual(setup['irun'], 1)
        self.assertEqual(list(self.root['PROJECT_STATE']['activity'].values())[-1]['status'], 'failed')

    def test_collect_rejects_prepared_only_run(self):
        self.cg['RUN_MANIFEST'] = dict(status='prepared', points=['a'], workDir='/tmp/test')
        with self.assertRaisesRegex(ValueError, '不能收集'):
            self.actions.collect()
        self.cg['SCRIPTS']['downsync.py'].run.assert_not_called()

    def test_collect_publishes_correct_dimension_without_resubmission(self):
        self.cg['RUN_MANIFEST'] = dict(status='submitted_or_finished', dimensions=2, points=['a'], workDir='/tmp/test')
        setup = self.cg['SETTINGS']['SETUP']; setup.update(irun=1, idownsync=1, idimrun=1)
        def download():
            self.cg['RUN_MANIFEST']['status'] = 'loaded'
        def publish():
            self.assertEqual((setup['irun'], setup['idownsync']), (0, 0))
            self.cg['RUN_DB']['from_manifest'] = {'result': 1}
        self.cg['SCRIPTS']['downsync.py'].run.side_effect = download
        self.cg['SCRIPTS']['CGYROScan_2d.py'].run.side_effect = publish
        self.actions.collect()
        self.assertIn('from_manifest', self.cg['RUN_DB'])
        self.assertEqual((setup['irun'], setup['idownsync']), (1, 1))
        self.cg['SCRIPTS']['runCGYRO.py'].run.assert_not_called()

    def test_missing_prerequisites_disable_buttons_and_callbacks_recheck(self):
        ui = self.render('cgyro')
        for label in ('仅生成输入', '运行配置的扫描', '收集当前结果'):
            callback, options = ui.button(label)
            self.assertEqual(options['state'], 'disabled')
            with self.assertRaises(ValueError):
                callback()

    def test_transfer_missing_tgyro_results_blocks_local_input_generation(self):
        ui = self.render('transfer')
        _, options = ui.button('生成各半径局部输入')
        self.assertEqual(options['state'], 'disabled')
        self.assertIn('TGYRO', options['help'])

    def test_tglf_conflict_only_stages_diff(self):
        current = dict(tglf(), SAT_RULE=2, OLD=8)
        self.tg['FILES'] = {'input.tglf': current, 'old_result': [1, 2]}
        self.send('tglf')
        self.assertEqual(self.tg['FILES']['input.tglf'], current)
        _, pending = self.pending()
        differences = {row[0]: row for row in pending['differences']}
        self.assertEqual(differences['SAT_RULE'][1:], ('变化', '2', '0'))
        self.assertEqual(differences['OLD'][1], '移除')
        self.assertEqual(self.actions.settings['page'], 'review')

    def test_keep_current_tglf_preserves_its_entire_result_container(self):
        current = {'input.tglf': dict(tglf(), SAT_RULE=2), 'result': [7, 8]}
        self.tg['FILES'] = current
        self.send('tglf')
        key, record = self.pending()
        self.actions.resolve_input(key, False)
        self.assertIs(self.tg['FILES'], current)
        self.assertEqual(record['status'], 'kept_current')
        self.assertEqual(record['incoming']['SAT_RULE'], 0)

    def test_accept_input_archives_old_results_without_relabelling(self):
        previous = {'input.tglf': dict(tglf(), SAT_RULE=2), 'result': [7, 8]}
        self.tg['FILES'] = previous
        self.send('tglf')
        key, record = self.pending()
        self.actions.resolve_input(key, True)
        self.assertEqual(list(self.tg['FILES']), ['input.tglf'])
        self.assertEqual(self.tg['FILES']['input.tglf']['SAT_RULE'], 0)
        archive = list(self.root['PROJECT_STATE']['activity'].values())[-1]['previous_tglf_files']
        self.assertEqual(archive, previous)
        self.tg['FILES']['input.tglf']['SAT_RULE'] = 3
        self.assertEqual(archive['input.tglf']['SAT_RULE'], 2)

    def test_changed_target_cannot_accept_stale_diff(self):
        self.tg['FILES']['input.tglf'] = dict(tglf(), SAT_RULE=2)
        self.send('tglf')
        key, _ = self.pending()
        self.tg['FILES']['input.tglf']['SAT_RULE'] = 5
        with self.assertRaisesRegex(ValueError, '当前 TGLF 输入'):
            self.actions.resolve_input(key, True)
        self.assertEqual(self.tg['FILES']['input.tglf']['SAT_RULE'], 5)

    def test_changed_transfer_source_cannot_accept_stale_diff(self):
        self.tg['FILES']['input.tglf'] = dict(tglf(), SAT_RULE=2)
        self.send('tglf')
        key, _ = self.pending()
        self.transfer['Transfer_file']['input.tglf']['KY'] = .6
        with self.assertRaisesRegex(ValueError, 'Transfer 源输入'):
            self.actions.resolve_input(key, True)

    def test_pending_input_blocks_tglf_until_choice_is_made(self):
        self.configure('tglf')
        self.tg['FILES']['input.tglf'] = dict(tglf(), SAT_RULE=2)
        self.send('tglf')
        ui = self.render('tglf')
        callback, options = ui.button('运行当前 input.tglf')
        self.assertEqual(options['state'], 'disabled')
        with self.assertRaisesRegex(ValueError, '待确认'):
            callback()
        key, _ = self.pending(); self.actions.resolve_input(key, False)
        self.actions.run('tglf', 'runTGLF', (('FILES', 'input.tglf'),))
        self.tg['SCRIPTS']['runTGLF'].run.assert_called_once()

    def test_review_page_renders_actual_values_and_both_choices(self):
        self.tg['FILES']['input.tglf'] = dict(tglf(), SAT_RULE=2)
        self.send('tglf')
        ui = self.render('review')
        ui.button('保留当前 TGLF 输入')
        ui.button('使用待传入输入，并保存原版本')
        self.assertTrue(any(name == 'Label' and 'SAT_RULE' in args[0] for name, args, _ in ui.events))

    def test_imported_tglf_also_requires_choice(self):
        self.tg['FILES']['input.tglf'] = dict(tglf(), SAT_RULE=2)
        self.actions.readers['tglf'] = lambda filename: tglf()
        self.actions.settings['tglf_file'] = '/synthetic/input.tglf'
        self.actions.import_input('tglf')
        self.assertTrue(project.pending_inputs(self.root))
        self.assertEqual(self.tg['FILES']['input.tglf']['SAT_RULE'], 2)

    def test_profile_handoff_archives_old_scan_and_invalidates_local_inputs(self):
        scan = self.root['TGLF_scan']
        scan.update({'input.tglf': {.5: tglf()}, 'scanResults': {'old': [1]}})
        self.transfer['Transfer_file']['input.gacode'] = {'rho': [0., .5, 1.]}
        self.actions.settings['transfer_source'] = json.dumps(['Transfer_tool', 'Transfer_file', 'input.gacode'])
        self.actions.handoff('profiles')
        self.assertNotIn('input.tglf', scan)
        self.assertNotIn('scanResults', scan)
        archived = list(self.root['PROJECT_STATE']['activity'].values())[-1]['tglf_data']
        self.assertEqual(archived['scanResults']['old'], [1])
        self.assertEqual(scan['TGYRO']['PROFILES_GEN']['INPUTS']['input.gacode']['rho'], [0., .5, 1.])

    def test_sync_endpoint_keeps_command_and_resources(self):
        self.configure()
        before = copy.deepcopy(self.cg['SETTINGS']['REMOTE_SETUP']['localhost'])
        self.actions.resolve_server = lambda node: dict(server='localhost', tunnel='')
        self.actions.workdir = lambda node, server: '/tmp/new-project'
        self.actions.sync_endpoint('cgyro')
        after = self.cg['SETTINGS']['REMOTE_SETUP']['localhost']
        self.assertEqual(after['executable'], before['executable'])
        self.assertEqual(after['workDir'], '/tmp/new-project')

    def test_both_save_manifests_register_new_libraries_and_empty_state(self):
        for prefix, filename in [((), 'CGYRO_TGLF_scan/OMFITsave.txt'), (('CGYRO_TGLF_scan',), 'OMFITsave.txt')]:
            rows = {row.keys: row for row in parse_tree((REPO / filename).read_bytes())}
            self.assertEqual(rows[prefix + ('PROJECT_STATE',)].kind, 'OMFITtree')
            for name in ('OMFITlib_project', 'OMFITlib_project_ui'):
                self.assertIn(prefix + ('LIB', name), rows)
        self.assertEqual(self.root['SETTINGS']['MODULE']['defaultGUI'], "root['GUIS']['main']")

    def test_ready_button_rechecks_upstream_input_at_click_time(self):
        self.send(); self.configure()
        callback, options = self.render('cgyro').button('运行配置的扫描')
        self.assertEqual(options['state'], 'normal')
        self.transfer['Transfer_file']['input.cgyro']['Q'] = 4.
        with self.assertRaises(ValueError):
            callback()
        self.cg['SCRIPTS']['runCGYRO.py'].run.assert_not_called()

    def test_transfer_seed_has_its_own_choice_and_archives_old_tgyro(self):
        self.transfer['INPUTS']['input.tglf'] = dict(tglf(), SAT_RULE=2)
        self.transfer['OUTPUTS']['TGYRO'] = {'old_flux': [7, 8]}
        self.actions.readers['tglf'] = lambda filename: tglf()
        self.actions.settings['transfer_tglf_file'] = '/synthetic/seed'
        self.actions.import_transfer_seed('tglf')
        key, record = self.pending()
        self.assertEqual(record['destination'], 'transfer')
        self.assertFalse(project.pending_inputs(self.root, 'tglf'))
        self.assertIn('TGYRO', self.transfer['OUTPUTS'])
        self.actions.resolve_input(key, True)
        self.assertNotIn('TGYRO', self.transfer['OUTPUTS'])
        self.assertEqual(self.transfer['INPUTS']['input.tglf']['SAT_RULE'], 0)
        archives = self.root['PROJECT_STATE']['activity'].values()
        self.assertTrue(any(record.get('tgyro_result') == {'old_flux': [7, 8]} for record in archives))

    def test_transfer_tgyro_seed_invalidates_previous_generation(self):
        self.transfer['OUTPUTS']['TGYRO'] = {'old_flux': [7, 8]}
        self.actions.readers['tgyro'] = lambda filename: {'DIR': {}, 'TGYRO_RMIN': .3, 'TGYRO_RMAX': .7}
        self.actions.settings['transfer_tgyro_file'] = '/synthetic/input.tgyro'
        self.actions.import_transfer_seed('tgyro')
        self.assertIn('input.tgyro', self.transfer['INPUTS'])
        self.assertNotIn('TGYRO', self.transfer['OUTPUTS'])

    def test_generated_tglf_requires_the_same_explicit_choice(self):
        self.tg['FILES'] = {'input.tglf': dict(tglf(), SAT_RULE=2), 'result': [42]}
        self.root['TGLF_scan']['input.tglf'] = {.5: tglf()}
        self.render('tglf').button('比较并传入当前 TGLF 单文件')[0]()
        key, record = self.pending()
        self.assertEqual(self.tg['FILES']['result'], [42])
        self.assertEqual(record['source'], ['TGLF_scan', 'input.tglf', .5])
        self.actions.resolve_input(key, False)
        self.assertEqual(self.tg['FILES']['input.tglf']['SAT_RULE'], 2)
        self.actions.use_generated_tglf()
        key, _ = self.pending()
        self.actions.resolve_input(key, True)
        self.assertEqual(self.tg['FILES']['input.tglf']['SAT_RULE'], 0)
        self.assertTrue(any(r.get('previous_tglf_files', {}).get('result') == [42]
                            for r in self.root['PROJECT_STATE']['activity'].values()))

    def test_cached_local_generation_keeps_current_input_and_results(self):
        scan = self.root['TGLF_scan']
        scan['SETTINGS']['PHYSICS']['rho'] = .5
        scan['TGYRO']['INPUTS']['input.tgyro'] = {}
        scan['TGYRO']['PROFILES_GEN']['OUTPUTS']['input.gacode'] = {}
        scan['input.tglf'] = {.5: tglf()}
        existing = self.tg['FILES'] = {'input.tglf': dict(tglf(), SAT_RULE=2), 'result': [42]}
        self.tg['LIB']['OMFITlib_tglf_cache'].runNoGUI = lambda: {
            'provenance': lambda *args: {}, 'matches': lambda *args: True}
        class End(Exception):
            pass
        def end():
            raise End()
        env = dict(root=scan, OMFITtree=dict, OMFITx=SimpleNamespace(End=end), copy=copy,
                   arange=np.arange, argmin=np.argmin, printi=lambda *args: None)
        with self.assertRaises(End):
            exec((REPO / 'CGYRO_TGLF_scan/TGLF_scan/SCRIPTS/setup_tglf.py').read_text(encoding='utf-8'), env)
        self.assertIs(self.tg['FILES'], existing)
        self.assertEqual(existing['input.tglf']['SAT_RULE'], 2)
        self.assertEqual(existing['result'], [42])

    def test_radial_scans_pass_private_input_and_never_replace_single_file(self):
        scan = self.root['TGLF_scan']
        scan['SETTINGS']['PHYSICS']['rho'] = .5
        scan['input.tglf'] = {.5: tglf()}
        existing = self.tg['FILES'] = {'input.tglf': dict(tglf(), SAT_RULE=2), 'result': [42]}
        for dimension, script in [(1, 'runTGLFscan'), (2, 'runTGLFscan2D'), ('UQ', 'runTGLFUQscan')]:
            for fail in (False, True):
                with self.subTest(dimension=dimension, fail=fail):
                    scan['SETTINGS']['PHYSICS']['scanDimensions'] = dimension
                    def run(inputTGLF):
                        self.assertEqual(inputTGLF['SAT_RULE'], 0)
                        inputTGLF['SAT_RULE'] = 9
                        if fail:
                            raise RuntimeError('synthetic solver failure')
                    self.tg['SCRIPTS'][script].run.side_effect = run
                    env = dict(root=scan, OMFITtree=dict, copy=copy, printi=lambda *args: None)
                    code = (REPO / 'CGYRO_TGLF_scan/TGLF_scan/SCRIPTS/runScanAtRho.py').read_text(encoding='utf-8')
                    if fail:
                        with self.assertRaisesRegex(RuntimeError, 'synthetic'):
                            exec(code, env)
                    else:
                        exec(code, env)
                    self.assertIs(self.tg['FILES'], existing)
                    self.assertEqual(existing['input.tglf']['SAT_RULE'], 2)
                    self.assertEqual(scan['input.tglf'][.5]['SAT_RULE'], 0)
                    self.assertEqual(existing['result'], [42])

    def test_growth_scan_restores_single_file_after_success_or_failure(self):
        from unittest.mock import patch
        scan = self.root['TGLF_scan']
        scan['SETTINGS']['PHYSICS'].update(Var_r=.5, RelativeChange_RLTS_1=.1)
        scan['input.tglf'] = {.5: tglf()}
        scan['TGLF_inputs_to_scan'] = {'RLTS_1': True}
        fake_lib = SimpleNamespace(TGLF_var_group_scan=lambda *args: {'RLTS_1': ['RLTS_1']})
        for fail in (False, True):
            existing = self.tg['FILES'] = {'input.tglf': dict(tglf(), SAT_RULE=2), 'result': [42]}
            def run():
                if fail:
                    raise RuntimeError('synthetic solver failure')
                self.tg['FILES']['result'] = [7]
            self.tg['SCRIPTS']['runTGLF'].run.side_effect = run
            env = dict(root=scan, OMFITtree=dict, copy=copy)
            env['defaultVars'] = lambda **kwargs: env.update(kwargs)
            code = (REPO / 'CGYRO_TGLF_scan/TGLF_scan/SCRIPTS/runGrowthRateScans.py').read_text(encoding='utf-8')
            with patch.dict(sys.modules, OMFITlib_tglf=fake_lib):
                if fail:
                    with self.assertRaisesRegex(RuntimeError, 'synthetic'):
                        exec(code, env)
                else:
                    exec(code, env)
                    self.assertEqual(scan['TGLF_SCAN_DB']['scans']['TGLF_baseline_FILES']['result'], [7])
            self.assertIs(self.tg['FILES'], existing)
            self.assertEqual(existing['result'], [42])
            self.assertEqual(scan['input.tglf'][.5]['SAT_RULE'], 0)


if __name__ == '__main__':
    unittest.main()
