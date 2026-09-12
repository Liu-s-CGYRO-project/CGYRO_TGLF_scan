# -*-Python-*-
# Created by smithsp at 2013/07/24 14:29
#
# this sctipt looks at the rotation prediction according to the Rice scaling

from scipy.constants import mu_0, m_p

defaultVars(beta_t=None, qstar=None, ion_mass_amu=None, impurity_charge=None)
if any(value is None for value in (beta_t, qstar, ion_mass_amu, impurity_charge)):
    raise OMFITexception('Rice estimate requires beta_t (fraction), qstar, ion_mass_amu and impurity_charge; no D-T/carbon assumptions are applied automatically')
if beta_t <= 0 or qstar <= 0 or ion_mass_amu <= 0 or impurity_charge <= 1:
    raise OMFITexception('Rice estimate requires positive beta_t, qstar, ion mass and impurity charge > 1')

Bt = input_gacode['BT_EXP']
ne = input_gacode['ne'] * 1e19
Zeff = input_gacode['z_eff']
Rmaj = input_gacode['rmaj']
# for k in input_gacode:
#    if 'header' not in k:
#        continue
#    line = input_gacode[k]
#    if 'MAJOR RADIUS' in line:
#        R0 = float(line.split(':')[1].split('m')[0])
#        break
m_i = ion_mass_amu * m_p
Z_I = impurity_charge
if np.any(ne <= 0) or np.any(1 - (Zeff - 1) / Z_I <= 0):
    raise OMFITexception('Profiles are outside the positive-density, single-effective-impurity Rice approximation')
m_ave = m_i / (1 - (Zeff - 1) / Z_I)
c_alfven = Bt / sqrt(mu_0 * ne * m_ave)
betaT = beta_t
M_A_Rice = 0.65 * betaT**1.4 * qstar**2.3
vtor = M_A_Rice * c_alfven

figure()
plot(vtor)
title('$V_{tor}$')

figure()
plot(vtor / Rmaj)
title('$V_{tor}/R$')
