# -*-Python-*-
# Created by thomek at 27 Sep 2016  16:43

import matplotlib.patches as mpatches

defaultVars(loggb=False, gb=True, nit=None)

fn = FigureNotebook(0, 'TGYRO Flux Matching')

for chkey, chtex, chname, mks in zip(
    ['eflux_e', 'eflux_i', 'pflux_e', 'pflux_i', 'mflux_e', 'mflux_i', 'p_e', 'p_i'],
    ['Q_e', 'Q_i', '\\Gamma_e', '\\Gamma_i', '\Pi_e', '\Pi_i', 'S_e', 'S_i'],
    [
        'Electron Energy',
        'Ion Energy',
        'Electron Particle',
        'Ion Particle',
        'Electron Momentum',
        'Ion Momentum',
        'Electron Power Flow',
        'Ion Power Flow',
    ],
    ['MW/m^2', 'MW/m^2', 'e19m^2/s', 'e19m^2/s', 'J/m^2', 'J/m^2', 'MW', 'MW'],
):

    ls = ['-', '--', ':', '-.']
    th = [2, 2, 3, 3]
    fig, ax = fn.subplots(label=chname)
    title = ['Final Iteration Comparison']

    for i, run in enumerate(scratch['plot_runids']):
        j = i - int(4 * floor(i / 4))
        input = root['RUN_DB'][run]['PROFILES_GEN']['input.gacode']
        input_tgyro = root['RUN_DB'][run]['INPUTS']['input.tgyro']
        output = root['RUN_DB'][run]['OUTPUTS']['output']

        output['eflux_i_neo'] = output['eflux_i1_neo']
        output['eflux_i_tur'] = output['eflux_i1_tur']
        output['pflux_i_neo'] = output['pflux_i1_neo']
        output['pflux_i_tur'] = output['pflux_i1_tur']
        output['mflux_i_neo'] = output['mflux_i1_neo']
        output['mflux_i_tur'] = output['mflux_i1_tur']

        nit = len(output['convergence']) - 1
        if len(scratch['plot_runids']) > 5:
            c = cm.rainbow_r(linspace(0, 1, len(scratch['plot_runids'])))
        else:
            c = default_matplotlib_line_cycle

        if gb:
            if chkey == 'p_e' or chkey == 'p_i':
                try:
                    scale = 1 / output['{}_GB'.format(chtex.split('_')[0].split('\\')[-1])][nit, :]
                except KeyError:
                    printe('{}'.format(chkey) + '_GB is not presently available in this copy of gacode. Using MKS units')
            else:
                scale = np.ones(output['rho'].shape[1])
        else:
            if chkey == 'p_e' or chkey == 'p_i':
                scale = np.ones(output['rho'].shape[1])
            else:
                scale = output['{}_GB'.format(chtex.split('_')[0].split('\\')[-1])][nit, :]

        if chkey != 'p_i' and chkey != 'p_e':  # Normal power flow plots

            if chkey == 'mflux_i':
                tot_key = 'mflux_tot'
                target_key = 'mflux_target'
                ax.plot(output['rho'][nit, :], output[tot_key][nit, :] * scale, color=c[i], linestyle='-', label=run, linewidth=1)
            elif chkey != 'pflux_i' and chkey != 'mflux_e':
                tot_key = '{}_tot'.format(chkey)
                target_key = '{}_target'.format(chkey)
                ax.plot(output['rho'][nit, :], output[tot_key][nit, :] * scale, color=c[i], linestyle='-', label=run, linewidth=1)
            else:
                ax.plot(
                    output['rho'][nit, :],
                    output['{}_tur'.format(chkey)][nit, :] * scale,
                    color=c[i],
                    linestyle='--',
                    label=run,
                    linewidth=2,
                )

            if chkey in ('eflux_e', 'pflux_e', 'mflux_e'):
                slab = 'e'
            else:
                # Primary ion name
                slab = input['IONS'][1][0]  # this assumes that the ion order/number isnt changing

            if i == (len(scratch['plot_runids']) - 1):
                if chkey != 'pflux_i' and chkey != 'mflux_e':
                    ax.plot(output['rho'][nit, :], output[tot_key][nit, :] * scale, linestyle='', label='Fluxes')  # Legend Label
                    ax.plot(
                        output['rho'][nit, :], output[target_key][nit, :] * scale, color='black', label='Target', linewidth=2
                    )  # Target from last run,hopefully all the same
                    ax.plot(
                        output['rho'][nit, :], output[tot_key][nit, :] * scale, color=c[i], linestyle='-', label='Total', linewidth=1
                    )  # All total fluxes
                ax.plot(
                    output['rho'][nit, :],
                    output['{}_tur'.format(chkey)][nit, :] * scale,
                    color=c[i],
                    linestyle='--',
                    label='Tur({})'.format(slab),
                    linewidth=2,
                )
                ax.plot(
                    output['rho'][nit, :],
                    output['{}_neo'.format(chkey)][nit, :] * scale,
                    color=c[i],
                    linestyle=':',
                    label='Neo({})'.format(slab),
                    linewidth=2,
                )
            else:
                ax.plot(output['rho'][nit, :], output['{}_tur'.format(chkey)][nit, :] * scale, color=c[i], linestyle='--', linewidth=2)
                ax.plot(output['rho'][nit, :], output['{}_neo'.format(chkey)][nit, :] * scale, color=c[i], linestyle=':', linewidth=2)

            if chkey == 'eflux_i' or chkey == 'pflux_i' or chkey == 'mflux_i':  # Plot other ions turb and neo fluxes
                for s in range(2, input_tgyro['LOC_N_ION'] + 1):
                    for fmt in ['{}_tur{}', '{}_i{}_tur']:
                        if '{}_tur{}'.format(chkey, s) not in output:
                            continue
                        if input_tgyro['TGYRO_THERM_FLAG{}'.format(s)]:
                            slab = input['IONS'][s][0]
                            ax.plot(
                                output['rho'][nit, :],
                                output['{}_tur{}'.format(chkey, s)][nit, :] * scale,
                                linewidth=2,
                                color=c[i],
                                linestyle='--',
                            )
                            ax.plot(
                                output['rho'][nit, :],
                                output['{}_neo{}'.format(chkey, s)][nit, :] * scale,
                                linewidth=2,
                                color=c[i],
                                linestyle=':',
                            )
                        if i == (len(scratch['plot_runids']) - 1) and s == 2:
                            ax.plot(
                                output['rho'][nit, :],
                                output['{}_tur{}'.format(chkey, s)][nit, :] * scale,
                                label='Turb({})'.format(slab),
                                linewidth=4,
                                color=c[i],
                                linestyle='--',
                            )
                            ax.plot(
                                output['rho'][nit, :],
                                output['{}_neo{}'.format(chkey, s)][nit, :] * scale,
                                label='Neo({})'.format(slab),
                                linewidth=4,
                                color=c[i],
                                linestyle=':',
                            )

        elif chkey == 'p_e':  # Electron power flow plot
            ax.plot(
                output['rho'][nit, :], output['{}_tot'.format(chkey)][nit, :] * scale, label=run, color=c[i], linestyle='-', linewidth=1
            )
            if i != (len(scratch['plot_runids']) - 1):
                ax.plot(output['rho'][nit, :], output['{}_aux'.format(chkey)][nit, :] * scale, color=c[i], linestyle='--', linewidth=1)
                ax.plot(
                    output['rho'][nit, :],
                    output['{}_exch[-]'.format(chkey.split('_')[0].split('\\')[-1])][nit, :] * scale,
                    color=c[i],
                    linestyle=':',
                    linewidth=2,
                )
                ax.plot(
                    output['rho'][nit, :],
                    output['{}_expwd[-]'.format(chkey.split('_')[0].split('\\')[-1])][nit, :] * scale,
                    color=c[i],
                    linestyle='-.',
                    linewidth=2,
                )
            else:
                ax.plot(
                    output['rho'][nit, :],
                    output['{}_tot'.format(chkey)][nit, :] * scale,
                    label='Total({})'.format(slab),
                    color=c[i],
                    linestyle='-',
                    linewidth=1,
                )
                ax.plot(
                    output['rho'][nit, :],
                    output['{}_aux'.format(chkey)][nit, :] * scale,
                    label='Aux({})'.format(slab),
                    color=c[i],
                    linestyle='--',
                    linewidth=1,
                )
                ax.plot(
                    output['rho'][nit, :],
                    output['{}_exch[-]'.format(chkey.split('_')[0].split('\\')[-1])][nit, :] * scale,
                    label='Col Exc({})'.format(slab),
                    color=c[i],
                    linestyle=':',
                    linewidth=2,
                )
                ax.plot(
                    output['rho'][nit, :],
                    output['{}_expwd[-]'.format(chkey.split('_')[0].split('\\')[-1])][nit, :] * scale,
                    label='Tur Exc({})'.format(slab),
                    color=c[i],
                    linestyle='-.',
                    linewidth=2,
                )

        elif chkey == 'p_i':  # Ion power flot plot
            ax.plot(
                output['rho'][nit, :], output['{}_tot'.format(chkey)][nit, :] * scale, label=run, color=c[i], linestyle='-', linewidth=1
            )
            if i != (len(scratch['plot_runids']) - 1):
                ax.plot(output['rho'][nit, :], output['{}_aux'.format(chkey)][nit, :] * scale, color=c[i], linestyle='--', linewidth=1)
                ax.plot(
                    output['rho'][nit, :],
                    output['{}_exch[-]'.format(chkey.split('_')[0].split('\\')[-1])][nit, :] * scale,
                    color=c[i],
                    linestyle=':',
                    linewidth=2,
                )
                ax.plot(
                    output['rho'][nit, :],
                    output['{}_expwd[-]'.format(chkey.split('_')[0].split('\\')[-1])][nit, :] * scale,
                    color=c[i],
                    linestyle='-.',
                    linewidth=2,
                )
            else:
                ax.plot(
                    output['rho'][nit, :],
                    output['{}_tot'.format(chkey)][nit, :] * scale,
                    label='Total({})'.format(slab),
                    color=c[i],
                    linestyle='-',
                    linewidth=1,
                )
                ax.plot(
                    output['rho'][nit, :],
                    output['{}_aux'.format(chkey)][nit, :] * scale,
                    label='Aux({})'.format(slab),
                    color=c[i],
                    linestyle='--',
                    linewidth=1,
                )
                ax.plot(
                    output['rho'][nit, :],
                    output['{}_exch[-]'.format(chkey.split('_')[0].split('\\')[-1])][nit, :] * scale,
                    label='Col Exc({})'.format(slab),
                    color=c[i],
                    linestyle=':',
                    linewidth=2,
                )
                ax.plot(
                    output['rho'][nit, :],
                    output['{}_expwd[-]'.format(chkey.split('_')[0].split('\\')[-1])][nit, :] * scale,
                    label='Tur Exc({})'.format(slab),
                    color=c[i],
                    linestyle='-.',
                    linewidth=2,
                )

        ax.set_xlabel('$\\rho$')
        if gb:
            ax.set_ylabel('${}$'.format(chtex) + '$/{}$'.format(chtex) + '$_{GB}$')
            if loggb:
                ax.set_yscale('symlog')
        else:
            ax.set_ylabel('${}({})$'.format(chtex, mks))
        patch = [mpatches.Patch(alpha=0)]
        handles, labels = ax.get_legend_handles_labels()
        handles = patch + handles
        labels = ['Run IDs'] + labels
        l = ax.legend(handles, labels, loc='best')
        l.draggable()
