"""Dependency gates, archived input replacement, and legacy choice compatibility."""
import ast
import copy
from contextlib import contextmanager, nullcontext
import json
import numpy as np
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from omfit_mapping import treeify

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'CGYRO_TGLF_scan/LIB'))
sys.path.insert(0, str(REPO / 'OMFITtemplates/LIB'))
from OMFITlib_template_archive import parse_tree
import OMFITlib_project as project
from OMFITlib_transfer_workflow import discard_legacy_outputs
from OMFITlib_project_ui import ProjectUI
import OMFITlib_workbench_runtime_ui as runtime_ui


@contextmanager
def headless_runtime_controls():
    """Mock only Tk construction; run runtime rows and draft callbacks normally."""
    class Variable:
        def __init__(self, master=None, value=''):
            self.value, self.callbacks = value, {}
        def get(self):
            return self.value
        def set(self, value):
            self.value = value
            for callback in self.callbacks.values():
                callback()
        def trace_add(self, mode, callback):
            token = str(len(self.callbacks))
            self.callbacks[token] = callback
            return token
        def trace_remove(self, mode, token):
            self.callbacks.pop(token)
    def entry(master, **kwargs):
        return SimpleNamespace(master=master, pack=Mock(), bind=Mock(), **kwargs)
    with patch.object(runtime_ui.tk, 'StringVar', Variable), patch.object(runtime_ui.ttk, 'Entry', entry):
        yield


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


class CgyroInput(dict):
    """The native input reader's copy boundary, without invoking a solver."""
    def duplicate(self):
        return copy.deepcopy(self)


def cgyro():
    return CgyroInput(N_SPECIES=2, N_RADIAL=16, N_THETA=24, Q=2., RMIN=.5, RMAJ=3.,
                      Z_1=1., Z_2=-1., MASS_1=1., MASS_2=.00027,
                      DENS_1=1., DENS_2=1., TEMP_1=1., TEMP_2=1.)


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
        self._aux = {}  # Native OMFIT exposes a mapping, not a generated method.
    def same_row(self):
        return nullcontext()
    def __getattr__(self, name):
        def record(*args, **kwargs):
            if name in ('Entry', 'ComboBox', 'CheckBox', 'FilePicker'):
                parent, key = resolve_path(self.root, args[0])
                parent.setdefault(key, copy.deepcopy(kwargs.get('default', None)))
            self.events.append((name, args, kwargs))
            if name in ('Label', 'Button', 'ComboBox', 'Entry', 'FilePicker'):
                return SimpleNamespace(master=SimpleNamespace())
            if name == 'CheckBox':
                return (SimpleNamespace(),)  # OMFIT returns a tuple of controls.
            if name == 'CompoundGUI' and kwargs.get('workbench', None) is not None:
                # These native child GUIs execute their host's tab renderer.
                host = kwargs['workbench']
                if args[0] is self.root['GUIS']['CGYRO_controls']:
                    host.render_cgyro_scan_tabs()
                elif args[0] is self.root['GUIS']['TGLF_controls']:
                    host.render_scan_tabs()
        return record
    def button(self, label):
        return next((args[1], kwargs) for name, args, kwargs in self.events if name == 'Button' and args[0] == label)


