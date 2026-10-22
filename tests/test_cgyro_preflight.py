"""GUI preflight checks parameters without creating native input-file copies."""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(path) for path in (REPO / 'CGYRO_TGLF_scan').rglob('LIB')]
import OMFITlib_cgyro_plan as plan


class FileInput(dict):
    copies = 0

    def duplicate(self):
        type(self).copies += 1
        return type(self)(copy.deepcopy(dict(self)))


def fixture(ions=('BASE',), radii=5):
    source = dict(N_SPECIES=3, N_RADIAL=16, N_THETA=24, Q=2., RMIN=.5,
                  RMAJ=3., N_ENERGY=8, N_XI=16, Z_1=1., MASS_1=1.,
                  DENS_1=.5, TEMP_1=1., Z_2=1., MASS_2=1.5,
                  DENS_2=.5, TEMP_2=1., Z_3=-1., MASS_3=.000272,
                  DENS_3=1., TEMP_3=1., metadata=[['unchanged']],
                  vector=np.array([1., 2.]))
    root = {'SETTINGS': {'WORKBENCH': {
        'cgyro_source_mode': 'current', 'cgyro_radii': {},
        'cgyro_ion_cases': {key: key in ions for key in plan.ION_CASES}}},
        'CGYRO_scan': {'SETTINGS': {
            'EXPERIMENT': {'runid': 'Jet'}, 'SETUP': {'idimrun': 1},
            'PHYSICS': {'kyarr': [.1, .2], '1d': {'Para': 'N_THETA', 'Range': [16, 32]}}},
            'INPUTS': {'input.cgyro_' + str(index): FileInput(copy.deepcopy(source))
                       for index in range(1, radii + 1)}}}
    return root


class PreflightTests(unittest.TestCase):
    def setUp(self):
        FileInput.copies = 0

    def test_repeated_gui_validation_does_not_duplicate_original_or_hdt_files(self):
        for ions in (('BASE',), ('H', 'D', 'T')):
            with self.subTest(ions=ions):
                root = fixture(ions)
                before = plan.input_digest(root['CGYRO_scan']['INPUTS'])
                for _ in range(3):
                    self.assertEqual(plan.cgyro_plan_issues(root), [])
                self.assertEqual(FileInput.copies, 0)
                self.assertEqual(plan.input_digest(root['CGYRO_scan']['INPUTS']), before)

    def test_nested_preflight_values_do_not_alias_source_inputs(self):
        root = fixture(('BASE', 'H', 'D', 'T'), radii=1)
        original = root['CGYRO_scan']['INPUTS']['input.cgyro_1']
        original_digest = plan.input_digest(original)
        validate = plan.validate_input

        def mutate_checked_copy(effective, kind):
            effective['metadata'][0].append('temporary')
            effective['vector'][0] = 99.
            validate(effective, kind)

        with patch.object(plan, 'validate_input', side_effect=mutate_checked_copy):
            self.assertEqual(plan.cgyro_plan_issues(root), [])
        self.assertEqual(plan.input_digest(original), original_digest)

    def test_actual_preparation_still_uses_native_independent_file_objects(self):
        root = fixture(radii=1)
        source = root['CGYRO_scan']['INPUTS']['input.cgyro_1']
        row = plan.cgyro_sources(root)[0]
        physics = root['CGYRO_scan']['SETTINGS']['PHYSICS']
        for ion in ('BASE', 'H', 'D', 'T'):
            with self.subTest(ion=ion):
                value, _, _, _ = plan._cgyro_case_input(root, row, source, ion, physics, 1)
                self.assertIsInstance(value, FileInput)
                self.assertIsNot(value, source)
                value['metadata'][0].append(ion)
                value['vector'][0] = 99.
        self.assertEqual(FileInput.copies, 4)
        self.assertEqual(source['metadata'], [['unchanged']])
        np.testing.assert_array_equal(source['vector'], [1., 2.])

    def test_invalid_physics_is_still_rejected_before_submission(self):
        root = fixture(('H', 'D', 'T'), radii=1)
        root['CGYRO_scan']['INPUTS']['input.cgyro_1']['PROFILE_MODEL'] = 2
        self.assertIn('局部输入', plan.cgyro_plan_issues(root)[0])
        self.assertEqual(FileInput.copies, 0)
        root = fixture(radii=1)
        root['CGYRO_scan']['SETTINGS']['PHYSICS']['1d']['Range'] = [1.5]
        self.assertIn('整数', plan.cgyro_plan_issues(root)[0])
        self.assertEqual(FileInput.copies, 0)

    def test_radius_selector_uses_saved_metadata_without_loading_input_files(self):
        class Unopened(dict):
            def __getitem__(self, key):
                raise AssertionError('radius selector opened a solver input')

        root = fixture()
        root['SETTINGS']['WORKBENCH']['cgyro_source_mode'] = 'generated'
        root['Transfer_tool'] = {'OUTPUTS': {
            'Profiles_gen': Unopened({'input.cgyro_1': None, 'input.cgyro_2': None}),
            'Particle_processing': {'local_inputs': {
                'input.cgyro_1': {'rho': .33}, 'input.cgyro_2': {'rho': .5}}}}}
        self.assertEqual([row['rho'] for row in plan.cgyro_sources(root)], [.33, .5])

    def test_legacy_radius_still_reads_input_metadata_when_saved_record_is_absent(self):
        root = fixture(radii=1)
        root['CGYRO_scan']['INPUTS']['input.cgyro_1']['rho'] = .33
        self.assertEqual(plan.cgyro_sources(root)[0]['rho'], .33)


if __name__ == '__main__':
    unittest.main()
