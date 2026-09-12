# -*-Python-*-
# Created by meneghini at 2015/02/11 22:06

defaultVars(deadstart=False, verbose=False, test=True)

if test:
    verbose = True

if deadstart and not test:
    root['SCRIPTS']['run_profiles_gen'].run(gEQDSK=EPED['OUTPUTS']['gEQDSK'], profpowbal=None)

if verbose:
    figure()
    import matplotlib.transforms as mtransforms

    def plot_regions(showText):
        trans = mtransforms.blended_transform_factory(gca().transData, gca().transAxes)
        fill_between(rho, 0, 1, where=(rho_core <= rho) & (rho <= rho_nml), facecolor='blue', alpha=0.1, transform=trans)
        fill_between(rho, 0, 1, where=rho >= rho_ped, facecolor='red', alpha=0.1, transform=trans)
        axvline(rho_core, ls='--', color='gray')
        if showText:
            text((0.0 + rho_core) / 2.0, ylim()[1] * 1.05, 'CORE', horizontalalignment='center', fontsize=10, color='k')
            txt = 'GUESS'
        if rho_nml > 0:
            axvline(rho_nml, ls='--', color='gray')
            if showText:
                text((rho_core + rho_nml) / 2.0, ylim()[1] * 1.05, 'TGLF', horizontalalignment='center', fontsize=10, color='k')
                txt = 'NML'
        axvline(rho_ped, ls='--', color='gray')
        if showText:
            text((max([rho_core, rho_nml]) + rho_ped) / 2.0, ylim()[1] * 1.05, txt, horizontalalignment='center', fontsize=10, color='k')
            text((rho_ped + 1.0) / 2.0, ylim()[1] * 1.05, 'EPED', horizontalalignment='center', fontsize=10, color='k')


e_19 = constants.e * 1e19

if deadstart:
    tmp = {}
    tmp.update(EPED['PROFILES'])
    tmp['Te'] = tmp['ptot'] / e_19 * 1e19 / 1e3 / 2.0
    tmp['ni_1'] = tmp['ne']
    tmp['Ti_1'] = tmp['Te']
    merge_profiles = [('ne', 1e19, 'e'), ('Te', 1, 'e'), ('ni_1', 1e19, 'D'), ('Ti_1', 1, 'D')]
    if not test:
        root['OUTPUTS']['input.gacode']['IONS'][1] = ['D', 1, 2.0, 'therm']

else:
    # Here we decide how to redistribute pressure/density among species
    # from ne, ptot of EPED to density and temperatures for individual species
    # by keeping the original ratios of densities and pressures at rho_nml
    i = int(max([root['SETTINGS']['PHYSICS']['rho_nml'], 0.8]) * len(root['OUTPUTS']['input.gacode_base']['ne']))
    normp = {}
    normn = {}
    normt = {}
    for k in range(1, 11):
        if k in root['OUTPUTS']['input.gacode_base']['IONS'] and root['OUTPUTS']['input.gacode_base']['IONS'][k][3] == 'therm':
            pp = root['OUTPUTS']['input.gacode_base']['ni_%d' % k] * root['OUTPUTS']['input.gacode_base']['Ti_%d' % k] * e_19 * 1e3
            normp[k] = (pp / root['OUTPUTS']['input.gacode_base']['ptot'])[i]
            normn[k] = (root['OUTPUTS']['input.gacode_base']['ni_%d' % k] / root['OUTPUTS']['input.gacode_base']['ne'])[i]
            normt[k] = (root['OUTPUTS']['input.gacode_base']['Ti_%d' % k] / root['OUTPUTS']['input.gacode_base']['Te'])[i]
    normp[0] = (
        root['OUTPUTS']['input.gacode_base']['ne']
        * root['OUTPUTS']['input.gacode_base']['Te']
        * e_19
        * 1e3
        / root['OUTPUTS']['input.gacode_base']['ptot']
    )[i]

    # "EPED" profiles for each thermal species
    merge_profiles = [('ne', 1e19, 'e'), ('Te', 1, 'e')]
    tmp = {}
    tmp['Pe'] = EPED['PROFILES']['ptot'] * normp[0]
    tmp['ne'] = EPED['PROFILES']['ne']
    tmp['Te'] = tmp['Pe'] / tmp['ne'] / e_19 * 1e19 / 1e3
    for k in normn:
        tmp['Pi_%d' % k] = EPED['PROFILES']['ptot'] * normp[k]
        tmp['ni_%d' % k] = tmp['ne'] * normn[k]
        tmp['Ti_%d' % k] = tmp['Pi_%d' % k] / tmp['ni_%d' % k] / e_19 * 1e19 / 1e3
        name = root['OUTPUTS']['input.gacode_base']['IONS'][k][0]
        merge_profiles.extend([('ni_%d' % k, 1e19, name), ('Ti_%d' % k, 1, name)])

# for k in tmp:
#    figure(num=k[0])
#    plot(tmp[k],label=k)
#    legend(loc=0)

# merge profiles
for kk, (what, norm, name) in enumerate(merge_profiles):
    print(what)
    x1 = EPED['PROFILES']['rho']
    y1 = tmp[what] / norm
    z1 = calcz(x1, y1)

    if not (deadstart and test):
        x0 = rho = root['OUTPUTS']['input.gacode_base']['rho']
        y0 = root['OUTPUTS']['input.gacode_base'][what]
        z0 = calcz(x0, y0)
    else:
        x0 = rho = x1
        y0 = y1
        z0 = z1

    if deadstart:
        rho_nml = 0
    else:
        rho_nml = rho[argmin(abs(rho - root['SETTINGS']['PHYSICS']['rho_nml']))]
    rho_core = rho[argmin(abs(rho - root['SETTINGS']['PHYSICS']['rho_core']))]
    rho_ped = rho[argmin(abs(rho - root['SETTINGS']['PHYSICS']['rho_ped']))]
    pivot = max([0.8, rho_ped])

    xm, zm = mergez(x0, z0, x1, z1, rho_core, rho_nml, rho_ped, rho)
    y = integz(xm, zm, pivot, interp1e(x1, y1)(pivot), rho)
    if not test:
        root['OUTPUTS']['input.gacode'][what] = y

    # plotting
    if verbose:
        txt = 'Blended'
        if rho_nml <= 0:
            txt = 'Starting'

        whatNice = what[0] + '_{' + name + '}'

        ax = subplot(2, len(merge_profiles), 1 + kk)
        if rho_nml > 0:
            plot(x0, y0, '-b', label='Original profile')
        plot(x1, y1, 'r', label='EPED profile')
        plot(rho, y, '--k', lw=2.0, label=txt + ' profile')
        ylabel('$' + whatNice + '$')
        plot_regions(True)
        title('$\,$')

        subplot(2, len(merge_profiles), len(merge_profiles) + 1 + kk, sharex=ax)
        if rho_nml > 0:
            plot(x0, z0, '-b', label='Original profile')
        plot(x1, z1, 'r', label='EPED profile')
        plot(xm, zm, '--k', lw=2.0, label=txt + ' profile')
        ylim([0, max(z1) + 2])
        ylabel('$- ' + whatNice + '\'/' + whatNice + '$')
        xlabel('$\\rho$')
        plot_regions(False)
        yscale('symlog')

        # tight_layout()
        autofmt_sharex()
        # legend(loc=2).draggable(True)

# enforce quasineutrality, total pressure, zeff
root['SCRIPTS']['enforce_quasineutrality'].run()
