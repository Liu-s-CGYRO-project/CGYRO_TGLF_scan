# -*-Python-*-
# Created by meneghini at 2013/03/08 18:55

defaultVars(
    param=root['SETTINGS']['PHYSICS']['scanParameter'],
    expGm=nan,
    expQe=nan,
    expQi=nan,
    expPi=nan,
    gbGm=nan,
    gbQ=nan,
    gbPi=nan,
    what=['Gam/Gam_GB', 'Q/Q_GB', 'Pi/Pi_GB'],
    results='scanResults',
    combine_ions=root['SETTINGS']['PHYSICS']['combine_ions'],
    doSave=False,
)

if isinstance(results, str):
    results = root[results]

labels = {'Gam/Gam_GB': r'$\Gamma/\Gamma_{GB}$', 'Q/Q_GB': r'$Q/Q_{GB}$', 'Pi/Pi_GB': r'$\Pi/\Pi_{GB}$'}

species = [k[0] for k in results[param][list(results[param].keys())[0]]]

outlines = []
outlines.append(param + ' ' + '%f ' * len(results[param]) % tuple(results[param].keys()))
outlines.append('')
if not doSave:
    fig, axs = subplots(1, len(what), sharex=True, num=gcf().number)
for k, name in enumerate(what):
    for p2, t in enumerate(species):
        if not combine_ions or (combine_ions and t in ['elec', 'ion1']):
            data, prange = results[param].across("['*'][%d]['%s']" % (p2, name), returnKeys=True)
            data = array(data)
            if t == species[-1] and combine_ions:
                t = 'ions'
        else:
            data += array(results[param].across("['*'][%d]['%s']" % (p2, name)))
            if t != species[-1]:
                continue
            if combine_ions:
                t = 'ions'

        if combine_ions and t not in ['elec', 'ions']:
            continue

        quantity = name
        color = None
        norm = 1.0
        if name == 'Gam/Gam_GB':
            if not isnan(gbGm):
                norm = gbGm
                labels[name] = labels[name].split('/')[0].rstrip('$') + '$'
                quantity = name.split('/')[0]
            if not doSave and not isnan(expGm):
                axs[k].plot(root['FILES']['input.tglf'][param], expGm * norm, marker='*', ms=15)
                color = axs[k].lines[-1].get_color()
        elif name in ['Q/Q_GB', 'Q_low/Q_GB']:
            if t == 'elec':
                expQ = expQe
            else:
                expQ = expQi
            if not isnan(gbQ):
                norm = gbQ
                labels[name] = labels[name].split('/')[0].rstrip('$') + '$'
                quantity = name.split('/')[0]
            if not doSave and not isnan(expQ):
                axs[k].plot(root['FILES']['input.tglf'][param], expQ * norm, marker='*', ms=15)
                color = axs[k].lines[-1].get_color()
        elif name == 'Pi/Pi_GB':
            if not isnan(gbPi):
                norm = gbPi
                labels[name] = labels[name].split('/')[0].rstrip('$') + '$'
                quantity = name.split('/')[0]
            if not doSave and not isnan(expPi):
                axs[k].plot(root['FILES']['input.tglf'][param], expPi * norm, marker='*', ms=15)
                color = axs[k].lines[-1].get_color()

        if not doSave:
            if color is None:
                if is_uncertain(data):
                    uband(prange, data * norm, label=t, marker='.', ls='-', alpha=0.75, ax=axs[k])
                else:
                    axs[k].plot(prange, data * norm, label=t, marker='.', ls='-', alpha=0.75)
            else:
                if is_uncertain(data):
                    uband(prange, data * norm, label=t, color=color, marker='.', ls='-', alpha=0.75, ax=axs[k])
                else:
                    axs[k].plot(prange, data * norm, label=t, color=color, marker='.', ls='-', alpha=0.75)
            axs[k].set_title(labels[name])
            axs[k].axvline(root['FILES']['input.tglf'][param], color='black', ls='--')

        outlines.append(t + ' ' + quantity)
        s = StringIO()
        numpy.savetxt(s, nominal_values(data * norm), fmt='%.5f')
        outlines.append(s.getvalue())

if doSave:
    print('\n'.join(outlines))
    tmp = OMFITascii('scan_' + param + '.txt', fromString='\n'.join(outlines))
    tmp.deployGUI()
else:
    suptitle('Scan of ' + root['SETTINGS']['PHYSICS']['scanParameter'])
    legend(loc=0).draggable(True)
    fig.tight_layout()
    subplots_adjust(left=0.06, right=0.97)
