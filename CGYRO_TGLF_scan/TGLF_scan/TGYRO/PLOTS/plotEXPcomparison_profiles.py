"""
Compare TGYRO results with experemental data from OMFITprofiles or QUICKFIT module
"""

defaultVars(
    run_db=scratch.get('plot_runids', []),
    tav=root['PROFILES_GEN']['TRXPL']['SETTINGS']['EXPERIMENT']['avgtim'],
    t_tgyro=root['PROFILES_GEN']['TRXPL']['SETTINGS']['EXPERIMENT']['time'],
    plot_all_times=False,  # if True it plots each times inside the average window separatly, if False - as a standart deviation
    fields_to_plot=['Te', 'Ti', 'ne', 'omega'],
    legend_label=[],  # Option to create the user's define legend ['sim1','sim2',...](length of the list should be equal to the number of TGYRO runs plotted)), otherwise RUN_DBs will be used as a legend
    subplots=False,  # each field can be ploted on the separate tab (False) or all together (True)
    plot_interpolation=True,
)

# plot settings - it might be useful to easily change these settings
# ------------------------------------------------------
linewidth = 4  # tgyro lines
elinewidth = 3  # exp points errorbar linewidth
fontsize = 18
markersize = 12  # exp points size
fmt = 'none'  # marker type for experimental points , can be 'none' or any awailable symbol '*','o','s'...
marker_tgyro = 'o'  # can be empty '' or any awailable symbol '*','o','s' ...
markersize_tgyro = 12  # exp points size
scale_min = 0.1  # % of min value to set ymin for the plot
scale_max = 1.3  # % of max value to set ymax for the plot
xmin = 0  # min xAxis  in rho
xmax = 1  # max xAxis  in rho
exp_lim1 = 0  #  min xlim for experimental points to show
exp_lim2 = 1.1  # max xlim for experimental points to show
target_prof_color = 'grey'  # color of the target=TRANSP profiles
show_exp_errorbars = True

# --------------------------------------------------------

'''
Dictionary contains {'Variable':[1 - 'Variable name in input.gacode = TRANSP',
2 -'Variable name in TGYRO',
3 - 'Variable name in OMFITprofiles',
4 - 'Scale coefficient for OMFITprofiles variable',
5 - 'Ylabel for plot',
6 - 'Scale coefficient for TGYRO variable'],
7 - 'Scale coefficient for target variable']}
'''


dict_names = {
    'Te': ['Te', 'te', 'T_e', 1e-3, '$T_e$ [keV]', 1, 1],
    'Ti': ['Ti_1', 'ti1', 'T_12C6', 1e-3, '$T_i$  [keV]', 1, 1],
    'ne': ['ne', 'ne', 'n_e', 1e-19, r'$n_e$ $[10^{19} \; m^{-3}]$', 1e-13, 1],
    'omega': ['omega0', 'w0', 'omega_tor_12C6', 1e-5, r'$\omega$  $[10^5 \; rad/s]$', 1e-5, 1e-5],
}

# ----------------------------------------------------------------------------


if len(run_db) == 0:
    printw('Select runIDs to plot')
    OMFITx.End()


# searching for the experimental data in loaded module
try:
    exp_prof = profiles_module['OUTPUTS']['FIT']
except:
    printe("Can't find FIT in profile_module. Reload project with existing profiles module or pick existing from the tree.")
    OMFITx.End()


# this will work only of the input.gacode was created from TRANSP
shot_tgyro = root['PROFILES_GEN']['TRXPL']['SETTINGS']['EXPERIMENT']['shot']
shot_exp = profiles_module['SETTINGS']['EXPERIMENT']['shot']
if shot_tgyro != shot_exp:
    printe(f'Comparison of different shots: TGYRO shot number {shot_tgyro} and profiles_module shot number {shot_exp}')


# assume all  run_db have the same profile_gen input
gacode = root['RUN_DB'][run_db[-1]]['PROFILES_GEN']['input.gacode']

fn = FigureNotebook(0, 'TGYRO vs Experimental data')
if subplots:
    fig, axx = fn.subplots(2, 2)


