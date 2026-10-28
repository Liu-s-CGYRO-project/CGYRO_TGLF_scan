"""Runtime draft edits refresh status without replacing focused native fields."""
from collections import Counter
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_cgyro_storage
import test_gui_tab_pages as fixture
import test_gui_refresh_native as native
import OMFITlib_workbench_runtime_ui as runtime_ui

SOURCE = native.SOURCE


class RuntimeBoundaryTests(unittest.TestCase):
    def setUp(self):
        source = patch.object(fixture, 'SOURCE', SOURCE)
        source.start()
        self.addCleanup(source.stop)
        host_fixture = fixture.NativeTabsTests()
        self.addCleanup(host_fixture.doCleanups)
        host_fixture.setUp()
        self.host = host_fixture.host
        self.counts, self.events = Counter(), []
        self.host.root.bind('<<update_treeGUI>>', lambda event: self.events.append('tree'), add='+')
        self.host.tree['SETTINGS'] = {'GACODE_RUNTIME': {}}
        counts, host = self.counts, self.host
        class View(runtime_ui.RuntimePage):
            def runtime_apply(view, config):
                counts['status'] += 1
                view.status = view.ui.Label(str(host.tree['number']))
            def environment(view, config, prefix):
                counts['environment'] += 1
                view.entry = view.runtime_entry("root['number']", 'MPI', updateGUI=True)
                view.combo = view.runtime_choice("root['mode']", ['spectra', 'ballooning'], 'Mode',
                                                updateGUI=True, postcommand=lambda location: counts.update(['postcommand']))
            def runtime_commands(view, prefix):
                counts['commands'] += 1
                view.command_entry = view.runtime_entry("root['text']", 'Command', updateGUI=True)
            def gacode_installations(view, config):
                counts['installations'] += 1
            def runtime_records(view):
                raise AssertionError('Unselected records read')
            def runtime_history(view):
                raise AssertionError('Unselected history read')
        self.view = View()
        self.view.root = self.host.tree
        self.view.actions = SimpleNamespace(factory=dict)
        self.view.settings = {}
        def render(ui):
            counts['window'] += 1
            self.view.ui = ui
            self.header = ui.Label('Workbench header')
            self.view.render_run()
        with patch.object(runtime_ui, 'initialize_runtime', return_value={}):
            self.host.render(render)
        self.events.clear()

    def test_numeric_commit_keeps_field_notebook_and_other_windows(self):
        view = self.view
        field, notebook, header = view.entry, view.runtime_pages.notebook, self.header
        field.delete(0, 'end')
        field.insert(0, '24')
        self.host.submit_entry(field)
        self.host.drain(80)
        self.assertEqual(self.host.tree['number'], 24)
        self.assertEqual(str(view.status.cget('text')), '24')
        self.assertEqual(self.counts, dict(window=1, status=2, environment=1))
        for widget in (field, notebook, header):
            self.assertTrue(widget.winfo_exists())
        self.assertEqual(self.events, [])
        self.assertEqual(self.host.updates, [])

    def test_structural_choice_rebuilds_only_tab_and_status(self):
        view = self.view
        notebook, field = view.runtime_pages.notebook, view.entry
        view.combo.set('ballooning')
        self.host.invoke(lambda: view.combo.event_generate('<<ComboboxSelected>>'))
        self.host.drain(80)
        self.assertEqual(self.counts, dict(window=1, status=2, environment=2, postcommand=1))
        self.assertFalse(field.winfo_exists())
        self.assertIs(view.runtime_pages.notebook, notebook)
        self.assertTrue(notebook.winfo_exists())
        self.assertEqual(self.events, [])
        self.assertEqual(self.host.updates, [])
        view.runtime_pages.select('commands')
        self.host.drain()
        self.assertEqual(self.counts['commands'], 1)
        self.assertEqual(self.counts['window'], 1)


if __name__ == '__main__':
    unittest.main()
