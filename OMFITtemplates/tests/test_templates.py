"""Archive-level regression tests; never load results or execute template code."""
import copy
import ast
import builtins
import hashlib
import importlib
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import zipfile

MODULE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE / 'LIB'))
from OMFITlib_template_archive import Project, Row, TemplateError, json_bytes, location_keys, parse_tree, tree_bytes
from OMFITlib_template_service import (
    Cancelled, Template, apply_update, inspect_project, list_library, plan_update,
    publish, read_history, release_name, transfer, new_file,
)


def row(keys, kind='OMFITtree', ref='', value=None):
    location = ''.join('[' + repr(key) + ']' for key in keys)
    return Row(' <-:-:-> '.join([location, kind, '_' + repr(value) if value is not None else './' + ref if ref else '', '{}']))


def fixture(path, version=1, prefix='', omit=None):
    settings = {'MODULE': {'ID': 'Demo', 'version': version}, 'DEPENDENCIES': {'dependency': str(version)},
                'PHYSICS': {'x': version, 'dynamic': None, 'old_static': 10 if version == 1 else None,
                            'old_dynamic': None if version == 1 else 20}, 'REMOTE_SETUP': {'server': 'server' + str(version)}}
    if version == 2:
        settings['PHYSICS']['added'] = 42
        settings['PHYSICS']['added_expression'] = None
    rows = [row(['Demo'], 'OMFITmodule'), row(['Demo', 'SCRIPTS']),
            row(['Demo', 'SCRIPTS', 'run'], 'OMFITpythonTask', 'Demo/SCRIPTS/run.py'),
            row(['Demo', 'SCRIPTS', 'old' if version == 1 else 'new'], 'OMFITpythonTask', 'Demo/SCRIPTS/' + ('old.py' if version == 1 else 'new.py')),
            row(['Demo', 'SETTINGS'], 'OMFITsettings', 'Demo/SettingsNamelist.txt'),
            row(['Demo', 'SETTINGS', 'PHYSICS', 'dynamic'], 'OMFITexpression', value='source_' + str(version)),
            row(['Demo', 'SETTINGS', 'PHYSICS', 'old_dynamic' if version == 1 else 'old_static'], 'OMFITexpression', value='version_' + str(version)),
            row(['Demo', 'RUN_DB']), row(['Demo', 'RUN_DB', 'run' + str(version)]),
            row(['Demo', 'RUN_DB', 'run' + str(version), 0.5], 'importNdarray', 'Demo/data/v' + str(version) + '.npy'),
            row(['Demo', 'RUN_DB', 'run' + str(version), 'job.py'], 'OMFITpythonTask', 'Demo/data/job.py'),
            row(['Demo', 'FILES'], 'OMFITgacode', 'Demo/files'),
            row(['Other'], 'OMFITmodule'), row(['Other', 'SCRIPTS']),
            row(['Other', 'SCRIPTS', 'task'], 'OMFITpythonTask', 'Other/task.py'),
            row(['MainSettings'], 'OMFITsettings', 'MainSettingsNamelist.txt')]
    if version == 2:
        rows.append(row(['Demo', 'SETTINGS', 'PHYSICS', 'added_expression'], 'OMFITexpression', value='new_default'))
    files = {'Demo/SettingsNamelist.txt': json_bytes(settings),
             'Demo/SCRIPTS/run.py': ('# release ' + str(version)).encode(),
             'Demo/SCRIPTS/' + ('old.py' if version == 1 else 'new.py'): b'# helper',
             'Demo/data/v' + str(version) + '.npy': b'UNTOUCHED-RESULT-' + bytes([version]) * 4096,
             'Demo/data/job.py': b'# generated calculation script',
             'Demo/unreferenced-cache': b'CACHE-' + bytes([version]),
             'Other/task.py': b'# other module', 'MainSettingsNamelist.txt': json_bytes({'user': 'me'})}
    if omit:
        files.pop(omit, None)
    files['OMFITsave.txt'] = tree_bytes(rows)
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as output:
        for name, content in files.items():
            output.writestr(prefix + name, content)
        output.writestr(prefix + 'Demo/files/', b'')
    return files


