"""Verify synthetic local cards, or replay the historical five-radius data when supplied."""
import copy
import csv
import math
import os
from pathlib import Path
import runpy
import tempfile
from types import SimpleNamespace
import unittest

from OMFITlib_transfer_equivalent import jet_fuel_audit_lines, jet_fuel_local_input
from OMFITlib_transfer_particles import (JET_FUEL_LABEL, JET_FUEL_MODE, PRESETS,
                                         detect_main_ions, prepare_particles, species)
from OMFITlib_transfer_schemes import SCHEMES


FIXTURES = Path(os.environ.get('OMFIT_JET96482_TEST_CARDS') or Path(__file__).with_name('fixtures') / 'jet_fuel_synthetic')
SCRIPT = Path(__file__).resolve().parents[1] / 'CGYRO_TGLF_scan/Transfer_tool/SCRIPTS/profiles_gen4input.py'
FIELDS = ('Z', 'MASS', 'DENS', 'TEMP', 'DLNNDR', 'DLNTDR')
CURVATURE = ('SDLNNDR', 'SDLNTDR')
SOURCE = [('D', 1, 2.0005209, 'therm'), ('Be', 4, 8.9514317, 'therm'),
          ('Ni', 28, 58.304192, 'therm'), ('D', 1, 2.0005209, 'fast'), ('H', 1, 1.0004845, 'fast')]
OPTIONS = dict(particle_mode=JET_FUEL_MODE, minimum=0.5, maximum=0.85, coordinate='rho')


class Card(dict):
    def duplicate(self):
        return copy.deepcopy(self)


def source_profile(ions=SOURCE):
    return Card(N_ION=len(ions), IONS=dict(enumerate(ions, 1)))


def original_cards():
    with (FIXTURES / 'local_cards.csv').open() as stream:
        rows = csv.reader(stream)
        cards = {float(rho): Card() for rho in next(rows)[1:]}
        for name, *values in rows:
            for card, value in zip(cards.values(), values):
                card[name] = float(value)
    return cards


def expected_results():
    with (FIXTURES / 'three_species.csv').open() as stream:
        expected = {}
        for row in csv.DictReader(stream):
            target = expected.setdefault(float(row['rho']), {})
            for field in FIELDS:
                target[field + '_' + row['species']] = float(row[field])
    return expected


def audit_from_card(card):
    indices = range(1, int(card['N_SPECIES']) + 1)
    ions = [str(i) for i in indices if card['Z_' + str(i)] > 0]
    electron, = [str(i) for i in indices if card['Z_' + str(i)] == -1]
    ne = card['DENS_' + electron]
    return dict(charge_residual=math.fsum(card['Z_' + i] * card['DENS_' + i] for i in ions) - ne,
                zeff=math.fsum(card['Z_' + i]**2 * card['DENS_' + i] for i in ions) / ne,
                pressure=math.fsum(card['DENS_' + i] * card['TEMP_' + i] for i in ions),
                pressure_gradient=math.fsum(card['DENS_' + i] * card['TEMP_' + i] *
                                            (card['DLNNDR_' + i] + card['DLNTDR_' + i]) for i in ions))


