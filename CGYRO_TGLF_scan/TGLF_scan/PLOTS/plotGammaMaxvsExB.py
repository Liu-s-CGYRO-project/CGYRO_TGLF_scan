# -*-Python-*-
# Created by thomek at 15 Jun 2016  09:58
# Modified by avdeevag at Sep 2022


"""
This script plots max growth rates vs ExB shear over radial coordinates or scan parameters.

defaultVars parameters:

scans: list contaning locations of the data. E.g. root['Experimental_spectra'] or ['TGLF_scan']['scanResults_spectra'][0.5]['RLTS_1'].
Several inputs can be compared if they are in the python list e.g. [['TGLF_scan']['Experimental_spectra'], ['TGLF_scan_2']['Experimental_spectra'] ]
labels : user defined lables for each item in scans. Can also be left empty, e.g. []
plot_subdominant: True or False; can plot subdominant modes if needed
plot_high_ky: True or False; can plot max growth rates for high_ky (electron scale) modes. Usually don't need it as they are always much higher than ExB
color_ExB: list of colors, should be equal to len(scans);
x_delta: True or False;  if different scans are compared (e.g a/Lte and a/Lti) it might be useful to use (a/Lte - a/Lte_exp)/a/Lte_exp rather than a/Lte values
xlabel: if experimental values are plotted it should be 'rho', if scan values are plotted it should be e.g.'RLTS_1'
ax - axes for subplot if this script is used from the command box to make subplot
"""


defaultVars(
    scans=[root.get('Experimental_spectra', None)],
    labels=[''],
    plot_subdominant=False,
    plot_high_ky=False,
    colors_ExB=['k', 'grey'],
    colors=None,
    x_delta=False,
    xlabel=r'$\rho$',
    ax=None,
)

if None in scans:
    printw("Specify the location of data:  ['Experimental_spectra'] or ['scanResults_spectra'][r][variable_to_scan]")
    OMFITx.End()

if len(scans) > len(labels):
    printw('Lenght of scans and labels should be the same')
    OMFITx.End()

if colors == None:
    colors = mpl.cm.rainbow(linspace(0, 1, len(scans)))

if ax == None:

    fig, ax = plt.subplots(1, 1, sharex=True, figsize=(8.7, 8.2))


for j, scan in enumerate(scans):

    rho = []
    gamma_max_high = []
    gamma_max_low = []
    gamma_sub_max_high = []
    gamma_sub_max_low = []
    vExB = []
    ky = []

    for rho_scan in scan.keys():
        rho.append(rho_scan)
        vExB.append(scan[rho_scan]['input.tglf']['VEXB_SHEAR'])
        gamma = scan[rho_scan]['eigenvalue_spectrum']['gamma(1)']
        gamma_subdom = scan[rho_scan]['eigenvalue_spectrum']['gamma(2)']
        ky = scan[rho_scan]['eigenvalue_spectrum']['ky']

        gamma_max_low.append(nanmax(ma.masked_array(gamma, ky > 1), axis=0))  ## low ky
        gamma_max_high.append(nanmax(ma.masked_array(gamma, ky < 1), axis=0))  ## high ky

        gamma_sub_max_low.append(nanmax(ma.masked_array(gamma_subdom, ky > 1), axis=0))  ## low ky
        gamma_sub_max_high.append(nanmax(ma.masked_array(gamma_subdom, ky < 1), axis=0))  ## high ky

    if x_delta:
        delta = zeros(len(rho))
        for n, rho_scan_value in enumerate(rho):
            midle = len(rho) // 2
            delta[n] = (rho[n] - rho[midle]) / (rho[midle]) * 100
        rho = delta
        xlabel = r'$\Delta$ [%]'
        ax.axvline(x=0, linestyle='--', color='k')

    # plot ExB shearing rate
    ax.plot(rho, vExB, '--', label='$\gamma_{ExB}$', color=colors_ExB[j])

    # plot Gamma

    (line,) = ax.plot(rho, gamma_max_low, '-', lw=3, label=fr'{labels[j]}' + ' $\gamma_{max}$ ' + ' low-k')
    if plot_high_ky:
        ax.plot(rho, gamma_max_high, '--', lw=3, color=line.get_color(), label=fr'{labels[j]}' + ' $\gamma_{max}$ ' + ' high-k')

    if plot_subdominant:
        ax.plot(
            rho, gamma_sub_max_low, ':', color=line.get_color(), label=fr'{labels[j]}' + ' $\gamma_{max}$ ' + ' low-k' + ' subdominant mode'
        )
        if plot_high_ky:
            ax.plot(
                rho,
                gamma_sub_max_high,
                '.',
                color=line.get_color(),
                label=fr'{labels[j]}' + ' $\gamma_{max}$ ' + ' high-k' + ' subdominant mode',
            )


ax.set_xlabel(xlabel)
ax.set_ylabel(r'$\gamma \; (a/c_s)$')
ax.set_xlim(min(rho), max(rho))
ax.set_yscale('symlog')
ax.legend().draggable(True)
