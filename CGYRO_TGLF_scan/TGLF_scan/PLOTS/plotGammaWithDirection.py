# -*-Python-*-
# Created by avdeevag at 14 Sep 2022  09:06

"""
This script plots the growth rates of the most unstable and subdomimant (if selected) modes over the range of wavenumbers.
Ion and electron directions are defined by the sign of real frequency

rho_range - list of radial locations from the 'Experimental_spectra' or 'scanResults_spectra' to compare
plot_subdominat - if False only the main modes will be plotted
labels - list of labels
ax - axes for sublot if this script is used from the command box to make subplot
"""


defaultVars(
    rho_range=[root['SETTINGS']['PHYSICS'].get('rho', None)],
    scans=[root.get('Experimental_spectra', None)],
    labels=[fr"$\rho$ = {root['SETTINGS']['PHYSICS'].get('rho',None)}"],
    plot_submodes=True,
    ax=None,
    colors=None,
)


markersize = 10
markersize_sub = 6
markers = ['o'] * len(scans)
markers_sub = ['s'] * len(scans)  # marker for submodes


if None in scans or None in rho_range:
    printw("Specify the location of data:  ['Experimental_spectra'] or ['scanResults_spectra'][r][variable_to_scan]")
    OMFITx.End()

if len(scans) != len(rho_range) or len(scans) > len(labels):
    printw('Lenght of scans, rho_range and labels should be the same')
    OMFITx.End()

if colors == None:
    colors = mpl.cm.rainbow(linspace(0, 1, len(rho_range)))

if ax == None:

    fig, ax = plt.subplots(1, 1, sharex=True, figsize=(8.7, 8.2))


for index, scan in enumerate(scans):
    r = rho_range[index]
    ky = scan[r]['eigenvalue_spectrum']['ky']

    color = colors[index]
    marker = markers[index]
    marker_sub = markers_sub[index]
    label_main = labels[index]

    # main unsatabel mode
    gamma_main = scan[r]['eigenvalue_spectrum']['gamma(1)']
    freq_main = scan[r]['eigenvalue_spectrum']['freq(1)']

    # subdominant mode
    if plot_submodes:
        gamma_sub = scan[r]['eigenvalue_spectrum']['gamma(2)']
        freq_sub = scan[r]['eigenvalue_spectrum']['freq(2)']

    # variables needed to print the legend only for one point
    i_legend_ion = 0
    i_legend = 0

    # plot vExB
    # ----------------------------------------------------------------------------------------
    vExB = scan[r]['input.tglf']['VEXB_SHEAR']
    ax.axhline(vExB, linestyle='--', lw=3, color=color)

    if index == 0:
        ax.annotate(r' $\gamma_{ExB}$', xy=(8, vExB * 0.8), xycoords='data', ha='left', va='center', fontsize=30).draggable()
    # --------------------------------------------------------------------------------
    # define mode direction by the sign of its frequency

    for i in range(len(freq_main)):

        if freq_main[i] < 0:
            i_legend_ion = i

            ax.plot(ky[i], gamma_main[i], marker=marker, markersize=markersize, color=color)

        elif freq_main[i] > 0:
            i_legend = i

            ax.plot(ky[i], gamma_main[i], marker=marker, markersize=markersize, mec=color, fillstyle='none', mew=3)

    # submodes
    if plot_submodes:
        for i in range(len(freq_sub)):
            if freq_sub[i] < 0:
                i_legend_ion_sub = i
                ax.plot(ky[i], gamma_sub[i], marker=marker_sub, markersize=markersize_sub, color=color)

            elif freq_sub[i] > 0:
                i_legend_sub = i
                ax.plot(ky[i], gamma_sub[i], marker=marker_sub, markersize=markersize_sub, mec=color, fillstyle='none', mew=2)

    # Legend handles are added only for signs actually present in the data.
    for direction, sign_value in [('Electron direction', 1), ('Ion direction', -1)]:
        indices = np.flatnonzero(np.sign(freq_main) == sign_value)
        if len(indices):
            idx = indices[-1]
            ax.plot(ky[idx], gamma_main[idx], marker=marker, markersize=markersize,
                    color=color, label=direction, fillstyle='none' if sign_value > 0 else 'full', mew=3)
    if plot_submodes:
        for direction, sign_value in [('Submode - electron direction', 1), ('Submode - ion direction', -1)]:
            indices = np.flatnonzero(np.sign(freq_sub) == sign_value)
            if len(indices):
                idx = indices[-1]
                ax.plot(ky[idx], gamma_sub[idx], marker=marker_sub, markersize=markersize_sub,
                        color=color, label=direction, fillstyle='none' if sign_value > 0 else 'full', mew=2)



ax.set_yscale('log')
ax.set_xscale('log')


ax.legend(numpoints=1, frameon=False, loc='best').draggable()
ax.set_xlim([min(ky) * 0.88, max(ky) * 1.2])
ax.set_ylim([2e-2, 2e1])
ax.set_ylabel('$\gamma \; (a/c_s)$')
ax.set_xlabel('$k_\\theta\\rho_s$')

shot = root['SETTINGS']['EXPERIMENT']['shot']  # useful to have here to change the title to shot and time
time = root['SETTINGS']['EXPERIMENT']['time']
ax.set_title(fr'$\rho$ = {r}')
