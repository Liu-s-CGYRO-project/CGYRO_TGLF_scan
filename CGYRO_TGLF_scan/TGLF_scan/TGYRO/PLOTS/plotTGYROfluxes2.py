# -*-Python-*-
# Created by grierson at 03 Aug 2016  07:28

# Plot the flux profiles in GB or MKS units
# Each panel is initial and final fluxes in first and
# second row, respectively.

defaultVars(loggb=False, gb=True, nit=None)

input = root['INPUTS']['input.tgyro']
output = root['OUTPUTS']['output']
# Use convergence to define the last iteration
if nit is None:
    nit = len(output['convergence']) - 1

fn = FigureNotebook(0, 'TGYRO Flux Matching')

for chkey, chsym, chtex, chname, mks in zip(
    ['eflux', 'pflux', 'mflux', 'p'],
    ['Q', 'Gamma', 'Pi', 'S'],
    ['Q', '\\Gamma', '\\Pi', 'P'],
    ['Energy', 'Particles', 'Momentum', 'Power Flow'],
    ['MW/m^2', 'e19m^2/s', 'J/m^2', 'MW'],
):
    fig, ax = fn.subplots(2, 2, label=chname, sharex=False)
    title = ['Initial Iteration #0', 'Final Iteration #{}'.format(nit)]
    # i and it are indicies for iteration
    for i, it in enumerate([0, nit]):
        if gb:
            if chkey == 'p':
                try:
                    scale = 1 / output['{}_GB'.format(chsym)][it, :]
                except KeyError:
                    printe('{}'.format(chsym) + '_GB is not presently available in this copy of gacode. Using MKS units')
            else:
                scale = np.ones(output['rho'].shape[1])
        else:
            if chkey == 'p':
                scale = np.ones(output['rho'].shape[1])
            else:
                scale = output['{}_GB'.format(chsym)][it, :]
        # j and ei are indicies for electron or ion
        for j, ei in zip([0, 1], ['e', 'i']):
            if ei == 'e':
                slab = 'e'
            else:
                # Primary ion name
                slab = PROFILES_GEN['OUTPUTS']['input.gacode']['IONS'][1][0]
            # Momentum flux is only target and total (because it's all ion)
            if chkey == 'mflux':
                target_key = '{}_target'.format(chkey)
                tot_key = '{}_tot'.format(chkey)
            else:
                target_key = '{}_{}_target'.format(chkey, ei)
                tot_key = '{}_{}_tot'.format(chkey, ei)
            # Particle flux is only for electrons and momentum flux is only for ions
            if chkey == 'eflux' or (chkey == 'pflux' and ei == 'e') or (chkey == 'mflux' and ei == 'i'):
                ax[i, j].plot(output['rho'][it, :], output[target_key][it, :] * scale, marker='o', mfc='None', color='grey', label='Target')
                ax[i, j].plot(
                    output['rho'][it, :], output[tot_key][it, :] * scale, marker='o', markersize=2.0, color='black', label='Total'
                )
            if chkey != 'p' and ei == 'e':
                ax[i, j].plot(output['rho'][it, :], output['{}_{}_tur'.format(chkey, ei)][it, :] * scale, label='Turb({})'.format(slab))
                ax[i, j].plot(output['rho'][it, :], output['{}_{}_neo'.format(chkey, ei)][it, :] * scale, label='Neo({})'.format(slab))
            if ei == 'i':
                for s in range(1, input['LOC_N_ION'] + 1):
                    if input['TGYRO_THERM_FLAG{}'.format(s)] and chkey != 'p':
                        slab = PROFILES_GEN['OUTPUTS']['input.gacode']['IONS'][s][0]
                        ax[i, j].plot(
                            output['rho'][it, :], output['{}_{}{}_tur'.format(chkey, ei, s)][it, :] * scale, label='Turb({})'.format(slab)
                        )
                        ax[i, j].plot(
                            output['rho'][it, :], output['{}_{}{}_neo'.format(chkey, ei, s)][it, :] * scale, label='Neo({})'.format(slab)
                        )
            if chkey == 'p' and ei == 'e':
                ax[i, j].plot(output['rho'][it, :], output['{}_{}_tot'.format(chkey, ei)][it, :] * scale, label='Total({})'.format(slab))
                ax[i, j].plot(output['rho'][it, :], output['{}_{}_aux'.format(chkey, ei)][it, :] * scale, label='Aux({})'.format(slab))
                ax[i, j].plot(output['rho'][it, :], output['{}_exch[-]'.format(chkey)][it, :] * scale, label='Col Exc({})'.format(slab))
                ax[i, j].plot(output['rho'][it, :], output['{}_expwd[-]'.format(chkey)][it, :] * scale, label='Tur Exc({})'.format(slab))
                ax[i, j].plot(output['rho'][it, :], output['{}_brem'.format(chkey)][it, :] * scale, label='Brem({})'.format(slab))
                ax[i, j].plot(output['rho'][it, :], output['{}_sync'.format(chkey)][it, :] * scale, label='Sync({})'.format(slab))
                ax[i, j].plot(output['rho'][it, :], output['{}_line'.format(chkey)][it, :] * scale, label='Line({})'.format(slab))
                ax[i, j].plot(output['rho'][it, :], output['{}_{}_fus'.format(chkey, ei)][it, :] * scale, label='Fusion({})'.format(slab))
            if chkey == 'p' and ei == 'i':
                ax[i, j].plot(output['rho'][it, :], output['{}_{}_tot'.format(chkey, ei)][it, :] * scale, label='Total({})'.format(slab))
                ax[i, j].plot(output['rho'][it, :], output['{}_{}_aux'.format(chkey, ei)][it, :] * scale, label='Aux({})'.format(slab))
                ax[i, j].plot(output['rho'][it, :], output['{}_exch'.format(chkey)][it, :] * scale, label='Col Exc({})'.format(slab))
                ax[i, j].plot(output['rho'][it, :], output['{}_expwd'.format(chkey)][it, :] * scale, label='Tur Exc({})'.format(slab))
                ax[i, j].plot(output['rho'][it, :], output['{}_{}_fus'.format(chkey, ei)][it, :] * scale, label='Fusion({})'.format(slab))
            ax[i, j].set_title(title[i])
            if i:
                ax[i, j].set_xlabel('$\\rho$')
            if gb:
                if chkey != 'p':
                    ax[i, j].set_ylabel('${}_{}$'.format(chtex, ei) + '$/{}$'.format(chtex) + '$_{GB}$')
                else:
                    if 'S_GB' not in output:
                        ax[i, j].set_ylabel('${}_{}({})$'.format(chtex, ei, mks))
                    else:
                        ax[i, j].set_ylabel('${}_{}$'.format(chtex, ei) + '$/{}$'.format(chsym) + '$_{GB}$')
                if loggb:
                    ax[i, j].set_yscale('symlog')
            else:
                ax[i, j].set_ylabel('${}_{}({})$'.format(chtex, ei, mks))
            l = ax[i, j].legend(loc='best')
            l.draggable()
            cornernote('%s' % ((root['SETTINGS']['EXPERIMENT']['runid'])), '', ax=ax[i, j])
