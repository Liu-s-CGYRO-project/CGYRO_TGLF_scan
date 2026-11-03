"""Selection/plot boundaries for the dedicated one-factor convergence case."""
import copy
from contextlib import contextmanager
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'CGYRO_TGLF_scan/LIB'))
import OMFITlib_compare_cases as cases
import OMFITlib_compare_state as state
import OMFITlib_compare_cgyro_selection as selection
import OMFITlib_compare_cgyro as plotting
import OMFITlib_compare_ui as compare_ui
from test_compare_convergence import fixture as indexed_case
from OMFITlib_compare_convergence import convergence_groups


class UI:
    def __init__(self):
        self.events = []
        self.rows = []
        self.row = None

    @contextmanager
    def same_row(self):
        previous = self.row
        self.row = []
        self.rows.append(self.row)
        try:
            yield
        finally:
            self.row = previous

    def __getattr__(self, method):
        def record(*args, **kwargs):
            self.events.append((method, args, kwargs))
            if method == 'CheckBox' and self.row is not None:
                self.row.append(args[1])
        return record


GROUPS = {
    'N_THETA': dict(axis='N_THETA', label='沿场分辨率', baseline_value=32, values=[24, 32, 48]),
    'N_XI': dict(axis='N_XI', label='俯仰角分辨率', baseline_value=48, values=[32, 48, 64]),
}


def fixture():
    settings = dict(runid='Jet_convergence', nr_CGYRO=['nr=1'], cgyro_view='收敛测试',
                    convergence_selected_by_nr={'nr=1': {'N_THETA': [24, 32, 48], 'N_XI': [32, 48, 64]}},
                    convergence_flags_by_nr={'nr=1': {'N_THETA': True, 'N_XI': True}})
    root = dict(SETTINGS=dict(PHYSICS=dict(compare_mode='CGYRO_vs_CGYRO', CGYRO_vs_CGYRO=settings)),
                CGYRO_scan=dict(RUN_DB={'Jet_convergence': {'nr=1': {}}}))
    state.initialize_settings(root)
    return root, settings


