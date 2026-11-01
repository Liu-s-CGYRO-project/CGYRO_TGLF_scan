"""Selection/plot boundaries for the dedicated one-factor convergence case."""
import copy
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

    def __getattr__(self, method):
        def record(*args, **kwargs):
            self.events.append((method, args, kwargs))
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
    def test_selector_has_one_case_and_independent_directions_without_cartesian_controls(self):
        root, settings = fixture()
        ui = UI()
        app = cases.CaseSelection(root, ui)
        with patch.object(app, '_choose_cgyro', return_value=({'nr=1': {}}, ['nr=1'])), \
                patch.object(cases, 'convergence_groups', return_value=copy.deepcopy(GROUPS)), \
                patch.object(app, '_multi_axis_entries', side_effect=AssertionError('Cartesian UI used')):
            app.render_mode_cgyro_vs_cgyro(settings)
        self.assertEqual(settings['cgyro_view'], '收敛测试')
        self.assertEqual([args[0] for kind, args, _ in ui.events if kind == 'Separator'], ['收敛测试'])
        self.assertEqual(len([1 for kind, args, _ in ui.events if kind == 'Entry']), 2)
        self.assertFalse(any(' × ' in str(args) for _, args, _ in ui.events))

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

    def test_one_case_groups_every_direction_into_one_convergence_page(self):
        ctx = dict(convergence_plot=True, plot_3d=False, nr_CGYRO=['nr=1'])
        items = [dict(nr='nr=1', para=key) for key in GROUPS]
        pages = plotting.group_plot_pages(items, ctx)
        self.assertEqual(pages, [('收敛测试', items)])

    def test_distinct_radius_and_time_ky_never_share_one_convergence_page(self):
        ctx = dict(convergence_plot=True, plot_3d=False, plot_time_traces=True, merge_all_nr_plot=True,
                   nr_CGYRO=['nr=1', 'nr=2'])
        items = [dict(nr=nr, para='N_XI', trace={'ky': ky}) for nr, ky in [('nr=1', .5), ('nr=2', .5), ('nr=1', -.5)]]
        pages = plotting.group_plot_pages(items, ctx)
        self.assertEqual(len(pages), 3)
        self.assertTrue(all(label.startswith('收敛测试 / ') for label, _ in pages))
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
        ctx = selection.build_context(root)
        items = plotting.collect_plot_items(root, ctx)
        self.assertEqual(ctx['_diagnostics'], [])
        self.assertEqual(len(items), 6)
        baseline = {item['slice_meta']['axis']: item for item in items if item['value'] == item['slice_meta']['baseline_value']}
        self.assertEqual(set(baseline), {'N_XI', 'E_MAX'})
        self.assertEqual(list(baseline['N_XI']['series'][1]), [32., 32.])
        self.assertEqual(list(baseline['E_MAX']['series'][1]), [64., 64.])
        self.assertEqual(list(baseline['N_XI']['series'][0]), [-.5, .5])


if __name__ == '__main__':
    unittest.main()
