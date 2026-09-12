# -*-Python-*-
# Created by avdeevag at 13 Sep 2022  18:24

"""
This script plots fluxes (Qi and Qe) over wavenumbers. Can plot normalized on max values and iterate over different modules. Colors, linestyles, labels can be specified default variables as well as ax to make a combination of subplots.  

defaultVars parameters
----------------------
scans: list contaning locations of the data. E.g. root['Experimental_spectra'] or ['TGLF_scan']['scanResults_spectra'][0.5]['RLTS_1'].
Several inputs can be compared if they are in the python list e.g. [['TGLF_scan']['Experimental_spectra'], ['TGLF_scan_2']['Experimental_spectra'] ]
rho_array: list of radial locations
labels : user defined labels for each item in scans. Can be  empty ['']
plot_normilized: can plot values normilized on max
flux - should be 'Qe' or 'Qi' ; by default Qe and Qi are plotted as a subplot, but only one should be selected if ax is used.
"""


defaultVars(
    rho_range=[root['SETTINGS']['PHYSICS'].get('rho', None)],
    scans=[root.get('Experimental_spectra', None)],
    labels=[fr"$\rho$ = {root['SETTINGS']['PHYSICS'].get('rho',None)}"],
    plot_normilized=False,
    ax=None,
    colors=None,
    linestyles=None,
    flux=None,
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

if ax != None and flux == None:
    printw('Choose which flux to plot by defining variable "flux": can be "Qe" or "Qi" ')
    OMFITx.End()

if ax == None:
    flux = None
    fig, ax = plt.subplots(2, 1, sharex=True, figsize=(8.7, 8.2))


for n, scan in enumerate(scans):
    color = colors[n]
    linestyle = linestyles[n]

    r = rho_range[n]
    spectrum = scan[r]['sum_flux_spectrum']

    ky = spectrum['ky']
    Qe = spectrum['energy'][0, 0, :]
    Qi = spectrum['energy'][1, 0, :]
    if plot_normilized:
        Qe = Qe / max(Qe)
        Qi = Qi / max(Qi)
    if flux == None:
        ax[0].plot(ky, Qe, color=color, linestyle=linestyle, label=f'{labels[n]} ')
        ax[1].plot(ky, Qi, color=color, linestyle=linestyle, label=f'{labels[n]}')

    elif flux == 'Qe':
        ax.plot(ky, Qe, color=color, linestyle=linestyle, label=f'{labels[n]}')
    elif flux == 'Qi':
        ax.plot(ky, Qi, color=color, linestyle=linestyle, label=f'{labels[n]}')


xlabel('$k_\\theta\\rho_s$')
xlim(min(ky), max(ky))

shot = root['SETTINGS']['EXPERIMENT']['shot']
time = root['SETTINGS']['EXPERIMENT']['time']

print(fr'#{shot}, t = {time} ms')


if flux == None:
    ax[0].legend(frameon=False).draggable()
    ax[0].axvline(x=1, linestyle='--', color='k')
    ax[1].axvline(x=1, linestyle='--', color='k')
    ax[0].set_ylim(0, None)
    ax[1].set_ylim(0, None)
    ax[0].set_ylabel(r'$Q_{e}/Q_{GB}$')
    ax[1].set_ylabel(r'$Q_{i}/Q_{GB}$')
    ax[0].semilogx()
    ax[1].semilogx()
    # suptitle(fr'$\rho$ = {r}')
else:
    ax.legend(frameon=False).draggable()
    ax.axvline(x=1, linestyle='--', color='k')
    ax.set_ylabel(f'${flux}' + '/Q_{GB}$')
    ax.semilogx()
    ax.annotate(rf'$\rho$ = {r}', xy=(0.1, 0.9), xycoords='axes fraction', ha='left', va='center', fontsize=30).draggable()
