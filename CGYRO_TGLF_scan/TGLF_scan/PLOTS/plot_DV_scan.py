# -*-Python-*-
# Created by sciortinof at 16 Jul 2019  16:48

"""
This script plots the particle transport coefficient scans obtained with DV_scans_gui.
"""

defaultVars(
    shade_DV=root['SETTINGS']['PHYSICS']['shade_DV'],
    plot_STRAHL_corrections=root['SETTINGS']['PHYSICS']['plot_STRAHL_corrections'],
    quantities_to_plot=root['scan_vars_to_plot'],  # D,V, V/D, etc.
    variables_to_scan=root['TGLF_inputs_to_scan'],  # gives the order requested by user -- could be different from order of original scan
)

rcParams['xtick.labelsize'] = 20
rcParams['ytick.labelsize'] = 20
rcParams['axes.labelsize'] = 20
rcParams.update({'font.size': 24})
plt.style.use('seaborn-v0_8-deep' if 'seaborn-v0_8-deep' in plt.style.available else 'default')
legendsize = 28
var_labelsize = 30

# Results tree:
data_label = 'D_and_v_' + root['SETTINGS']['PHYSICS']['runs_label']
data_root = root['TGLF_SCAN_DB'][data_label]

# get minor radius
a = root['TGYRO']['RUN_DB']['sim1']['PROFILES_GEN']['input.gacode']['rmin'][-1]

# User can hard-code quantities to plot here, or rely on the DV_scans_gui
if quantities_to_plot is None:
    extra_str = ['_corr' if plot_STRAHL_corrections else ''][0]

    if root['SETTINGS']['PHYSICS']['transport_matrix_method']:
        quants = ['D' + extra_str, 'v' + extra_str, 'RVtot/D' + extra_str]
        ylabels = ['$D [m^2/s]$', '$v_p [m/s]$', '$R V_{tot}/D$']
    else:
        quants = ['D' + extra_str, 'v' + extra_str, 'VoD' + extra_str]  # ,'gamma_n']  # add gamma to see particle flux variation
        ylabels = ['$D [m^2/s]$', '$v [m/s]$', '$v/D [m^{-1}]$']  # , '$\Gamma [m^{-2} s^{-1}]$']

else:
    # Get names and labels of quantities to plot from quantities_to_plot, names of scanned variables and their labels from variables_to_scan
    quants = quantities_to_plot.keys()
    ylabels = list(quantities_to_plot.values())
scan_vars = list(variables_to_scan.keys())
labels = list(variables_to_scan.values())
if len(quants) == 0 or len(scan_vars) == 0:
    raise ValueError('Select at least one output quantity and one scanned variable')

# -----------------------
# Create axes:
fig, ax = plt.subplots(len(quants), len(scan_vars), figsize=(len(scan_vars) * 5, len(quants) * 2.5),
                       sharex='col', sharey='row', squeeze=False)

# obtain  rho
rho = data_root['rhoList']['baseline']  # radii for all other scans are redudant (all the same)

ylims = []

# loop over quantities to be plotted
for qq, quant in enumerate(quants):

    # Get max and min y-axis for all scans
    all_vals = [data_root[quant][key] for key in data_root[quant].keys()]
    ylims.append([np.min(all_vals), np.max(all_vals)])

    # obtain and plot baseline
    for idx, varr in enumerate(scan_vars):
        ax[qq, idx].plot(rho, data_root[quant]['baseline'], 'bo-', lw=2, label='Baseline')
    ax[qq, 0].set_ylabel(ylabels[qq], fontsize=20)


# -----------------------

# for idx,var_name in enumerate(scan_vars):
for idx, var_name in enumerate(variables_to_scan.keys()):

    for scan_dir in ['up', 'down']:
        plot_style = 'gv-' if scan_dir == 'down' else 'r^-'
        label_sign = r'-' if scan_dir == 'down' else r'+'

        # Plot perturbed case over a column
        for qq, quant in enumerate(quants):

            ax[qq, idx].plot(rho, data_root[quant]['{}_{}'.format(var_name, scan_dir)], plot_style, lw=2, label=label_sign + r' 2 $\sigma$')
            ax[qq, idx].set_xticks(rho)

            if shade_DV:
                ax[qq, idx].fill_between(
                    rho, data_root[quant]['baseline'], data_root[quant]['{}_{}'.format(var_name, scan_dir)], facecolor='b', alpha=0.1
                )
            ax[qq, idx].set_ylim([ylims[qq][0] - 0.5, ylims[qq][1] + 0.5])
            ax[qq, idx].grid('on')

    #################
    ax[-1, idx].set_xlabel('$\\rho_{\phi}$', fontsize=20)

    # labels for each scanned variable
    ax[0, idx].text(
        0.80,
        0.2,
        labels[idx],
        fontsize=var_labelsize,
        horizontalalignment='center',
        verticalalignment='center',
        transform=ax[0, idx].transAxes,
        bbox=dict(boxstyle='round', facecolor='skyblue', alpha=0.5),
    )

ax[-1, -1].legend(loc='upper right', prop={'size': legendsize}, bbox_to_anchor=(1.2, 1.4)).draggable()
labels = [item.get_yticklabels() for item in ax[:, 1:].flatten()]

plt.subplots_adjust(left=0.05, right=0.99, top=0.92, bottom=0.08, hspace=0.1, wspace=0.05)

# if only one variable has been scanned, reset subplots_adjust to better default
if ax.shape[1] == 1:
    plt.tight_layout()

# show only 4 radial ticks
[axxx.locator_params(axis='x', nbins=4) for axxx in ax.flatten()]
