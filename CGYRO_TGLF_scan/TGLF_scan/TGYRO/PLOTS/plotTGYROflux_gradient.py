# -*-Python-*-
# Created by grierson at 15 Jun 2021  17:35

"""
This script plots the "diagonal" elements of the transport matrix to visualize the flux-graident
relationship traversed during TGYRO iterations.
Individual channel flux-gradient relationships are first shown for all combinations of
energy, particle and momentum flux for neoclassical and turbulent flux cycling through species.
Total fluxes are then shown for each channel (energy, particle, momentum) summed over 
neoclassical, turbulent and species contributions.
A horizontal line shows the evolution of the target.
Color indicates interation.

defaultVars parameters
----------------------
:param None: None for now.  Could add choice of units (gB, MKS) or others.
"""

defaultVars()

input = root['INPUTS']['input.tgyro']
output = root['OUTPUTS']['output']

# Number of radial zones
nzones = shape(output['rho'])[1] - 1
nr = int(np.ceil(np.sqrt(float(nzones))))
nc = int(np.floor(np.sqrt(float(nzones))))
if nr * nc < nzones:
    nr = nr + 1

# Number of iterations
nit = len(output['convergence'])
colorby = linspace(0, 1, nit)
cmap = 'viridis'
nm = matplotlib.colors.Normalize(colorby.min(), colorby.max())
sm = matplotlib.cm.ScalarMappable(cmap=cmap, norm=nm)
sm.set_array(colorby)
colors = sm.cmap(sm.norm(colorby))

# Number of ions used in flux calculations
nion = input['LOC_N_ION']

species = [PROFILES_GEN['OUTPUTS']['input.gacode']['IONS'][i][0] for i in range(1, nion + 1)]
species.insert(0, 'e')
printi('Species {}'.format(species))

fn = FigureNotebook(0, 'TGYRO Flux-Gradient Channels and Species')

for chkey, chsym, chtex, chname, mks in zip(
    ['eflux', 'pflux', 'mflux'],
    ['Q', 'Gamma', 'Pi'],
    ['Q', '\\Gamma', '\\Pi'],
    ['Energy', 'Particles', 'Momentum'],
    ['MW/m^2', 'e19m^2/s', 'J/m^2'],
):
    # j and ei are indicies for electron or ion
    for j, s in zip(range(len(species)), species):

        # Set diagnoal norm inverse scale length
        if chkey == 'eflux':
            if s == 'e':
                aoLkey = 'a/Lt{}'.format(s)
            else:
                aoLkey = 'a/Lti{}'.format(j)
        elif chkey == 'pflux':
            if s == 'e':
                aoLkey = 'a/Ln{}'.format(s)
            else:
                aoLkey = 'a/Lni{}'.format(j)
        elif chkey == 'mflux':
            if s == 'e':
                continue
            else:
                aoLkey = 'a*gamma_e/cs'

        # Set neoclassical and turbulent fluxes
        if s == 'e':
            neoKey = '{}_{}_neo'.format(chkey, s)
            turKey = '{}_{}_tur'.format(chkey, s)
        else:
            neoKey = '{}_i{}_neo'.format(chkey, j)
            turKey = '{}_i{}_tur'.format(chkey, j)

        fig, ax = fn.subplots(nrows=nr, ncols=nc, label=chname + '({})'.format(s), sharex=False)
        axf = ax.flatten()
        for i in range(nzones):
            axf[i].plot(output[aoLkey][:, i + 1], output[neoKey][:, i + 1], color='k')
            axf[i].plot(output[aoLkey][:, i + 1], output[turKey][:, i + 1], color='k')
            axf[i].scatter(output[aoLkey][:, i + 1], output[neoKey][:, i + 1], s=40, c='grey', alpha=0.75, edgecolors='None')
            axf[i].scatter(output[aoLkey][:, i + 1], output[turKey][:, i + 1], s=40, c=colorby, alpha=0.75, edgecolors='None')
            axf[i].set_title('$\\rho$={0:0.2f}'.format(output['rho'][0, i + 1]))
            axf[i].axhline(0.0, ls='dashed', color='k')
            axf[i].axvline(0.0, ls='dashed', color='k')
        for i in range(shape(ax)[1]):
            ax[-1, i].set_xlabel(aoLkey)
        for i in range(shape(ax)[0]):
            ax[i, 0].set_ylabel('${}({})$'.format(chtex, s))


fn = FigureNotebook(0, 'TGYRO Flux-Gradient Totals')

for chkey, chsym, chtex, chname, mks in zip(
    ['eflux', 'pflux', 'mflux'],
    ['Q', 'Gamma', 'Pi'],
    ['Q', '\\Gamma', '\\Pi'],
    ['Energy', 'Particles', 'Momentum'],
    ['MW/m^2', 'e19m^2/s', 'J/m^2'],
):
    # j and ei are indicies for electron or ion
    for j, s in zip([0, 1], ['e', 'i']):
        if chkey == 'eflux':
            if s == 'e':
                aoLkey = 'a/Lt{}'.format(s)
            else:
                aoLkey = 'a/Lt{}1'.format(s)
        elif chkey == 'pflux':
            if s == 'e':
                aoLkey = 'a/Ln{}'.format(s)
            else:
                continue
        elif chkey == 'mflux':
            if s == 'e':
                continue
            else:
                aoLkey = 'a*gamma_e/cs'

        tarKey = '{}_{}_target'.format(chkey, s)
        totKey = '{}_{}_tot'.format(chkey, s)
        if chkey == 'mflux':
            tarKey = 'mflux_target'
            totKey = 'mflux_tot'

        fig, ax = fn.subplots(nrows=nr, ncols=nc, label=chname + '({})'.format(s), sharex=False)
        axf = ax.flatten()
        for i in range(nzones):
            for k in range(nit):
                axf[i].axhline(output[tarKey][k, i + 1], color=colors[k], alpha=0.3)
            axf[i].plot(output[aoLkey][:, i + 1], output[totKey][:, i + 1], color='k')
            axf[i].scatter(output[aoLkey][:, i + 1], output[totKey][:, i + 1], s=40, c=colorby, alpha=0.75, edgecolors='None')
            axf[i].set_title('$\\rho$={0:0.2f}'.format(output['rho'][0, i + 1]))
            axf[i].axhline(0.0, ls='dashed', color='k')
            axf[i].axvline(0.0, ls='dashed', color='k')
        for i in range(shape(ax)[1]):
            ax[-1, i].set_xlabel(aoLkey)
        for i in range(shape(ax)[0]):
            ax[i, 0].set_ylabel('${}({})$'.format(chtex, s))
