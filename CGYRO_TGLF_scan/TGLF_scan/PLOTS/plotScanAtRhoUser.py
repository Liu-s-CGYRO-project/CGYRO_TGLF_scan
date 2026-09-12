# -*-Python-*-
# Created by avdeevag at 17 Dec 2022  10:03

"""
This script plots growth rates for particular radial location and compare with ExB shear.  Scans between different modules can be compared for selected radial locations with subdominant modes shown or not.


defaultVars parameters:

scans: list contaning locations of the data. E.g. root['Experimental_spectra'] or ['TGLF_scan']['scanResults_spectra'][0.5]['RLTS_1'].
Several inputs can be compared if they are in the python list e.g. [['TGLF_scan']['Experimental_spectra'], ['TGLF_scan_2']['Experimental_spectra'] ]
rho_range: list of radial locations; the lenght of this array should be the same with len(scans)
labels : user defined lables for each item in scans. Can also be empty, e.g. ['']
plot_subdominant: True or False; can plot or not subdominant modes
plot_frequency: plot real frequencies
plot_gamma: plot gamma
ax - axes for sublot if this script is used from the command box to make subplot


"""


import numpy as np

defaultVars(
    rho_range=[root['SETTINGS']['PHYSICS'].get('rho', None)],
    scans=[root.get('Experimental_spectra', None)],
    labels=[''],
    plot_subdominant=True,
    plot_frequency=True,
    plot_gamma=True,
    ax=None,
    colors=None,
    linestyles=None,
    linestyles_sub=None,
)

if None in scans or None in rho_range:
    printw("Specify the location of data:  ['Experimental_spectra'] or ['scanResults_spectra'][r][variable_to_scan]")
    OMFITx.End()

if len(labels) < len(scans) or len(rho_range) != len(scans):
    printw('Length of scans,rho_array and labels should be the same')
    OMFITx.End()


if colors == None:
    colors = mpl.cm.rainbow(linspace(0, 1, len(scans)))

if linestyles == None:
    linestyles = ['-'] * len(scans)

if linestyles_sub == None:
    linestyles_sub = ['--'] * len(scans)


if ax != None and plot_frequency == True and plot_gamma == True:
    printw("If ax is specified choose to plot either frequency or gamma")
    OMFITx.End()

if ax == None:

    # make default subplots if ax is not specified
    if plot_frequency and plot_gamma:
        fig, ax = plt.subplots(2, 1, figsize=(8, 8), sharex=True)
    else:
        fig, ax = plt.subplots(1, 1, figsize=(8, 8))


for n, scan in enumerate(scans):
    color = colors[n]
    linestyle = linestyles[n]
    linestyle_sub = linestyles_sub[n]

    r = rho_range[n]

    gamma1 = scan[r]['eigenvalue_spectrum']['gamma(1)']
    # subdominant mode
    if plot_subdominant:
        gamma2 = scan[r]['eigenvalue_spectrum']['gamma(2)']

    freq1 = scan[r]['eigenvalue_spectrum']['freq(1)']
    # subdominant mode
    if plot_subdominant:
        freq2 = scan[r]['eigenvalue_spectrum']['freq(2)']

    ky = scan[r]['eigenvalue_spectrum']['ky']
    vExB = scan[r]['input.tglf']['VEXB_SHEAR']

    if plot_frequency and not plot_gamma:
        ylabel_axis = r'$\omega \; (a/c_s)$'
        (line,) = ax.plot(ky, freq1, color=color, linestyle=linestyle, label=fr'{labels[n]} $\rho$ = {r}')
        ax.axhline(y=0, color='k', linestyle='--')
        if plot_subdominant:
            ax.plot(ky, freq2, linestyle=linestyle_sub, color=line.get_color(), label=fr'{labels[n]} $\rho$ = {r} - subdominant mode')

    if plot_gamma and not plot_frequency:
        ylabel_axis = r'$\gamma \; (a/c_s)$'
        (line,) = ax.plot(ky, gamma1, color=color, linestyle=linestyle, label=fr'{labels[n]} $\rho$ = {r}')

        if plot_subdominant:
            ax.plot(ky, gamma2, linestyle=linestyle_sub, color=line.get_color(), label=fr'{labels[n]} $\rho$ = {r} - subdominant mode')
        # --------plot ExB line --------------------------------
        ax.axhline(vExB, linestyle=':', color=line.get_color())
        if n == 0:

            ax.annotate(
                '$\gamma_{ExB} $', xy=(max(ky) * 0.6, vExB * 0.8), xycoords='data', ha='left', va='center', color=line.get_color()
            ).draggable()

    # --------------------------------------------------------------------
    if plot_frequency and plot_gamma:
        ylabel_axis = r'$\gamma \; (a/c_s)$'
        (line,) = ax[0].plot(ky, freq1, color=color, linestyle=linestyle, label=fr'{labels[n]} $\rho$ = {r}')

        ax[1].plot(ky, gamma1, linestyle=linestyle, color=line.get_color(), label=fr'{labels[n]} $\rho$ = {r}')
        ax[1].axhline(vExB, linestyle=':', color=line.get_color())
        ax[0].set_ylabel(r'$\omega \; (a/c_s)$')
        # ------------plot ExB line ------------------------------
        ax[0].axhline(y=0, color='k', linestyle='--')
        if n == 0:

            ax[1].annotate(
                '$\gamma_{ExB} $', xy=(max(ky) * 0.6, vExB * 0.8), xycoords='data', ha='left', va='center', color=line.get_color()
            ).draggable()
        # --------------------------------------------------------------------------
        if plot_subdominant:
            ax[1].plot(ky, gamma2, linestyle=linestyle_sub, color=line.get_color(), label=fr'{labels[n]} $\rho$ = {r} - subdominant mode')
            ax[0].plot(ky, freq2, linestyle=linestyle_sub, color=line.get_color(), label=fr'{labels[n]} $\rho$ = {r} - subdominant mode')


plot_axes = np.atleast_1d(ax).ravel()
for plot_axis in plot_axes:
    plot_axis.set_xscale('log')
    plot_axis.set_xlim(0.08, 26)
    plot_axis.set_xlabel('$k_\\theta\\rho_s$')
    plot_axis.legend(loc='best')
if plot_frequency and plot_gamma:
    plot_axes[0].set_yscale('linear')
    plot_axes[0].set_ylabel(r'$\omega \; (a/c_s)$')
    plot_axes[1].set_yscale('log')
    plot_axes[1].set_ylabel(r'$\gamma \; (a/c_s)$')
else:
    plot_axes[0].set_yscale('linear' if plot_frequency else 'log')
    plot_axes[0].set_ylabel(ylabel_axis)

shot = root['SETTINGS']['EXPERIMENT']['shot']
time = root['SETTINGS']['EXPERIMENT']['time']

plot_axes[0].figure.suptitle(fr'#{shot}; t= {time} ms;')
