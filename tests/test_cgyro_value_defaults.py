"""Scan mode defaults use the parameter's units and retain manual lists."""
from types import SimpleNamespace
import unittest

from OMFITlib_cgyro_scan_values import parameter_range_defaults, range_values, scan_axes
from OMFITlib_workbench_scan_ui import ScanControls


class ValueDefaultTests(unittest.TestCase):
    def setUp(self):
        self.ui = ScanControls()
        self.ui.actions = SimpleNamespace(factory=dict)
        self.source = dict(N_THETA=32, BETAE_UNIT=.0001, TEMP_1=2.)

    def spec(self, cfg):
        return self.ui.scan_value_spec(cfg.setdefault('value_specs', {}), 'Range', cfg['Range'],
                                       cfg['Para'], self.source)

    def test_nonuniform_grid_list_seeds_integer_range(self):
        spec = parameter_range_defaults('N_THETA', [16., 24., 32., 48.])
        self.assertEqual(spec, dict(start=16, end=48, count=5))
        self.assertEqual(range_values(spec, 'N_THETA'), [16, 24, 32, 40, 48])

    def test_switching_parameter_uses_own_reference_and_same_parameter_keeps_list(self):
        cfg = dict(Para='BETAE_UNIT', Range=[.0001, .0002])
        self.spec(cfg)
        cfg['Para'] = 'N_THETA'
        self.ui.cgyro_axis_parameter_changed(cfg, 'Para', 'Range', self.source)
        self.assertEqual(cfg['Range'], [32])
        self.assertEqual(self.spec(cfg)['start'], 32)
        cfg['Range'] = [16, 24, 32, 48]
        self.ui.cgyro_axis_parameter_changed(cfg, 'Para', 'Range', self.source)
        self.assertEqual(cfg['Range'], [16, 24, 32, 48])

    def test_modes_preserve_manual_list_and_valid_custom_range(self):
        cfg = dict(Para='N_THETA', Range=[16., 24., 32., 48.])
        spec = self.spec(cfg)
        spec.update(start=16, end=64, count=4)
        for mode in ('range', 'original', 'factor', 'list'):
            spec['mode'] = mode
            self.ui.cgyro_axis_mode_changed(cfg, 'Para', 'Range', self.source)
        self.assertEqual(cfg['Range'], [16, 24, 32, 48])
        self.assertTrue(all(isinstance(value, int) for value in cfg['Range']))
        self.assertEqual((spec['start'], spec['end'], spec['count']), (16, 64, 4))

    def test_legacy_fractional_grid_range_is_repaired_on_mode_selection(self):
        cfg = dict(Para='N_THETA', Range=[16, 24, 32, 48])
        spec = self.spec(cfg)
        spec.update(mode='range', start=16., end=48., count=4)
        self.ui.cgyro_axis_mode_changed(cfg, 'Para', 'Range', self.source)
        self.assertEqual(scan_axes({'1d': cfg}, 1, self.source)[0]['values'], [16, 24, 32, 40, 48])
        self.assertEqual(cfg['Range'], [16, 24, 32, 48])

    def test_list_commit_updates_range_defaults_without_rounding_user_values(self):
        cfg = dict(Para='N_THETA', Range=[32])
        spec = self.spec(cfg)
        cfg['Range'] = [16, 24, 32, 48]
        self.ui.cgyro_axis_list_changed(cfg, 'Para', 'Range')
        self.assertEqual((spec['start'], spec['end'], spec['count']), (16, 48, 5))
        for bad in ([16, 24.5], [True, 32], [float('nan')], [0]):
            cfg['Range'] = bad
            with self.assertRaises(ValueError):
                self.ui.cgyro_axis_list_changed(cfg, 'Para', 'Range')
            self.assertIs(cfg['Range'], bad)

    def test_float_parameters_and_zero_reference_remain_explicit(self):
        cfg = dict(Para='BETAE_UNIT', Range=[0., .0001, .0002])
        spec = self.spec(cfg)
        self.assertEqual(spec['count'], 3)
        self.assertEqual(range_values(spec, 'BETAE_UNIT'), [0., .0001, .0002])
        cfg['Para'] = 'TEMP_1'
        self.ui.cgyro_axis_parameter_changed(cfg, 'Para', 'Range', self.source)
        self.assertEqual(cfg['Range'], [2])
        self.assertEqual(self.source['TEMP_1'], 2.)

    def test_unavailable_old_axis_can_still_open_for_parameter_selection(self):
        cfg = dict(Para='OLD_PARAMETER', Range={'__ndarray_tolist__': [1, 2]})
        self.assertEqual(self.spec(cfg)['parameter'], 'OLD_PARAMETER')
        cfg['Para'] = 'N_THETA'
        self.ui.cgyro_axis_parameter_changed(cfg, 'Para', 'Range', self.source)
        self.assertEqual(cfg['Range'], [32])


if __name__ == '__main__':
    unittest.main()
