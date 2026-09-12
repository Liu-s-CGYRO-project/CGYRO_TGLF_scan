# -*-Python-*-
# Created by smithsp at 2013/06/14 10:52

defaultVars(output=root['OUTPUTS']['output'], iterations=None)
if iterations is None:
    if output['eflux_e_tot'].shape[0] > 1:
        iterations = [0, -1]
    else:
        iterations = [0]
elif not iterable(iterations):
    iterations = [iterations]

fig, axs = subplots(len(iterations), 2, sharex=True, squeeze=False, sharey=False, num=gcf().number)

fig.suptitle('Fluxes in GyroBohm units:')
axs.flat[0].set_title('Ion Energy Fluxes')
axs.flat[1].set_title('Electron Energy Fluxes')
x = output.sprofile('r/a')
x0 = output['r/a'][0, :]
colors = rcParams['axes.prop_cycle'].by_key()['color']
for row, place in enumerate(iterations):
    place = list(range(0, output['eflux_e_tot'].shape[0]))[place]
    for yi, yv in enumerate(['i', 'e']):
        sca(axs[row, yi])
        if yi == 0:
            gca().set_ylabel('Iteration #%s' % place)
        for q, ql in [('tot', 'Total'), ('target', 'Target')]:
            y0 = output['eflux_%s_%s' % (yv, q)][place, :]
            y = interp(x, x0, y0)
            ls = '-'
            if q == 'target':
                ls = '--'
            semilogy(x, y, label=ql, ls=ls, color='black')
        for q, ql in [('neo', 'Neo'), ('tur', 'Turbulent')]:
            for spec in range(1, 6):
                spec_str = str(spec)
                if spec == 1:
                    spec_str = ''
                tag = 'eflux_%s_%s%s' % (yv, q, spec_str)
                if tag not in output:
                    # print('%s not in output'%tag)
                    continue
                y0 = output[tag][place, :]
                y = interp(x, x0, y0)
                ls = '-'
                if q == 'neo':
                    ls = '-.'
                semilogy(x, y, label=ql + spec_str, color=colors[spec], ls=ls)
        yscale('symlog')
        legend(loc='upper left').draggable(True)
