"""Agg regressions for convergence panels, using prepared numeric data only.

The shared native-reader stand-ins satisfy imports; no native reader or result
file is used by these tests. They do not claim to exercise a live OMFIT window.
"""
import copy
from pathlib import Path
import sys
import unittest
import warnings
from unittest.mock import patch

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backend_bases import MouseEvent
from matplotlib.colors import to_rgba
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_cgyro_storage  # Explicit isolated-process native import boundary.
import OMFITlib_compare_cgyro_render as render


class Notebook:
    def __init__(self):
        self.figures = []

    def subplots(self, *args, **kwargs):
        label = kwargs.pop('label')
        figure, axes = plt.subplots(*args, **kwargs)
        figure.set_label(label)
        self.figures.append(figure)
        return figure, axes


def context(**changes):
    result = dict(plot_mode='Plot 2D', plot_gamma_ratio=False, error_flag='none',
                  divide_by_ky=False, divide_by_ky2=False, highlight_max_gamma=False,
                  selected_single_ky=[.1], eigen_abs=True, ave_window=.1,
                  lw=1.8, ms=5, fs1=10, fs2=8, bwith=1,
                  style=dict(font_size=10, legend_font_size=8),
                  legend_order_mode='Plot order', legend_order_text='')
    result.update(changes)
    return result


def spectra(axis='N_ENERGY', values=(16., 32., 48.), baseline=32., token=None, offset=0.):
    ky = np.array([-.1, .1, .3])
    items = []
    for value in values:
        omega = ky * value + offset
        gamma = ky ** 2 * value + offset
        items.append(dict(nr='nr=1__rho=0.33__ion=T', para=token or '@' + axis, value=value,
                          slice_meta=dict(convergence=True, axis=axis, baseline_value=baseline,
                                          label=axis, fixed={'N_RADIAL': 32.}),
                          series=(ky, omega, gamma, np.full(3, .01), np.full(3, .02),
                                  np.zeros(3), np.zeros(3))))
    return items


def cloud(axis='N_ENERGY', baseline=32., values=(16., 32., 48.), token=None):
    source = spectra(axis, values=values, baseline=baseline, token=token)
    points = np.concatenate([np.column_stack((item['series'][0],
                                             np.full(3, item['value']),
                                             item['series'][1], item['series'][2])) for item in source])
    result = {key: value for key, value in source[0].items() if key not in ('value', 'series')}
    result.update(cloud=tuple(points[:, column] for column in range(4)),
                  axis_name=axis, scan_values=list(values))
    return result