def rewrite(path, mutator):
    with zipfile.ZipFile(path) as archive:
        entries = {i.filename: archive.read(i) for i in archive.infolist()}
    mutator(entries)
    with zipfile.ZipFile(path, 'w') as archive:
        for name, content in entries.items():
            archive.writestr(name, content)


def add_module(path, name='Added'):
    def change(entries):
        nodes = parse_tree(entries['OMFITsave.txt'])
        nodes += [row([name], 'OMFITmodule'), row([name, 'GUIS']),
                  row([name, 'GUIS', 'main'], 'OMFITpythonGUI', name + '/GUIS/main.py'),
                  row([name, 'SETTINGS'], 'OMFITsettings', name + '/SettingsNamelist.txt'),
                  row([name, 'SETTINGS', 'PHYSICS', 'dynamic'], 'OMFITexpression', value='new_module_default'),
                  row([name, 'RUN_DB']), row([name, 'RUN_DB', 'sample'], 'OMFITascii', name + '/sample.dat')]
        entries['OMFITsave.txt'] = tree_bytes(nodes)
        entries[name + '/GUIS/main.py'] = b'# added module GUI'
        entries[name + '/SettingsNamelist.txt'] = json_bytes({
            'MODULE': {'ID': name, 'defaultGUI': "root['GUIS']['main']"},
            'PHYSICS': {'gain': 3, 'dynamic': None}})
        entries[name + '/sample.dat'] = b'NEW-MODULE-EXAMPLE'
    rewrite(path, change)


class TemplatesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.old, self.new = self.dir / 'current.zip', self.dir / 'new.zip'
        self.old_files = fixture(self.old, 1)
        self.new_files = fixture(self.new, 2)
        self.library = self.dir / 'library'
        self.meta = {'id': 'demo', 'name': '测试模板', 'author': 'alice', 'version': '2.0', 'description': '增添设置'}

    def release(self, examples=False):
        return Path(publish(self.new, self.library, self.meta, ['Demo'], examples))

    def plan(self, examples=False, data='keep', settings='keep'):
        return plan_update(self.old, self.release(examples), data, settings)

    def result(self, plan):
        output = self.dir / 'result.zip'
        apply_update(plan, output)
        return Project(output)

    def test_default_template_excludes_cases_and_global_state(self):
        with Template(self.release()) as template:
            template.verify()
            self.assertFalse(template.manifest['examples'])
            self.assertTrue(all('/data/' not in n for n in template.files))
            self.assertFalse(any(n.startswith('Other/') or n.startswith('MainSettings') for n in template.files))
            self.assertIn(('Demo', 'RUN_DB'), {r.keys for r in template.rows})
            self.assertFalse(any(len(r.keys) > 2 and r.keys[1] == 'RUN_DB' for r in template.rows))

    def test_preserve_result_bytes_and_other_modules(self):
        before = self.old.read_bytes()
        with self.result(self.plan()) as result:
            for name in ['Demo/data/v1.npy', 'Demo/data/job.py', 'Demo/unreferenced-cache', 'Other/task.py', 'MainSettingsNamelist.txt']:
                self.assertEqual(result.read(name), self.old_files[name])
            self.assertIn('Demo/files', result.directories)
            self.assertNotIn('Demo/SCRIPTS/old.py', result.files)
            self.assertIn('Demo/SCRIPTS/new.py', result.files)
            self.assertEqual(result.read('Demo/SCRIPTS/run.py'), b'# release 2')
        self.assertEqual(self.old.read_bytes(), before)

    def test_preserve_settings_and_expression_origin(self):
        with self.result(self.plan()) as result:
            data = json.loads(result.read('Demo/SettingsNamelist.txt'))
            self.assertEqual(data['PHYSICS']['x'], 1)
            self.assertEqual(data['PHYSICS']['added'], 42)
            self.assertEqual(data['REMOTE_SETUP']['server'], 'server1')
            self.assertEqual(data['MODULE']['version'], 2)
            self.assertEqual(data['DEPENDENCIES']['dependency'], '2')
            rows = {r.keys: r for r in result.rows}
            prefix = ('Demo', 'SETTINGS', 'PHYSICS')
            self.assertEqual(rows[prefix + ('dynamic',)].fields[2], "_'source_1'")
            self.assertEqual(rows[prefix + ('added_expression',)].fields[2], "_'new_default'")
            self.assertIn(prefix + ('old_dynamic',), rows)
            self.assertNotIn(prefix + ('old_static',), rows)

    def test_template_settings_adopt_values_and_expressions(self):
        with self.result(self.plan(settings='template')) as result:
            settings = json.loads(result.read('Demo/SettingsNamelist.txt'))
            self.assertEqual(settings['PHYSICS']['x'], 2)
            self.assertEqual(settings['REMOTE_SETUP']['server'], 'server2')
            rows = {r.keys: r for r in result.rows}
            self.assertIn(('Demo', 'SETTINGS', 'PHYSICS', 'old_static'), rows)
            self.assertNotIn(('Demo', 'SETTINGS', 'PHYSICS', 'old_dynamic'), rows)

    def test_examples_replace_only_selected_module_data(self):
        with self.result(self.plan(examples=True, data='examples')) as result:
            self.assertNotIn('Demo/data/v1.npy', result.files)
            self.assertEqual(result.read('Demo/data/v2.npy'), self.new_files['Demo/data/v2.npy'])
            self.assertEqual(result.read('Demo/unreferenced-cache'), self.new_files['Demo/unreferenced-cache'])
            self.assertEqual(result.read('Other/task.py'), self.old_files['Other/task.py'])
            self.assertNotIn(('Demo', 'RUN_DB', 'run1'), {r.keys for r in result.rows})

    def test_examples_package_can_still_preserve_current_data(self):
        with self.result(self.plan(examples=True)) as result:
            self.assertIn('Demo/data/v1.npy', result.files)
            self.assertNotIn('Demo/data/v2.npy', result.files)

    def test_no_examples_cannot_erase_current_data(self):
        with self.assertRaisesRegex(TemplateError, '没有示例'):
            self.plan(data='examples')

    def test_file_and_tree_changes_are_reviewable(self):
        plan = self.plan()
        changes = {(c['action'], c['path']) for c in plan['changes']}
        self.assertIn(('delete', 'Demo/SCRIPTS/old.py'), changes)
        self.assertIn(('add', 'Demo/SCRIPTS/new.py'), changes)
        self.assertTrue(any('old' in c['path'] and c['action'] == 'delete' for c in plan['tree_changes']))

    def test_same_release_has_no_formatting_only_changes(self):
        plan = plan_update(self.new, self.release())
        self.assertEqual(plan['changes'], [])
        self.assertEqual(plan['tree_changes'], [])

    def test_project_zip_comment_is_preserved(self):
        with zipfile.ZipFile(self.old, 'a') as archive:
            archive.comment = b'Project description and provenance'
        with self.result(self.plan()) as result:
            self.assertEqual(result.z.comment, b'Project description and provenance')

    def test_multiple_roots_are_canonicalized(self):
        path = publish(self.new, self.library, self.meta, ['Other', 'Demo'])
        with Template(path) as template:
            self.assertEqual(template.roots, ['Demo', 'Other'])

    def test_update_existing_and_add_missing_root_preserves_data_and_settings(self):
        add_module(self.new)
        package = publish(self.new, self.library, self.meta, ['Demo', 'Added'])
        before = self.old.read_bytes()
        plan = plan_update(self.old, package)
        self.assertEqual(plan['updated_modules'], ['Demo'])
        self.assertEqual(plan['added_modules'], ['Added'])
        self.assertIn({'action': 'add', 'path': "['Added']"}, plan['tree_changes'])
        with self.result(plan) as result:
            self.assertEqual(result.roots, ['Added', 'Demo', 'Other'])
            self.assertEqual(result.read('Demo/data/v1.npy'), self.old_files['Demo/data/v1.npy'])
            self.assertEqual(result.read('Demo/unreferenced-cache'), self.old_files['Demo/unreferenced-cache'])
            self.assertEqual(result.read('Other/task.py'), self.old_files['Other/task.py'])
            self.assertEqual(result.read('Demo/SCRIPTS/run.py'), b'# release 2')
            settings = json.loads(result.read('Demo/SettingsNamelist.txt'))
            self.assertEqual(settings['PHYSICS']['x'], 1)
            self.assertEqual(settings['REMOTE_SETUP']['server'], 'server1')
            self.assertEqual(settings['PHYSICS']['added'], 42)
            self.assertEqual(result.read('Added/GUIS/main.py'), b'# added module GUI')
            self.assertEqual(json.loads(result.read('Added/SettingsNamelist.txt'))['PHYSICS']['gain'], 3)
            nodes = {node.keys: node for node in result.rows}
            self.assertEqual(nodes[('Added', 'SETTINGS', 'PHYSICS', 'dynamic')].fields[2], "_'new_module_default'")
            self.assertIn(('Added', 'RUN_DB'), nodes)
            self.assertNotIn('Added/sample.dat', result.files)
            output = result.path
        self.assertEqual(self.old.read_bytes(), before)
        # Re-applying the same package must not repeatedly add or rewrite it.
        repeated = plan_update(output, package)
        self.assertEqual(repeated['added_modules'], [])
        self.assertEqual(repeated['changes'], [])
        self.assertEqual(repeated['tree_changes'], [])

    def test_template_can_add_only_new_modules(self):
        add_module(self.new)
        package = publish(self.new, self.library, self.meta, ['Added'])
        plan = plan_update(self.old, package)
        self.assertEqual(plan['updated_modules'], [])
        self.assertEqual(plan['added_modules'], ['Added'])
        with self.result(plan) as result:
            for name, data in self.old_files.items():
                if name != 'OMFITsave.txt':
                    self.assertEqual(result.read(name), data)
            self.assertEqual(result.read('Added/GUIS/main.py'), b'# added module GUI')

    def test_template_can_initialize_project_without_modules(self):
        def empty(entries):
            entries.clear()
            entries['OMFITsave.txt'] = tree_bytes([row(['MainSettings'], 'OMFITsettings', 'MainSettingsNamelist.txt')])
            entries['MainSettingsNamelist.txt'] = b'{"keep": 42}'
        rewrite(self.old, empty)
        plan = self.plan()
        self.assertEqual(plan['updated_modules'], [])
        self.assertEqual(plan['added_modules'], ['Demo'])
        with self.result(plan) as result:
            self.assertEqual(result.roots, ['Demo'])
            self.assertEqual(result.read('MainSettingsNamelist.txt'), b'{"keep": 42}')
            self.assertEqual(json.loads(result.read('Demo/SettingsNamelist.txt'))['PHYSICS']['x'], 2)

    def test_new_module_examples_follow_explicit_data_policy(self):
        add_module(self.new)
        package = publish(self.new, self.library, self.meta, ['Demo', 'Added'], include_examples=True)
        for policy in ('keep', 'examples'):
            with self.subTest(policy=policy):
                output = self.dir / (policy + '.zip')
                apply_update(plan_update(self.old, package, data_policy=policy), output)
                with Project(output) as result:
                    self.assertEqual('Added/sample.dat' in result.files, policy == 'examples')
                    self.assertEqual('Demo/data/v1.npy' in result.files, policy == 'keep')
                    self.assertEqual(result.read('Other/task.py'), self.old_files['Other/task.py'])
                    if policy == 'examples':
                        self.assertEqual(result.read('Added/sample.dat'), b'NEW-MODULE-EXAMPLE')

    def test_new_module_does_not_replace_existing_nonmodule_tree(self):
        add_module(self.new)
        def conflict(entries):
            entries['OMFITsave.txt'] += tree_bytes([row(['Added']), row(['Added', 'saved'], 'OMFITascii', 'saved.dat')])
            entries['saved.dat'] = b'USER DATA'
        rewrite(self.old, conflict)
        before = self.old.read_bytes()
        package = publish(self.new, self.library, self.meta, ['Demo', 'Added'])
        with self.assertRaisesRegex(TemplateError, '同名.*Added'):
            plan_update(self.old, package)
        self.assertEqual(self.old.read_bytes(), before)

    def test_new_module_cannot_overwrite_existing_unreferenced_file(self):
        add_module(self.new)
        rewrite(self.old, lambda entries: entries.update({'Added/GUIS/main.py': b'USER FILE'}))
        before = self.old.read_bytes()
        package = publish(self.new, self.library, self.meta, ['Added'])
        with self.assertRaisesRegex(TemplateError, '覆盖保留数据'):
            plan_update(self.old, package)
        self.assertEqual(self.old.read_bytes(), before)

    def test_new_module_directory_cannot_replace_existing_file(self):
        add_module(self.new)
        rewrite(self.old, lambda entries: entries.update({'Added/GUIS': b'USER FILE'}))
        package = publish(self.new, self.library, self.meta, ['Added'])
        with self.assertRaisesRegex(TemplateError, '文件与目录重名'):
            plan_update(self.old, package)

    def test_ambiguous_release_identity_is_rejected(self):
        self.meta['author'] = 'a__b'
        with self.assertRaisesRegex(TemplateError, '连续下划线'):
            self.release()

    def test_published_version_is_immutable(self):
        path = self.release()
        before = path.read_bytes()
        with self.assertRaisesRegex(TemplateError, '已存在'):
            self.release()
        self.assertEqual(path.read_bytes(), before)

    def test_same_id_across_authors_and_versions(self):
        self.release()
        self.meta['author'] = 'bob'
        self.release()
        self.meta['version'] = '10.0'
        self.release()
        releases, errors = list_library(self.library)
        self.assertEqual(len(releases), 3)
        self.assertFalse(errors)

    def test_transfer_is_verified_and_non_overwriting(self):
        source = self.release()
        target = self.dir / 'shared' / source.name
        transfer(source, target)
        self.assertEqual(source.read_bytes(), target.read_bytes())
        with self.assertRaisesRegex(TemplateError, '已存在'):
            transfer(source, target)

    def test_tampered_template_rejected_by_plan_and_import(self):
        path = self.release()
        rewrite(path, lambda e: e.__setitem__('payload/Demo/SCRIPTS/run.py', b'# corrupted'))
        with self.assertRaises(TemplateError):
            plan_update(self.old, path)
        with self.assertRaises(TemplateError):
            transfer(path, self.dir / 'bad-copy.zip')

    def test_equal_size_hash_tampering_is_detected(self):
        path = self.release()
        rewrite(path, lambda e: e.__setitem__('payload/Demo/SCRIPTS/run.py', b'# release 9'))
        with self.assertRaisesRegex(TemplateError, 'SHA-256'):
            plan_update(self.old, path)

    def test_unlisted_payload_rejected(self):
        path = self.release()
        rewrite(path, lambda e: e.__setitem__('payload/extra.py', b''))
        with self.assertRaisesRegex(TemplateError, '列表不一致'):
            Template(path)

    def test_scope_metadata_cannot_reclassify_results_as_code(self):
        path = self.release(True)
        def mutate(entries):
            manifest = json.loads(entries['manifest.json'])
            manifest['files']['Demo/data/v2.npy']['kind'] = 'code'
            entries['manifest.json'] = json_bytes(manifest)
        rewrite(path, mutate)
        with self.assertRaisesRegex(TemplateError, '描述不一致'):
            Template(path)

    def test_changed_source_requires_new_preview(self):
        plan = self.plan()
        fixture(self.old, version=2)
        with self.assertRaisesRegex(TemplateError, '重新预览'):
            apply_update(plan, self.dir / 'out.zip')

    def test_changed_template_requires_new_preview(self):
        plan = self.plan()
        rewrite(Path(plan['template']), lambda e: e.__setitem__('manifest.json', e['manifest.json'] + b' '))
        with self.assertRaisesRegex(TemplateError, '重新预览'):
            apply_update(plan, self.dir / 'out.zip')

    def test_existing_output_never_overwritten(self):
        plan = self.plan()
        output = self.dir / 'out.zip'
        output.write_bytes(b'keep me')
        with self.assertRaisesRegex(TemplateError, '已存在'):
            apply_update(plan, output)
        self.assertEqual(output.read_bytes(), b'keep me')

    def test_same_source_as_destination_refused(self):
        with self.assertRaisesRegex(TemplateError, '新的工程'):
            apply_update(self.plan(), self.old)

    def test_cancel_publication_cleans_partial(self):
        cancel = threading.Event()
        def progress(*args):
            cancel.set()
        with self.assertRaises(Cancelled):
            publish(self.new, self.library, self.meta, ['Demo'], progress=progress, cancel=cancel)
        self.assertFalse(list(self.library.glob('*')))

    def test_cancel_apply_cleans_partial(self):
        plan = self.plan()
        cancel = threading.Event()
        def progress(*args):
            cancel.set()
        with self.assertRaises(Cancelled):
            apply_update(plan, self.dir / 'out.zip', progress, cancel)
        self.assertFalse((self.dir / 'out.zip').exists())
        self.assertFalse(list(self.dir.glob('*.partial')))

    def test_receipt_records_version_policy_and_original(self):
        plan = self.plan()
        with self.result(plan) as result:
            path = result.path
        records = read_history(path)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['current'], str(self.old))
        self.assertEqual(records[0]['release']['author'], 'alice')
        self.assertEqual(records[0]['data_policy'], 'keep')

    def test_wrapped_project_folder(self):
        fixture(self.old, prefix='wrapped/')
        with self.result(self.plan()) as result:
            self.assertEqual(result.read('Demo/data/v1.npy'), self.old_files['Demo/data/v1.npy'])

    def test_linux_result_names_are_preserved_inside_zip(self):
        rewrite(self.old, lambda e: e.__setitem__('Demo/N_TOROIDAL>1/result', b'Linux result'))
        with self.result(self.plan()) as result:
            self.assertEqual(result.read('Demo/N_TOROIDAL>1/result'), b'Linux result')

    def test_missing_backing_data_stops_publish(self):
        fixture(self.new, version=2, omit='Demo/data/v2.npy')
        with self.assertRaisesRegex(TemplateError, '缺少引用'):
            self.release()

    def test_posix_traversal_and_ambiguous_paths_rejected(self):
        for name in ('../escape.py', '/absolute.py', 'a/../bad', 'a//bad', 'a/./bad', 'a///', 'a/\ncontrol'):
            with self.subTest(name=name):
                path = self.dir / 'unsafe.zip'
                fixture(path)
                rewrite(path, lambda entries: entries.__setitem__(name, b''))
                with self.assertRaises(TemplateError):
                    Project(path)

    def test_case_distinct_files_remain_distinct(self):
        rewrite(self.old, lambda e: e.update({'Demo/data/Case.npy': b'upper', 'Demo/data/case.npy': b'lower'}))
        with self.result(self.plan()) as result:
            self.assertEqual(result.read('Demo/data/Case.npy'), b'upper')
            self.assertEqual(result.read('Demo/data/case.npy'), b'lower')

    def test_posix_names_have_no_dos_restrictions(self):
        names = ['Demo/AUX', 'Demo/CON', 'Demo/trailing.', 'Demo/trailing ', 'Demo/shot:time', 'Demo/literal\\name']
        rewrite(self.old, lambda entries: entries.update({name: name.encode() for name in names}))
        with self.result(self.plan()) as result:
            for name in names:
                self.assertEqual(result.read(name), name.encode())

    def test_canonical_duplicate_member_rejected(self):
        rewrite(self.old, lambda entries: entries.__setitem__('./Demo/data/v1.npy', b'alias'))
        with self.assertRaisesRegex(TemplateError, '重复路径'):
            Project(self.old)

    def test_racing_publications_do_not_overwrite(self):
        barrier = threading.Barrier(2)
        successes, errors = [], []
        destination = self.dir / 'racing.zip'
        def writer(value):
            try:
                with new_file(destination) as temporary:
                    temporary.write_bytes(value)
                    barrier.wait(timeout=5)
                successes.append(value)
            except Exception as exc:
                errors.append(exc)
        workers = [threading.Thread(target=writer, args=(value,)) for value in (b'first', b'second')]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(10)
        self.assertEqual(len(successes), 1)
        self.assertEqual(destination.read_bytes(), successes[0])
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], FileExistsError)
        self.assertFalse(list(self.dir.glob('*.partial')))

    def test_executable_mode_is_preserved_in_releases_and_updates(self):
        with zipfile.ZipFile(self.new, 'a') as source:
            info = source.getinfo('Demo/SCRIPTS/run.py')
            info.create_system = 3
            info.external_attr = (0o100755 << 16)
            info.comment = b'executable task'
            source.comment = b'permission fixture'  # Commit the updated central directory.
        template_path = self.release()
        with Template(template_path) as template:
            self.assertEqual(template.files['Demo/SCRIPTS/run.py'].external_attr >> 16, 0o100755)
        with self.result(plan_update(self.old, template_path)) as result:
            self.assertEqual(result.files['Demo/SCRIPTS/run.py'].external_attr >> 16, 0o100755)
            self.assertEqual(result.files['Demo/SCRIPTS/run.py'].comment, b'executable task')

    def test_tree_location_never_evaluates_code(self):
        with self.assertRaises(TemplateError):
            location_keys("[__import__('os').system('never execute')]")
        self.assertEqual(location_keys("['a'][0.5][3]"), ('a', 0.5, 3))

    def test_saved_modules_and_settings_follow_omfit_project_info_order(self):
        nodes = [row(['First'], 'OMFITmodule'), row(['Second'], 'OMFITmodule'),
                 row(['First', 'Sub'], 'OMFITmodule'),
                 row(['First', 'SETTINGS'], 'OMFITsettings', 'first.txt'),
                 row(['Second', 'SETTINGS'], 'OMFITsettings', 'second.txt'),
                 row(['First', 'Sub', 'SETTINGS'], 'OMFITsettings', 'sub.txt')]
        pending, matched = [], []
        for node in parse_tree(tree_bytes(nodes)):
            if node.kind == 'OMFITmodule':
                pending.append(node.keys)
            elif pending and node.keys == pending[-1] + ('SETTINGS',):
                matched.append(pending.pop())
        self.assertEqual(pending, [])
        self.assertEqual(set(matched), {('First',), ('First', 'Sub'), ('Second',)})

    def test_duplicate_tree_nodes_rejected(self):
        rewrite(self.old, lambda e: e.__setitem__('OMFITsave.txt', e['OMFITsave.txt'] + tree_bytes([row(['Demo'])])))
        with self.assertRaisesRegex(TemplateError, '重复树节点'):
            Project(self.old)

    def test_empty_library_is_valid(self):
        self.assertEqual(list_library(self.library), ([], []))

    def test_corrupt_library_entry_reported_not_hidden(self):
        self.library.mkdir()
        (self.library / 'bad.omfittpl.zip').write_bytes(b'bad')
        good, errors = list_library(self.library)
        self.assertFalse(good)
        self.assertEqual(len(errors), 1)

    def test_removed_submodule_requires_explicit_structural_work(self):
        def mutate(entries):
            entries['OMFITsave.txt'] += tree_bytes([row(['Demo', 'OldSub'], 'OMFITmodule')])
        rewrite(self.old, mutate)
        with self.assertRaisesRegex(TemplateError, '删除了子模块'):
            self.plan()

    def test_current_result_cannot_be_overwritten_by_template_code_path(self):
        def mutate(entries):
            entries['OMFITsave.txt'] = entries['OMFITsave.txt'].replace(b'./Demo/data/v1.npy', b'./Demo/SCRIPTS/new.py')
            entries['Demo/SCRIPTS/new.py'] = entries.pop('Demo/data/v1.npy')
        rewrite(self.old, mutate)
        with self.assertRaisesRegex(TemplateError, '覆盖保留数据'):
            self.plan()

    def test_unknown_module_scope_rejected(self):
        with self.assertRaisesRegex(TemplateError, '存在的顶层'):
            publish(self.new, self.library, self.meta, ['Unknown'])

    def test_inspection_counts_results_separately(self):
        result = inspect_project(self.new, ['Demo'])
        self.assertEqual(result['files']['code'], 2)
        self.assertEqual(result['files']['settings'], 1)
        self.assertEqual(result['files']['data'], 3)

    def test_libraries_work_with_omfit_injected_namespace(self):
        try:
            import numpy as np
        except ImportError:
            self.skipTest('numpy needed only to reproduce OMFIT namespace injection')
        registry = {}
        original_import = builtins.__import__
        def omfit_import(name, globals=None, locals=None, fromlist=(), level=0):
            if not name.startswith('OMFITlib_template_'):
                return original_import(name, globals, locals, fromlist, level)
            if name not in registry:
                library = type('OMFITLibrary', (), {})()
                registry[name] = library
                library.__dict__.update(vars(np))
                library.__dict__.update(__name__=name, __builtins__=dict(vars(builtins), __import__=omfit_import))
                script = (MODULE / 'LIB' / (name + '.py')).read_text(encoding='utf-8')
                exec(compile(script, name, 'exec'), library.__dict__)
            return registry[name]
        service = omfit_import('OMFITlib_template_service')
        release = service.publish(self.new, self.library, self.meta, ['Demo'])
        plan = service.plan_update(self.old, release)
        service.apply_update(plan, self.dir / 'injected.zip')
        with Project(self.dir / 'injected.zip') as result:
            self.assertEqual(result.read('Demo/data/v1.npy'), self.old_files['Demo/data/v1.npy'])
        github = omfit_import('OMFITlib_template_github')
        self.assertEqual(github.repository('team/demo'), 'team/demo')
        self.assertEqual(github.GitHub('team/demo', token='').repo, 'team/demo')
        session = omfit_import('OMFITlib_template_session')
        self.assertEqual(session.OMFITSession(type('FakeOMFIT', (), {'filename': 'test.zip'})()).project_path(), 'test.zip')

    def test_python39_and_native_module_references(self):
        for path in MODULE.rglob('*.py'):
            tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path), feature_version=(3, 9))
            compile(tree, str(path), 'exec')
        for node in parse_tree((MODULE / 'OMFITsave.txt').read_bytes()):
            if node.ref:
                self.assertTrue((MODULE / node.ref).is_file(), node.ref)


if __name__ == '__main__':
    unittest.main(verbosity=2)
