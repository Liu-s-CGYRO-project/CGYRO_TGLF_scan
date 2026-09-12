# -*-Python-*-
# Created by smithsp at 2013/06/14 15:42

defaultVars(output=root['OUTPUTS']['output'], what=['Te', 'Ti', 'ne', 'm'])

n_it, n_rad = output['te'].shape
nc = max(1, int(n_rad**0.5))
nr = max(1, (n_rad + nc - 1) // nc)

fig, axs = subplots(nr, nc, num=gcf().number, squeeze=False, sharex=True)
fig.suptitle('Flux Convergence')
eflux_e_target = output['eflux_e_target']
eflux_i_target = output['eflux_i_target']
eflux_e_tot = output['eflux_e_tot']
eflux_i_tot = output['eflux_i_tot']
for ir in range(n_rad):
    ax = axs.flat[ir]
    ax.text(0.5, 0.95, r'$\rho=%2.2f$' % (output['rho'][0, ir]), ha='center', va='top', transform=ax.transAxes)
    for spec, color in zip(['e', 'i'], ['blue', 'red']):
        if 'T' + spec in what:
            for q, ls in zip(['target', 'tot'], ['--', '-']):
                ax.plot(output['eflux_%s_%s' % (spec, q)][:, ir], color=color, ls=ls, label='Energy %s %s' % (spec, q))
    if 'm' in what:
        for q, ls in zip(['target', 'tot'], ['--', '-']):
            ax.plot(output['mflux_%s' % q][:, ir], color='green', ls=ls, label='Momentum Flux %s' % q)
    if 'ne' in what:
        for q, ls in zip(['target', 'tot'], ['--', '-']):
            ax.plot(output['pflux_e_%s' % q][:, ir], color='cyan', ls=ls, label='Particle Flux %s' % q)
    if ir == 0:
        ax.legend(loc='lower center').draggable(True)
fig.tight_layout()
