"""Shared environment migration and the settings consumed by real runners."""
import copy
import ast
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / 'CGYRO_TGLF_scan/LIB')]
from test_project import fixture, UI
from omfit_mapping import treeify
from OMFITlib_project import ProjectActions, PAGES, runtime_issues
from OMFITlib_project_runtime import (TARGETS, initialize_runtime, applied_runtime, apply_runtime,
    shared_issues, shared_multi_settings, validate_runtime, node_at)
from OMFITlib_project_ui import ProjectUI


class RuntimeTests(unittest.TestCase):
    tree_factory = dict
    def setUp(self):
        self.root = fixture()
        self.cg = self.root['CGYRO_scan']
        self.cg['SETTINGS']['REMOTE_SETUP'].update(serverPicker='cluster', server='user@cluster',
            tunnel='', workDir='/work/user/OMFITtmp/project/cgyro', cluster=dict(scheduler='slurm',
            queue='normal', w='24:00:00', nodes=2, ntasks_per_node=8, array_parallel=5,
            environment='export GACODE_ROOT=/shared/gacode\nsource "$GACODE_ROOT/shared/bin/gacode_setup"',
            executable='cgyro -e . -n {mpi}'))
        self.root = treeify(self.root, self.tree_factory)
        self.cg = self.root['CGYRO_scan']

    def test_initialize_prefills_once_without_changing_module_settings(self):
        previous = copy.deepcopy(self.cg['SETTINGS'])
        config = initialize_runtime(self.root)
        self.assertEqual(config['workDir'], '/work/user/OMFITtmp/project')
        self.assertEqual(config['server'], 'user@cluster')
        self.assertEqual(self.cg['SETTINGS'], previous)
        config['queue'] = 'edited'
        self.assertEqual(initialize_runtime(self.root)['queue'], 'edited')
        self.assertIsNone(applied_runtime(self.root))

    def test_apply_synchronizes_all_endpoints_and_environment_without_results(self):
        class Result:
            def __deepcopy__(self, memo):
                raise AssertionError('Results accessed')
        result = Result()
        self.cg['Cases'] = {'unsaved': result}
        self.cg['SETTINGS']['SETUP']['workDir'] = '/local/OMFITtmp/cgyro'
        initialize_runtime(self.root)
        names = apply_runtime(self.root)
        self.assertEqual(len(names), 8)
        paths = []
        for name, path in TARGETS.items():
            settings = node_at(self.root, path)['SETTINGS']
            remote = settings['REMOTE_SETUP']
            self.assertEqual(remote['serverPicker'], 'cluster')
            self.assertEqual(remote['server'], 'user@cluster')
            self.assertEqual(remote['cluster']['server'], 'user@cluster')
            self.assertEqual(remote['cluster']['environment'], applied_runtime(self.root)['environment'])
            paths.append(remote['workDir'])
        self.assertEqual(len(paths), len(set(paths)))
        self.assertEqual(self.cg['SETTINGS']['REMOTE_SETUP']['cluster']['executable'], 'cgyro -e . -n 16')
        self.assertEqual(self.cg['SETTINGS']['SETUP']['workDir'], '/local/OMFITtmp/cgyro')
        self.assertIs(self.cg['Cases']['unsaved'], result)
        self.assertEqual(shared_issues(self.root), [])
        self.assertEqual(runtime_issues(self.root, 'cgyro'), [])
        self.assertEqual(runtime_issues(self.root, 'tglf'), [])

    def test_invalid_config_is_atomic(self):
        config = initialize_runtime(self.root)
        config['cores'] = 0
        previous = copy.deepcopy(self.cg['SETTINGS'])
        with self.assertRaises(ValueError):
            apply_runtime(self.root)
        self.assertEqual(self.cg['SETTINGS'], previous)
        self.assertIsNone(applied_runtime(self.root))

    def test_applied_config_and_backups_are_independent_of_draft(self):
        initialize_runtime(self.root)
        before = copy.deepcopy(self.cg['SETTINGS']['REMOTE_SETUP'])
        apply_runtime(self.root)
        self.assertEqual(self.root['PROJECT_STATE']['gacode_runtime']['previous']['cgyro']['REMOTE_SETUP'], before)
        self.root['SETTINGS']['GACODE_RUNTIME']['server'] = 'another'
        self.assertEqual(applied_runtime(self.root)['server'], 'user@cluster')
        self.assertTrue(shared_issues(self.root))
        self.assertTrue(runtime_issues(self.root, 'tglf'))

    def test_multi_input_uses_common_applied_environment(self):
        initialize_runtime(self.root)
        apply_runtime(self.root)
        multi = dict(execution='local', environment='old', tglf_command='wrong')
        shared_multi_settings(self.root, multi)
        self.assertEqual(multi['execution'], 'module')
        self.assertEqual(multi['environment'], applied_runtime(self.root)['environment'])
        self.assertEqual(multi['tgyro_command'], 'tgyro -t . -n {n_radii}')
        self.assertEqual(multi['tglf_command'], 'tglf -e .')

    def test_module_endpoint_drift_blocks_mixed_server_runs(self):
        initialize_runtime(self.root)
        apply_runtime(self.root)
        self.root['TGLF_scan']['TGLF']['SETTINGS']['REMOTE_SETUP']['server'] = 'other-server'
        self.assertTrue(shared_issues(self.root))
        self.assertTrue(runtime_issues(self.root, 'cgyro'))
        apply_runtime(self.root)
        self.assertEqual(shared_issues(self.root), [])

    def test_sync_reads_selected_server_and_preserves_user_root_directory(self):
        config = initialize_runtime(self.root)
        resolver = Mock(return_value=dict(server='new@cluster', tunnel='jump'))
        actions = ProjectActions(self.root, resolve_server=resolver, workdir=Mock(return_value='/new/default'))
        actions.sync_runtime_endpoint()
        resolver.assert_called_once_with('cluster')
        self.assertEqual(config['server'], 'new@cluster')
        self.assertEqual(config['workDir'], '/work/user/OMFITtmp/project')
        self.assertEqual(self.cg['SETTINGS']['REMOTE_SETUP']['server'], 'user@cluster')

    def test_menu_follows_workflow_and_environment_has_no_module_selector(self):
        self.assertEqual(list(PAGES.values()), ['overview', 'run', 'transfer', 'review', 'cgyro', 'tglf', 'multi', 'plots', 'templates'])
        actions = ProjectActions(self.root)
        actions.settings['page'] = 'run'
        ui = UI(self.root)
        ProjectUI(actions, ui).render()
        self.assertFalse(any(name == 'ComboBox' and "['runtime_module']" in args[0] for name, args, kw in ui.events))
        self.assertEqual(sum(name == 'Entry' and "['environment']" in args[0] for name, args, kw in ui.events), 1)
        ui.button('应用到整个工程')

    def test_native_tgyro_command_uses_actual_dir_rank_counts(self):
        initialize_runtime(self.root)
        apply_runtime(self.root)
        tgyro = self.root['TGLF_scan']['TGYRO']
        tgyro['INPUTS']['input.tgyro'] = {'DIR': {'TGLF1': [2, 'X=0.4'], 'TGLF2': 4}}
        source = Path(__file__).resolve().parents[1] / 'CGYRO_TGLF_scan/TGLF_scan/TGYRO/SCRIPTS/runTGYRObase.py'
        nodes = ast.parse(source.read_text(encoding='utf-8')).body
        selected = [node for node in nodes if
            isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'shared_command' for target in node.targets)
            or isinstance(node, ast.If) and isinstance(node.test, ast.Name) and node.test.id == 'shared_command']
        self.assertEqual(len(selected), 2)
        exec(compile(ast.Module(body=selected, type_ignores=[]), str(source), 'exec'), {'root': tgyro})
        command = tgyro['SETTINGS']['SETUP']['executable']
        self.assertTrue(command.endswith('tgyro -e . -n 6'))
        self.assertIn('source "$GACODE_ROOT/shared/bin/gacode_setup"', command)

    def test_transfer_rank_distribution_fits_shared_cpu_budget(self):
        initialize_runtime(self.root)
        apply_runtime(self.root)
        transfer = self.root['Transfer_tool']
        transfer['SETTINGS']['SETUP']['p_tgyro'] = 3
        source = Path(__file__).resolve().parents[1] / 'CGYRO_TGLF_scan/Transfer_tool/SCRIPTS/tgyro_tglf.py'
        nodes = ast.parse(source.read_text(encoding='utf-8')).body
        selected = []
        for node in nodes:
            if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'run_input' for target in node.targets):
                break
            selected.append(node)
        namespace = {'root': transfer}
        exec(compile(ast.Module(body=selected, type_ignores=[]), str(source), 'exec'), namespace)
        self.assertEqual(namespace['numcore'], 15)
        self.assertEqual(namespace['coreppoint'], 5)


if __name__ == '__main__':
    unittest.main()
