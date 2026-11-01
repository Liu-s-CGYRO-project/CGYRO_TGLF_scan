"""Each convergence direction uses its own exact saved baseline denominator."""
import unittest
from unittest.mock import patch

import numpy as np
import OMFITlib_compare_cgyro_data as data


def context(axis='E_MAX', baseline=8):
    return dict(runid='Jet_convergence', gamma_ref_value=32,
                _cgyro_slices={('nr=1', axis): dict(convergence=True, axis=axis,
                    baseline_value=baseline, coordinate_names=[axis], coordinates={})})


def series(values):
    def collect(root, ctx, nr, para, value, selected_ky=()):
        gamma = np.asarray(values.get(float(value), []), dtype=float)
        ky = np.asarray([.1, .5, .7][:len(gamma)])
        return ky, np.zeros(len(gamma)), gamma, None, None, None, None
    return collect


class ConvergenceRatioTests(unittest.TestCase):
    def test_each_direction_uses_own_baseline_ignoring_saved_global_reference(self):
        ctx = context()
        with patch.object(data, 'collect_value_series', side_effect=series({8: [2], 10: [4], 12: [6]})):
            x, ratios, reference = data.get_gamma_ratio_curve({}, ctx, 'nr=1', 'E_MAX', [8, 10, 12])
        self.assertEqual(reference, 8)
        np.testing.assert_array_equal(x, [8, 10, 12])
        np.testing.assert_array_equal(ratios, [1, 2, 3])

    def test_missing_baseline_does_not_use_first_or_nearest_scan_value(self):
        ctx = context()
        with patch.object(data, 'collect_value_series', side_effect=series({10: [4], 12: [6]})):
            result = data.get_gamma_ratio_curve({}, ctx, 'nr=1', 'E_MAX', [8, 10, 12])
        self.assertIsNone(result)
        self.assertIn('Convergence baseline is missing', ctx['_diagnostics'][0])

    def test_almost_equal_baseline_coordinate_is_not_substituted(self):
        ctx = context('ERROR_TOL', 1e-4)
        with patch.object(data, 'collect_value_series', side_effect=series({1.0000001e-4: [2], 1e-5: [4]})):
            result = data.get_gamma_ratio_curve({}, ctx, 'nr=1', 'ERROR_TOL', [1.0000001e-4, 1e-5])
        self.assertIsNone(result)

    def test_single_ky_retains_nearest_ky_selection_with_exact_baseline_value(self):
        ctx = dict(context(), gamma_ref_mode='single ky', gamma_ref_ky_values=[.48], abs_ky=False)
        with patch.object(data, 'collect_value_series', side_effect=series({8: [1, 2, 9], 10: [3, 8, 10]})):
            _, ratios, reference = data.get_gamma_ratio_curve({}, ctx, 'nr=1', 'E_MAX', [8, 10])
        self.assertEqual(reference, 8)
        np.testing.assert_array_equal(ratios, [1, 4])

    def test_zero_baseline_remains_undefined(self):
        ctx = context()
        with patch.object(data, 'collect_value_series', side_effect=series({8: [0], 10: [2]})):
            self.assertIsNone(data.get_gamma_ratio_curve({}, ctx, 'nr=1', 'E_MAX', [8, 10]))
        self.assertIn('Reference gamma is zero', ctx['_diagnostics'][0])

    def test_ordinary_scan_keeps_its_selected_nearest_reference(self):
        ctx = dict(gamma_ref_value=11.8)
        with patch.object(data, 'collect_value_series', side_effect=series({8: [2], 10: [4], 12: [6]})):
            _, ratios, reference = data.get_gamma_ratio_curve({}, ctx, 'nr=1', 'E_MAX', [8, 10, 12])
        self.assertEqual(reference, 12)
        np.testing.assert_allclose(ratios, [1 / 3, 2 / 3, 1])


if __name__ == '__main__':
    unittest.main()
