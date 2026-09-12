# -*-Python-*-
# Created by grierson at 25 Apr 2016  14:38

# Pre-allocate computed quantities
gamma_n = np.zeros((len(root['D_and_v']['rhoList']), root['TGLF']['SETTINGS']['PHYSICS']['scanParameterSteps']))
nisl = np.zeros((len(root['D_and_v']['rhoList']), root['TGLF']['SETTINGS']['PHYSICS']['scanParameterSteps']))
rmin = np.zeros(len(root['D_and_v']['rhoList']))
diffusion = np.zeros(len(root['D_and_v']['rhoList']))
pinch = np.zeros(len(root['D_and_v']['rhoList']))
for i, rho in enumerate(root['D_and_v']['rhoList']):
    ####
    # Form MKS Gamma, grad(n)/n, Gamma, etc...
    # MKS Gamma is from TGLF Gamma[imp] (in G/G_GB) * TGYRO Gamma_GB(10^19 m**-2 s**-1)
    # MKS n is from TGYRO ni_[imp]
    # MKS grad(n)/n is from the fact that RLNS_[imp] = -(1/n)dn/dr so grad(n)/n = -RNLS_[imp]/a
    #     grad(n)/n is negative inverse scale length
    ####
    # Note that the last array element is the one we want
    rho = round(rho, 3)
    ind_rho = closestIndex(root['tgyro_output']['rho'][0, :], rho)
    # Midplane minor radius
    rmin[i] = root['tgyro_output']['rmin'][0, ind_rho] * 1e-2
    # Gamma_GB
    gamma_GB = root['tgyro_output']['Gamma_GB'][0, ind_rho]
    # Impurity density in cm**-3 -> 10^19 m**-3
    ni = root['tgyro_output']['ni{}'.format(root['D_and_v']['impLoc'])][0, ind_rho] * 1e-13
    # Range of RLNS_? and output Gamma[imp]
    rlns = np.zeros(root['TGLF']['SETTINGS']['PHYSICS']['scanParameterSteps'])
    gamma = np.zeros(root['TGLF']['SETTINGS']['PHYSICS']['scanParameterSteps'])
    #    for j,k in enumerate(root['scanResults'][rho]['RLNS_{}'.format(root['D_and_v']['impLoc']+1)].keys()):
    #        rlns[j] = float(k)
    #        gamma[j] = root['scanResults'][rho]['RLNS_{}'.format(root['D_and_v']['impLoc']+1)][k]['Gam/Gam_GB'][root['D_and_v']['impLoc']]
    # This is a hack until we figure out the silly list <-> np array and precision
    k = list(root['scanResults'][rho]['RLNS_{}'.format(root['D_and_v']['impLoc'] + 1)].keys())
    rlns[0] = float(k[0])
    rlns[1] = float(k[1])
    rlns[2] = float(k[-1])
    gamma[0] = root['scanResults'][rho]['RLNS_{}'.format(root['D_and_v']['impLoc'] + 1)][k[0]]['Gam/Gam_GB'][root['D_and_v']['impLoc']]
    gamma[1] = root['scanResults'][rho]['RLNS_{}'.format(root['D_and_v']['impLoc'] + 1)][k[1]]['Gam/Gam_GB'][root['D_and_v']['impLoc']]
    gamma[2] = root['scanResults'][rho]['RLNS_{}'.format(root['D_and_v']['impLoc'] + 1)][k[-1]]['Gam/Gam_GB'][root['D_and_v']['impLoc']]

    # Particle flux (10^19 m**-2 s**-1)
    gamma_MKS = gamma * gamma_GB
    # Gamma/n
    gamma_n[i, :] = gamma_MKS / ni
    # Negative inverse scale length (m**-1)
    nisl[i, :] = -rlns / (root['tgyro_output']['a'] * 1e-2)

    print('Ion density: {}'.format(ni))
    print('RLNS: {}'.format(rlns))
    print('-ISL: {}'.format(nisl[i, :]))
    print('Particle flux (GB): {}'.format(gamma))
    print('Particle flux (10**19 m**-2 s**-1): {}'.format(gamma_MKS))
    print('Gamma(MKS)/ni: {}'.format(gamma_n[i, :]))
    ####
    # Extract D, V from linear fit of Gamma/n (m/s) vs. grad(n)/n (m**-1) with
    # the slope being -D (m**/2) and the y-intercept begin V (m/s)
    ####
    # Fit y = A + B*x
    fitAB = np.polyfit(nisl[i, :], gamma_n[i, :], 1)
    diffusion[i] = -1.0 * fitAB[0]
    pinch[i] = fitAB[1]
    print('D (m**2/s): {}'.format(diffusion[i]))
    print('V (m/s): {}'.format(pinch[i]))


root['D_and_v']['gamma_n'] = gamma_n
root['D_and_v']['nisl'] = nisl
root['D_and_v']['D'] = diffusion
root['D_and_v']['v'] = pinch
root['D_and_v']['pf'] = pinch / diffusion

# Create smooth zero flux impurity density profile
rmin_ext = np.insert(rmin, 0, 0.0)
rmin2 = linspace(0.0, np.max(rmin), 101)
pf = pinch / diffusion
# pinch=0 on axis
pf_ext = np.insert(pf, 0, 0.0)
pf2 = interpolate.interp1d(rmin_ext, pf_ext)(rmin2)
# Integrand
ingrd = np.zeros(len(rmin2))
for i in range(1, len(rmin2)):
    ingrd[i] = scipy.integrate.simps(pf2[0:i], x=rmin2[0:i])
prof = np.exp(ingrd)
# Remove boundary condition
prof -= prof[-1]

root['D_and_v']['ingrd'] = ingrd
root['D_and_v']['gzrho'] = interpolate.interp1d(root['D_and_v']['input.gacode_orig']['rmin'], root['D_and_v']['input.gacode_orig']['rho'])(
    rmin2
)
root['D_and_v']['gzprof'] = prof
