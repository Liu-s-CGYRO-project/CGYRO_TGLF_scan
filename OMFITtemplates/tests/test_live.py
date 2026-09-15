"""Live updates: object identity, native-style expressions, rollback and stale plans."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'LIB'))
from OMFITlib_template_archive import parse_tree, tree_bytes, TemplateError
from OMFITlib_template_live import Prepared, raw
from OMFITlib_template_session import OMFITSession
from OMFITlib_template_service import publish
from test_templates import fixture, row, rewrite


class OMFITmodule(dict):
    filename = ''


class OMFITpythonTask:
    def __init__(self, text):
        self.text = text
    def read(self):
        return self.text
    def run(self):
        return self.text


class OMFITexpression:
    def __init__(self, expression):
        self.expression = expression
    def __bool__(self):
        raise AssertionError('An expression must not be evaluated')


class UnreadResult:
    def __deepcopy__(self, memo):
        raise AssertionError('Calculation results must not be copied')
    def read(self):
        raise AssertionError('Calculation results must not be read')


class LiveOMFIT(dict):
    filename = 'current.zip'
    zip = True
    def saveas(self, *args, **kw):
        raise AssertionError('Live updates must not save or reload the project')
    save = load = saveas


def load_fixture(entry):
    """File-node constructors are adapters; class identities match OMFIT types."""
    entry = Path(entry)
    tree = LiveOMFIT()
    for record in parse_tree(entry.read_bytes()):
        parent = tree
        for key in record.keys[:-1]:
            parent = parent[key]
        if record.kind == 'OMFITmodule':
            value = OMFITmodule()
        elif record.kind == 'OMFITsettings':
            value = json.loads((entry.parent / record.ref).read_bytes())
        elif record.kind.startswith('OMFITpython'):
            value = OMFITpythonTask((entry.parent / record.ref).read_text(encoding='utf-8'))
        elif record.kind == 'OMFITexpression':
            value = OMFITexpression(record.fields[2])
        elif record.kind == 'OMFITtree':
            value = {}
        else:
            value = UnreadResult()
        parent[record.keys[-1]] = value
    return tree


def factory(entry, **kw):
    return load_fixture(entry)


def current_fixture():
    expression = OMFITexpression('live_input')
    module = OMFITmodule(SCRIPTS={'run': OMFITpythonTask('# locally edited run'),
                                 'old': OMFITpythonTask('# old')}, GUIS={'main': OMFITpythonTask('# old GUI')},
        SETTINGS={'MODULE': {'ID': 'Demo', 'version': 1}, 'PHYSICS': {'x': 99, 'dynamic': expression},
                  'REMOTE_SETUP': {'server': 'live-server'}},
        RUN_DB={'unsaved_result': UnreadResult()}, FILES=UnreadResult())
    return LiveOMFIT(Demo=module, Other=UnreadResult(), MainSettings={'session': 'unchanged'})


class LiveTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        source = self.directory / 'template-source.zip'
        fixture(source, 2)
        def add_gui(entries):
            rows = parse_tree(entries['OMFITsave.txt'])
            rows += [row(['Demo', 'GUIS']), row(['Demo', 'GUIS', 'main'], 'OMFITpythonGUI', 'Demo/GUIS/main.py')]
            entries['OMFITsave.txt'] = tree_bytes(rows)
            entries['Demo/GUIS/main.py'] = b'# updated GUI'
        rewrite(source, add_gui)
        self.template = publish(source, self.directory / 'library',
            dict(id='demo', name='Live test', author='test', version='2'), ['Demo'])
        self.with_examples = publish(source, self.directory / 'examples',
            dict(id='demo', name='Examples', author='test', version='2'), ['Demo'], include_examples=True)
        self.omfit = current_fixture()
        self.session = OMFITSession(self.omfit, tree_factory=factory)

    def plan(self, settings='keep', data='keep'):
        prepared = Prepared(self.with_examples if data == 'examples' else self.template, data, settings)
        return self.session.preview_live(prepared)

    def test_patch_retains_live_unsaved_results_module_and_settings_identities(self):
        module = self.omfit['Demo']
        results, files = module['RUN_DB'], module['FILES']
        settings, expression = module['SETTINGS'], module['SETTINGS']['PHYSICS']['dynamic']
        other, main, filename = self.omfit['Other'], self.omfit['MainSettings'], self.omfit.filename
        plan = self.plan()
        module['RUN_DB']['arrived_after_preview'] = UnreadResult()
        self.session.apply_live(plan)
        self.assertIs(self.omfit['Demo'], module)
        self.assertIs(module['RUN_DB'], results)
        self.assertIs(module['FILES'], files)
        self.assertIs(module['SETTINGS'], settings)
        self.assertIs(settings['PHYSICS']['dynamic'], expression)
        self.assertEqual(settings['PHYSICS']['x'], 99)
        self.assertEqual(settings['PHYSICS']['added'], 42)
        self.assertEqual(settings['REMOTE_SETUP']['server'], 'live-server')
        self.assertEqual(settings['MODULE']['version'], 2)
        self.assertIn('new', module['SCRIPTS'])
        self.assertNotIn('old', module['SCRIPTS'])
        self.assertEqual(module['SCRIPTS']['run'].read(), '# release 2')
        self.assertIs(self.omfit['Other'], other)
        self.assertIs(self.omfit['MainSettings'], main)
        self.assertEqual(self.omfit.filename, filename)

    def test_settings_policy_and_undo_restore_old_objects_without_losing_new_results(self):
        settings = self.omfit['Demo']['SETTINGS']
        expression = settings['PHYSICS']['dynamic']
        old_run = self.omfit['Demo']['SCRIPTS']['run']
        self.session.apply_live(self.plan(settings='template'))
        self.assertEqual(settings['PHYSICS']['x'], 2)
        self.omfit['Demo']['RUN_DB']['new_result'] = UnreadResult()
        self.session.undo_live()
        self.assertEqual(settings['PHYSICS']['x'], 99)
        self.assertIs(settings['PHYSICS']['dynamic'], expression)
        self.assertIs(self.omfit['Demo']['SCRIPTS']['run'], old_run)
        self.assertIn('new_result', self.omfit['Demo']['RUN_DB'])
        self.assertFalse(self.session.can_undo_live())

    def test_changed_code_after_preview_is_rejected(self):
        plan = self.plan()
        self.omfit['Demo']['SCRIPTS']['run'].text = '# newer local edit'
        with self.assertRaisesRegex(TemplateError, '已修改'):
            self.session.apply_live(plan)
        self.assertEqual(self.omfit['Demo']['SETTINGS']['MODULE']['version'], 1)

    def test_changed_project_after_preview_is_rejected(self):
        plan = self.plan()
        self.omfit['Demo'] = current_fixture()['Demo']
        with self.assertRaisesRegex(TemplateError, '结构已改变'):
            self.session.apply_live(plan)

    def test_undo_does_not_overwrite_subsequent_code_edits(self):
        self.session.apply_live(self.plan())
        self.omfit['Demo']['SCRIPTS']['run'].text = '# edited after update'
        with self.assertRaisesRegex(TemplateError, '已修改'):
            self.session.undo_live()

    def test_refresh_failure_rolls_back_code_and_settings(self):
        before = self.omfit['Demo']['SCRIPTS']['run']
        self.session._refresh_live = Mock(side_effect=[RuntimeError('GUI failed'), None])
        with self.assertRaisesRegex(TemplateError, '已恢复原节点'):
            self.session.apply_live(self.plan(settings='template'))
        self.assertIs(self.omfit['Demo']['SCRIPTS']['run'], before)
        self.assertEqual(self.omfit['Demo']['SETTINGS']['PHYSICS']['x'], 99)
        self.assertFalse(self.session.can_undo_live())

    def test_native_gui_controller_rebound_and_redrawn_in_same_window(self):
        old = self.omfit['Demo']['GUIS']['main']
        plan = self.plan()  # A window opened after preview must also be refreshed.
        gui = SimpleNamespace(pythonFile=old, top=Mock(), update=Mock())
        gui.top.winfo_exists.return_value = True
        api = SimpleNamespace(_GUIs={'current': gui}, _clearClosedGUI=Mock(), OMFITaux={})
        self.session.gui_api = api
        self.session.apply_live(plan)
        api._clearClosedGUI.assert_not_called()
        self.assertIsNot(gui.pythonFile, old)
        self.assertEqual(gui.pythonFile.read(), '# updated GUI')
        gui.update.assert_called_once()
        self.session.undo_live()
        self.assertIs(gui.pythonFile, old)
        self.assertEqual(gui.update.call_count, 2)

    def test_partial_tree_assignment_failure_is_rolled_back(self):
        class FailOnce(dict):
            def __setitem__(self, key, value):
                if key == 'added' and not hasattr(self, 'failed'):
                    self.failed = True
                    raise OSError('write rejected')
                super().__setitem__(key, value)
        self.omfit['Demo']['SETTINGS']['PHYSICS'] = FailOnce(self.omfit['Demo']['SETTINGS']['PHYSICS'])
        before = self.omfit['Demo']['SCRIPTS']['run']
        with self.assertRaisesRegex(TemplateError, '已恢复原节点'):
            self.session.apply_live(self.plan())
        self.assertIs(self.omfit['Demo']['SCRIPTS']['run'], before)
        self.assertEqual(self.omfit['Demo']['SETTINGS']['MODULE']['version'], 1)
        self.assertNotIn('added', self.omfit['Demo']['SETTINGS']['PHYSICS'])

    def test_examples_policy_is_explicit_and_undo_keeps_original_results(self):
        old = self.omfit['Demo']['RUN_DB']
        self.session.apply_live(self.plan(data='examples'))
        self.assertIsNot(self.omfit['Demo']['RUN_DB'], old)
        self.session.undo_live()
        self.assertIs(self.omfit['Demo']['RUN_DB'], old)

    def test_keep_does_not_extract_or_construct_example_data(self):
        prepared = Prepared(self.with_examples)
        self.assertFalse((prepared.path / 'Demo/data/v2.npy').exists())
        tree = factory(prepared.entry)
        self.assertEqual(tree['Demo']['RUN_DB'], {})
        self.assertNotIn('FILES', tree['Demo'])

    def test_deleted_submodule_is_blocked_when_preserving_results(self):
        self.omfit['Demo']['Child'] = OMFITmodule(RUN_DB={'case': UnreadResult()})
        with self.assertRaisesRegex(TemplateError, '删除了子模块'):
            self.plan()

    def test_new_module_can_be_inserted_into_unsaved_project(self):
        del self.omfit['Demo']
        self.omfit.filename = ''
        self.session.apply_live(self.plan())
        self.assertIsInstance(self.omfit['Demo'], OMFITmodule)
        self.assertEqual(self.omfit.filename, '')
        self.session.undo_live()
        self.assertNotIn('Demo', self.omfit)

    def test_preview_and_apply_reject_worker_thread(self):
        errors = []
        prepared = Prepared(self.template)
        def work():
            try:
                self.session.preview_live(prepared)
            except Exception as exc:
                errors.append(exc)
        worker = threading.Thread(target=work)
        worker.start()
        worker.join()
        self.assertEqual(len(errors), 1)
        self.assertIn('主线程', str(errors[0]))


if __name__ == '__main__':
    unittest.main()
