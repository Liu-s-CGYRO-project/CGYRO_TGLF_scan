# -*-Python-*-
# Created by thomek at 27 Sep 2016  16:43

defaultVars(loggb=False, gb=True, nit=None)

fn = FigureNotebook(0, 'TGYRO Flux Convergence')

# Flux convergence
for chkey, chtex, chname, mks in zip(
    ['eflux_e', 'eflux_i', 'pflux_e', 'mflux'],
    ['Q_e', 'Q_i', '\\Gamma_e', '\Pi_i'],
    ['Electron Energy', 'Ion Energy', 'Electron Particle', 'Ion Momentum'],
    ['MW/m^2', 'MW/m^2', 'e19m^2/s', 'J/m^2'],
):
    ls = ['--', '-.', ':', '--', '-.', ':', '--', '-.', ':']
    mk = ['^', 's', 'D', 'x', '.', 'v', '8', '+', '*']
    th = [2, 3, 3, 2, 3, 3, 2, 3, 3]

    fig, ax = fn.subplots(label=chname)
    for k, run in enumerate(scratch['plot_runids']):
        output = root['RUN_DB'][run]['OUTPUTS']['output']
        c = cm.rainbow_r(linspace(0, 1, len(output['rho'][0, :])))
        nit = len(output['convergence'])
        if k >= len(mk):
            printi('This will plot only {} runs at once'.format(len(mk)))
        else:
            if gb:
                scale = np.ones(output['rho'].shape)
            else:
                scale = output['{}_GB'.format(chtex.split('_')[0].split('\\')[-1])]

            for i, r in enumerate(output['rho'][0, :]):
                if i == 0:
                    if k == 0:
                        ax.plot(
                            arange(nit), output['{}_tot'.format(chkey)][:, i] * scale[:, i], linestyle='', label='Run IDs', linewidth=0.0
                        )  # Legend label
                    ax.plot(
                        arange(nit),
                        output['{}_tot'.format(chkey)][:, i] * scale[:, i],
                        marker=mk[k],
                        color=c[i],
                        linestyle=ls[k],
                        label=run,
                        linewidth=th[k],
                    )  # Legend label
                else:
                    ax.plot(
                        arange(nit),
                        output['{}_tot'.format(chkey)][:, i] * scale[:, i],
                        marker=mk[k],
                        markersize=4.0,
                        color=c[i],
                        linestyle=ls[k],
                        linewidth=th[k],
                    )  # TGYRO fluxes
                if k == (len(scratch['plot_runids']) - 1):
                    if i == 0:
                        ax.plot(
                            arange(nit),
                            output['{}_target'.format(chkey)][:, i] * scale[:, i],
                            label='Target Fluxes'.format(r),
                            color=c[i],
                            linestyle='',
                            linewidth=0,
                        )  # Legend label
                    ax.plot(
                        arange(nit),
                        output['{}_target'.format(chkey)][:, i] * scale[:, i],
                        marker='o',
                        markersize=4.0,
                        label='$\\rho$={0:0.2f}'.format(r),
                        color=c[i],
                        linestyle='-',
                    )  # Target Flux
                    ax.set_xlabel('Iteration')
                    if gb:
                        ax.set_ylabel('${}$'.format(chtex) + '/${}$'.format(chtex.split('_')[0]) + '$_{GB}$')
                        if loggb:
                            ax.set_yscale('symlog')
                    else:
                        ax.set_ylabel('${}({})$'.format(chtex, mks))

    l = ax.legend(loc='upper left')
    l.draggable()