class JetFuelTests(unittest.TestCase):
    def test_gui_scheme_uses_original_species_without_altering_the_source_composition(self):
        self.assertEqual(PRESETS[JET_FUEL_LABEL], JET_FUEL_MODE)
        self.assertEqual(SCHEMES[JET_FUEL_MODE], (JET_FUEL_LABEL, dict(particle_mode=JET_FUEL_MODE)))
        profile = source_profile()
        profile.update(ne=[1, 1], ni_1=[0.12, 0.13], ni_4=[0.5, 0.7])
        prepared, report = prepare_particles(profile, OPTIONS)
        self.assertEqual(prepared, profile)
        self.assertIsNot(prepared, profile)
        self.assertEqual(report['before'], species(profile))
        self.assertEqual(report['main_ions'], detect_main_ions(profile, OPTIONS))
        self.assertEqual([ion['index'] for ion in report['main_ions']], [1])

    def test_five_complete_locpargen_cards_through_generation_and_all_archived_fields(self):
        native, expected = original_cards(), expected_results()
        self.assertEqual(list(native), [0.5, 0.5875, 0.675, 0.7625, 0.85])
        self.assertEqual(set(native), set(expected))
        profile, report = prepare_particles(source_profile(), OPTIONS)
        with tempfile.TemporaryDirectory() as workdir:
            outputs = {'TGYRO': {'rho': [[0, *native]]}, 'Particle_processing': report}
            root = {'SETTINGS': {'SETUP': {'workDir': workdir}}, 'INPUTS': {'input.gacode': profile},
                    'OUTPUTS': outputs}

            def locpargen(module, inputs, outputs, workdir, executable, **kwargs):
                self.assertIs(inputs[0][0], profile)
                rho = float(executable.split()[-1])
                for name in outputs:
                    values = native[rho] if name == 'input.cgyro.locpargen' else {'NS': 6, 'TAUS_4': 31}
                    Path(workdir, name).write_text('\n'.join(f'{k}={v}' for k, v in values.items()))
                return 0

            def read_card(path):
                pairs = (line.split('=') for line in Path(path).read_text().splitlines())
                return Card((key, float(value)) for key, value in pairs)

            environment = dict(root=root, OMFITx=SimpleNamespace(executable=locpargen), OMFITgacode=read_card,
                               OMFITtree=dict)
            runpy.run_path(str(SCRIPT), init_globals=environment)
            result = outputs['Profiles_gen']
            records = outputs['Particle_processing']['local_inputs']
            self.assertEqual(len(jet_fuel_audit_lines(records)), len(native))
            for index, (rho, original) in enumerate(native.items(), 1):
                with self.subTest(rho=rho):
                    key = 'input.cgyro_' + str(index)
                    card = result[key]
                    self.assertEqual(result['input.tglf_' + str(index)], {'NS': 6, 'TAUS_4': 31})
                    self.assertEqual(card['N_SPECIES'], 3)
                    self.assertEqual(len(expected[rho]), 18)
                    for field, value in expected[rho].items():
                        self.assertAlmostEqual(card[field], value, delta=1e-14, msg=field)
                    removed = {'SBETA'} | {f'{f}_{i}' for f in CURVATURE for i in range(1, 7)}
                    removed.update(f'{f}_{i}' for f in FIELDS for i in range(4, 7))
                    self.assertEqual(set(card), set(original) - removed)
                    for field in set(card) - set(expected[rho]) - {'N_SPECIES'}:
                        self.assertEqual(card[field], original[field], field)
                    self.assertEqual(records[key]['rho'], rho)
                    for stage, values in [('before', original), ('after', card)]:
                        for field, value in audit_from_card(values).items():
                            self.assertAlmostEqual(records[key]['equivalent'][stage][field], value, delta=4e-15)
            audit = records['input.cgyro_1']['equivalent']
            self.assertNotEqual(audit['before']['charge_residual'], 0)
            for field in ('charge_residual', 'zeff'):
                self.assertAlmostEqual(audit['before'][field], audit['after'][field], delta=2e-15)
            self.assertGreater(audit['before']['pressure'], audit['after']['pressure'])
            self.assertGreater(audit['before']['pressure_gradient'], audit['after']['pressure_gradient'])

            # A failure at the final radius may not publish four new cards over the completed set.
            native[0.85]['DENS_2'] = native[0.85]['DENS_3'] = 0
            with self.assertRaisesRegex(ValueError, '总密度'):
                runpy.run_path(str(SCRIPT), init_globals=environment)
            self.assertIs(outputs['Profiles_gen'], result)
            self.assertIs(outputs['Particle_processing']['local_inputs'], records)

    def test_permuted_source_with_fast_d_first_and_electron_in_the_middle(self):
        original = original_cards()[0.5]
        card = original.copy()
        order = [4, 3, 6, 2, 5, 1]
        for new, old in enumerate(order, 1):
            for field in FIELDS + CURVATURE:
                card[f'{field}_{new}'] = original[f'{field}_{old}']
        profile = source_profile([SOURCE[i-1] for i in order if i != 6])
        self.assertEqual(detect_main_ions(profile, OPTIONS)[0]['index'], 5)
        jet_fuel_local_input(card, species(profile))
        for field, value in expected_results()[0.5].items():
            self.assertAlmostEqual(card[field], value, delta=1e-14, msg=field)

    def test_impurity_temperature_and_both_gradients_use_impurity_density_weights(self):
        card = original_cards()[0.5]
        card.update(TEMP_2=2.1, TEMP_3=3.4, DLNNDR_2=0.3, DLNNDR_3=-1.7, DLNTDR_2=1.4, DLNTDR_3=0.8,
                    DENS_6=1.3, TEMP_6=1.2, DLNNDR_SCALE_6=0.9, SHAPE_SIN3=0.02)
        original = card.copy()
        jet_fuel_local_input(card, species(source_profile()))
        n2, n3 = original['DENS_2'], original['DENS_3']
        for field in ('TEMP', 'DLNNDR', 'DLNTDR'):
            target = (n2 * original[field + '_2'] + n3 * original[field + '_3']) / (n2 + n3)
            self.assertAlmostEqual(card[field + '_2'], target)
        self.assertEqual((card['DENS_3'], card['TEMP_3']), (1.0, 1.0))
        self.assertEqual(card['SHAPE_SIN3'], 0.02)
        self.assertNotIn('DLNNDR_SCALE_6', card)

    def test_unknown_species_mismatched_card_or_global_geometry_fail_before_writing(self):
        ions = species(source_profile())
        for diff, metadata in [({}, [dict(ions[0], kind='fast'), *ions[1:]]),
                               ({}, [ions[0], dict(ions[1], name='C'), *ions[2:]]),
                               ({'MASS_2': 12}, ions), ({'GLOBAL_FLAG': 1}, ions)]:
            with self.subTest(diff=diff, metadata=metadata):
                card = original_cards()[0.5]
                card.update(diff)
                original = card.copy()
                with self.assertRaises(ValueError):
                    jet_fuel_local_input(card, metadata)
                self.assertEqual(card, original)
