"""CGYRO regression cases using analytic spectra and real Matplotlib figures."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import warnings

import numpy as np
import matplotlib.pyplot as plt
from test_compare import fixture, Notebook, modules, FakeUI

controller = modules['cgyro']
data = modules['cgyro_data']
selection = modules['cgyro_selection']
eigen = modules['cgyro_eigen']
render = modules['cgyro_render']


def balloon_fields():
    theta = np.array([-1., 0., 1.])
    return {'theta_b_over_pi': theta, 'balloon_phi': np.array([1.+2j, 3.+1j, 1.-2j]),
            'balloon_apar': np.full(3, .3+.1j), 'balloon_epar': np.full(3, 7.+2j)}


class CGYROTest(unittest.TestCase):
    def setUp(self):
        self.root = fixture('CGYRO_vs_CGYRO')
        self.settings = self.root['SETTINGS']['PHYSICS']['CGYRO_vs_CGYRO']
        self.run = self.root['CGYRO_scan']['RUN_DB']['run']
        self.linear = self.run['nr=2']['A'][1.]['lin']
        Notebook.figures = []
        controller.FigureNotebook = Notebook

    def tearDown(self):
        plt.close('all')

    def context(self, **settings):
        self.settings.update(settings)
        return selection.build_context(self.root)

    def plot(self, **settings):
        self.settings.update(settings)
        figures = controller.run_plot(self.root)
        for figure in figures:
            figure.canvas.draw()
        return figures

    def add_balloon(self):
        for radius in self.run.values():
            for values in radius['A'].values():
                for point in values['lin'].values():
                    point['balloon'] = balloon_fields()

    def test_tail_means_std_and_main_ion_scaling(self):
        point = copy.deepcopy(self.linear['0.1'])
        point.update(n_time=4, freq={'omega': [[9., 9., 1., 3.]], 'gamma': [[8., 8., -4., -2.]]})
        point['input.cgyro.gen'].update(MASS_1=4., Z_1=2.)
        self.run['nr=2']['A'][1.]['lin'] = {'one': point}
        result = data.collect_value_series(self.root, self.context(ave_window=.5, normalize_main_ion=True), 'nr=2', 'A', 1.)
        np.testing.assert_allclose(np.asarray(result).ravel(), [.1, 4., -6., .5, 1/3, 2., 2.])

    def test_self_and_cross_model_readers_agree_on_raw_spectra(self):
        context = self.context(normalize_main_ion=True)
        own = data.collect_value_series(self.root, context, 'nr=2', 'A', 1.)
        cross = modules['series'].collect_cgyro_series(self.root, context, 'run', 'nr=2', 'A', 1.)
        np.testing.assert_allclose(own[:5], cross)
        self.assertTrue(np.any(own[2] < 0))

    def test_mismatched_time_count_is_reported_and_skipped(self):
        self.linear['0.1']['n_time'] = 30
        context = self.context()
        result = data.collect_value_series(self.root, context, 'nr=2', 'A', 1.)
        np.testing.assert_allclose(result[0], [.2, .4, .8])
        self.assertIn('disagree with n_time', '\n'.join(context['_diagnostics']))

    def test_nonfinite_tail_is_not_silently_replaced(self):
        self.linear['0.2']['freq']['gamma'][0][-1] = np.nan
        context = self.context()
        result = data.collect_value_series(self.root, context, 'nr=2', 'A', 1.)
        self.assertEqual(len(result[0]), 3)
        self.assertIn('non-finite', '\n'.join(context['_diagnostics']))

    def test_filter_rejects_unstable_omega_even_when_gamma_is_constant(self):
        self.linear['0.1']['freq']['omega'][0][-2:] = [1., -1.]
        context = self.context(ave_window=.1, error_filter=True)
        result = data.collect_value_series(self.root, context, 'nr=2', 'A', 1.)
        self.assertNotIn(.1, result[0])
        self.assertIn('fluctuation filter', '\n'.join(context['_diagnostics']))

    def test_ambiguous_numeric_scan_key_is_rejected(self):
        original = self.run['nr=2']['A'].pop(1.)
        self.run['nr=2']['A'].update({'1.00': original, '1.000': copy.deepcopy(original)})
        with self.assertRaisesRegex(ValueError, 'Ambiguous'):
            self.plot()
        self.assertEqual(Notebook.figures, [])

    def test_ky_input_accepts_numbers_lists_and_arrays(self):
        for value in ('0.1, 0.2', '[0.1, 0.2]', [.1, .2], np.array([.1, .2])):
            self.assertEqual(selection.parse_float_list_text(value), [.1, .2])
        self.assertEqual(selection.parse_float_list_text(.1), [.1])
        self.assertEqual(selection.parse_float_list_text(''), [])

    def test_invalid_active_ky_fails_before_figure_creation(self):
        for value in ('0.1, nope', 'nan', 'inf'):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'ky values'):
                self.plot(plot_mode='Plot single ky', single_ky_values=value)
        self.assertEqual(Notebook.figures, [])

    def test_inactive_ky_control_does_not_block_regular_spectra(self):
        self.assertEqual(len(self.plot(single_ky_values='bad old value', eigen_ky_values='bad')), 1)

    def test_direct_plot_checks_cgyro_even_when_other_workflow_is_selected(self):
        self.root['SETTINGS']['PHYSICS']['compare_mode'] = 'TGLF_vs_TGLF'
        self.root['TGLF_scan'].clear()
        self.assertEqual(len(self.plot()), 1)

    def test_unchecked_parameters_do_not_create_empty_notebook(self):
        with self.assertRaisesRegex(ValueError, 'remains selected'):
            self.plot(para_list_flag={0: False})
        self.assertEqual(Notebook.figures, [])

    def test_per_radius_selection_does_not_fall_back_to_another_radius(self):
        context = self.context(force_read_all_nr_items=True, nr_CGYRO=['nr=2', 'nr=10'],
                               selected_paras_by_nr={'nr=2': {'A': [1.]}})
        self.assertEqual(list(selection._iter_selected_parameter_items(context, 'nr=10')), [])
        self.assertEqual(len(self.plot()), 1)

    def test_blank_ratio_reference_uses_first_valid_selected_value(self):
        for scale, squared in ((False, False), (True, False), (False, True)):
            context = self.context(plot_mode='Plot γ/γ_ref', gamma_ref_value='',
                                   divide_by_ky=scale, divide_by_ky2=squared)
            x, ratio, reference = data.get_gamma_ratio_curve(self.root, context, 'nr=2', 'A', [2., 1.])
            np.testing.assert_allclose(x, [1., 2.])
            np.testing.assert_allclose(ratio, [.55/1.35, 1.])
            self.assertEqual(reference, 2.)
        self.assertEqual(len(self.plot()), 1)

    def test_ratio_zero_reference_reports_undefined_result(self):
        for point in self.linear.values():
            point['freq']['gamma'][0][:] = 0.
        with self.assertRaisesRegex(ValueError, 'Reference gamma is zero'):
            self.plot(plot_mode='Plot γ/γ_ref', gamma_ref_value=1.)
        self.assertEqual(Notebook.figures, [])

    def test_ratio_nearest_ky_repeats_are_not_counted_twice(self):
        context = self.context(plot_mode='Plot γ/γ_ref', gamma_ref_mode='single ky',
                               gamma_ref_ky_values='.11, .12, .2')
        _, ratio, _ = data.get_gamma_ratio_curve(self.root, context, 'nr=2', 'A', [1., 2.])
        np.testing.assert_allclose(ratio, [1., -.5], atol=1e-12)

    def test_single_ky_gaps_are_preserved(self):
        self.run['nr=2']['A'][2.]['lin'].pop('0.2')
        figure = self.plot(plot_mode='Plot single ky', single_ky_values='.2')[0]
        np.testing.assert_allclose(figure.axes[0].lines[0].get_xdata(), [1., 2.])
        self.assertTrue(np.isnan(figure.axes[0].lines[0].get_ydata()[1]))

    def test_grid_duplicate_average_and_missing_cells(self):
        x, y, omega, gamma = data.grid_scan_points(
            np.array([.1, .1, .2]), np.array([1., 1., 2.]), np.array([2., 4., 9.]), np.array([-2., 0., 3.]))
        np.testing.assert_allclose(omega, [[3., np.nan], [np.nan, 9.]], equal_nan=True)
        np.testing.assert_allclose(gamma, [[-1., np.nan], [np.nan, 3.]], equal_nan=True)

    def test_3d_pages_belong_to_notebook_and_do_not_accumulate_axes(self):
        first = self.plot(plot_mode='Plot 3D')[0]
        second = self.plot()[0]
        self.assertIsNot(first, second)
        self.assertIn(first, Notebook.figures)
        self.assertEqual(len(first.axes), 4)
        self.assertEqual(len(second.axes), 4)
        self.assertLess(first.axes[0].get_position().x1, first.axes[1].get_position().x0)

    def test_3d_one_point_and_sparse_scans_still_show_actual_points(self):
        point = self.linear['0.1']
        self.run['nr=2']['A'][1.]['lin'] = {'0.1': point}
        figure = self.plot(plot_mode='Plot 3D', selected_paras={'A': [1.]})[0]
        self.assertEqual(len(figure.axes[0].collections[0]._offsets3d[0]), 1)
        figure = self.plot(selected_paras={'A': [1., 2.]})[0]
        self.assertEqual(len(figure.axes[0].collections[0]._offsets3d[0]), 5)

    def test_spectra_only_uses_two_axes(self):
        self.assertEqual(len(self.plot(error_flag='No_error')[0].axes), 2)

    def test_legends_are_finalized_once_per_populated_axis(self):
        with patch.object(render, 'finalize_axis_legend', wraps=render.finalize_axis_legend) as finalizer:
            self.plot(nr_CGYRO=['nr=2', 'nr=10'], merge_all_nr_plot=True)
        self.assertEqual(finalizer.call_count, 4)

    def test_dense_legends_do_not_collapse_the_figure_layout(self):
        template = self.run['nr=2']['A'][1.]
        self.run['nr=2']['A'] = {float(index): copy.deepcopy(template) for index in range(1, 25)}
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter('always')
            figure = self.plot(selected_paras={'A': list(self.run['nr=2']['A'])})[0]
        self.assertFalse(any('collapsed' in str(item.message) for item in captured))
        for axis in figure.axes:
            self.assertEqual(len(axis.get_legend().get_texts()), 24)
            self.assertGreater(axis.get_position().width, .2)

    def test_raw_export_ignores_inactive_eigen_selection_and_restores_flag(self):
        self.settings.update(plot_mode='Plot eigen ball', eigen_ky_mode='single ky', eigen_ky_values='')
        app = modules['ui'].ComparisonUI(self.root, FakeUI(self.root))
        app.render()
        app._select_export_directory = lambda *args: None
        app._export()
        self.assertFalse(self.settings['linear_export_now'])

    def test_grid_and_log_preferences_apply_to_scan_and_ratio_views(self):
        for mode in ('Plot single ky', 'Plot γ/γ_ref'):
            with self.subTest(mode=mode):
                self.settings['style']['show_grid'] = False
                figure = self.plot(plot_mode=mode, plot_log_x=True, plot_log_y=True)[0]
                for axis in figure.axes:
                    self.assertEqual(axis.get_xscale(), 'log')
                    self.assertEqual(axis.get_yscale(), 'log')
                    self.assertFalse(any(line.get_visible() for line in axis.get_xgridlines()))

    def test_peak_marker_uses_raw_gamma_and_ignores_undefined_ky_scaling(self):
        point = copy.deepcopy(self.linear['0.1'])
        linear = {}
        for ky, gamma in ((0., 100.), (.1, 2.), (1., 3.)):
            entry = copy.deepcopy(point)
            entry.update(kyrhos=ky)
            entry['freq']['gamma'][0][:] = gamma
            linear[str(ky)] = entry
        self.run['nr=2']['A'][1.]['lin'] = linear
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            figure = self.plot(selected_paras={'A': [1.]}, divide_by_ky=True, highlight_max_gamma=True)[0]
        marker = figure.axes[2].lines[1]
        np.testing.assert_allclose(marker.get_xdata(), [1.])
        np.testing.assert_allclose(marker.get_ydata(), [3.])

    def test_eigen_saved_epar_is_not_modified_by_apar(self):
        point = copy.deepcopy(self.linear['0.1'])
        point['balloon'] = balloon_fields()
        curve = eigen.extract_eigen_curve(point)
        np.testing.assert_allclose(curve['epar_b'], np.full(3, 7.+2j))
        self.assertTrue(curve['has_epar'])

    def test_eigen_missing_epar_is_labelled_and_not_synthesized(self):
        self.add_balloon()
        for values in self.run['nr=2']['A'].values():
            for point in values['lin'].values():
                point['balloon'].pop('balloon_epar')
        figure = self.plot(plot_mode='Plot eigen ball')[0]
        self.assertEqual(len(figure.axes[1].lines), 0)
        self.assertIn('No valid saved', figure.axes[1].texts[0].get_text())
        self.assertEqual(len(figure.axes[0].lines), 4)

    def test_eigen_re_im_case_colors_match_across_fields_and_radii(self):
        self.add_balloon()
        figure = self.plot(plot_mode='Plot eigen ball', nr_CGYRO=['nr=2', 'nr=10'], merge_all_nr_plot=True)[0]
        colors = {}
        for axis in figure.axes:
            for line in axis.lines:
                label = line.get_label().rsplit(', ', 1)[0]
                self.assertEqual(colors.setdefault(label, line.get_color()), line.get_color())
        self.assertEqual(len(colors), 4)

    def test_eigen_loads_balloon_only_for_selected_ky(self):
        self.add_balloon()
        reads = []
        class CountedPoint(dict):
            def __getitem__(self, key):
                if key == 'balloon':
                    reads.append(self['kyrhos'])
                return super().__getitem__(key)
        for key, point in list(self.linear.items()):
            self.linear[key] = CountedPoint(point)
        self.plot(plot_mode='Plot eigen ball', selected_paras={'A': [1.]})
        self.assertEqual(reads, [.8])

    def test_eigen_nonfinite_or_misaligned_phi_does_not_make_empty_figure(self):
        self.add_balloon()
        self.linear['0.8']['balloon']['balloon_phi'] = np.array([1., np.nan, 3.])
        with self.assertRaisesRegex(ValueError, 'invalid saved balloon'):
            self.plot(plot_mode='Plot eigen ball', selected_paras={'A': [1.]})
        self.assertEqual(Notebook.figures, [])

    def test_export_retains_signed_data_and_keeps_earlier_export(self):
        with tempfile.TemporaryDirectory() as temporary:
            self.settings.update(linear_export_now=True, linear_export_dir=temporary, divide_by_ky=True)
            first = Path(controller.run_plot(self.root))
            metadata = json.loads((first / 'metadata.json').read_text(encoding='utf-8'))
            first_file = first / metadata['spectra'][0]['file']
            before = first_file.read_bytes()
            values = np.loadtxt(first_file)
            np.testing.assert_allclose(values[:, 2], [-.15, -.05, .15, .55])
            second = Path(controller.run_plot(self.root))
            self.assertNotEqual(first, second)
            self.assertEqual(first_file.read_bytes(), before)
            self.assertEqual(len(metadata['spectra']), 2)
            self.assertEqual(Notebook.figures, [])

    def test_duplicate_selected_values_do_not_overwrite_export_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            self.settings.update(linear_export_now=True, linear_export_dir=temporary, selected_paras={'A': [1., 1., '1']})
            path = Path(controller.run_plot(self.root))
            self.assertEqual(len(json.loads((path/'metadata.json').read_text())['spectra']), 1)

    def test_export_with_no_valid_data_does_not_create_empty_output_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            self.settings.update(linear_export_now=True, linear_export_dir=temporary, selected_paras={'A': [404.]})
            with self.assertRaisesRegex(ValueError, 'No valid selected CGYRO spectra'):
                controller.run_plot(self.root)
            self.assertEqual(list(Path(temporary).iterdir()), [])

    def test_plot_panel_shows_self_specific_controls_in_relevant_modes(self):
        ui = FakeUI(self.root)
        modules['ui'].ComparisonUI(self.root, ui).render()
        self.assertTrue(any(name == 'ComboBox' and args[0].endswith("['error_flag']") for _, name, args, _ in ui.events))
        self.settings['plot_mode'] = 'Plot 3D'
        ui = FakeUI(self.root)
        modules['ui'].ComparisonUI(self.root, ui).render()
        self.assertFalse(any(name == 'CheckBox' and args[0].endswith("['merge_all_nr_plot']") for _, name, args, _ in ui.events))


if __name__ == '__main__':
    unittest.main()
