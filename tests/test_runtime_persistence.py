"""Saved runtime identities using native pickle proxies and SettingsName.

Native classes are unchanged AST extracts. The host supplies paths, a pickle
reader and root lookup; JSON uses the real SettingsName nested-map conversion.
This tests the persistence boundary, not a complete OMFIT save/reopen session.
Result siblings are traps: configuration checks must never read their files.
"""
import ast
import copy
from contextlib import ExitStack
import json
from pathlib import Path
import pickle
import re
import sys
import tempfile
import unittest

import numpy as np
import test_server_capabilities as fixture

REPO = fixture.REPO
SOURCE = REPO.parents[2] / 'OMFIT-source-ASIPP_unstable/omfit'
sys.path.insert(0, str(REPO / 'tools'))
from validate_project_mapping import load_native_mapping
from OMFITlib_gacode_installations import choices, detection_is_current, same_endpoint
from OMFITlib_project_runtime import TARGETS, apply_runtime, node_at, shared_issues
from OMFITlib_server_capabilities import matching_profile, runtime_capability_contract


class RuntimePersistenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # One native class registry per isolated host, as in OMFIT itself.
        factory, registry, _ = load_native_mapping(SOURCE / 'omfit_classes/sortedDict.py')
        cls.tree_factory, cls.registry = factory, registry
        namespace = dict(os=__import__('os'), copy=copy, special1=object(),
                         printi=lambda *args: None,
                         parseLocation=lambda value: re.findall(r"\['([^']+)'\]", value),
                         buildLocation=lambda keys: 'OMFIT' + ''.join('[%r]' % key for key in keys))
        source = SOURCE / 'omfit_classes/omfit_base.py'
        definition = next(n for n in ast.parse(source.read_text(encoding='utf-8')).body
                          if isinstance(n, ast.ClassDef) and n.name == 'OMFITlazyLoad')
        exec(compile(ast.Module(body=[definition], type_ignores=[]), str(source), 'exec'), namespace)
        cls.lazy_type = namespace['OMFITlazyLoad']
        cls.lazy_namespace = namespace
        source = SOURCE / 'omfit_classes/omfit_json.py'
        definition = next(n for n in ast.parse(source.read_text(encoding='utf-8')).body
                          if isinstance(n, ast.ClassDef) and n.name == 'SettingsName')
        namespace = dict(SortedDict=factory, np=np)
        exec(compile(ast.Module(body=[definition], type_ignores=[]), str(source), 'exec'), namespace)
        cls.settings_type = namespace['SettingsName']
        cls.settings_type.baseDict = cls.settings_type

    def setUp(self):
        # Load reader adapters before replacing the native class registry.
        import test_cgyro_storage
        self.scope = ExitStack()
        self.addCleanup(self.scope.close)
        # Restore only our injected module. patch.dict(sys.modules) restores a
        # whole snapshot and evicts C extensions first imported by the fixture;
        # reimporting those extensions across tests can crash Python on exit.
        key = 'omfit_classes.utils_base'
        previous = sys.modules.get(key)
        self.scope.callback(lambda: sys.modules.__setitem__(key, previous)
                            if previous is not None else sys.modules.pop(key, None))
        sys.modules[key] = self.registry
        fixture.DetectionActionTests.setUp(self)
        self.paths = self.scope.enter_context(tempfile.TemporaryDirectory())
        self.loaded = []
        self.lazy_namespace.update(OMFIT=self.root, OMFITpickle=self.read_pickle)
        self.actions.remote_execute = lambda *args, **kw: fixture.DetectionActionTests.remote(self, *args, **kw)
        self.detection = self.actions.detect_gacode()
        apply_runtime(self.root, self.tree_factory)

    def tearDown(self):
        # Native nodes carry parent links. Release the isolated host while its
        # globals are still alive, not during Python's interpreter shutdown.
        self.lazy_namespace.pop('OMFIT')
        self.lazy_namespace.pop('OMFITpickle')
        self.actions.remote_execute = None
        dict.clear(self.root)
        self.root = self.actions = self.detection = self.config = None

    def read_pickle(self, filename, **kwargs):
        self.loaded.append(Path(filename).name)
        with open(filename, 'rb') as stream:
            return pickle.load(stream)

    def reopen(self):
        # SETTINGS persists as JSON; plain dict children of the PROJECT_STATE
        # OMFITtree persist as separate pickles exposed through OMFITlazyLoad.
        for path in TARGETS.values():
            module = node_at(self.root, path)
            if module is not None:
                module['SETTINGS'] = json.loads(json.dumps(module['SETTINGS']),
                                               object_pairs_hook=self.settings_type)
        self.config = self.root['SETTINGS']['GACODE_RUNTIME']
        for key in ('endpoint', 'capabilities'):
            filename = Path(self.paths) / (key + '.pickle')
            filename.write_bytes(pickle.dumps(self.detection[key]))
            self.detection[key] = self.lazy_type(
                "OMFIT['PROJECT_STATE']['gacode_detection']['%s']" % key, 'OMFITpickle', str(filename))
        self.root['CGYRO_scan']['RUN_DB'] = self.lazy_type(
            "OMFIT['CGYRO_scan']['RUN_DB']", 'OMFITpickle', str(Path(self.paths) / 'must-not-read-results'))
        self.loaded.clear()

    def selected(self):
        return self.root['CGYRO_scan']['SETTINGS']['REMOTE_SETUP']['cluster']

    def test_first_check_after_reopen_preserves_applied_settings_without_results(self):
        self.reopen()
        proxy = self.detection['capabilities']
        # Old comparison is false even after .get() delegates to the real dict.
        self.assertEqual(proxy.get('version', None), fixture.VERSION)
        self.assertNotEqual(self.selected()['server_capabilities'], proxy)
        self.detection['capabilities'] = proxy
        self.assertEqual(shared_issues(self.root), [])
        self.assertEqual(shared_issues(self.root), [])
        self.assertTrue(self.root['CGYRO_scan']['RUN_DB'].dynaLoad)
        self.assertEqual(self.loaded, ['capabilities.pickle'])

    def test_first_matching_profile_returns_values_not_lazy_identity(self):
        expected = copy.deepcopy(self.detection['capabilities'])
        self.reopen()
        profile = matching_profile(self.config, self.detection)
        self.assertIsInstance(profile, dict)
        self.assertEqual(profile, expected)
        self.assertEqual(runtime_capability_contract(self.config, profile),
                         runtime_capability_contract(self.config, self.selected()['server_capabilities']))

    def test_redetection_metadata_and_other_queues_do_not_invalidate_allocation(self):
        profile = self.detection['capabilities']
        profile.update(checked='new time', hostname='other-login', login_cpus=999,
                       limits={'nofile_soft': '32'}, tools={}, draft_changes=[])
        profile['partitions']['unselected'] = {'not': 'allocation policy'}
        self.assertEqual(shared_issues(self.root), [])

    def test_real_capacity_changes_still_require_apply_or_reject_resources(self):
        original = copy.deepcopy(self.detection['capabilities'])
        changes = ({'cpus_per_node': 48}, {'wall_time': '02:00:00'},
                   {'node_groups': [dict(cpus=64, memory_mib=128000, node_count=6)]},
                   {'available': False}, {'cpus_per_node': 16})
        for change in changes:
            with self.subTest(change=change):
                self.detection['capabilities'] = copy.deepcopy(original)
                self.detection['capabilities']['partitions']['normal'].update(change)
                self.assertTrue(shared_issues(self.root))
        self.detection['capabilities'] = original
        self.selected()['server_capabilities']['version'] = 1
        self.assertTrue(shared_issues(self.root))

    def test_lost_report_is_not_silently_accepted_as_unchanged(self):
        self.detection.pop('capabilities')
        self.assertTrue(shared_issues(self.root))
        apply_runtime(self.root, self.tree_factory)
        self.assertEqual(shared_issues(self.root), [])

    def test_saved_installation_labels_and_recent_validation_retain_endpoint(self):
        before = choices(self.config, self.detection, 'cgyro')
        self.reopen()
        self.assertEqual(choices(self.config, self.detection, 'cgyro'), before)
        self.assertTrue(detection_is_current(self.config, self.detection))
        self.assertTrue(same_endpoint(self.detection['endpoint'],
                                     {'server': 'user@cluster', 'tunnel': ''}))
        self.assertNotIn('must-not-read-results', self.loaded)

    def test_installation_only_probe_keeps_capabilities_after_reopen(self):
        expected = copy.deepcopy(self.detection['capabilities'])
        self.reopen()
        _, current = self.actions._probe_gacode(scan=False)
        self.assertEqual(current['capabilities'], expected)
        self.assertEqual(shared_issues(self.root), [])

    def test_repeated_save_reopen_and_apply_do_not_require_configuration_again(self):
        for _ in range(2):
            self.reopen()
            self.assertEqual(shared_issues(self.root), [])
            # Load only the second small identity before simulating another save.
            self.detection['endpoint'] = dict(self.detection['endpoint'].items())
        apply_runtime(self.root, self.tree_factory)
        self.assertEqual(shared_issues(self.root), [])

    def test_endpoint_and_version_changes_cannot_reuse_saved_report(self):
        self.reopen()
        for change in ({'server': 'other'}, {'tunnel': 'different-jump'}):
            config = dict(self.config)
            config.update(change)
            self.assertEqual(matching_profile(config, self.detection), {})
        self.detection['capabilities']['version'] = 1
        self.assertEqual(matching_profile(self.config, self.detection), {})
        self.assertTrue(shared_issues(self.root))
        self.assertFalse(same_endpoint({}, {}))

    def test_equivalent_queue_time_spelling_and_group_order_are_stable(self):
        profile = fixture.parse_probe(fixture.output([
            'normal*|32|126536|01:00:00|up|UNLIMITED|3',
            'normal*|64|255500|01:00:00|up|UNLIMITED|2']), self.config)
        self.detection['capabilities'] = profile
        apply_runtime(self.root, self.tree_factory)
        profile['partitions']['normal']['wall_time'] = '60'
        profile['partitions']['normal']['node_groups'].reverse()
        self.assertEqual(shared_issues(self.root), [])


if __name__ == '__main__':
    unittest.main()