class ProjectTest(unittest.TestCase):
    tree_factory = dict

    def setUp(self):
        self.root = treeify(fixture(), self.tree_factory)
        self.actions = project.ProjectActions(self.root, self.tree_factory)
        self.cg = self.root['CGYRO_scan']
        self.tg = self.root['TGLF_scan']['TGLF']
        self.transfer = self.root['Transfer_tool']

    def test_open_and_generation_settings_preserve_legacy_transfer_outputs(self):
        outputs = self.transfer.setdefault('OUTPUTS', self.tree_factory())
        outputs['Profiles_gen'] = {'input.cgyro_1': cgyro()}
        # Retired branches can contain unique inputs unrelated to the current
        # radius/particle scheme. Opening a GUI grants no deletion authority.
        legacy = {name: {'unique': object()} for name in
                  ('Profiles_gen_H', 'Profiles_gen_D_simplified', 'History')}
        outputs.update(legacy)
        project.ProjectActions(self.root, self.tree_factory)
        project.initialize_generation(self.transfer, self.tree_factory)
        self.assertEqual(discard_legacy_outputs(self.transfer), [])
        for name, value in legacy.items():
            self.assertIs(outputs[name], value)

    def configure(self, name='cgyro'):
        node = project.module(self.root, name)
        remote = node['SETTINGS']['REMOTE_SETUP']
        remote.update(dict(serverPicker='localhost', server='localhost', tunnel='', workDir='/tmp/test'))
        if name == 'cgyro':
            remote['localhost'] = dict(scheduler='local', environment='source /chosen/setup', executable='cgyro -e . -n 1')
        else:
            node['SETTINGS']['SETUP']['executable'] = 'tglf -e .'

    def send(self, name='cgyro'):
        self.transfer['Transfer_file']['input.' + name] = cgyro() if name == 'cgyro' else tglf()
        source = ('Transfer_tool', 'Transfer_file', 'input.' + name)
        self.actions.settings['transfer_source'] = json.dumps(source)
        if name == 'cgyro':
            self.cg['SETTINGS']['EXPERIMENT']['runid'] = 'test'
            # Native OMFITsettings decodes serialized arrays; this JSON-only
            # fixture supplies an evaluated ky list explicitly.
            self.cg['SETTINGS']['PHYSICS']['kyarr'] = [.1]
            self.actions.settings['cgyro_source_mode'] = 'imported'
            self.actions.settings['cgyro_ion_cases'] = dict(BASE=True, H=False, D=False, T=False)
        self.actions.handoff(name)

    def pending(self):
        return next(iter(project.pending_inputs(self.root).items()))

    def legacy_choice(self, destination='tglf'):
        """An old saved candidate; current imports intentionally do not create it.

        1.17 removed the review page and archives inputs on explicit import.
        Keep testing resolve_input using the actual pre-1.17 persisted record.
        """
        branch = 'FILES' if destination == 'tglf' else 'INPUTS'
        current = project.read(self.root, project.MODULES[destination] + (branch, 'input.tglf'))
        incoming = tglf()
        source = ('Transfer_tool', 'Transfer_file', 'input.tglf')
        self.transfer['Transfer_file']['input.tglf'] = copy.deepcopy(incoming)
        record = self.actions._record('Legacy input choice', status='awaiting_choice',
            current=copy.deepcopy(current), incoming=copy.deepcopy(incoming),
            destination=destination, current_digest=project.input_digest(current),
            incoming_digest=project.input_digest(incoming), source=list(source),
            differences=project.input_difference(current, incoming))
        return record['id'], record

    def assert_no_scripts_run(self):
        def visit(node):
            if isinstance(node, SimpleNamespace):
                node.run.assert_not_called()
            elif hasattr(node, 'items'):
                for value in node.values():
                    visit(value)
        visit(self.root)

    def render(self, page, name=None):
        self.actions.settings['page'] = page
        if name:
            self.actions.settings['runtime_module'] = name
        ui = UI(self.root)
        with headless_runtime_controls():
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

    def test_existing_cgyro_file_requires_explicit_source_selection(self):
        self.configure()
        self.cg['SETTINGS']['EXPERIMENT']['runid'] = 'test'
        self.cg['INPUTS']['input.cgyro'] = cgyro()
        self.assertTrue(project.cgyro_input_issues(self.root))
        with self.assertRaisesRegex(ValueError, '选择 CGYRO 当前输入'):
            self.actions.run_cgyro()
        self.cg['SCRIPTS']['runCGYRO.py'].run.assert_not_called()

    def test_successful_handoff_is_independent_and_preserves_frozen_results(self):
        old = cgyro(); old['Q'] = 9.
        self.cg['INPUTS']['input.cgyro'] = old
        # 1.15 prepares a batch on explicit selection. Published inputs/results
        # belong to RUN_DB; an active editor card is not another archive.
        frozen = self.cg['RUN_DB']['previous'] = {'input': old.duplicate(), 'result': [42]}
        self.send()
        self.assertEqual(project.cgyro_input_issues(self.root), [])
        active = self.cg['INPUTS']['input.cgyro']
        prepared = self.cg['BATCH_INPUTS']['1']['BASE']
        self.assertIsNot(active, self.transfer['Transfer_file']['input.cgyro'])
        self.assertIsNot(active, prepared)
        active['Q'] = 7.
        self.assertEqual(prepared['Q'], 2.)
        self.assertEqual(self.transfer['Transfer_file']['input.cgyro']['Q'], 2.)
        self.assertEqual(frozen, {'input': old, 'result': [42]})
        self.assert_no_scripts_run()

    def test_changed_transfer_source_prepares_new_independent_batch(self):
        self.send(); self.configure()
        previous = self.cg['BATCH_INPUTS']
        frozen = self.cg['RUN_DB']['previous'] = {'input': previous['1']['BASE'].duplicate(), 'result': [42]}
        self.transfer['Transfer_file']['input.cgyro']['Q'] = 3.
        plan = self.actions.run_cgyro(prepare=True)
        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0]['source'], ['Transfer_tool', 'Transfer_file', 'input.cgyro'])
        self.assertEqual(plan[0]['case_id'], 'nr=1__rho=unknown__ion=BASE')
        self.assertEqual(self.cg['BATCH_INPUTS']['1']['BASE']['Q'], 3.)
        self.assertEqual(previous['1']['BASE']['Q'], 2.)
        self.assertEqual(frozen['input']['Q'], 2.)
        self.assertEqual(frozen['result'], [42])
        self.assert_no_scripts_run()

    def test_upstream_profile_edit_does_not_relabel_explicit_imported_input(self):
        self.transfer['Transfer_file']['input.gacode'] = {'rho': [0., .5, 1.]}
        self.send()
        old_batch = self.cg['BATCH_INPUTS']
        self.transfer['Transfer_file']['input.gacode']['rho'][1] = .4
        self.assertEqual(project.cgyro_input_issues(self.root), [])
        plan = self.actions.run_cgyro(prepare=True)
        self.assertEqual(self.cg['BATCH_INPUTS'], old_batch)
        self.assertIsNot(self.cg['BATCH_INPUTS'], old_batch)
        self.assertEqual(plan[0]['source'], ['Transfer_tool', 'Transfer_file', 'input.cgyro'])
        self.assert_no_scripts_run()

    def test_changed_active_editor_is_restored_after_running_selected_source(self):
        self.send(); self.configure()
        self.cg['INPUTS']['input.cgyro']['N_THETA'] = 32
        editor = self.cg['INPUTS']['input.cgyro']
        def run(**kwargs):
            self.assertEqual(self.cg['INPUTS']['input.cgyro']['N_THETA'], 24)
            self.assertIsNot(self.cg['INPUTS']['input.cgyro'], editor)
            self.cg['RUN_MANIFEST'] = {'status': 'published'}
        self.cg['SCRIPTS']['runCGYRO.py'].run.side_effect = run
        self.actions.run_cgyro()
        self.assertIs(self.cg['INPUTS']['input.cgyro'], editor)
        self.assertEqual(editor['N_THETA'], 32)
        self.assertEqual(self.transfer['Transfer_file']['input.cgyro']['N_THETA'], 24)

    def test_import_existing_cgyro_file_goes_through_transfer(self):
        self.actions.readers['cgyro'] = lambda filename: cgyro()
        self.actions.settings['cgyro_file'] = '/synthetic/input.cgyro'
        self.actions.import_input('cgyro')
        self.assertIn('input.cgyro', self.transfer['Transfer_file'])
        self.assertNotIn('input.cgyro', self.cg['INPUTS'])
        self.assertEqual(self.actions.settings['page'], 'cgyro')
        self.assertEqual(self.actions.settings['cgyro_source_mode'], 'imported')
        self.assert_no_scripts_run()

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
        self.cg['SCRIPTS']['runCGYRO.py'].run.side_effect = lambda **kwargs: self.assertEqual(setup['irun'], 1)
        self.actions.run_cgyro()
        self.assertEqual(setup['irun'], 0)

    def test_run_exception_restores_flags_input_and_records_failure(self):
        self.send(); self.configure()
        original = self.cg['INPUTS']['input.cgyro']
        setup = self.cg['SETTINGS']['SETUP']; setup.update(dict(irun=0, idownsync=0))
        def fail(**kwargs):
            self.assertEqual((setup['irun'], setup['idownsync']), (1, 1))
            self.assertTrue(kwargs['wait_for_completion'])
            raise RuntimeError('test failure')
        self.cg['SCRIPTS']['runCGYRO.py'].run.side_effect = fail
        with self.assertRaises(RuntimeError):
            self.actions.run_cgyro()
        self.assertEqual((setup['irun'], setup['idownsync']), (0, 0))
        self.assertIs(self.cg['INPUTS']['input.cgyro'], original)
        self.assertEqual(list(self.root['PROJECT_STATE']['activity'].values())[-1]['status'], 'failed')

    def test_prepare_validation_failure_preserves_existing_batch_without_running(self):
        self.send()
        previous = self.cg['BATCH_INPUTS']
        original = self.cg['INPUTS']['input.cgyro']
        self.transfer['Transfer_file']['input.cgyro']['N_SPECIES'] = 0
        with self.assertRaises(ValueError):
            self.actions.run_cgyro(prepare=True)
        self.assertIs(self.cg['BATCH_INPUTS'], previous)
        self.assertIs(self.cg['INPUTS']['input.cgyro'], original)
        self.assert_no_scripts_run()

    def test_collect_rejects_prepared_only_run(self):
        self.cg['RUN_MANIFEST'] = dict(status='prepared', points=['a'], workDir='/tmp/test')
        with self.assertRaisesRegex(ValueError, '不能收集'):
            self.actions.collect()
        self.cg['SCRIPTS']['downsync.py'].run.assert_not_called()

    def test_job_recovery_entry_is_available_without_current_input_or_manifest(self):
        self.actions.settings['cgyro_main_tab'] = 'results'
        ui = self.render('cgyro')
        callback, options = ui.button('按作业号恢复')
        self.assertNotEqual(options.get('state', ''), 'disabled')
        self.actions.settings['cgyro_recovery_job'] = '123'
        self.actions.settings['cgyro_recovery_manifest'] = '/tmp/old/manifest.json'
        self.actions.settings['cgyro_recovery_advanced'] = True
        with patch.object(self.actions, 'sync_endpoint') as endpoint:
            callback()
        endpoint.assert_called_once_with('cgyro')
        self.cg['SCRIPTS']['recover_job.py'].run.assert_called_once_with(
            job_id='123', manifest_path='/tmp/old/manifest.json')
        self.cg['SCRIPTS']['runCGYRO.py'].run.assert_not_called()
        self.cg['SCRIPTS']['downsync.py'].run.assert_not_called()

    def test_recovery_panel_shows_only_requested_job_not_old_pending_history(self):
        import OMFITlib_workbench_cgyro_ui as cgyro_ui
        self.actions.settings['cgyro_main_tab'] = 'results'
        old = dict(run_token='old', job_id='9537283', status='failed', collection_status='pending',
                   case_id='nr=11__rho=0.99__ion=BASE', batch_id='recovery')
        selected = dict(run_token='selected', job_id='9817420', status='submitted_or_finished',
                        collection_status='pending', case_id='nr=1__rho=0.33__ion=T', batch_id='recovery')
        self.cg.update(dict(RUN_MANIFEST=copy.deepcopy(selected),
            RUN_HISTORY={'old': {'manifest': old}, 'selected': {'manifest': selected}},
            RUN_BATCH=dict(batch_id='recovery', tokens=['old', 'selected'],
                           case_ids=[old['case_id'], selected['case_id']], focus_token='selected')))
        with patch.object(cgyro_ui.ResultBrowser, 'render'):
            ui = self.render('cgyro')
        labels = '\n'.join(str(args[0]) for name, args, kwargs in ui.events if name == 'Label')
        self.assertIn('9817420', labels)
        self.assertNotIn('9537283', labels)
        self.assertIn('本次恢复作业：完整 0 / 1', labels)
        self.assertEqual(self.cg['RUN_HISTORY']['old']['manifest'], old)
        self.assert_no_scripts_run()

    def test_radius_delete_cancel_and_confirm_use_exact_previewed_scope(self):
        import OMFITlib_workbench_cgyro_ui as cgyro_ui
        self.actions.settings['cgyro_main_tab'] = 'results'
        old = dict(runid='Jet', run_token='old', nr=11, rho=.99,
                   case_id='nr=11__rho=0.99__ion=BASE', job_id='9537283', status='failed')
        self.cg['RUN_HISTORY'] = {'old': {'manifest': old}}
        self.actions.settings['cgyro_cleanup_open'] = True
        self.actions.settings['cgyro_cleanup_radius'] = 'Jet | nr=11 | ρ=0.99'
        ui = self.render('cgyro')
        callback, _ = ui.button('删除该半径的记录和结果')
        combo = next((args, kwargs) for name, args, kwargs in ui.events
                     if name == 'ComboBox' and 'cgyro_cleanup_radius' in str(args[0]))
        self.assertIsInstance(combo[0][1], list)
        self.assertEqual(combo[0][2], '删除范围')
        self.assertNotIn('choices', combo[1])
        with patch.object(cgyro_ui, 'confirm_scope', return_value=None):
            callback()
        self.cg['SCRIPTS']['remove_radius.py'].run.assert_not_called()
        with patch.object(cgyro_ui, 'confirm_scope', side_effect=lambda parent, text, challenge: challenge):
            callback()
        arguments = self.cg['SCRIPTS']['remove_radius.py'].run.call_args.kwargs
        self.assertEqual((arguments['runid'], arguments['nr'], arguments['rho'], arguments['confirm']),
                         ('Jet', '11', .99, True))
        self.assertEqual(arguments['expected']['jobs'], ['9537283'])

    def test_task_manager_entry_does_not_enumerate_or_delete_on_ordinary_render(self):
        import OMFITlib_workbench_cgyro_ui as cgyro_ui
        self.actions.settings['cgyro_main_tab'] = 'results'
        with patch.object(cgyro_ui, 'TaskManager') as manager:
            ui = self.render('cgyro')
            _, options = ui.button('任务管理 / 删除任务…')
            self.assertFalse(options['updateGUI'])
            manager.assert_not_called()
        self.cg['SCRIPTS']['remove_tasks.py'].run.assert_not_called()

    def test_task_deletion_action_passes_exact_native_preview_and_challenge(self):
        report = dict(tokens=['one'], revision='fixed')
        self.actions.remove_cgyro_tasks(['one'], expected=report, confirmation='DELETE ABCD')
        self.cg['SCRIPTS']['remove_tasks.py'].run.assert_called_once_with(
            tokens=['one'], confirm=True, expected=report, confirmation='DELETE ABCD')
        self.cg['SCRIPTS']['runCGYRO.py'].run.assert_not_called()
        self.cg['SCRIPTS']['downsync.py'].run.assert_not_called()

    def test_collect_publishes_correct_dimension_without_resubmission(self):
        self.cg['RUN_MANIFEST'] = dict(status='submitted_or_finished', dimensions=2, points=['a'], workDir='/tmp/test')
        setup = self.cg['SETTINGS']['SETUP']; setup.update(dict(irun=1, idownsync=1, idimrun=1))
        def collect(**kwargs):
            self.assertEqual((setup['irun'], setup['idownsync']), (0, 1))
            self.assertEqual(kwargs, dict(collect_stopped=True, allow_solver_retries=False))
            self.assertEqual(self.cg['RUN_MANIFEST']['dimensions'], 2)
            self.cg['RUN_DB']['from_manifest'] = {'result': 1}
        self.cg['SCRIPTS']['CGYROScan.py'].run.side_effect = collect
        self.actions.collect()
        self.assertIn('from_manifest', self.cg['RUN_DB'])
        self.assertEqual((setup['irun'], setup['idownsync']), (1, 1))
        self.cg['SCRIPTS']['runCGYRO.py'].run.assert_not_called()
        self.cg['SCRIPTS']['CGYROScan.py'].run.assert_called_once()

    def test_missing_prerequisites_disable_buttons_and_callbacks_recheck(self):
        ui = self.render('cgyro')
        callback, options = ui.button('运行所选扫描')
        self.assertEqual(options['state'], 'disabled')
        for action in (callback, self.actions.collect, lambda: self.actions.run_cgyro(prepare=True)):
            with self.assertRaises(ValueError):
                action()
        self.assert_no_scripts_run()

    def test_overview_uses_input_presence_without_parsing_or_scan_preflight(self):
        class UnreadInput(dict):
            def keys(self):
                raise AssertionError('Overview parsed the input card')
            def __getitem__(self, key):
                raise AssertionError('Overview read a parameter')
        self.cg['INPUTS']['input.cgyro'] = UnreadInput()
        with patch('OMFITlib_project_ui.cgyro_input_issues', side_effect=AssertionError('Full preflight')):
            ui = self.render('overview')
        labels = [args[0] for name, args, kwargs in ui.events if name == 'Label']
        self.assertTrue(any('CGYRO 当前输入：已载入' in text for text in labels))
        self.assert_no_scripts_run()

    def test_explicit_configuration_check_keeps_scan_validation(self):
        with patch.object(project, 'cgyro_input_issues', return_value=['Selected input is invalid']) as check:
            self.actions.check()
        check.assert_called_once_with(self.root)
        self.assertIn('Selected input is invalid', self.actions.settings['message'])

    def test_transfer_missing_profile_blocks_pipeline_execution(self):
        ui = self.render('transfer')
        _, options = ui.button('运行 Transfer_tool')
        self.assertEqual(options['state'], 'disabled')
        self.assertIn('input.gacode', options['help'])
        self.assert_no_scripts_run()

    def test_tglf_handoff_archives_previous_results_without_running(self):
        current = dict(tglf(), SAT_RULE=2, OLD=8)
        self.tg['FILES'] = {'input.tglf': current, 'old_result': [1, 2]}
        self.send('tglf')
        self.assertEqual(self.tg['FILES']['input.tglf'], tglf())
        self.assertEqual(list(self.tg['FILES']), ['input.tglf'])
        self.assertFalse(project.pending_inputs(self.root))
        archive = list(self.root['PROJECT_STATE']['activity'].values())[-1]['previous_tglf_files']
        self.assertEqual(archive, {'input.tglf': current, 'old_result': [1, 2]})
        self.tg['FILES']['input.tglf']['SAT_RULE'] = 5
        self.transfer['Transfer_file']['input.tglf']['SAT_RULE'] = 6
        current['SAT_RULE'] = 9
        self.assertEqual(archive['input.tglf']['SAT_RULE'], 2)
        self.assert_no_scripts_run()

    def test_same_tglf_input_keeps_results_without_duplicate_archive(self):
        current = self.tg['FILES'] = {'input.tglf': tglf(), 'result': [7, 8]}
        self.send('tglf')
        self.send('tglf')
        self.assertIs(self.tg['FILES'], current)
        self.assertEqual(current['result'], [7, 8])
        self.assertFalse(self.root['PROJECT_STATE'].get('activity', {}))
        self.assert_no_scripts_run()

    def test_keep_current_tglf_preserves_its_entire_result_container(self):
        current = {'input.tglf': dict(tglf(), SAT_RULE=2), 'result': [7, 8]}
        self.tg['FILES'] = current
        key, record = self.legacy_choice()
        self.actions.resolve_input(key, False)
        self.assertIs(self.tg['FILES'], current)
        self.assertEqual(record['status'], 'kept_current')
        self.assertEqual(record['incoming']['SAT_RULE'], 0)

    def test_accept_input_archives_old_results_without_relabelling(self):
        previous = {'input.tglf': dict(tglf(), SAT_RULE=2), 'result': [7, 8]}
        self.tg['FILES'] = previous
        key, record = self.legacy_choice()
        self.actions.resolve_input(key, True)
        self.assertEqual(list(self.tg['FILES']), ['input.tglf'])
        self.assertEqual(self.tg['FILES']['input.tglf']['SAT_RULE'], 0)
        archive = list(self.root['PROJECT_STATE']['activity'].values())[-1]['previous_tglf_files']
        self.assertEqual(archive, previous)
        self.tg['FILES']['input.tglf']['SAT_RULE'] = 3
        self.assertEqual(archive['input.tglf']['SAT_RULE'], 2)

    def test_changed_target_cannot_accept_stale_diff(self):
        self.tg['FILES']['input.tglf'] = dict(tglf(), SAT_RULE=2)
        key, _ = self.legacy_choice()
        self.tg['FILES']['input.tglf']['SAT_RULE'] = 5
        with self.assertRaisesRegex(ValueError, '当前 TGLF 输入'):
            self.actions.resolve_input(key, True)
        self.assertEqual(self.tg['FILES']['input.tglf']['SAT_RULE'], 5)

    def test_changed_transfer_source_cannot_accept_stale_diff(self):
        self.tg['FILES']['input.tglf'] = dict(tglf(), SAT_RULE=2)
        key, _ = self.legacy_choice()
        self.transfer['Transfer_file']['input.tglf']['KY'] = .6
        with self.assertRaisesRegex(ValueError, 'Transfer 源输入'):
            self.actions.resolve_input(key, True)

    def test_old_pending_input_migrates_to_kept_current_without_replacing_results(self):
        current = self.tg['FILES'] = {'input.tglf': dict(tglf(), SAT_RULE=2), 'result': [42]}
        key, record = self.legacy_choice()
        project.ProjectActions(self.root, self.tree_factory)
        self.assertIs(self.tg['FILES'], current)
        self.assertEqual(record['status'], 'kept_current')
        self.assertEqual(record['incoming']['SAT_RULE'], 0)
        self.assertIn(key, self.root['PROJECT_STATE']['activity'])
        self.assertFalse(project.pending_inputs(self.root))
        self.assert_no_scripts_run()

    def test_legacy_review_shortcut_opens_current_tglf_input_page(self):
        self.actions.open_page('review')
        self.assertEqual(self.actions.settings['page'], 'tglf')
        self.assertEqual(self.actions.settings['tglf']['page'], 'scan')
        self.assertEqual(self.actions.settings['tglf']['scan_page'], 'input')
        self.assert_no_scripts_run()

    def test_imported_tglf_archives_previous_input_without_running(self):
        self.tg['FILES']['input.tglf'] = dict(tglf(), SAT_RULE=2)
        self.actions.readers['tglf'] = lambda filename: tglf()
        self.actions.settings['tglf_file'] = '/synthetic/input.tglf'
        self.actions.import_input('tglf')
        self.assertFalse(project.pending_inputs(self.root))
        self.assertEqual(self.tg['FILES']['input.tglf']['SAT_RULE'], 0)
        archive = list(self.root['PROJECT_STATE']['activity'].values())[-1]['previous_tglf_files']
        self.assertEqual(archive['input.tglf']['SAT_RULE'], 2)
        self.assert_no_scripts_run()

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
        callback, options = self.render('cgyro').button('运行所选扫描')
        self.assertEqual(options['state'], 'normal')
        self.transfer['Transfer_file']['input.cgyro']['N_SPECIES'] = 0
        with self.assertRaises(ValueError):
            callback()
        self.cg['SCRIPTS']['runCGYRO.py'].run.assert_not_called()

    def test_transfer_seed_replacement_archives_old_tgyro_without_running(self):
        self.transfer['INPUTS']['input.tglf'] = dict(tglf(), SAT_RULE=2)
        self.transfer['OUTPUTS']['TGYRO'] = {'old_flux': [7, 8]}
        self.actions.readers['tglf'] = lambda filename: tglf()
        self.actions.settings['transfer_tglf_file'] = '/synthetic/seed'
        self.actions.import_transfer_seed('tglf')
        self.assertFalse(project.pending_inputs(self.root))
        self.assertNotIn('TGYRO', self.transfer['OUTPUTS'])
        self.assertEqual(self.transfer['INPUTS']['input.tglf']['SAT_RULE'], 0)
        archives = self.root['PROJECT_STATE']['activity'].values()
        self.assertTrue(any(record.get('tgyro_result', None) == {'old_flux': [7, 8]} for record in archives))
        self.assert_no_scripts_run()

    def test_transfer_tgyro_seed_invalidates_previous_generation(self):
        self.transfer['OUTPUTS']['TGYRO'] = {'old_flux': [7, 8]}
        self.actions.readers['tgyro'] = lambda filename: {'DIR': {}, 'TGYRO_RMIN': .3, 'TGYRO_RMAX': .7}
        self.actions.settings['transfer_tgyro_file'] = '/synthetic/input.tgyro'
        self.actions.import_transfer_seed('tgyro')
        self.assertIn('input.tgyro', self.transfer['INPUTS'])
        self.assertNotIn('TGYRO', self.transfer['OUTPUTS'])

    def test_generated_tglf_replacement_archives_prior_single_file(self):
        self.tg['FILES'] = {'input.tglf': dict(tglf(), SAT_RULE=2), 'result': [42]}
        self.root['TGLF_scan']['input.tglf'] = {.5: tglf()}
        self.actions.settings['generated_tglf_source'] = json.dumps(['TGLF_scan', 'input.tglf', .5])
        self.actions.use_generated_tglf()
        self.assertFalse(project.pending_inputs(self.root))
        self.assertEqual(self.tg['FILES']['input.tglf']['SAT_RULE'], 0)
        self.assertTrue(any(r.get('previous_tglf_files', {}).get('result', None) == [42]
                            for r in self.root['PROJECT_STATE']['activity'].values()))
        self.assert_no_scripts_run()

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
        env = dict(root=scan, OMFITtree=self.tree_factory, OMFITx=SimpleNamespace(End=end), copy=copy,
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
                    def run(inputTGLF, **kwargs):
                        self.assertEqual(inputTGLF['SAT_RULE'], 0)
                        inputTGLF['SAT_RULE'] = 9
                        if fail:
                            raise RuntimeError('synthetic solver failure')
                    self.tg['SCRIPTS'][script].run.side_effect = run
                    env = dict(root=scan, OMFITtree=self.tree_factory, copy=copy, printi=lambda *args: None)
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
        scan['SETTINGS']['PHYSICS'].update(dict(Var_r=.5, RelativeChange_RLTS_1=.1))
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
            env = dict(root=scan, OMFITtree=self.tree_factory, copy=copy)
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