class ConvergencePlottingTests(unittest.TestCase):
    def test_ordinary_source_does_not_offer_convergence_from_another_run_or_constant_case(self):
        for per_case in (False, True):
            with self.subTest(per_case=per_case):
                root, settings = fixture()
                settings.update(runid='Jet', force_read_all_nr_items=per_case)
                root['CGYRO_scan']['RUN_DB']['Jet_convergence']['nr=1'] = indexed_case()
                run = {'nr=1': {'N_THETA': {'24': {}, '32': {}}},
                       'different_constant': indexed_case()}
                ui = UI()
                app = cases.CaseSelection(root, ui)
                with patch.object(app, '_choose_cgyro', return_value=(run, ['nr=1'])):
                    app.render_mode_cgyro_vs_cgyro(settings)
                self.assertEqual(settings['cgyro_view'], '常规扫描')
                self.assertFalse(any(kind == 'CheckBox' and args[1] == 'convergence_test'
                                     for kind, args, _ in ui.events))
                self.assertFalse(any('此案例没有' in str(args) for _, args, _ in ui.events))
                self.assertTrue(any('N_THETA' in row for row in ui.rows))

    def test_unresolved_current_case_does_not_offer_convergence(self):
        root, settings = fixture()
        case = indexed_case()
        for name in list(case):
            if not name.startswith('__'):
                case[name] = {}  # Retained index, missing physical references.
        ui = UI()
        app = cases.CaseSelection(root, ui)
        with patch.object(app, '_choose_cgyro', return_value=({'nr=1': case}, ['nr=1'])):
            app.render_mode_cgyro_vs_cgyro(settings)
        self.assertEqual(settings['cgyro_view'], '常规扫描')
        self.assertNotIn('convergence_test', [name for row in ui.rows for name in row])

    def test_selector_has_one_case_and_independent_directions_without_cartesian_controls(self):
        root, settings = fixture()
        ui = UI()
        app = cases.CaseSelection(root, ui)
        with patch.object(app, '_choose_cgyro', return_value=({'nr=1': {}}, ['nr=1'])), \
                patch.object(cases, 'convergence_groups', return_value=copy.deepcopy(GROUPS)), \
                patch.object(app, '_multi_axis_entries', side_effect=AssertionError('Cartesian UI used')):
            app.render_mode_cgyro_vs_cgyro(settings)
        self.assertEqual(settings['cgyro_view'], '收敛测试')
        self.assertEqual([args[0] for kind, args, _ in ui.events if kind == 'Separator'],
                         ['扫描参数与取值', '收敛测试'])
        self.assertEqual(len([1 for kind, args, _ in ui.events if kind == 'Entry']), 2)
        self.assertFalse(any(' × ' in str(args) for _, args, _ in ui.events))
        self.assertFalse(any(kind == 'ComboBox' and 'cgyro_view' in str(args) for kind, args, _ in ui.events))
        toggles = [kwargs for kind, args, kwargs in ui.events if kind == 'CheckBox' and args[1] == 'convergence_test']
        self.assertEqual(len(toggles), 1)
        self.assertEqual(toggles[0]['mapFalseTrue'], ['常规扫描', '收敛测试'])
        self.assertEqual(ui.rows, [['convergence_test']])

    def test_convergence_choice_is_in_the_selected_isotopes_scan_grid(self):
        root, settings = fixture()
        case = indexed_case()
        for name in ('N_RADIAL', 'N_THETA', 'ordinary'):
            case[name] = {'1': {}, '2': {}}
        ui = UI()
        app = cases.CaseSelection(root, ui)
        with patch.object(app, '_choose_cgyro', return_value=({'nr=1': case}, ['nr=1'])):
            app.render_mode_cgyro_vs_cgyro(settings)
        self.assertEqual(ui.rows, [['N_RADIAL', 'N_THETA'], ['ordinary', 'convergence_test']])
        self.assertTrue(all(kwargs.get('state') == 'disabled' for kind, args, kwargs in ui.events
                            if kind == 'CheckBox' and args[1] in ('N_RADIAL', 'N_THETA', 'ordinary')))
        captions = [args[1] if kind == 'CheckBox' else args[0] for kind, args, _ in ui.events
                    if kind in ('Separator', 'CheckBox')]
        self.assertLess(captions.index('扫描参数与取值'), captions.index('convergence_test'))
        self.assertLess(captions.index('convergence_test'), captions.index('收敛测试'))

    def test_ordinary_and_convergence_controls_keep_separate_selections(self):
        root, settings = fixture()
        case = indexed_case()
        case['ordinary'] = {'1': {}, '2': {}}
        settings.update(cgyro_view='常规扫描', selected_paras={'ordinary': [1]})
        ui = UI()
        app = cases.CaseSelection(root, ui)
        saved = copy.deepcopy(settings['convergence_selected_by_nr'])
        with patch.object(app, '_choose_cgyro', return_value=({'nr=1': case}, ['nr=1'])):
            app.render_mode_cgyro_vs_cgyro(settings)
            self.assertEqual([args[1] for kind, args, _ in ui.events if kind == 'Entry'], ['ordinary'])
            self.assertEqual(settings['convergence_selected_by_nr'], saved)
            settings['cgyro_view'] = '收敛测试'
            ui.events.clear()
            app.render_mode_cgyro_vs_cgyro(settings)
            self.assertNotIn('ordinary', [args[1] for kind, args, _ in ui.events if kind == 'Entry'])
            self.assertEqual(settings['selected_paras'], {'ordinary': [1]})
            settings['cgyro_view'] = '常规扫描'
            ui.events.clear()
            app.render_mode_cgyro_vs_cgyro(settings)
            self.assertEqual([args[1] for kind, args, _ in ui.events if kind == 'Entry'], ['ordinary'])
            self.assertEqual(settings['selected_paras'], {'ordinary': [1]})

    def test_per_case_scan_choices_survive_exclusive_convergence_selection(self):
        root, settings = fixture()
        case = indexed_case()
        case['ordinary'] = {'1': {}, '2': {}}
        settings.update(nr_CGYRO=['nr=1', 'nr=2'], force_read_all_nr_items=True,
                        selected_paras={'ordinary': [1, 2]},
                        selected_paras_by_nr={'nr=1': {'ordinary': [1]}, 'nr=2': {'ordinary': [2]}})
        saved = copy.deepcopy(settings['selected_paras_by_nr'])
        ui = UI()
        app = cases.CaseSelection(root, ui)
        with patch.object(app, '_choose_cgyro', return_value=({'nr=1': case, 'nr=2': case}, ['nr=1', 'nr=2'])):
            app.render_mode_cgyro_vs_cgyro(settings)
            self.assertEqual(ui.rows, [['ordinary', 'convergence_test'], ['ordinary']])
            self.assertEqual(settings['selected_paras_by_nr'], saved)
            self.assertEqual(settings['selected_paras'], {'ordinary': [1, 2]})
            self.assertNotIn('ordinary', [args[1] for kind, args, _ in ui.events if kind == 'Entry'])
            settings['cgyro_view'] = '常规扫描'
            ui.events.clear()
            app.render_mode_cgyro_vs_cgyro(settings)
        self.assertEqual([args[1] for kind, args, _ in ui.events if kind == 'Entry'], ['ordinary', 'ordinary'])
        self.assertEqual(settings['selected_paras_by_nr'], saved)

    def test_convergence_only_run_does_not_leak_into_unchecked_ordinary_list(self):
        root, settings = fixture()
        settings['cgyro_view'] = '常规扫描'
        ui = UI()
        app = cases.CaseSelection(root, ui)
        with patch.object(app, '_choose_cgyro', return_value=({'nr=1': indexed_case()}, ['nr=1'])):
            app.render_mode_cgyro_vs_cgyro(settings)
        self.assertEqual(ui.rows, [['convergence_test']])
        self.assertFalse(any(kind == 'Entry' for kind, _, _ in ui.events))
        self.assertTrue(any('没有共同的扫描参数' in str(args) for _, args, _ in ui.events))

    def test_ordinary_plot_does_not_read_stale_selected_convergence_branches(self):
        root, settings = fixture()
        settings.update(cgyro_view='常规扫描', selected_paras={'N_ENERGY': [48]})
        root['CGYRO_scan']['RUN_DB']['Jet_convergence']['nr=1'] = indexed_case()
        ctx = selection.build_context(root)
        with patch.object(plotting, 'collect_value_series', side_effect=AssertionError('result read')):
            self.assertEqual(plotting.collect_plot_items(root, ctx), [])
        self.assertFalse(ctx['convergence_plot'])

    def test_unchecked_direction_and_values_survive_reopen(self):
        root, settings = fixture()
        settings['convergence_flags_by_nr']['nr=1']['N_XI'] = False
        settings['convergence_selected_by_nr']['nr=1']['N_THETA'] = [48]
        restored = json.loads(json.dumps(settings))
        app = cases.CaseSelection(root, UI())
        with patch.object(cases, 'convergence_groups', return_value=copy.deepcopy(GROUPS)):
            app._convergence_entries(restored, lambda *k: str(k), {'nr=1': {}}, ['nr=1'], {'nr=1': ('one', '')})
        self.assertEqual(state.convergence_selection(restored, 'nr=1'), {'N_THETA': [48]})
        self.assertFalse(restored['convergence_flags_by_nr']['nr=1']['N_XI'])

    def test_unavailable_case_and_stale_values_are_not_offered_or_sent_to_plot(self):
        root, settings = fixture()
        settings['convergence_selected_by_nr']['nr=1']['N_THETA'] = [24, 32, 64]
        settings['convergence_selected_by_nr']['nr=2'] = {'N_THETA': [32]}
        settings['convergence_flags_by_nr']['nr=2'] = {'N_THETA': True}
        groups = copy.deepcopy(GROUPS)
        groups['N_THETA']['values'] = [32, 48]
        ui = UI()
        app = cases.CaseSelection(root, ui)
        app._convergence_entries(settings, lambda *k: str(k), {}, ['nr=1', 'nr=2'],
                                 {'nr=1': ('one', ''), 'nr=2': ('unavailable', '')},
                                 groups_by_nr={'nr=1': groups, 'nr=2': {}})
        self.assertEqual(state.convergence_selection(settings, 'nr=1')['N_THETA'], [32])
        self.assertEqual(state.convergence_selection(settings, 'nr=2'), {})
        self.assertFalse(any('unavailable' in str(args) or '此案例没有' in str(args) for _, args, _ in ui.events))

    def test_saved_ordinary_flags_follow_names_when_convergence_entries_are_removed(self):
        root, settings = fixture()
        case = indexed_case()
        case['ordinary'] = {'1': {}, '2': {}}
        root['CGYRO_scan']['RUN_DB']['Jet_convergence']['nr=1'] = case
        settings.update(cgyro_view='常规扫描', selected_paras={'ordinary': [1], 'N_ENERGY': [48]},
                        para_list_flag={0: False, 1: True},
                        _selector_keys={'para_list_flag': ['N_ENERGY', 'ordinary']})
        self.assertEqual(selection._sanitize_selected_parameters(root, settings), ({'ordinary': [1]}, {}))
        settings['para_list_flag'] = {0: True, 1: False}
        self.assertEqual(selection._sanitize_selected_parameters(root, settings), ({}, {}))

    def test_settings_validation_ignores_stale_cartesian_filters(self):
        root, settings = fixture()
        settings.update(selected_paras={'A': [1]}, cgyro_multi={'A': {'values': {'B': 'invalid'}}})
        self.assertEqual(state.selection_check(root)['errors'], [])
        settings['convergence_flags_by_nr']['nr=1'] = {'N_THETA': False, 'N_XI': False}
        self.assertIn('请选择 CGYRO 扫描参数及取值。', state.selection_check(root)['errors'])

    def test_ratio_options_ignore_hidden_ordinary_scan_reference(self):
        root, settings = fixture()
        settings.update(plot_mode='Plot γ/γ_ref', gamma_ref_value='old invalid reference')
        self.assertEqual(state.selection_check(root)['errors'], [])
        ui = UI()
        app = compare_ui.ComparisonUI(root, ui)
        app.ui = ui
        app.mode, app.state, app.plot_settings = 'CGYRO_vs_CGYRO', settings, settings
        with patch.object(app, '_entry') as entry, patch.object(app, '_combo'):
            app._render_ratio()
        self.assertNotIn('gamma_ref_value', [call.args[0] for call in entry.call_args_list])
        self.assertTrue(any('各方向自己的基准' in str(args) for _, args, _ in ui.events))

    def test_context_uses_only_selected_direction_and_no_generic_axis_expansion(self):
        root, settings = fixture()
        settings['convergence_flags_by_nr']['nr=1']['N_XI'] = False
        settings['convergence_selected_by_nr']['nr=1']['N_THETA'] = '[24, 48]'
        reference = object()
        view = {'N_THETA': {32: {'lin': {'.5': reference}}}}
        meta = {'N_THETA': dict(GROUPS['N_THETA'], convergence=True)}
        with patch.object(selection, 'comparison_case_view', side_effect=AssertionError('generic view')), \
                patch.object(selection, '_sanitize_selected_parameters', side_effect=AssertionError('old selectors')), \
                patch.object(selection, 'convergence_case_view', return_value=(view, {'N_THETA': [24, 32, 48]}, meta, [])) as build:
            ctx = selection.build_context(root)
        self.assertEqual(build.call_args.args[1], {'N_THETA': [24., 48.]})
        self.assertIs(ctx['_cgyro_views']['nr=1']['N_THETA'][32]['lin']['.5'], reference)
        self.assertTrue(ctx['convergence_plot'])
        self.assertEqual(list(selection._iter_selected_parameter_items(ctx, 'nr=1')), [('N_THETA', [24., 32., 48.])])

    def test_selection_snapshots_follow_run_switches(self):
        _, settings = fixture()
        state.activate_source(settings, 'Jet_convergence')
        state.activate_source(settings, 'Another')
        self.assertNotIn('convergence_selected_by_nr', settings)
        settings['cgyro_view'] = '常规扫描'
        state.activate_source(settings, 'Jet_convergence')
        self.assertEqual(settings['cgyro_view'], '收敛测试')
        self.assertEqual(list(settings['convergence_selected_by_nr']['nr=1']), list(GROUPS))

    def test_one_case_has_a_top_level_page_for_each_direction(self):
        ctx = dict(convergence_plot=True, plot_3d=False, nr_CGYRO=['nr=1'])
        items = [dict(nr='nr=1', para=key) for key in GROUPS]
        pages = plotting.group_plot_pages(items, ctx)
        self.assertEqual(pages, [('N_THETA', [items[0]]), ('N_XI', [items[1]])])

    def test_distinct_radius_and_time_ky_never_share_one_convergence_page(self):
        ctx = dict(convergence_plot=True, plot_3d=False, plot_time_traces=True, merge_all_nr_plot=True,
                   nr_CGYRO=['nr=1', 'nr=2'])
        items = [dict(nr=nr, para='N_XI', trace={'ky': ky}) for nr, ky in [('nr=1', .5), ('nr=2', .5), ('nr=1', -.5)]]
        pages = plotting.group_plot_pages(items, ctx)
        self.assertEqual(len(pages), 3)
        self.assertTrue(all(label.startswith('N_XI / ') for label, _ in pages))
        self.assertTrue(all(len(values) == 1 for _, values in pages))

    def test_two_runs_with_different_baselines_do_not_mix_same_axis_tokens(self):
        ctx = dict(convergence_plot=True, plot_3d=True, nr_CGYRO=['nr=1'])
        items = [dict(nr='nr=1', para='N_THETA', source_label=run) for run in ['first', 'second']]
        pages = plotting.group_plot_pages(items, ctx)
        self.assertEqual(len(pages), 2)
        self.assertTrue(all(len(values) == 1 for _, values in pages))
        self.assertIn('first', pages[0][0])
        self.assertIn('second', pages[1][0])

    def test_real_index_to_selected_spectra_includes_each_correct_baseline(self):
        root, settings = fixture()
        case = indexed_case()
        for record in case['__SCANS__'].values():
            for row in record['tasks'].values():
                numeric = row['input_parameters']
                node = case
                for key in row['result_path'][:-1]:
                    node = node[key]
                # A deterministic in-memory solver result; the real selection,
                # full-input join and frequency-statistics code run unchanged.
                node[row['result_path'][-1]] = dict(n_time=5, kyrhos=numeric['KY'],
                    freq=dict(omega=[[float(numeric['N_ENERGY'])] * 5], gamma=[[float(numeric['N_XI'])] * 5]))
        cid = 'nr=1__rho=0.33__ion=T'
        tokens = {group['axis']: key for key, group in convergence_groups(case).items()}
        root['CGYRO_scan']['RUN_DB']['Jet_convergence'] = {cid: case}
        settings.update(nr_CGYRO=[cid], divide_by_ky=False,
            convergence_selected_by_nr={cid: {tokens['N_XI']: [32, 64], tokens['E_MAX']: [10, 12]}},
            convergence_flags_by_nr={cid: {tokens['N_XI']: True, tokens['E_MAX']: True}})
        # Simulate native index persistence: physical data in this fixture is
        # JSON-safe, and no task/ancestry record exists in the reopened tree.
        root = json.loads(json.dumps(root))
        class UnreadOrdinary(dict):
            def __getitem__(self, key):
                raise AssertionError('Convergence plotting opened an ordinary result')
            def get(self, key, default=None):
                raise AssertionError('Convergence plotting opened an ordinary result')
        root['CGYRO_scan']['RUN_DB']['Jet_convergence'][cid]['ordinary'] = {
            '1': {'lin': {'.5': UnreadOrdinary()}}}
        root['SETTINGS']['PHYSICS']['CGYRO_vs_CGYRO']['selected_paras'] = {'ordinary': [1]}
        ctx = selection.build_context(root)
        items = plotting.collect_plot_items(root, ctx)
        self.assertEqual(ctx['selected_paras'], {})
        self.assertEqual(ctx['_diagnostics'], [])
        self.assertEqual(len(items), 6)
        baseline = {item['slice_meta']['axis']: item for item in items if item['value'] == item['slice_meta']['baseline_value']}
        self.assertEqual(set(baseline), {'N_XI', 'E_MAX'})
        self.assertEqual(list(baseline['N_XI']['series'][1]), [32., 32.])
        self.assertEqual(list(baseline['E_MAX']['series'][1]), [64., 64.])
        self.assertEqual(list(baseline['N_XI']['series'][0]), [-.5, .5])


if __name__ == '__main__':
    unittest.main()
