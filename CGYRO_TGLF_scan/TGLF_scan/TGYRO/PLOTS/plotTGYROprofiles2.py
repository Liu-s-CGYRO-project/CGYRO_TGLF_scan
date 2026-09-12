# -*-Python-*-
# Created by grierson at 03 Aug 2016  09:13

# Plot input profiles and scale length and compare with solution and input.gacode.new
defaultVars(nit=None)

# Inputs
input = PROFILES_GEN['OUTPUTS']['input.gacode']
a = np.max(input['rmin'])

# Outputs
output = root['OUTPUTS']['output']
if 'input.gacode' in root['OUTPUTS']:
    input_new = root['OUTPUTS']['input.gacode']
else:
    input_new = None

if nit is None:
    nit = len(output['convergence']) - 1

ipkeys = ['Te', 'Ti_1', 'ne', 'omega0']
opkeys = ['te', 'ti1', 'ne', 'w0']
lpkeys = ['te', 'ti1', 'ne', 'a*gamma_e/cs']
ptexs = ['T_e', 'T_i', 'n_e', '\\omega_0']
pnames = ['Electron Temperature', 'Ion Temperature', 'Electron Density', 'Toroidal Rotation']
punits = ['keV', 'keV', 'e19m**-3', 'rad/s']
pscales = [1.0, 1.0, 1e-13, 1.0]

# Add the ion properties to these lists
nion = root['INPUTS']['input.tgyro']['LOC_N_ION']
ion_ipkeys = []
ion_opkeys = []
ion_lpkeys = []
ion_ptexs = []
ion_pnames = []
ion_punits = []
ion_pscales = []
for i in range(nion):
    ion_ipkeys.append('ni_{}'.format(i + 1))
    ion_opkeys.append('ni{}'.format(i + 1))
    ion_lpkeys.append('ni{}'.format(i + 1))
    ion_ptexs.append('n_{{{}}}'.format(input['IONS'][i + 1][0]))
    ion_pnames.append('Ion Density({})'.format(i + 1))
    ion_punits.append('e19m**-3')
    ion_pscales.append(1e-13)

# Insert these lists into the master lists
[ipkeys.insert(3, i) for i in ion_ipkeys[::-1]]
[opkeys.insert(3, i) for i in ion_opkeys[::-1]]
[lpkeys.insert(3, i) for i in ion_lpkeys[::-1]]
[ptexs.insert(3, i) for i in ion_ptexs[::-1]]
[pnames.insert(3, i) for i in ion_pnames[::-1]]
[punits.insert(3, i) for i in ion_punits[::-1]]
[pscales.insert(3, i) for i in ion_pscales[::-1]]

fn = FigureNotebook(0, 'TGYRO Profiles and Scale Lengths')
for ipkey, opkey, lpkey, ptex, pname, punit, pscale in zip(ipkeys, opkeys, lpkeys, ptexs, pnames, punits, pscales):
    fig, ax = fn.subplots(2, 2, label=pname)

    # Profiles in rho
    ax[0, 0].plot(input['rho'], input[ipkey], color='grey', label='Input')
    ax[0, 0].plot(output['rho'][0, :], output[opkey][0, :] * pscale, color='grey', marker='o', mfc='None', label='It #0', linestyle='None')
    if input_new is not None:
        ax[0, 0].plot(input_new['rho'], input_new[ipkey], color='black')
    else:
        ax[0, 0].plot(output['rho'][nit, :], output[opkey][nit, :] * pscale, color='black')
    ax[0, 0].plot(
        output['rho'][nit, :],
        output[opkey][nit, :] * pscale,
        color='black',
        marker='o',
        markersize=2.0,
        label='It #{}'.format(nit),
        linestyle='None',
    )
    ax[0, 0].set_title(pname)
    ax[0, 0].set_ylabel('${}$'.format(ptex))
    ax[0, 0].legend(loc='best')

    # a/L_X in rho
    if ipkey == 'omega0':
        cs = np.sqrt(input['Te'] * 1e3 * scipy.constants.e / 2.0 / scipy.constants.m_p)
        der = -(input['rmin'] / input['q']) * deriv(input['rmin'], input['omega0'])
        aol = a * der / cs
        aolt = output['a*gamma_e/cs']
        ylab = '$a\\gamma_E/c_s$'
    else:
        aol = -a * deriv(input['rmin'], input[ipkey]) / input[ipkey]
        aolt = output['a/L{}'.format(lpkey)]
        ylab = '$a/L{}$'.format(lpkey)
    ylim = [np.floor(np.min(aolt)), np.ceil(np.max(aolt))]
    if ylim[1] <= 1.0:
        ylim = [np.floor(np.min(aolt)), np.ceil(np.max(aolt) * 10.0) / 10.0]
    ax[1, 0].plot(input['rho'], aol, color='grey')
    ax[1, 0].plot(output['rho'][0, :], aolt[0, :], color='grey', marker='o', mfc='None', label='It #0')
    ax[1, 0].plot(output['rho'][nit, :], aolt[nit, :], color='black', marker='o', markersize=2.0, label='It #{}'.format(nit))
    ax[1, 0].set_title('Norm. Inverse Scale Length')
    ax[1, 0].set_xlabel('$\\rho$')
    ax[1, 0].set_ylim(ylim)
    ax[1, 0].set_ylabel(ylab)

    # Profiles in iteration
    c = cm.rainbow_r(linspace(0, 1, len(output['rho'][0, :])))
    for i, r in enumerate(output['rho'][0, :]):
        ax[0, 1].plot(arange(nit + 1), output[opkey][:, i], marker='o', markersize=2.0, label='$\\rho$={0:0.2f}'.format(r), color=c[i])
    l = ax[0, 1].legend(loc='upper left')
    l.draggable()
    l.get_frame().set_alpha(0.25)
    ax[0, 1].set_title(pname)

    # a/L_X in iteration
    for i, r in enumerate(output['rho'][0, :]):
        ax[1, 1].plot(arange(nit + 1), aolt[:, i], marker='o', markersize=2.0, label='$\\rho$={0:0.2f}'.format(r), color=c[i])
    l = ax[1, 1].legend(loc='upper left')
    l.draggable()
    l.get_frame().set_alpha(0.25)
    ax[1, 1].set_title('Norm. Inverse Scale Length')
    ax[1, 1].set_xlabel('Iteration')
    cornernote('%s' % ((root['SETTINGS']['EXPERIMENT']['runid'])), '', ax=ax[1, 1])