class ConvergenceRenderTests(unittest.TestCase):
    def setUp(self):
        self.notebook = Notebook()

    def tearDown(self):
        plt.close('all')

    def draw(self, items, **options):
        return render.render_convergence_page(self.notebook, context(**options), '收敛测试', items)

    def test_each_direction_has_omega_gamma_column_and_own_baseline(self):
        items = spectra() + spectra('N_XI', baseline=48.) + spectra('N_THETA')
        figure = self.draw(items)
        self.assertEqual(len(self.notebook.figures), 1)
        self.assertEqual(figure.get_label(), '收敛测试')
        self.assertEqual(len(figure.axes), 6)
        for column, name in enumerate(('N_ENERGY', 'N_XI', 'N_THETA')):
            upper, lower = figure.axes[column], figure.axes[column + 3]
            self.assertIn(name, upper.get_title())
            self.assertEqual(len(upper.lines), 3)
            self.assertEqual(len(lower.lines), 3)
            for axis in (upper, lower):
                baseline = [line for line in axis.lines if '基准' in line.get_label()]
                self.assertEqual(len(baseline), 1)
                self.assertEqual(to_rgba(baseline[0].get_color()), to_rgba('black'))
                self.assertEqual(baseline[0].get_linestyle(), '--')
        self.assertIn('10%', figure._suptitle.get_text())

    def test_same_axis_different_fixed_group_keeps_distinct_panels_and_picking(self):
        first = spectra(token='@energy-e8')
        second = spectra(token='@energy-e10', offset=10.)
        second[0]['slice_meta']['label'] = 'N_ENERGY · E_MAX=10'
        figure = self.draw(first + second)
        self.assertEqual(len(figure.axes), 4)
        self.assertIn('E_MAX=10', figure.axes[1].get_title())
        np.testing.assert_allclose(figure.axes[0].lines[0].get_ydata(), first[0]['series'][1])
        np.testing.assert_allclose(figure.axes[1].lines[0].get_ydata(), second[0]['series'][1])
        self.assertNotEqual(figure.axes[0].lines[1]._comparison_identity,
                            figure.axes[1].lines[1]._comparison_identity)
        self.assertEqual(figure.axes[0].lines[1]._comparison_identity,
                         figure.axes[2].lines[1]._comparison_identity)

    def test_absent_baseline_is_not_replaced_or_labelled_as_another_curve(self):
        figure = self.draw(spectra(values=(16., 48.)))
        self.assertIn('结果缺失', figure.axes[0].get_title())
        for axis in figure.axes:
            self.assertFalse(any('基准' in line.get_label() for line in axis.lines))
            self.assertEqual(len(axis.lines), 2)

    def test_relative_fluctuations_are_rows_in_the_same_direction_column(self):
        figure = self.draw(spectra() + spectra('N_XI'), error_flag='CGYRO')
        self.assertEqual(len(figure.axes), 8)
        np.testing.assert_allclose(figure.axes[4].lines[0].get_ydata(), .01)
        np.testing.assert_allclose(figure.axes[6].lines[0].get_ydata(), .02)
        self.assertIn('omega', figure.axes[4].get_title())
        self.assertIn('gamma', figure.axes[6].get_title())

    def test_signed_ky_scaling_preserves_original_arrays(self):
        items = spectra(values=(32.,))
        saved = copy.deepcopy(items)
        figure = self.draw(items, divide_by_ky=True)
        np.testing.assert_allclose(figure.axes[0].lines[0].get_xdata(), [-.1, .1, .3])
        np.testing.assert_allclose(figure.axes[0].lines[0].get_ydata(), [32., 32., 32.])
        for old, new in zip(saved[0]['series'], items[0]['series']):
            np.testing.assert_array_equal(old, new)

    def test_single_ky_baseline_guide_uses_available_point_only(self):
        figure = self.draw([cloud(), cloud('N_XI', values=(16., 48.))], plot_mode='Plot single ky')
        self.assertEqual(len(figure.axes), 4)
        for index in (0, 2):
            baseline = [line for line in figure.axes[index].lines if '基准' in line.get_label()]
            self.assertEqual(len(baseline), 1)
            np.testing.assert_array_equal(baseline[0].get_xdata(), [32., 32.])
        self.assertIn('结果缺失', figure.axes[1].get_title())
        self.assertFalse(any('基准' in line.get_label() for line in figure.axes[1].lines))

    def test_time_histories_use_all_direction_columns_without_averaging_caption(self):
        items = spectra(values=(32.,)) + spectra('N_XI', values=(32.,))
        for item in items:
            item.pop('series')
            item['trace'] = dict(ky=.2, time=np.array([0., 1., 2.]), omega=np.array([1., 2., 3.]),
                                 gamma=np.array([.1, .2, .3]))
        figure = self.draw(items, plot_mode='Plot time traces')
        self.assertEqual(len(figure.axes), 4)
        self.assertNotIn('统计窗口', figure._suptitle.get_text())
        for axis in figure.axes:
            self.assertIn('ky=0.2', axis.lines[0].get_label())
            self.assertEqual(axis.lines[0].get_color(), 'black')

    def test_eigenmode_fields_share_direction_columns(self):
        items = spectra(values=(32.,)) + spectra('N_XI', values=(32.,))
        for item in items:
            item.pop('series')
            item['ky'] = .2
            item['eigen'] = dict(theta_over_pi=np.array([-1., 0., 1.]),
                                 phi_b=np.array([.1, 1., .1], dtype=complex),
                                 epar_b=np.array([.2, 1., .2], dtype=complex), has_epar=True,
                                 has_apar=False, has_bpar=False)
        figure = self.draw(items, plot_mode='Plot eigen ball')
        self.assertEqual(len(figure.axes), 8)
        self.assertEqual(len(figure.axes[0].lines), 1)
        self.assertEqual(len(figure.axes[2].lines), 1)
        self.assertEqual(len(figure.axes[4].lines), 0)
        self.assertIn('No valid saved', figure.axes[4].texts[0].get_text())
        self.assertEqual(figure.axes[0].lines[0].get_color(), 'black')

    def test_ratio_page_marks_only_actual_baseline_coordinates(self):
        items = [cloud(), cloud('N_XI')]
        for item in items:
            item.pop('cloud')
            item['ratio'] = np.array([16., 32., 48.]), np.array([.9, 1., 1.01]), 32.
        figure = self.draw(items, plot_gamma_ratio=True)
        self.assertEqual(len(figure.axes), 2)
        self.assertTrue(all(any('基准' in line.get_label() for line in axis.lines) for axis in figure.axes))
        self.assertNotEqual(figure.axes[0].lines[-1]._comparison_identity,
                            figure.axes[1].lines[-1]._comparison_identity)

    def test_surface_page_has_every_scan_and_actual_baseline_curve(self):
        figure = self.draw([cloud(), cloud('N_XI')], plot_mode='Plot 3D')
        panels = [axis for axis in figure.axes if axis.name == '3d']
        self.assertEqual(len(panels), 4)
        self.assertIn('N_ENERGY', panels[0].get_title())
        self.assertIn('N_XI', panels[1].get_title())
        for panel in panels:
            baseline, = [line for line in panel.lines if '基准' in line.get_label()]
            self.assertEqual(baseline.get_color(), 'black')
            self.assertEqual(baseline.get_linestyle(), '--')

    def test_legend_click_does_not_hide_other_direction_baseline(self):
        figure = self.draw(spectra(token='@a') + spectra(token='@b', offset=2.))
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            figure.canvas.draw()
        axis = figure.axes[0]
        label = next(text for text in axis.get_legend().get_texts() if '基准' in text.get_text())
        extent = label.get_window_extent(figure.canvas.get_renderer())
        event = MouseEvent('button_press_event', figure.canvas,
                           (extent.x0 + extent.x1) / 2, (extent.y0 + extent.y1) / 2, button=1)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            figure.canvas.callbacks.process('button_press_event', event)
        self.assertFalse(figure.axes[0].lines[1].get_visible())
        self.assertFalse(figure.axes[2].lines[1].get_visible())
        self.assertTrue(figure.axes[1].lines[1].get_visible())
        self.assertTrue(figure.axes[3].lines[1].get_visible())

    def test_prepared_series_render_does_not_read_results(self):
        with patch('OMFITlib_compare_cgyro_data.collect_value_series', side_effect=AssertionError('result read')), \
                patch('OMFITlib_compare_cgyro_data.frequency_stats', side_effect=AssertionError('result read')):
            figure = self.draw(spectra())
        self.assertEqual(len(figure.axes), 2)

    def test_empty_selection_does_not_open_an_empty_case(self):
        self.assertIsNone(self.draw([]))
        self.assertEqual(self.notebook.figures, [])

    def test_explicit_figure_dimensions_remain_honored(self):
        figure = self.draw(spectra(), style=dict(figure_width=8., figure_height=7.))
        np.testing.assert_allclose(figure.get_size_inches(), [8., 7.])


if __name__ == '__main__':
    unittest.main()
