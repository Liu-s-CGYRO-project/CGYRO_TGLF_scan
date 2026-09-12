# -*-Python-*-
# Created by avdeevag at 16 Dec 2022  20:05

# -*-Python-*-


"""
This script plots contribution of low-k <1 modes into heat fluxes - calculated based only on main modes
This plot can scan through different tglf scan modules (or outputs) and compare results
Works for the 'Experimental spectra' results or for results of scan , e.g.  root[scanResults_spectra][0.5][RLTS_1]


defaultVars parameters:

scans: list contaning locations of the data. E.g. root['Experimental_spectra'] or ['TGLF_scan']['scanResults_spectra'][0.5]['RLTS_1'].
Several inputs can be compared if they are in the python list e.g. [['TGLF_scan']['Experimental_spectra'], ['TGLF_scan_2']['Experimental_spectra'] ]
labels : user defined lables for each item in scans. Can be empty, e.g. ['','']
plot_scan_in_delta: True or False;  change the x_axis to delta values :(a/Lte - a/Lte_exp)/a/Lte_exp instead of just a/Lte values; for plotting the results of the scan
plot_qe: plot contribution into electron heat flux
plot_qi: plot contribution into ion heat flux

"""

defaultVars(
    scans=[root.get('Experimental_spectra', None)],
    labels=[''],
    plot_scan_in_delta=False,
    plot_qe=True,
    plot_qi=False,
)


if None in scans:
    printw('Specify the location of data')
    OMFITx.End()

if len(scans) != len(labels):
    printw('Length of scans and labels should be the same')
    OMFITx.End()

fig, ax = plt.subplots(nrows=1, ncols=1, figsize=(8.5, 8))


for j, scan in enumerate(scans):

    field = 'energy'

    rho_scan = []
    qe_high = []
    qe_low = []
    qi_high = []
    qi_low = []

    for i, rho in enumerate(scan.keys()):

        rho_scan.append(rho)
        evs = scan[rho]['sum_flux_spectrum']
        ky = nominal_values(evs['ky'])

        qe = nominal_values(evs[field][0, 0, :])
        qe_low.append(sum(ma.masked_array(qe, ky >= 1)) / sum(qe))
        qe_high.append(sum(ma.masked_array(qe, ky < 1)) / sum(qe))

        qi = nominal_values(evs[field][1, 0, :])
        qi_low.append(sum(ma.masked_array(qi, ky >= 1)) / sum(qi))
        qi_high.append(sum(ma.masked_array(qi, ky < 1)) / sum(qi))

    if plot_scan_in_delta:

        delta = zeros(len(rho_scan))
        for n, rho_scan_value in enumerate(rho_scan):
            midle = len(rho_scan) // 2
            delta[n] = (rho_scan[n] - rho_scan[midle]) / (rho_scan[midle]) * 100
        rho_scan = delta
        xlabel = r'$\Delta$ [%]'
        ax.axvline(0, linestyle='--', color='k')
    else:
        xlabel = r'$\rho$'

    label = labels[j]

    if plot_qe:

        qe_percentage = [x * 100 for x in qe_low]
        ax.plot(rho_scan, qe_percentage, 's-', label=f'$Q_e$ {label}')

    if plot_qi:

        qi_percentage = [x * 100 for x in qi_low]
        ax.plot(rho_scan, qi_percentage, 's-', label=f'$Q_i$ {label}')

ax.legend()

ax.set_xlabel(xlabel)
ax.set_ylabel('Contribution of low-k modes into total flux [%]')
ax.set_ylim(0, 100)
