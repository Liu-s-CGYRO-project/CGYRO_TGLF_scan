"""Independent tools refresh their own native Tk region and build visible tabs.

The unchanged OMFIT widgets/CompoundGUI run in the native test host. Reader
and scheduler probes are counted so navigation cannot silently do that work.
"""
from collections import Counter, OrderedDict
import copy
from types import ModuleType, SimpleNamespace
import sys
import unittest
from unittest.mock import patch

import test_cgyro_storage  # Existing isolated native reader stand-ins.
import test_gui_refresh_native as native
import test_gui_tab_pages as tabs_fixture
import OMFITlib_plot_style_ui as style_ui
import OMFITlib_cgyro_results as results_ui
import OMFITlib_tglf_multi_ui as multi_ui
import OMFITlib_compare_ui as compare_ui
import OMFITlib_compare_cases as compare_cases
import OMFITlib_workbench_cgyro_ui as cgyro_ui
from OMFITlib_gui_deferred import TabPages, deferred_section

SOURCE = native.SOURCE


class RefreshBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.start_patch(patch.object(tabs_fixture, 'SOURCE', SOURCE))
        fixture = tabs_fixture.NativeTabsTests()
        self.addCleanup(fixture.doCleanups)
        fixture.setUp()
        self.host = fixture.host
        native.native_definitions(SOURCE / 'omfit_classes/OMFITx.py',
                                 {'CheckBox', 'Separator'}, self.host.api.__dict__)
        self.host.api.TitleGUI = lambda title: self.host.owner.top.title(title)
        self.host.tree['SETTINGS'] = {'WORKBENCH': {}}
        self.counts = Counter()

    def start_patch(self, patcher):
        value = patcher.start()
        self.addCleanup(patcher.stop)
        return value

    def build(self, render):
        def build(ui):
            self.counts['window'] += 1
            self.header = ui.Label('External task management')
            self.external_action = ui.Button('External task action', lambda: None)
            render(ui)
        self.host.render(build)

    def combo(self, containing):
        return next(widget for widget in self.host.descendants(self.host.owner.top)
                    if isinstance(widget, native.ttk.Combobox)
                    and containing in tuple(widget.cget('values')))

    def choose(self, combo, caption):
        combo.set(caption)
        self.host.invoke(lambda: combo.event_generate('<<ComboboxSelected>>'))
        self.host.drain(60)

    def assert_external_survives(self, header, action):
        self.assertIs(self.header, header)
        self.assertIs(self.external_action, action)
        self.assertTrue(header.winfo_exists())
        self.assertTrue(action.winfo_exists())
        self.assertEqual(self.counts['window'], 1)
        self.assertEqual(self.host.updates, [])

    def assert_notebooks_alive(self):
        self.assertTrue(all(notebook.winfo_exists() for notebook in self.host.owner.notebooks.values()))

    def test_palette_and_style_reset_rebuild_only_standalone_editor(self):
        render = self.start_patch(patch.object(style_ui, '_render_style', wraps=style_ui._render_style))
        self.build(lambda ui: style_ui.render_style(self.host.tree, ui))
        header, action = self.header, self.external_action
        first = self.combo('自定义')
        self.choose(first, '自定义')
        self.assertEqual(self.host.tree['SETTINGS']['PLOT_STYLE']['palette'], 'custom')
        self.assertFalse(first.winfo_exists())
        labels = [str(widget.cget('text')) for widget in self.host.descendants(self.host.owner.top)
                  if isinstance(widget, native.ttk.Label)]
        self.assertTrue(any(text.startswith('颜色列表') for text in labels))
        self.host.button(self.host.owner.top, '重置样式').invoke()
        self.host.drain(60)
        self.assertEqual(self.host.tree['SETTINGS']['PLOT_STYLE']['palette'], 'okabe_ito')
        self.assertEqual(render.call_count, 3)
        self.assert_external_survives(header, action)

    def test_result_selection_rebuilds_only_browser_without_opening_results(self):
        view = results_ui._view_settings(self.host.tree)
        view['run_token'] = 'scan-a'
        options = OrderedDict([('Scan A', 'scan-a'), ('Scan B', 'scan-b')])
        entry = dict(scan_axes=[dict(name='N_ENERGY')], dimensions=1,
                     tasks={'p000001': dict(values={'N_ENERGY': 48, 'KY': .5})})
        select = self.start_patch(patch.object(results_ui, 'selected_record', side_effect=lambda *a, **k:
                                               (view, view['run_token'], entry, options)))
        self.start_patch(patch.object(results_ui, 'record_details', return_value='metadata'))
        reader = self.start_patch(patch.object(results_ui, '_result_node', side_effect=AssertionError('result opened')))
        summary = self.start_patch(patch.object(results_ui, '_frequency_summary', side_effect=AssertionError('result parsed')))
        def render(ui):
            self.browser = results_ui.ResultBrowser(self.host.tree, ui)
            self.browser.render()
        self.build(render)
        header, action = self.header, self.external_action
        content = self.browser.content
        self.choose(self.combo('Scan B'), 'Scan B')
        self.assertEqual(view['run_token'], 'scan-b')
        self.assertEqual(select.call_count, 2)
        self.assertIs(self.browser.content, content)
        reader.assert_not_called()
        summary.assert_not_called()
        self.assert_external_survives(header, action)

    def build_multi(self):
        plan = dict(coordinate='rho', radii=[.5], parameters={'NKY': 12})
        attempt = dict(status='complete', workdir='/synthetic/result', result={'opaque': True})
        point = dict(radius=.5, status='complete', attempts={'a': attempt}, selected_attempt='a')
        run = dict(created='2026-10-27', status='complete', plan=plan, points={'p': point})
        self.host.tree['TGLF_CASES'] = {'case-a': dict(enabled=True, label='Profile A', radii='', extra='',
            source='/synthetic/input.gacode', info={'points': 4, 'ions': 2}, sha256='abc',
            runs={'run-a': run}, selected_run='run-a', **{'input.gacode': {'opaque': True}})}
        self.scripts = {name: SimpleNamespace(run=lambda **kw: self.fail('Unexpected script execution'))
                        for name in ('run_tglf_multi', 'import_tglf_multi')}
        self.host.tree['SCRIPTS'] = self.scripts
        self.probes = {}
        for name, result in [('shared_issues', []), ('prepared_run_issues', []), ('case_plan', plan),
                             ('profile_digest', 'digest'), ('flux_summary', 'flux metadata')]:
            self.probes[name] = self.start_patch(patch.object(multi_ui, name, return_value=result))
        def render(ui):
            self.multi = multi_ui.MultiInputUI(self.host.tree, ui)
            self.multi.render()
        self.build(render)

    def select_multi(self, tab):
        self.multi.pages.select(tab)
        self.host.root.update()
        self.host.drain(60)

    def test_multi_open_and_settings_never_prepare_check_or_read_hidden_results(self):
        self.build_multi()
        header, action, notebook = self.header, self.external_action, self.multi.pages.notebook
        for tab in ('settings', 'cases', 'settings'):
            self.select_multi(tab)
        for probe in self.probes.values():
            probe.assert_not_called()
        self.assertIs(self.multi.pages.notebook, notebook)
        self.assertEqual(self.multi.settings['view_tab'], 'settings')
        self.assert_external_survives(header, action)
        self.assert_notebooks_alive()

    def test_multi_case_action_invalidates_other_tabs_and_keeps_notebook_registry_live(self):
        self.build_multi()
        header, action = self.header, self.external_action
        self.select_multi('results')
        self.assertEqual(self.probes['flux_summary'].call_count, 1)
        self.select_multi('cases')
        old_notebook = self.multi.pages.notebook
        self.host.button(self.host.owner.top, '复制为新案例').invoke()
        self.host.drain(60)
        self.assertEqual(len(self.multi.cases), 2)
        self.assertFalse(old_notebook.winfo_exists())
        self.assertEqual(self.probes['flux_summary'].call_count, 1)
        self.select_multi('results')
        labels = [str(widget.cget('text')) for widget in self.host.descendants(self.host.owner.top)
                  if isinstance(widget, native.ttk.Label)]
        self.assertTrue(any(text.startswith('已选择 2 / 2 个案例') for text in labels))
        self.assertEqual(self.probes['prepared_run_issues'].call_count, 3)
        self.assertEqual(self.probes['flux_summary'].call_count, 2)
        self.assert_external_survives(header, action)
        self.assert_notebooks_alive()
        # Native GUI.update reads this registry before clearing its children.
        self.host.owner.update()
        self.host.root.update()
        self.assert_notebooks_alive()

    def test_multi_result_refresh_keeps_tool_header_and_current_notebook(self):
        self.build_multi()
        self.select_multi('results')
        notebook = self.multi.pages.notebook
        import_button = self.host.button(self.host.owner.top, '导入多个 input.gacode')
        self.host.button(self.host.owner.top, '刷新状态').invoke()
        self.host.drain(60)
        self.assertEqual(self.probes['flux_summary'].call_count, 2)
        self.assertIs(self.multi.pages.notebook, notebook)
        self.assertTrue(import_button.winfo_exists())
        self.assertEqual(self.host.updates, [])
        self.assert_notebooks_alive()

    def test_comparison_check_refreshes_only_selected_mode_and_shared_footer(self):
        self.host.tree['SETTINGS']['PHYSICS'] = {'compare_mode': 'TGLF_vs_TGLF'}
        counts = Counter()
        class Controls:
            def __run__(script, comparison, mode, **kwargs):
                counts[mode] += 1
                comparison.render_controls(mode)
        module = ModuleType('omfit_classes.omfit_python')
        module.OMFITpythonGUI = Controls
        self.start_patch(patch.dict(sys.modules, {'omfit_classes.omfit_python': module}))
        self.host.tree['GUIS'] = {'Compare_controls': Controls()}
        self.start_patch(patch.object(compare_ui.ComparisonUI, 'render_mode_tglf_vs_tglf',
                                     lambda pane, state: pane.ui.Label('Synthetic indexed cases')))
        self.start_patch(patch.object(compare_ui, 'comparison_issues', return_value=[]))
        check = self.start_patch(patch.object(compare_ui, 'selection_check', return_value={'errors': []}))
        def render(ui):
            self.compare = compare_ui.ComparisonUI(self.host.tree, ui)
            self.compare.render()
        self.build(render)
        header, action, notebook = self.header, self.external_action, self.compare.mode_notebook
        pane = self.compare.panes[2]
        old_status = pane.status_label
        self.host.button(self.host.owner.top, '检查选择').invoke()
        self.host.drain(60)
        self.assertEqual(counts, {'TGLF_vs_TGLF': 2})
        self.assertEqual(check.call_count, 3)
        self.assertFalse(old_status.winfo_exists())
        self.assertTrue(pane.status_label.winfo_exists())
        self.assertIs(self.compare.mode_notebook, notebook)
        self.assert_external_survives(header, action)
        self.assert_notebooks_alive()

    def build_task_change_listener(self):
        self.task_state = dict(page='tasks', results=2)
        self.host.tree['CGYRO_scan'] = {}
        callbacks = []
        def manager(parent, module, delete, factory, on_changed):
            callbacks.append(on_changed)
            return SimpleNamespace(window=native.tk.Toplevel(self.host.root), on_changed=on_changed)
        self.start_patch(patch.object(cgyro_ui, 'TaskManager', side_effect=manager))
        def render(ui):
            view = cgyro_ui.CgyroPage()
            view.root, view.settings, view.ui = self.host.tree, {}, ui
            view.actions = SimpleNamespace(remove_cgyro_tasks=lambda *a, **k: None, factory=dict)
            def body():
                self.counts[self.task_state['page']] += 1
                self.current_count = ui.Label(str(self.task_state['results']))
                if self.task_state['page'] == 'tasks':
                    TabPages(ui, {'results': 'Results'}, {}, 'tab',
                             lambda tab: view.render_cgyro_cleanup(self.host.tree['CGYRO_scan']))
            self.task_body = deferred_section(ui, body, local=True, container=True, action=True)
            self.task_body.parent.master._cgyro_action_refresh = self.task_body.refresh
            self.task_body.show()
        self.build(render)
        self.host.button(self.host.owner.top, '任务管理 / 删除任务…').invoke()
        self.task_callback = callbacks[0]

    def test_task_delete_after_page_navigation_updates_current_page_only(self):
        self.build_task_change_listener()
        self.task_state['page'] = 'plots'
        self.task_body.refresh.request()
        self.host.drain(60)
        header, action = self.header, self.external_action
        self.task_state['results'] = 1
        self.task_callback()
        self.host.drain(60)
        self.assertEqual(str(self.current_count.cget('text')), '1')
        self.assertEqual(self.counts['tasks'], 1)
        self.assertEqual(self.counts['plots'], 2)
        self.assert_external_survives(header, action)

    def test_task_delete_after_explicit_window_refresh_targets_new_body(self):
        self.build_task_change_listener()
        self.task_state['page'] = 'plots'
        self.host.owner.update()
        self.host.root.update()
        self.host.updates.clear()
        self.task_state['results'] = 1
        self.task_callback()
        self.host.drain(60)
        self.assertEqual(str(self.current_count.cget('text')), '1')
        self.assertEqual(self.counts['window'], 2)
        self.assertEqual(self.counts['plots'], 2)
        self.assertEqual(self.host.updates, [])

    def build_comparison_options(self, mode='CGYRO_vs_CGYRO'):
        class Tasks(dict):
            visits = 0
            def values(tasks):
                for row in super().values():
                    tasks.visits += 1
                    yield row
        self.point_tables = []
        runs = {}
        for name in ('Jet', 'Other A', 'Other B'):
            tasks = Tasks({'p' + str(index): dict(result_path=['A', 1, 'lin', index / 1000.])
                           for index in range(1000)})
            self.point_tables.append(tasks)
            info = dict(scan_axes=[dict(name='A', values=[1])], parameters=['A'])
            case = {'A': {}, '__SCANS__': {'A': dict(info=info, tasks=tasks)}, '__INFO__': info, '__TASKS__': tasks}
            runs[name] = {'nr=1_rho=0.33': case}
        self.host.tree['CGYRO_scan'] = {'RUN_DB': runs}
        self.tglf_points = Tasks({'p' + str(index): dict(status='failed') for index in range(999)})
        self.tglf_points['p999'] = dict(status='complete')
        self.host.tree['TGLF_scan'] = {'RUN_DB': {'tglf-run': dict(points=self.tglf_points)}}
        self.host.tree['SETTINGS']['PHYSICS'] = dict(compare_mode=mode,
            CGYRO_vs_CGYRO=dict(runid='Jet', nr_CGYRO=['nr=1__rho=0.33__ion=BASE'],
                selected_paras={'A': [1]}, view_tab='plot'),
            TGLF_vs_TGLF=dict(TGLF=dict(result_source='tglf-run', spectra_mode='1D',
                                      rho_selected=[.33], selected_paras={'A': [1]}), view_tab='plot'))
        namespace = self.host.api.__dict__
        def defaults(location, default):
            if default is not self.host.special:
                locations = location if isinstance(location, list) else [location]
                values = default if isinstance(location, list) else [default]
                for path, value in zip(locations, values):
                    try:
                        eval(path, namespace)
                    except KeyError:
                        namespace['_fixture_default'] = copy.deepcopy(value)
                        exec(path + ' = _fixture_default', namespace)
            return default, False
        namespace['_setDefault'] = defaults
        namespace['_eval'] = lambda location: ([eval(item, namespace) for item in location]
                                              if isinstance(location, list) else eval(location, namespace))
        namespace['repr_eval'] = lambda location, preentry=None, collect=False: repr(
            preentry(namespace['_eval'](location)) if preentry else namespace['_eval'](location))
        class Controls:
            def __run__(script, comparison, mode, **kwargs):
                comparison.render_controls(mode)
        module = ModuleType('omfit_classes.omfit_python')
        module.OMFITpythonGUI = Controls
        self.start_patch(patch.dict(sys.modules, {'omfit_classes.omfit_python': module}))
        self.host.tree['GUIS'] = {'Compare_controls': Controls()}
        self.catalog = self.start_patch(patch.object(compare_cases, 'catalog_runs', wraps=compare_cases.catalog_runs))
        self.tree_events = []
        self.host.root.bind('<<update_treeGUI>>', lambda event: self.tree_events.append('tree'), add='+')
        def render(ui):
            self.compare = compare_ui.ComparisonUI(self.host.tree, ui)
            self.compare.render()
        self.build(render)
        self.tree_events.clear()

    def test_plot_checkbox_never_walks_archive_catalog_or_point_tables(self):
        self.build_comparison_options()
        header, action = self.header, self.external_action
        footer = self.compare.panes[compare_ui.MODES.index('CGYRO_vs_CGYRO')].status_label
        self.host.tree['SETTINGS']['PHYSICS']['CGYRO_vs_CGYRO']['ave_window'] = 0
        control = next(widget for widget in self.host.descendants(self.host.owner.top)
                       if isinstance(widget, native.ttk.Checkbutton) and widget.cget('text') == 'X 对数轴')
        # Native CheckBox commits via ButtonRelease, independently of command.
        self.host.invoke(lambda: control.event_generate('<ButtonRelease-1>'))
        self.host.drain(60)
        self.assertTrue(self.host.tree['SETTINGS']['PHYSICS']['CGYRO_vs_CGYRO']['plot_log_x'])
        self.catalog.assert_not_called()
        self.assertEqual([tasks.visits for tasks in self.point_tables], [0, 0, 0])
        self.assertEqual(self.tglf_points.visits, 0)
        self.assertEqual(self.tree_events, [])
        self.assertTrue(footer.winfo_exists())
        self.assertIn('选择尚未完成', str(footer.cget('text')))
        self.assert_external_survives(header, action)

    def test_tglf_plot_option_refresh_does_not_requery_result_availability(self):
        self.build_comparison_options('TGLF_vs_TGLF')
        self.assertEqual(self.tglf_points.visits, 1000)
        pane = self.compare.panes[compare_ui.MODES.index('TGLF_vs_TGLF')]
        footer = pane.status_label
        control = next(widget for widget in self.host.descendants(self.host.owner.top)
                       if isinstance(widget, native.ttk.Checkbutton) and widget.cget('text') == 'X 对数轴')
        self.host.invoke(lambda: control.event_generate('<ButtonRelease-1>'))
        self.host.drain(60)
        self.assertTrue(pane.plot_settings['plot_log_x'])
        self.assertEqual(self.tglf_points.visits, 1000)
        self.assertEqual([tasks.visits for tasks in self.point_tables], [0, 0, 0])
        self.catalog.assert_not_called()
        self.assertEqual(self.tree_events, [])
        self.assertIs(pane.status_label, footer)
        # An explicit check still revalidates availability after data changes.
        self.tglf_points['p999']['status'] = 'failed'
        self.host.button(self.host.owner.top, '检查选择').invoke()
        self.host.drain(60)
        self.assertEqual(self.tglf_points.visits, 2000)
        self.assertIn('暂无可绘图', str(pane.status_label.cget('text')))
        self.assertEqual(str(self.host.button(self.host.owner.top, '绘制所选数据').cget('state')), 'disabled')


if __name__ == '__main__':
    unittest.main()
