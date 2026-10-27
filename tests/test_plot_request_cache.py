"""Plot-local reuse must never alias owners, windows or a later plot request."""
import copy
import importlib
import unittest
from unittest.mock import patch

import numpy as np
import test_cgyro_storage  # Explicit native-reader stand-ins, as in read-boundary tests.
from test_compare import fixture, modules

core, series = modules['core'], modules['series']
sources = importlib.import_module('OMFITlib_plot_sources')


class CountedResult(dict):
    def __init__(self, values):
        super().__init__(values)
        self.reads = 0

    def __getitem__(self, key):
        if key == 'freq':
            self.reads += 1
        return super().__getitem__(key)


class OMFITobject:
    """Native file marker: result_view keeps the physical reader opaque."""


class NativeResult(CountedResult, OMFITobject):
    pass


def result(gamma):
    return CountedResult(dict(n_time=len(gamma), freq={'omega': [np.ones(len(gamma))], 'gamma': [gamma]}))


class PlotRequestCacheTests(unittest.TestCase):
    def test_repeated_comparison_pages_average_each_selected_owner_once(self):
        root = fixture()
        linear = root['CGYRO_scan']['RUN_DB']['run']['nr=2']['A'][1.]['lin']
        for key, value in list(linear.items()):
            linear[key] = NativeResult(value)
        ctx = core.build_context(root)
        expected = series.collect_cgyro_series(root, ctx, 'run', 'nr=2', 'A', 1.)
        self.assertEqual(len(expected[0]), 4)
        again = series.collect_cgyro_series(root, ctx, 'run', 'nr=2', 'A', 1.)
        np.testing.assert_equal(expected, again)
        self.assertEqual([item.reads for item in linear.values()], [2] * 4)
        self.assertEqual(len(ctx['_cgyro_frequency_stats']), 4)
        self.assertNotIn('_cgyro_frequency_stats', root)

    def test_window_and_new_request_do_not_reuse_stale_statistics(self):
        data, cache = result([1., 1., 3., 3.]), {}
        self.assertEqual(core.cgyro_frequency_stats(data, .5, cache)[1][0], 3.)
        self.assertEqual(core.cgyro_frequency_stats(data, 1., cache)[1][0], 2.)
        data['freq']['gamma'][0] = [7.] * 4
        self.assertEqual(core.cgyro_frequency_stats(data, .5, {})[1][0], 7.)
        self.assertEqual(len(cache), 2)

    def test_owner_identity_not_point_number_and_fresh_packed_views_share_stats(self):
        cache, first_module, second_module = {}, {}, {}
        first = result([1., 1.])
        first._payload_module, first._payload_key = first_module, 'a' * 64
        same = result([1., 1.])
        same._payload_module, same._payload_key = first_module, 'a' * 64
        other = result([2., 2.])
        other._payload_module, other._payload_key = first_module, 'b' * 64
        foreign = result([3., 3.])
        foreign._payload_module, foreign._payload_key = second_module, 'a' * 64
        for item in (first, same, other, foreign):
            item['task_id'] = 'p000001'
        self.assertEqual([core.cgyro_frequency_stats(item, 1., cache)[1][0]
                          for item in (first, same, other, foreign)], [1., 1., 2., 3.])
        self.assertEqual([item.reads for item in (first, same, other, foreign)], [2, 0, 2, 2])

    def test_invalid_statistics_are_still_rejected_and_not_cached(self):
        cache, data = {}, result([1., np.nan])
        with self.assertRaisesRegex(ValueError, 'non-finite'):
            core.cgyro_frequency_stats(data, 1., cache)
        self.assertFalse(cache)
        data['freq']['gamma'][0] = [2., 2.]
        self.assertEqual(core.cgyro_frequency_stats(data, 1., cache)[1][0], 2.)

    def test_tglf_modes_decode_selected_spectrum_once_per_request(self):
        spectrum = dict(ky=np.array([-.2, .4]), freq=np.array([[1., 2.], [3., 4.]]),
                        gamma=np.array([[5., 6.], [7., 8.]]))
        class Unselected(dict):
            def __getitem__(self, key):
                raise AssertionError('Unselected TGLF payload opened')
        points = {'p000001': dict(status='complete', source=['input'], parameters={'A': 1.},
                                 result={'eigenvalue_spectrum': spectrum}),
                  'p000002': dict(status='complete', source=['input'], parameters={'A': 2.},
                                 result=Unselected(eigenvalue_spectrum={}))}
        root = {'TGLF_scan': {'RUN_DB': {'selected': dict(mode='1d', points=points, plan={
            'axes': [{'name': 'A'}], 'sources': [{'path': ['input'], 'rho': .3}]})}}}
        state = {'result_source': 'selected', 'spectra_mode': '1D'}
        ctx = {'tglf_state': state}
        with patch.object(sources, 'spectrum_arrays', wraps=sources.spectrum_arrays) as decode:
            for mode in (1, 2, 1):
                ky, omega, gamma = series.collect_tglf_series(root, ctx, .3, 'A', 1., mode)
                np.testing.assert_array_equal(ky, [-.2, .4])
                np.testing.assert_array_equal(gamma, spectrum['gamma'][mode - 1])
            self.assertEqual(decode.call_count, 1)
            # A later plot creates a new view, even if its selection is identical.
            points['p000001']['result']['eigenvalue_spectrum'] = copy.deepcopy(spectrum)
            points['p000001']['result']['eigenvalue_spectrum']['gamma'][0] = [9., 10.]
            fresh = {'tglf_state': state}
            np.testing.assert_array_equal(series.collect_tglf_series(root, fresh, .3, 'A', 1.)[2], [9., 10.])
            self.assertEqual(decode.call_count, 2)


if __name__ == '__main__':
    unittest.main()
