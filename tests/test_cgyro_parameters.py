"""Native catalog coverage and explicit overrides on sparse CGYRO inputs."""
import json
from pathlib import Path
import unittest

import test_cgyro_storage  # Isolated OMFIT file adapters, no result files.
import test_cgyro_preflight as preflight
from OMFITlib_cgyro_parameters import (COMMON, FIELDS, apply_parameters, field_spec,
    initialize_parameters, managed_parameter, parameter_catalog, parameter_value, validated_overrides)
from OMFITlib_cgyro_parameter_help import parameter_help


class CgyroParameterTests(unittest.TestCase):
    def test_catalog_covers_every_native_editable_definition_without_an_input_file(self):
        snapshot = json.loads((Path(__file__).parent / 'fixtures/cgyro_parser_defaults.json').read_text(encoding='utf-8'))
        defaults = snapshot['defaults']
        managed = {name for name in defaults if managed_parameter(name)}
        catalog = parameter_catalog([])
        self.assertEqual(len(defaults), 247)
        self.assertEqual(len(managed), 48)
        self.assertEqual(set(catalog), set(defaults) - managed)
        for name, spec in catalog.items():
            with self.subTest(name=name):
                self.assertEqual(spec['reference'], defaults[name])
                self.assertEqual(spec['kind'], 'int' if type(defaults[name]) is int else 'float')
        self.assertEqual(len(COMMON), 53)
        self.assertIn('HIPREC_FLAG', COMMON)
        self.assertLess(len(COMMON), len(catalog))

    def test_opening_catalog_does_not_enable_defaults_or_modify_sparse_source(self):
        source = {'N_SPECIES': 2, 'N_ENERGY': 32, 'N_XI': 48}
        previous = dict(source)
        physics = {}
        parameters = initialize_parameters(physics, source)
        self.assertEqual(len(parameters), 199)
        self.assertEqual(parameters['HIPREC_FLAG'], dict(enabled=False, value=0))
        self.assertFalse(any(item['enabled'] for item in parameters.values()))
        self.assertEqual(apply_parameters(source, physics, 0), {})
        self.assertEqual(source, previous)

    def test_hiprec_and_omitted_native_parameters_reach_each_prepared_input(self):
        root = preflight.fixture(('BASE', 'T'), radii=2)
        node = root['CGYRO_scan']
        physics = node['SETTINGS']['PHYSICS']
        explicit = dict(HIPREC_FLAG=1, FIELD_PRINT_FLAG=1, MOMENT_PRINT_FLAG=1,
                        RESTART_STEP=100, COLLISION_PRECISION_MODE=64, THETA_PLOT=8)
        physics['fixed_parameters'] = {name: dict(enabled=True, value=value) for name, value in explicit.items()}
        self.assertEqual(preflight.plan.cgyro_plan_issues(root), [])
        for row in preflight.plan.cgyro_sources(root):
            source = preflight.plan.read(root, row['path'])
            previous = preflight.plan.input_digest(source)
            for ion in ('BASE', 'T'):
                current, _, _, overrides = preflight.plan._cgyro_case_input(root, row, source, ion, physics, 1)
                self.assertEqual(overrides, explicit)
                for name, value in explicit.items():
                    self.assertEqual(current[name], value)
                    self.assertIs(type(current[name]), int)
            self.assertEqual(preflight.plan.input_digest(source), previous)

    def test_saved_explicit_output_values_survive_reopen_and_changing_reference(self):
        physics = {'fixed_parameters': {'HIPREC_FLAG': dict(enabled=True, value=1),
                    'H_PRINT_FLAG': dict(enabled=True, value=0)}}
        reopened = json.loads(json.dumps(physics))
        for source in ({}, dict(HIPREC_FLAG=0, H_PRINT_FLAG=1)):
            initialize_parameters(reopened, source)
            self.assertEqual(validated_overrides(reopened, [source]), {'HIPREC_FLAG': 1, 'H_PRINT_FLAG': 0})

    def test_scan_axis_and_constant_use_the_same_new_catalog(self):
        physics = {'1d': {'Para': 'HIPREC_FLAG'}, 'fixed_parameters': {
            'HIPREC_FLAG': dict(enabled=True, value=1), 'RES_WEIGHT_POWER': dict(enabled=False, value=2.)},
            'constant_parameter': 'RES_WEIGHT_POWER'}
        source = {}
        self.assertEqual(apply_parameters(source, physics, 1), {'RES_WEIGHT_POWER': 2})
        self.assertEqual(source['HIPREC_FLAG'], 0)  # Seed is replaced by each scanned value.
        self.assertEqual(source['RES_WEIGHT_POWER'], 2)

    def test_integer_and_precision_checks_use_native_types(self):
        for name in ('RESTART_STEP', 'HIPREC_FLAG', 'MPIIO_STRIPE_FACTOR', 'COLLISION_FIELD_MAX_L'):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, '整数'):
                parameter_value(name, 1.5)
        for value in (-1, 2, float('nan')):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parameter_value('HIPREC_FLAG', value)
        self.assertEqual(parameter_value('COLLISION_FIELD_MAX_L', -2), -2)
        self.assertEqual(field_spec('TEMP_11')['group'], 'species')
        self.assertEqual(field_spec('SHAPE_S_SIN6')['group'], 'geometry')
        self.assertIn('ERROR_TOL', parameter_help('HIPREC_FLAG'))
        self.assertIn('float64', parameter_help('HIPREC_FLAG'))

    def test_site_extensions_are_retained_only_when_supported_by_each_selected_input(self):
        source = dict(FULL_T_ASYM_COMPRESSION=0)
        self.assertIn('FULL_T_ASYM_COMPRESSION', parameter_catalog([source]))
        self.assertNotIn('FULL_T_ASYM_COMPRESSION', parameter_catalog([{}]))
        physics = {'fixed_parameters': {'FULL_T_ASYM_COMPRESSION': dict(enabled=True, value=1)}}
        self.assertEqual(validated_overrides(physics, [source]), {'FULL_T_ASYM_COMPRESSION': 1})
        with self.assertRaisesRegex(ValueError, '部分所选输入'):
            validated_overrides(physics, [source, {}])
        for name in ('KY', 'NONLINEAR_FLAG', 'N_TOROIDAL', 'DENS_2'):
            physics = {'fixed_parameters': {name: dict(enabled=True, value=1)}}
            with self.subTest(name=name), self.assertRaises(ValueError):
                validated_overrides(physics, [source])


if __name__ == '__main__':
    unittest.main()
