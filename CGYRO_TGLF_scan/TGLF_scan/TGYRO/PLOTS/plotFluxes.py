"""
This script allows comparison of different combination of fluxes (power balance, turbulent, total) for different run_ids.
Can iterate over different modules if a list of locations of RUN_DB outputs is specified.

AX is an input parameter, to make a combination of subplots

Each item in scans will be plotted by different color, for each item several fluxes can be plotted by grey line, solid line, dashed line, dotted dashed line
(e.g total total flux, turbulent, neoclassical) and any of them can be set None.


Grey is an array for only power balance fluxes as it is devided on volume



iteration: can plot fluxes for any choosen iteration

"""
# list of fluxes abreviations
#'Qi_target','Qe_target','Qe_turb', 'Qi1_turb','Qe_neo','Qi_neo','Qei',


defaultVars(
    run_db=scratch.get('plot_runids', []),
    labels=scratch.get('plot_runids', []),
    plot_grey=['Electron_PB']
    * len(scratch.get('plot_runids', [])),  # this is  an array only for power balance fluxes as it is devided on volume
    labels_grey=['Qe PB'] * len(scratch.get('plot_runids', [])),
    plot_solid=['Qe_total'] * len(scratch.get('plot_runids', [])),
    labels_solid=['Qe total'] * len(scratch.get('plot_runids', [])),
    plot_dashed=[
        'Qe_turb',
    ]
    * len(scratch.get('plot_runids', [])),
    labels_dashed=['Qe TGLF'] * len(scratch.get('plot_runids', [])),
    plot_dashed_dot=[None] * len(scratch.get('plot_runids', [])),  #
    labels_dashed_dot=[None] * len(scratch.get('plot_runids', [])),  #
    iteration=-1,
    colors=None,
    ax=None,
)


if len(plot_grey) < len(run_db) or len(plot_solid) < len(run_db) or len(plot_dashed) < len(run_db) or len(plot_dashed_dot) < len(run_db):
    printw('Lenght of all plot-* arrays should be equal to len(run_db)')
    OMFITx.End()


if colors == None:
    colors = mpl.cm.rainbow(linspace(0, 1, len(run_db)))

if ax == None:

    fig, ax = plt.subplots(1, 1, sharex=True, figsize=(8.7, 8.2))

# useful array for gray colors on the plot
colors_pb = ['dimgray', 'dimgrey', 'gray', 'grey', 'darkgrey', 'darkgray']


for index, run_id in enumerate(run_db):

    color = colors[index]

    TGYRO_output_dict = {}

    # fluxes TGYRO output
    TGYRO_output = root['RUN_DB'][run_id]['OUTPUTS']['output']  #   maybe later will want to change this line
    TGYRO_power_balance = root['RUN_DB'][run_id]['PROFILES_GEN']['input.gacode']

    TGYRO_output_dict['Qi_target'] = TGYRO_output['eflux_i_target'][iteration]  # [GB]
    TGYRO_output_dict['Qe_target'] = TGYRO_output['eflux_e_target'][iteration]  # [GB]
    TGYRO_output_dict['Qe_turb'] = TGYRO_output['eflux_e_tur'][iteration]  # [GB]
    # for number of ions in ...: # can make a summ of ion fluxes
    TGYRO_output_dict['Qi1_turb'] = TGYRO_output['eflux_i1_tur'][iteration]  # [GB]
    TGYRO_output_dict['Qe_neo'] = TGYRO_output['eflux_e_neo'][iteration]  # [GB]
    TGYRO_output_dict['Qi_neo'] = TGYRO_output['eflux_i1_neo'][iteration]  # [GB]
    TGYRO_output_dict['Qie'] = TGYRO_output['expwd_e_tur']  # turbulent exchange term
    # can add particle and momentum flux here

    TGYRO_output_dict['Qie'] = TGYRO_output['expwd_e_tur'][iteration]

    TGYRO_output_dict['Qe_total'] = TGYRO_output['eflux_e_tot'][iteration]
    TGYRO_output_dict['Qi_total'] = TGYRO_output['eflux_i_tot'][iteration]

    if root['RUN_DB'][run_id]['INPUTS']['input.tgyro']['TGYRO_USE_RHO'] != 1:
        rho = TGYRO_output['r/a'][iteration]
        xlable = 'r/a'
    else:
        rho = TGYRO_output['rho'][iteration]
        xlable = r'$\rho$'

    GB = TGYRO_output['Q_GB'][iteration] * 1e2

    TGYRO_output_dict['Ion_PB'] = TGYRO_power_balance['pow_i']
    TGYRO_output_dict['Electron_PB'] = TGYRO_power_balance['pow_e']
    TGYRO_output_dict['Electron_ion_PB'] = TGYRO_power_balance['pow_ei']  # collisional

    if root['RUN_DB'][run_id]['INPUTS']['input.tgyro']['TGYRO_USE_RHO'] != 1:
        TGYRO_output_dict['rho_PB'] = TGYRO_power_balance['rmin'] / max(TGYRO_power_balance['rmin'])
        xlabel = 'r/a'
    else:
        TGYRO_output_dict['rho_PB'] = TGYRO_power_balance['rho']
        xlabel = r'$\rho$'

    TGYRO_output_dict['vol_PB'] = TGYRO_power_balance['volp']

    # plot grey

    if plot_grey[index] is not None:
        label_pb = labels_grey[index]
        item_to_plot = plot_grey[index]
        ax.plot(
            TGYRO_output_dict['rho_PB'],
            TGYRO_output_dict[f'{item_to_plot}'] / TGYRO_output_dict['vol_PB'] * 1e2,
            color=colors_pb[index],
            linestyle='-',
            label=f'{label_pb} {labels[index]}',
            lw=5,
        )

    # plot solid
    if plot_solid[index] is not None:
        label_s = labels_solid[index]
        item_to_plot = plot_solid[index]
        ax.plot(rho, TGYRO_output_dict[f'{item_to_plot}'] * GB, 'o-', label=f'{label_s} {labels[index]}', color=color)

    if plot_dashed[index] is not None:

        item_to_plot = plot_dashed[index]
        label_d = labels_dashed[index]
        ax.plot(rho, TGYRO_output_dict[f'{item_to_plot}'] * GB, 'o--', label=f'{label_d} {labels[index]}', color=color)

    if plot_dashed_dot[index] is not None:

        item_to_plot = plot_dashed_dot[index]
        label_d_d = labels_dashed_dot[index]
        ax.plot(rho, TGYRO_output_dict[f'{item_to_plot}'] * GB, 'o-.', label=f'{label_d_d} {labels[index]}', color=color)

    ax.legend()
    ax.set_ylabel('Q $[W/cm^{2}]$')
    ax.set_xlabel(xlabel)
