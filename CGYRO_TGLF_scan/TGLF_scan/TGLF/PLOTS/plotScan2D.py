# -*-Python-*-
# Created by meneghini at 2015/03/28 13:52

defaultVars(
    param=root['SETTINGS']['PHYSICS']['scanParameter'],
    param2=root['SETTINGS']['PHYSICS']['scanParameter2D'],
    expGm=nan,
    expQe=nan,
    expQi=nan,
    expPi=nan,
    gbGm=nan,
    gbQ=nan,
    gbPi=nan,
    what=['Gam/Gam_GB', 'Q/Q_GB', 'Pi/Pi_GB'],
    results='scanResults2D',
    combine_ions=root['SETTINGS']['PHYSICS']['combine_ions'],
    doSave=False,
    plot_contours=False,
)


if isinstance(results, str):
    results = root[results]
results = results[param2 + '+' + param]

labels = {'Gam/Gam_GB': r'$\Gamma/\Gamma_{GB}$', 'Q/Q_GB': r'$Q/Q_{GB}$', 'Pi/Pi_GB': r'$\Pi/\Pi_{GB}$'}

species = list(results.values())[0].values()[0]['.']


def add_exp_text(exp_num, nom_val):
    if isfinite(nom_val):
        text(
            0.5,
            0.95,
            'Exp  %.2g\n%.0f%s' % (exp_num, (exp_num - nom_val) / exp_num * 100, '%'),
            va='top',
            ha='center',
            transform=gca().transAxes,
            color='white',
            weight='bold',
        )


x = array(list(results.keys()))
y = array(list(results[x[0]].keys()))
data = zeros((len(x), len(y)))
elec_ind = list(species).index('elec')


def plot_data(col, row, data, nrows, elec=False, norm=1, name=what[0]):
    if plot_contours:
        CS = contourf(x, y, data.T, rasterized=True)
    else:
        CS = pcolormesh(x, y, data.T, rasterized=True)

    colorbar(CS)

    gcf().set_size_inches(12, 6)

    axis('tight')
    if col == 0:
        ylabel('(' + t + ')\n' + param)
    if row == 0:
        title(labels[name])
    if row == nrows - 1:
        xlabel(param2)
    val1 = root['FILES']['input.tglf'][param]
    val2 = root['FILES']['input.tglf'][param2]
    axhline(val1, color='w', ls='-')
    axvline(val2, color='w', ls='-')
    axhline(val1, color='k', ls='--')
    axvline(val2, color='k', ls='--')

    nom_val = np.nan
    exp_val = np.nan
    if val2 in x and val1 in y:
        nom_val = data[x == val2, y == val1][0]

    ls = '-' if elec else '--'
    if name == 'Gam/Gam_GB':
        exp_val = expGm * norm
    elif name == 'Q/Q_GB' and elec:

        exp_val = expQe * norm
    elif name == 'Q/Q_GB' and not elec:

        exp_val = expQi * norm
    elif name == 'Pi/Pi_GB':
        exp_val = expPi * norm

    if isfinite(exp_val):
        add_exp_text(exp_val, nom_val)
        contour(
            x,
            y,
            data.T,
            levels=[exp_val],
            colors='w',
            linewidths=2,
            linestyles=ls,
        )


def print_data(outlines, species, quantity, data):
    outlines.append(species + ' ' + quantity)
    s = StringIO()
    numpy.savetxt(s, data, fmt='%.5f')
    outlines.append(s.getvalue())


outlines = []
outlines.append(param2 + ' ' + '%f ' * len(results) % tuple(results.keys()))
outlines.append(param + ' ' + '%f ' * len(list(results.values())[0]) % tuple(list(results.values())[0].keys()))
outlines.append('')

if not doSave:
    nrow = 2 if combine_ions else len(species)

    axes = gcf().subplots(nrow, len(what), sharex=True, sharey=True, squeeze=False)

for p1, name in enumerate(what):

    quantity = name

    norm = 1.0

    if name == 'Gam/Gam_GB' and not isnan(gbGm):
        norm = gbGm
        labels[name] = labels[name].split('/')[0] + '$'
        quantity = name.split('/')[0]
    elif name in ['Q/Q_GB', 'Q_low/Q_GB'] and not isnan(gbQ):
        norm = gbQ
        labels[name] = labels[name].split('/')[0] + '$'
        quantity = name.split('/')[0]
    elif name == 'Pi/Pi_GB' and not isnan(gbPi):
        norm = gbPi
        labels[name] = labels[name].split('/')[0] + '$'
        quantity = name.split('/')[0]

    if not combine_ions:
        for p2, t in enumerate(species):
            for k1, i1 in enumerate(results):
                for k2, i2 in enumerate(results[i1]):
                    data[k1, k2] = nominal_values(results[i1][i2][name][p2]) * norm

            if doSave:
                print_data(outlines, t, quantity, data)
            else:
                sca(axes[p2, p1])
                plot_data(p1, p2, data, len(species), elec=('elec' in t), norm=norm, name=name)

    else:
        p2 = elec_ind
        t = species[p2]
        for k1, i1 in enumerate(results):
            for k2, i2 in enumerate(results[i1]):
                data[k1, k2] = nominal_values(results[i1][i2][name][p2]) * norm
        if doSave:
            print_data(outlines, t, quantity, data)
        else:
            sca(axes[0, p1])
            plot_data(p1, 0, data, 2, True, norm=norm, name=name)

        data[:, :] = 0
        for p2, t in enumerate(species):
            if 'elec' in t:
                continue
            t = 'ions'
            for k1, i1 in enumerate(results):
                for k2, i2 in enumerate(results[i1]):
                    data[k1, k2] = data[k1, k2] + nominal_values(results[i1][i2][name][p2]) * norm
        if doSave:
            print_data(outlines, t, quantity, data)
        else:
            sca(axes[1, p1])
            plot_data(p1, 1, data, 2, False, norm=norm, name=name)

if doSave:
    print('\n'.join(outlines))
    tmp = OMFITascii('scan2D_' + param + '+' + param2 + '.txt', fromString='\n'.join(outlines))
    tmp.deployGUI()
else:
    autofmt_sharexy()
    tight_layout()
