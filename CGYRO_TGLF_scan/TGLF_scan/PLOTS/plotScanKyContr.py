# -*-Python-*-
# Created by avdeevag at 30 Aug 2022  06:49

"""
Plot scans with more flexible options

defaultVars parameters
----------------------
scans: list contaning locations of the data. E.g. root['Experimental_spectra'] or ['TGLF_scan']['scanResults_spectra'][0.5]['RLTS_1'].
tgyro_output: list with locations of tgyro_output. should be equal to len(scans)
IDs: scan paprameter
labels : user defined lables for each item in scans. Can also be left empty, e.g. []
colors: list of colors for
r: radial location
rho_exp: optional explicit reference grid index; default locates r on the actual grid
plot_electrons: plot electron heat flux
plot_ions: plot ion heat flux
plot_ky_contribution: plot contribution of low and high ky into fluxes
x_delta: True or False;  if we compare different scans (e.g a/Lte and a/Lti) it might be useful to use (a/Lte - a/Lte_exp)/a/Lte_exp rather than a/Lte values

"""


import numpy as np

def _reference_index(output, radial_value, use_rho=True, explicit_index=None):
    coordinate = np.asarray(output['rho' if use_rho else 'r/a'])
    if coordinate.ndim > 1:
        coordinate = coordinate[0]
    if coordinate.ndim != 1 or not len(coordinate) or not np.all(np.isfinite(coordinate)):
        raise ValueError('Reference radial grid must be a finite one-dimensional array')
    if explicit_index is not None:
        index = int(explicit_index)
        if index != explicit_index or not 0 <= index < len(coordinate):
            raise ValueError('rho_exp is outside the reference radial grid')
        return index
    if radial_value is None or not np.isfinite(radial_value):
        raise ValueError('Specify a finite scan radius')
    return int(np.argmin(np.abs(coordinate-radial_value)))

defaultVars(
    scans=[root],
    tgyro_outputs=[root],
    IDs=[root['TGLF']['SETTINGS']['PHYSICS'].get('scanParameter', None)],
    labels=[''],
    colors=None,
    r=root['SETTINGS']['PHYSICS'].get('rho', None),
    rho_exp=None,
    plot_electrons=True,
    plot_ions=False,
    plot_ky_contribution=True,
    x_delta=False,
    ax=None,
)

if None in scans or None in tgyro_outputs or None in IDs:
    printw("Specify the location of data, rho and scanParameter")
    OMFITx.End()

if len(scans) > len(labels) or len(scans) != len(tgyro_outputs):
    printw('Lenght of scans,tgyro_outputs and labels should be the same')
    OMFITx.End()

if colors == None:
    colors = mpl.cm.rainbow(linspace(0, 1, len(scans)))


if ax is None:
    fig, ax = plt.subplots(1, 1, sharex=True, figsize=(8, 8))
else:
    fig = ax.figure

rcParams['legend.numpoints'] = 1  # show only one marker for experimental==power balance point

for n, scan in enumerate(scans):
    scan_ID = IDs[n]
    tgyro_output = tgyro_outputs[n]
    label = labels[n]

    x_var = []  # array of x coordinates == IDs
    qe = []
    qi = []

    # to plot low and high k contributions
    qe_high = []
    qe_low = []
    qi_high = []
    qi_low = []
    field = 'energy'

    reference = tgyro_output['tgyro_output']
    reference_tgyro = tgyro_output.get('TGYRO', root['TGYRO'])
    use_rho = bool(reference_tgyro['INPUTS']['input.tgyro'].get('TGYRO_USE_RHO', True))
    reference_index = _reference_index(reference, r, use_rho, rho_exp)
    expQe = reference['eflux_e_target'][0][reference_index]
    expQi = tgyro_output['tgyro_output']['eflux_i_target'][0][reference_index]
    norm = 1 / tgyro_output['tgyro_output']['Q_GB'][0][reference_index]

    for i, x_coord in enumerate(scan['scanResults'][r][scan_ID].keys()):
        x_var.append(x_coord)
        qe.append(scan['scanResults'][r][scan_ID][x_coord]['Q/Q_GB'][0])

        qi.append(scan['scanResults'][r][scan_ID][x_coord]['Q/Q_GB'][1])
        # can add particle, momentum and exhange
        evs = scan['scanResults_spectra'][r][scan_ID][x_coord]['sum_flux_spectrum']
        ky = nominal_values(evs['ky'])

        qe_ky_array = nominal_values(evs[field][0, 0, :])
        qe_low.append(sum(ma.masked_array(qe_ky_array, ky >= 1)))
        qe_high.append(sum(ma.masked_array(qe_ky_array, ky < 1)))

        qi_ky_array = nominal_values(evs[field][1, 0, :])
        qi_low.append(sum(ma.masked_array(qi_ky_array, ky >= 1)))
        qi_high.append(sum(ma.masked_array(qi_ky_array, ky < 1)))

        if plot_electrons:
            y_var = qe
            y_label = '$Q_e/Q_{GB}$'
            y_var_k_cont_high = qe_high
            y_var_k_cont_low = qe_low
            exp_var = expQe

        if plot_ions:
            y_var = qi
            y_label = '$Q_i/Q_{GB}$'
            y_var_k_cont_high = qi_high
            y_var_k_cont_low = qi_low
            exp_var = expQi

    x_label = f'${scan_ID}$'

    if x_delta:

        delta = zeros(len(x_var))
        for nn, x_value in enumerate(x_var):
            middle = len(x_var) // 2
            delta[nn] = (x_var[nn] - x_var[middle]) / (x_var[middle]) * 100
        x_var = delta
        x_label = r'$\Delta$ [%]'
        ax.axvline(0, linestyle='--', color='k')
        ax.plot(0, exp_var, marker='s', color=colors[n], ms=15, label='Power balance')
    else:
        middle = len(x_var) // 2
        ax.axvline(x=x_var[middle], linestyle='--', color='k')
        # plot experimental point
        ax.plot(x_var[middle], exp_var, marker='s', color=colors[n], ms=15, label='Power balance')

    ax.plot(x_var, y_var, 's-', label='$Q_{tot}$' + f'{label}', color=colors[n])
    if plot_ky_contribution:
        if len(scans) == 1:
            color_h = 'orange'
            color_l = 'red'
        else:
            color_h = colors[n]
            color_l = colors[n]
        ax.plot(x_var, y_var_k_cont_high, 's--', label='$Q_{high_{k}}$' + f' {label}', color=color_h)
        ax.plot(x_var, y_var_k_cont_low, 's:', label='$Q_{low_{k}}$' + f' {label}', color=color_l)

    ax.set_ylabel(y_label)
    ax.set_xlabel(x_label)
    ax.legend()
    ax.set_xlim(-100, 100)
    ax.set_xlim(min(x_var), max(x_var))
    ax.set_ylim(0, None)

    fig.suptitle(f"# {root['SETTINGS']['EXPERIMENT']['shot']}; rho={r}")
