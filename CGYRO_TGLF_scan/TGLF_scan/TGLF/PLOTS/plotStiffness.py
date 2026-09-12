# -*-Python-*-
# Created by meneghini at 2015/07/05 13:36
# ['Gam/Gam_GB', 'Q/Q_GB', 'Pi/Pi_GB', 'S/S_GB']

defaultVars(tolerance=1, plot_stiff=True, plot_bars=False)
for sp, species in enumerate(root['FILES']['gbflux']['data']['.'][:1]):
    # figure(num='TGLF stiffness ' + species)
    for kk, what in enumerate(['Q/Q_GB']):
        tmp = SortedDict()
        tmp_temp = []
        for k, var in enumerate(root['STIFFNESS'].KEYS()):
            data_exist = False
            try:
                num = root['STIFFNESS'][var]['gbflux']['data'][what][sp] - root['FILES']['gbflux']['data'][what][sp]
                data_exist = True
            except Exception:
                pass
            if data_exist:
                den = root['STIFFNESS'][var]['input.tglf'][var] - root['FILES']['input.tglf'][var]
                if den == 0 or root['FILES']['gbflux']['data'][what][sp] == 0:
                    continue
                tmp_temp = root['FILES']['input.tglf'][var] / root['FILES']['gbflux']['data'][what][sp] * num / den
                if abs(tmp_temp) > tolerance:  # to plot only values which have significant impact
                    tmp[var] = tmp_temp

        if not len(tmp):
            printw('No finite nonzero stiffness values above the selected tolerance')
            continue

        i = argsort([abs(tmp[k]) for k in tmp if abs(tmp[k]) > tolerance])

        stiff = array([tmp[k] for k in list(tmp.keys())])[i]
        xstiff = arange(len(tmp))
        if plot_stiff:
            plot(xstiff, abs(stiff), 'k.-')
            plot(xstiff[where(stiff > 0)], stiff[where(stiff > 0)], 'or', label='Stiff > 0')
            plot(xstiff[where(stiff < 0)], -stiff[where(stiff < 0)], 'ob', label='Stiff < 0')
            legend()
            axhline(0, color='k', ls='--')
            grid(color='k', linestyle='--', linewidth=2, alpha=0.2)
            gca().set_yscale('log')
            xlim([0, max(xstiff)])

            xticks(xstiff, array(tmp.keys())[i], rotation=90, ha='center')
            ylabel('Stiffness $X/Q\\,{\\partial Q}/{\\partial X}$')
            title_inside(what)

        if plot_bars:
            raw = 2
            fig, ax1 = plt.subplots(1, 1, sharex=True, figsize=(raw * 7, raw * 4))
            x = np.arange(len(xstiff))
            width = 0.55  # width of bars

            te_rms = ax1.bar(x - width / 2, stiff, width)

            ax1.axhline(y=0, linewidth=2, linestyle='-', color='k')
            ax1.set_xticks(x)
            ax1.set_xticklabels(array(tmp.keys())[i], rotation=90, ha='center')
            ax1.set_xlim([0, max(xstiff)])
            ax1.grid(color='k', linestyle='--', linewidth=2, alpha=0.2)
            # ax1.set_ylabel(r'RMS error $\sigma$')

            def autolabel(ax, rects):
                """Attach a text label above each bar in *rects*, displaying its height."""
                for rect in rects:
                    height = rect.get_height()

                    ax.annotate(
                        '{:.2f}'.format(height),
                        xy=(rect.get_x() + rect.get_width() / 2, height),
                        xytext=(0, height),  # 3 points vertical offset
                        textcoords="offset points",
                        ha='center',
                        va='bottom',
                    ).draggable()

            # autolabel(ax1, te_rms)