for n, field in enumerate(fields_to_plot):

    gacode_name, TGYROname, name, prof_scale, ylabel, tgyro_scale, target_scale = dict_names[field]

    # start y axis plot from zero or less
    min_var = 0

    if not subplots:
        fig, ax = fn.subplots(1, 1, label=field)
    else:
        ax = axx.flat[n]

    target = gacode[gacode_name] * target_scale

    # it can be wrong for omega profiles crossing zero (intrinsic rotation, edge etc.)
    if field == 'omega':
        target = abs(target)

    target_rho = gacode['rho']

    # plot target profiles from input.gacode
    ax.plot(target_rho, target, '-', lw=3, color=target_prof_color, label='Target')

    min_var = min(min_var, nanmin(target))
    max_var = nanmax(target)

    try:
        if ismodule(profiles_module, 'OMFITprofiles'):

            multiplex_dir = profiles_module['LIB']['OMFITlib_general']
            multiplex = multiplex_dir.run()['multiplex_slices']

            # Warning: these data are already sliced over some window by OMFITprofiles, not a raw data
            exp_var = multiplex(name)  # read measurements from all signals

            # it will return sliced copy of the original dataset in the requested time range
            exp_var = exp_var.sel(time=slice(t_tgyro - tav, t_tgyro + tav))

            # rescale to expected units in plots
            exp_var[name] *= prof_scale

        elif ismodule(profiles_module, 'QUICKFIT'):

            # get raw data used for profile fitting (without removed points, including all corrections)
            exp_var = xarray.Dataset(profiles_module['OUTPUTS']['PLOT'][name])

            # apply separatrix scaler use on profiles fits also on the raw data
            if is_device(root['SETTINGS']['EXPERIMENT']['device'], 'DIII-D'):
                x_of_Sep = 1
                if name in ['T_e', 'n_e'] and 'TS' in profiles_module['OUTPUTS']['DIAGNOSTICS']:
                    TS = profiles_module['OUTPUTS']['DIAGNOSTICS']['TS']
                    x_of_Sep = np.interp(exp_var.time, TS['separatrix']['time'], TS['x_of_TeSep'])
                if name in ['omega_tor_12C6', 'T_12C6'] and 'CER' in profiles_module['OUTPUTS']['DIAGNOSTICS']:
                    CER = profiles_module['OUTPUTS']['DIAGNOSTICS']['CER']
                    x_of_Sep = np.interp(exp_var.time, CER['separatrix']['time'], CER['x_of_denscorr'])

                exp_var['rho'] = exp_var['rho'] / x_of_Sep

            # mask data outside of the requested time range
            exp_var = exp_var.where((exp_var.time * 1e3 >= t_tgyro - tav) & (exp_var.time * 1e3 <= t_tgyro + tav))
            # create Dataset similar to Dataset from OMFITprofiles
            del exp_var['time']  # time is not unique, cannot be used as coordinate
            exp_var[name] = xarray.DataArray(uarray(exp_var.data, exp_var.err) * prof_scale)
            # fake unique time coordinate
            exp_var['time'] = xarray.DataArray([t_tgyro], dims=['time'])

            # only plotting of all points is supported
            plot_all_times = True
        else:
            raise OMFITexception('Not supported profile module')

    except Exception:
        printe(f'No experimental measurement {name} found')
        exp_var = None

    if exp_var is None or len(exp_var['time']) == 0:
        printe(f'No experimental points {name} for this time window {t_tgyro} +/- {tav} in the loaded project')

    else:

        # select only the requested radial range
        exp_var = exp_var.where((exp_var.rho >= exp_lim1) & (exp_var.rho <= exp_lim2))

        if field == 'omega':
            exp_var[name] = np.abs(exp_var[name])

        # plot experimental data (for each time slice in the average window or mean+/-3sigma
        times = exp_var['time']
        if plot_all_times or len(times) == 1:
            for t in times:
                exp_var_t = exp_var.sel(time=t)
                if len(times) == 1:
                    label = 'exp. data = %d+/-%d ms' % (t, tav)
                else:
                    label = 'exp. data = %d ms' % t

                if show_exp_errorbars:
                    plot_options = {'fmt': fmt, 'ms': markersize, 'elinewidth': elinewidth, 'label': label}
                    uerrorbar(exp_var_t['rho'], exp_var_t[name], ax=ax, **plot_options)
                else:
                    plot_options = {'ms': 5, 'label': label, 'ls': 'none', 'marker': 'o'}
                    ax.plot(exp_var_t['rho'], nominal_values(exp_var_t[name]), **plot_options)

                min_var = min(min_var, nanmin(nominal_values(exp_var_t[name]) - std_devs(exp_var_t[name])))
                max_var = max(max_var, nanmax(nominal_values(exp_var_t[name]) + std_devs(exp_var_t[name])))

        else:

            val = exp_var[name].transpose('time', 'channel').values

            mean_val = np.nanmean(nominal_values(val), axis=0)
            std_val = np.nanstd(nominal_values(val), axis=0)
            rho_mean = exp_var['rho'].mean(dim='time', skipna=True)

            # Why is used 3 STD?
            ax.errorbar(
                rho_mean,
                mean_val,
                3 * std_val,
                fmt=fmt,
                ms=markersize,
                elinewidth=elinewidth,
                ecolor='grey',
                label=f'{name} averg data t = %3.1f - %3.1f ms' % (exp_var['time'][0], exp_var['time'][-1]),
            )
            min_var = min(min_var, nanmin(mean_val - 3 * std_val))
            max_var = max(max_var, nanmax(mean_val + 3 * std_val))

    for j, runID in enumerate(run_db):

        tgyro = root['RUN_DB'][runID]['OUTPUTS']['output']

        tgyro_var = tgyro[TGYROname][-1] * tgyro_scale

        if field == 'omega':
            tgyro_var = abs(tgyro_var)

        tgyro_rho = tgyro['rho'][-1]

        label_list = []
        if len(legend_label) < len(run_db):
            label_list = runID
        else:
            label_list = legend_label[j]

        # plot TGYRO prediction, interpolation to rho=0 is ploted by dashed lines

        (line,) = ax.plot(tgyro_rho[1:], tgyro_var[1:], marker=marker_tgyro, markersize=markersize_tgyro, lw=linewidth, label=label_list)
        if plot_interpolation:
            ax.plot(tgyro_rho[0:2], tgyro_var[0:2], lw=linewidth - 1, linestyle='--', color=line.get_color())

        min_var = min(min_var, nanmin(tgyro_var))
        max_var = max(max_var, nanmax(tgyro_var))

    ax.set_xlim(xmin, xmax)
    ax.set_xlabel(r'$\rho$', fontsize=fontsize)

    if not subplots:
        ax.legend()
    else:
        if n == 3:
            ax.legend()

    if field != 'omega':
        min_var = 0
    ax.set_ylim(min_var * scale_max, max_var * scale_max)
    ax.tick_params(axis="both", labelsize=fontsize)
    ax.set_ylabel(ylabel, fontsize=fontsize)

    fig.canvas.draw()
