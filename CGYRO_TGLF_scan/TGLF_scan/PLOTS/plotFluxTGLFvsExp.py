# -*-Python-*-
# Created by avdeevag at 14 Sep 2022  19:08

"""
This script plots TGLF fluxes vs Experimental values (tgyro_output) for all or selected radial locations in radial scan
works with root as an input
If both mks_units and total power are false - results will be in Q/Q_{GB}

mks_units : multiply fluxes on GB normalization
total_power: integrate fluxes over volume to get total power
rho_scan: user can specify radial locations if doesn't want to plot all of them from Experimental fluxes
flux: 'Qe' or 'Qi', used for subplots

"""
defaultVars(
    scans=[root], tgyro_outputs=[root], labels=[' '], colors=None, mks_units=True, total_power=False, rho_scan_user=None, ax=None, flux=None
)


if None in scans or None in tgyro_outputs:
    printw(
        "Specify the location of data:  ['Experimental_spectra'] or ['scanResults_spectra'][r][variable_to_scan] and location of tgyro_output"
    )
    OMFITx.End()

if len(scans) > len(labels) or len(scans) != len(tgyro_outputs):
    printw('Lenght of scans and labels should be the same')
    OMFITx.End()

if colors == None:
    colors = mpl.cm.rainbow(linspace(0, 1, len(scans)))

if ax != None and flux == None:
    printw('Choose which flux to plot by defining variable "flux": can be "Qe" or "Qi" ')
    OMFITx.End()


if ax == None:

    fig, ax = plt.subplots(nrows=2, ncols=1, sharex=True)
    plot_subplots = True
    flux = None


for j, scan in enumerate(scans):
    tgyro_output = tgyro_outputs[j]
    rho = tgyro_output['tgyro_output']['rho']
    # read experimental fluxes from TGYRO output
    expGm = tgyro_output['tgyro_output']['pflux_e_target'][0]
    expQe = tgyro_output['tgyro_output']['eflux_e_target'][0]
    expQi = tgyro_output['tgyro_output']['eflux_i_target'][0]
    expPi = tgyro_output['tgyro_output']['mflux_target'][0]
    # need dv/dr for calculation of the total power
    if mks_units and not total_power:

        GB_TGLF = tgyro_output['tgyro_output']['Q_GB'][0]
        vol_p = np.ones(len(expQe))
        y_units = '[$MW/cm^2$]'
    elif total_power:
        GB_TGLF = tgyro_output['tgyro_output']['Q_GB'][0]
        vol_p = tgyro_output['tgyro_output']['d(vol)/dr'][0]
        y_units = '[MW]'

    else:
        GB_TGLF = np.ones(len(expQe))
        vol_p = np.ones(len(expQe))
        y_units = '[$Q/Q_{GB}$]'

    results = scan['Experimental_fluxes']
    if rho_scan_user == None:
        rho_scan = list(results.keys())
    else:
        rho_scan = rho_scan_user

    TGLF_Qe = []
    TGLF_Qi = []
    exp_Qe = []
    exp_Qi = []
    for i, v in enumerate(rho_scan):
        evs = results[v]['data']

        inN = int(v * 100)  # need this to get the righ element from tgyro output

        TGLF_Qe.append(evs[0][2] * GB_TGLF[inN] * vol_p[inN])
        TGLF_Qi.append(evs[1][2] * GB_TGLF[inN] * vol_p[inN])
        exp_Qe.append(expQe[inN] * GB_TGLF[inN] * vol_p[inN])
        exp_Qi.append(expQi[inN] * GB_TGLF[inN] * vol_p[inN])
    if flux == None:
        if j % (len(scans)) == 0:  # use label for legend only for one radial point
            ax[0].plot(rho[0], expQe * GB_TGLF * vol_p, '-', label='TGYRO output', lw=2, color='k')
            ax[1].plot(rho[0], expQi * GB_TGLF * vol_p, '-', label='TGYRO output', lw=2, color='k')
        ax[0].plot(rho_scan, TGLF_Qe, 'o', markersize=8, label='TGLF ' + labels[j], color=colors[j])

        ax[1].plot(rho_scan, TGLF_Qi, 'o', markersize=8, color=colors[j])

        ax[0].set_ylabel('Qe ' + f'{y_units}')
        ax[1].set_xlabel(r'$\rho$')
        ax[1].set_ylabel(r'Qi ' + f'{y_units}')

    elif flux == 'Qe':
        if j % (len(scans)) == 0:  # use label for legend only for one radial point
            ax.plot(rho[0], expQe * GB_TGLF * vol_p, '-', label='$Q_e$ - TGYRO output', lw=2, color='k')
        ax.plot(rho_scan, TGLF_Qe, 'o', markersize=8, label='TGLF ' + labels[j], color=colors[j])

        ax.set_xlabel(r'$\rho$')
        ax.set_ylabel('TGLF $Q_e$' + f'{y_units}')

    elif flux == 'Qi':
        if j % (len(scans)) == 0:  # use label for legend only for one radial point
            ax.plot(rho[0], expQi * GB_TGLF * vol_p, '-', label='$Q_i$ - TGYRO output', lw=2, color='k')
        ax.plot(rho_scan, TGLF_Qi, 'o', markersize=8, label='TGLF ' + labels[j], color=colors[j])

        ax.set_xlabel(r'$\rho$')
        ax.set_ylabel('TGLF $Q_i$' + f'{y_units}')

if flux != None:
    ax.legend(loc='best')
else:
    ax[0].legend(loc='best')
