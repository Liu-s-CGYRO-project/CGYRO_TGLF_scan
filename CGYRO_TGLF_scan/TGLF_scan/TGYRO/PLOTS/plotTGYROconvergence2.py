# -*-Python-*-
# Created by grierson at 03 Aug 2016  13:24

defaultVars(loggb=False, gb=True)

output = root['OUTPUTS']['output']
# Use convergence to define the last iteration
nit = len(output['convergence'])

fn = FigureNotebook(0, 'TGYRO Flux Convergence')
fig, ax = fn.subplots(label='Global Residual')
ax.plot(arange(nit), output['convergence'], marker='o')
ax.set_xlabel('Iteration')
ax.set_ylabel('Residual')
ax.set_yscale('log')
cornernote('%s' % ((root['SETTINGS']['EXPERIMENT']['runid'])), '', ax=ax)

for chkey, chtex, chname, mks in zip(
    ['eflux_e', 'eflux_i', 'pflux_e', 'mflux', 'p', 'p'],
    ['Q_e', 'Q_i', '\\Gamma_e', '\Pi_i', 'S_e', 'S_i'],
    ['Electron Energy', 'Ion Energy', 'Electron Particle', 'Ion Momentum', 'Electron Power Flow', 'Ion Power Flow'],
    ['MW/m^2', 'MW/m^2', 'e19m^2/s', 'J/m^2', 'MW', 'MW'],
):

    if gb:
        if chkey == 'p':
            try:
                scale = 1 / output['{}_GB'.format(chtex.split('_')[0].split('\\')[-1])]
            except KeyError:
                printe('{}'.format(chtex.split('_')[0]) + '_GB is not presently available in this copy of gacode. Using MKS units')
        else:
            scale = np.ones(output['rho'].shape)
    else:
        if chkey == 'p':
            scale = np.ones(output['rho'].shape)
        else:
            scale = output['{}_GB'.format(chtex.split('_')[0].split('\\')[-1])]

    fig, ax = fn.subplots(label=chname)
    c = cm.rainbow_r(linspace(0, 1, len(output['rho'][0, :])))
    if chkey == 'p' and chtex == 'S_e':
        ax.plot(arange(nit), output['{}_e_tot'.format(chkey)][:, 0] * scale[:, 0], marker='o', markersize=0, label='Total', color=c[0])
        ax.plot(
            arange(nit),
            output['{}_e_aux'.format(chkey)][:, 0] * scale[:, 0],
            marker='o',
            markersize=0,
            color=c[0],
            label='Aux',
            linestyle='dashed',
        )
        ax.plot(
            arange(nit),
            output['{}_exch[-]'.format(chkey)][:, 0] * scale[:, 0],
            marker='o',
            markersize=0,
            color=c[0],
            label='Col Exch',
            linestyle='dashdot',
            linewidth=2,
        )
        ax.plot(
            arange(nit),
            output['{}_expwd[-]'.format(chkey)][:, 0] * scale[:, 0],
            marker='o',
            markersize=0,
            color=c[0],
            label='Turb Exc',
            linestyle='dotted',
            linewidth=4,
        )
    if chkey == 'p' and chtex == 'S_i':
        ax.plot(arange(nit), output['{}_i_tot'.format(chkey)][:, 0] * scale[:, 0], marker='o', markersize=0, label='Total', color=c[0])
        ax.plot(
            arange(nit),
            output['{}_i_aux'.format(chkey)][:, 0] * scale[:, 0],
            marker='o',
            markersize=0,
            color=c[0],
            label='Aux',
            linestyle='dashed',
        )
        ax.plot(
            arange(nit),
            output['{}_exch'.format(chkey)][:, 0] * scale[:, 0],
            marker='o',
            markersize=0,
            color=c[0],
            label='Col Exch',
            linestyle='dashdot',
            linewidth=2,
        )
        ax.plot(
            arange(nit),
            output['{}_expwd'.format(chkey)][:, 0] * scale[:, 0],
            marker='o',
            markersize=0,
            color=c[0],
            label='Turb Exc',
            linestyle='dotted',
            linewidth=4,
        )
    for i, r in enumerate(output['rho'][0, :]):
        if chkey != 'p':
            ax.plot(
                arange(nit),
                output['{}_target'.format(chkey)][:, i] * scale[:, i],
                marker='o',
                markersize=2.0,
                label='$\\rho$={0:0.2f}'.format(r),
                color=c[i],
            )
            ax.plot(
                arange(nit), output['{}_tot'.format(chkey)][:, i] * scale[:, i], marker='o', markersize=2.0, color=c[i], linestyle='dashed'
            )
        if chkey == 'p' and chtex == 'S_e':
            ax.plot(
                arange(nit),
                output['{}_e_tot'.format(chkey)][:, i] * scale[:, i],
                marker='o',
                markersize=2.0,
                label='$\\rho$={0:0.2f}'.format(r),
                color=c[i],
            )
            ax.plot(
                arange(nit),
                output['{}_e_aux'.format(chkey)][:, i] * scale[:, i],
                marker='o',
                markersize=2.0,
                color=c[i],
                linestyle='dashed',
            )
            ax.plot(
                arange(nit),
                output['{}_exch[-]'.format(chkey)][:, i] * scale[:, i],
                marker='o',
                markersize=2.0,
                color=c[i],
                linestyle='dashdot',
                linewidth=2,
            )
            ax.plot(
                arange(nit),
                output['{}_expwd[-]'.format(chkey)][:, i] * scale[:, i],
                marker='o',
                markersize=2.0,
                color=c[i],
                linestyle='dotted',
                linewidth=4,
            )
        if chkey == 'p' and chtex == 'S_i':
            ax.plot(
                arange(nit),
                output['{}_i_tot'.format(chkey)][:, i] * scale[:, i],
                marker='o',
                markersize=2.0,
                label='$\\rho$={0:0.2f}'.format(r),
                color=c[i],
            )
            ax.plot(
                arange(nit),
                output['{}_i_aux'.format(chkey)][:, i] * scale[:, i],
                marker='o',
                markersize=2.0,
                color=c[i],
                linestyle='dashed',
            )
            ax.plot(
                arange(nit),
                output['{}_exch'.format(chkey)][:, i] * scale[:, i],
                marker='o',
                markersize=2.0,
                color=c[i],
                linestyle='dashdot',
                linewidth=2,
            )
            ax.plot(
                arange(nit),
                output['{}_expwd'.format(chkey)][:, i] * scale[:, i],
                marker='o',
                markersize=2.0,
                color=c[i],
                linestyle='dotted',
                linewidth=4,
            )
    ax.set_xlabel('Iteration')
    if gb:
        if chkey != 'p':
            ax.set_ylabel('${}$'.format(chtex) + '/${}$'.format(chtex.split('_')[0]) + '$_{GB}$')
        if loggb:
            ax.set_yscale('symlog')
        if chkey == 'p' and chtex == 'S_e':
            if 'S_GB' in output:
                ax.set_ylabel('p_e' + '/${}$'.format(chtex.split('_')[0]) + '$_{GB}$')
            else:
                ax.set_ylabel('p_e' + ' ' + '$({})$'.format(mks))
        if chkey == 'p' and chtex == 'S_i':
            if 'S_GB' in output:
                ax.set_ylabel('p_i' + '/${}$'.format(chtex.split('_')[0]) + '$_{GB}$')
            else:
                ax.set_ylabel('p_i' + ' ' + '$({})$'.format(mks))

    else:
        ax.set_ylabel('${}({})$'.format(chtex, mks))
        if chkey == 'p' and chtex == 'S_e':
            ax.set_ylabel('p_e' + ' ' + '$({})$'.format(mks))
        if chkey == 'p' and chtex == 'S_i':
            ax.set_ylabel('p_i' + ' ' + '$({})$'.format(mks))
    l = ax.legend(loc='upper left')
    l.draggable()
    l.get_frame().set_alpha(0.25)
    cornernote('%s' % ((root['SETTINGS']['EXPERIMENT']['runid'])), '', ax=ax)
