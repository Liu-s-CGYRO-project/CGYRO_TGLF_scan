"""Exercise the OMFIT local conversion entry point with complete solver cards."""
from pathlib import Path
import runpy
import unittest

import numpy as np


SCRIPT = Path(__file__).resolve().parents[1] / 'CGYRO_TGLF_scan/Transfer_tool/SCRIPTS/convert_file.py'


class LocalConversionTest(unittest.TestCase):
    def setUp(self):
        x = np.linspace(.05, 1., 12)
        ones, zeros = np.ones_like(x), np.zeros_like(x)
        self.profile = dict(N_EXP=len(x), rmin=x, rhos=.001 * ones, rmaj=3 * ones, q=2 * ones,
                            omega0=zeros, ne=ones, Te=ones, ni_1=ones, Ti_1=ones)
        self.card = dict(NS=2, UNITS='CGYRO', KY=.47, RMIN_LOC=.5, RMAJ_LOC=3., Q_LOC=2.,
                         DRMAJDX_LOC=0., ZMAJ_LOC=0., DZMAJDX_LOC=0., KAPPA_LOC=1., S_KAPPA_LOC=0.,
                         DELTA_LOC=0., S_DELTA_LOC=0., ZETA_LOC=0., S_ZETA_LOC=0., SIGN_BT=1., SIGN_IT=1.,
                         XNUE=.1, DEBYE=0., BETAE=.01, VEXB_SHEAR=0., VPAR_SHEAR_1=0., VPAR_1=0.,
                         ZEFF=2.2, USE_BPER=False, USE_BPAR=False)
        for i, z, mass in ((1, -1., .000272444), (2, 1., 1.00026)):
            for key, val in dict(ZS=z, MASS=mass, AS=1., TAUS=1., RLNS=0., RLTS=0.).items():
                self.card[f'{key}_{i}'] = val
        self.geometry = dict(SHAT_SA=.7)
        for i in range(7):
            for family in (('cos', 'sin') if i >= 3 else ('cos',)):
                self.profile[f'shape_{family}{i}'] = zeros
                self.geometry[f'SHAPE_{family.upper()}{i}'] = .12 if (i, family) == (3, 'cos') else 0.
                self.geometry[f'SHAPE_S_{family.upper()}{i}'] = 0.
        self.files = {'input.tglf': self.card, 'input.gacode': self.profile}

    def convert(self):
        root = dict(SETTINGS={'PHYSICS': {'Transfer to cgyro': True, 'Transfer to tglf': False}},
                    Transfer_file=self.files, OUTPUTS={})
        runpy.run_path(str(SCRIPT), init_globals=dict(root=root, OMFITgacode=lambda *a, **kw: {},
                                                       OMFITtree=dict, print=lambda *a: None))
        return self.files['input.cgyro']

    def test_both_formats_use_explicit_ky_fields_zeff_and_local_geometry(self):
        for dump in (False, True):
            if dump:
                self.card.update(self.geometry)
            for nfield, bper, bpar in ((1, False, '.false.'), (2, True, False), (3, '.true.', True)):
                with self.subTest(dump=dump, nfield=nfield):
                    self.card.update(USE_BPER=bper, USE_BPAR=bpar)
                    target = self.convert()
                    self.assertEqual((target['KY'], target['N_FIELD']), (.47, nfield))
                    self.assertEqual((target['Z_EFF'], target['Z_EFF_METHOD'], target['COLLISION_MODEL']), (2.2, 1, 1))
                    self.assertEqual(target['SHAPE_COS3'], .12 if dump else 0.)
                    if dump:
                        self.assertEqual(target['S'], .7)

    def test_active_miller_shear_is_read_from_the_local_card(self):
        self.card.update(self.geometry, GEOMETRY_FLAG=1, Q_PRIME_LOC=16.)
        self.assertEqual(self.convert()['S'], 1.)

    def test_omitted_values_composition_and_unrepresentable_field_pair(self):
        for key in ('KY', 'USE_BPER', 'USE_BPAR'):
            del self.card[key]
        self.card['ZEFF'] = 1.
        saved = self.convert()
        self.assertEqual((saved['KY'], saved['N_FIELD'], saved['Z_EFF_METHOD'], saved['COLLISION_MODEL']),
                         (.3, 1, 2, 4))
        self.card['USE_BPAR'] = True
        with self.assertRaisesRegex(ValueError, 'USE_BPAR'):
            self.convert()
        self.assertIs(self.files['input.cgyro'], saved)
