# -*-Python-*-
# Created by sciortinof at 16 Jul 2019  16:41

"""
This script plots the growth rates and frequencies obtained from the scan of TGLF input prameters.
Use DV_scans_gui to run the scan.

The mode_number argument allows plotting of subdominant modes.
"""

defaultVars(
    variables_to_scan=root['TGLF_inputs_to_scan'],
    normalized_freq=root['SETTINGS']['PHYSICS']['normalized_freq'],
    separate_freq_plot=root['SETTINGS']['PHYSICS']['separate_freq_plot'],
    plot_gamma_lims=[None, None],
    plot_freq_lims=[None, None],
    mode_number=root['SETTINGS']['PHYSICS']['plot_mode_number'],  # dominant mode: 1; subdominant: 2, then 3, etc.
)

minGamma = plot_gamma_lims[0]
maxGamma = plot_gamma_lims[1]
minFreq = plot_freq_lims[0]
maxFreq = plot_freq_lims[1]


# Location where results of scans are located if scan was run:
scans_root = root['TGLF_SCAN_DB']['scans']

plt.style.use('seaborn-v0_8-deep' if 'seaborn-v0_8-deep' in plt.style.available else 'default')
matplotlib.rc('xtick', labelsize=20)
matplotlib.rc('ytick', labelsize=20)
matplotlib.rcParams.update({'font.size': 22})

# TGLF output folder (possibly change this to other folders in the future)
plotFolder = 'eigenvalue_spectrum'

# Get variables names and labels from variables_to_scan:
labels = list(variables_to_scan.values())
scan_vars = variables_to_scan.keys()

# Use variable-specific percent variation
percent_var = {}
for var_name in scan_vars:
    percent_var[var_name] = root['SETTINGS']['PHYSICS']['RelativeChange_%s' % var_name]

# get results from baseline "original" run
ky_original = copy.deepcopy(scans_root['TGLF_baseline_FILES'][plotFolder]['ky'])
gamma1_original = copy.deepcopy(scans_root['TGLF_baseline_FILES'][plotFolder]['gamma(%d)' % mode_number])
freq1_original = copy.deepcopy(scans_root['TGLF_baseline_FILES'][plotFolder]['freq(%d)' % mode_number])


# setup plots
if separate_freq_plot:
    fig, axs = plt.subplots(1, len(scan_vars), figsize=(len(scan_vars) * 5, 5), sharey=True, sharex=True)
    fig2, axs2 = plt.subplots(1, len(scan_vars), figsize=(len(scan_vars) * 5, 5), sharey=True, sharex=True)

else:
    fig, axs = plt.subplots(1, len(scan_vars), figsize=(len(scan_vars) * 5, 5), sharey=True, sharex=True)
    if len(scan_vars) == 1:
        axs = [axs]  # prevents error when scanning only 1 variable

axs = np.atleast_1d(axs)
if separate_freq_plot:
    axs2 = np.atleast_1d(axs2)

axs[0].text(
    0.20,
    0.9,
    'Dominant mode' if mode_number == 1 else r"Subdominant mode #" + str(mode_number),
    fontsize=22,
    horizontalalignment='center',
    color='red',
    verticalalignment='center',
    transform=axs[0].transAxes,
    bbox=dict(boxstyle='round', facecolor='skyblue', alpha=0.5),
)

# fig.suptitle('Dominant mode' if mode_number==1 else r"Subdominant mode #"+str(mode_number),fontsize=16)
#     x=0.3,y=0.95, )

# find maximum gamma for plotting
if plot_gamma_lims[1] is None:
    for idx, var_name in enumerate(scan_vars):
        if normalized_freq:
            all_vals = [
                scans_root['TGLF_' + var_name + '_' + scan_dir + '_FILES'][plotFolder]['gamma(1)']
                / scans_root['TGLF_' + var_name + '_' + scan_dir + '_FILES'][plotFolder]['ky']
                for var_name in scan_vars
                for scan_dir in ['Up', 'Down']
            ]
        else:
            all_vals = [
                scans_root['TGLF_' + var_name + '_' + scan_dir + '_FILES'][plotFolder]['gamma(1)']
                for var_name in scan_vars
                for scan_dir in ['Up', 'Down']
            ]
        gamma_max = np.max(all_vals) + 0.1  # add a little for better visualization


# ==============
# loop over scanned variables
for idx, var_name in enumerate(scan_vars):

    # read results of scans -- only the TGLF 'FILES' folder is stored
    ky_up = copy.deepcopy(scans_root['TGLF_' + var_name + '_Up_FILES'][plotFolder]['ky'])
    gamma1_up = copy.deepcopy(scans_root['TGLF_' + var_name + '_Up_FILES'][plotFolder]['gamma(%d)' % mode_number])
    freq1_up = copy.deepcopy(scans_root['TGLF_' + var_name + '_Up_FILES'][plotFolder]['freq(%d)' % mode_number])

    ky_down = copy.deepcopy(scans_root['TGLF_' + var_name + '_Down_FILES'][plotFolder]['ky'])
    gamma1_down = copy.deepcopy(scans_root['TGLF_' + var_name + '_Down_FILES'][plotFolder]['gamma(%d)' % mode_number])
    freq1_down = copy.deepcopy(scans_root['TGLF_' + var_name + '_Down_FILES'][plotFolder]['freq(%d)' % mode_number])

    # choose whether to plot frequencies normalized to k_theta*rho_s
    if normalized_freq:
        axs[idx].plot(ky_down, gamma1_down / ky_down, 'g-', lw=2, label='-{}%'.format(int(percent_var[var_name] * 100.0)))
        axs[idx].plot(ky_original, gamma1_original / ky_original, 'b-', lw=2, label='Baseline')
        axs[idx].plot(ky_up, gamma1_up / ky_up, 'r-', lw=2, label='+{}%'.format(int(percent_var[var_name] * 100.0)))

        # +ve frequency (electron diamagnetic drift direction)
        axs[idx].scatter(
            ky_down[freq1_down > 0],
            gamma1_down[freq1_down > 0] / ky_down[freq1_down > 0],
            marker='o',
            s=100,
            edgecolors='g',
            facecolors='none',
            label='_nolegend_',
        )
        axs[idx].scatter(
            ky_original[freq1_original > 0],
            gamma1_original[freq1_original > 0] / ky_original[freq1_original > 0],
            marker='o',
            s=100,
            edgecolors='b',
            facecolors='none',
            label='_nolegend_',
        )
        axs[idx].scatter(
            ky_up[freq1_up > 0],
            gamma1_up[freq1_up > 0] / ky_up[freq1_up > 0],
            marker='o',
            s=100,
            edgecolors='r',
            facecolors='none',
            label='_nolegend_',
        )

        # -ve frequency (ion diamagnetic drift direction)
        axs[idx].scatter(
            ky_down[freq1_down < 0],
            gamma1_down[freq1_down < 0] / ky_down[freq1_down < 0],
            marker='s',
            s=100,
            edgecolors='g',
            facecolors='none',
            label='_nolegend_',
        )
        axs[idx].scatter(
            ky_original[freq1_original < 0],
            gamma1_original[freq1_original < 0] / ky_original[freq1_original < 0],
            marker='s',
            s=100,
            edgecolors='b',
            facecolors='none',
            label='_nolegend_',
        )
        axs[idx].scatter(
            ky_up[freq1_up < 0],
            gamma1_up[freq1_up < 0] / ky_up[freq1_up < 0],
            marker='s',
            s=100,
            edgecolors='r',
            facecolors='none',
            label='_nolegend_',
        )

    else:
        axs[idx].plot(ky_down, gamma1_down, 'g-', lw=2, label='-{}%'.format(int(percent_var[var_name] * 100.0)))
        axs[idx].plot(ky_original, gamma1_original, 'b-', lw=2, label='Baseline')
        axs[idx].plot(ky_up, gamma1_up, 'r-', lw=2, label='+{}%'.format(int(percent_var[var_name] * 100.0)))

    axs[idx].set_xscale('log')
    axs[idx].set_xlim([0.1, 24.0])
    axs[idx].grid('on')

    # Also plot ExB shearing rate computed in TGLF:
    axs[idx].axhline(root['TGLF']['FILES']['input.tglf']['VEXB_SHEAR'], c='r', ls='--', label='ExB shearing rate')

    # ylims:
    if (minGamma is not None) or (maxGamma is not None):
        axs[idx].set_ylim([minGamma, maxGamma])
        axs[idx].set_yticks(np.linspace(*axs[idx].get_ylim(), num=6))
    else:
        axs[idx].set_ylim([0, gamma_max])  # axs[idx].get_ylim()[1]])

    # if user prefers to have a separate plot for real frequency:
    if separate_freq_plot:
        axs2[idx].grid('on')
        # axs[idx].set_xticklabels('')
        if normalized_freq:
            axs2[idx].plot(ky_original, freq1_original / ky_original, 'b', lw=2)
            axs2[idx].plot(ky_up, freq1_up / ky_up, 'r', lw=2)
            axs2[idx].plot(ky_down, freq1_down / ky_down, 'g', lw=2)
        else:
            axs2[idx].plot(ky_original, freq1_original, 'b', lw=2)
            axs2[idx].plot(ky_up, freq1_up, 'r', lw=2)
            axs2[idx].plot(ky_down, freq1_down, 'g', lw=2)

        axs2[idx].set_xscale('log')
        axs2[idx].set_xlim([0.1, 24.0])
        axs2[idx].axhline(y=0, color='k', linewidth=1, ls='--')
        if (minFreq is not None) or (maxFreq is not None):
            axs2[idx].set_ylim([minFreq, maxFreq])
            axs2[idx].set_yticks(np.linspace(*axs2[idx].get_ylim(), num=6))
        axs2[idx].set_xlabel('$k_{\\theta}\\rho_s$')
    else:
        axs[idx].set_xlabel('$k_{\\theta}\\rho_s$')

    axs[idx].legend(loc='upper right', prop={'size': 22}, bbox_to_anchor=(1.1, 1.1)).draggable()

    if idx == 0:
        # only show y-labels on left-most plot
        axs[idx].set_ylabel('$\\gamma$ / $k_\\theta\\rho_s$ $[c_s/a]$')
        if separate_freq_plot:
            axs2[idx].set_ylabel('$\\omega$ / $k_\\theta\\rho_s$ $[c_s/a]$')

    # add text label to identify variable that was scanned in each plot
    axs[idx].text(
        0.7,
        0.7,
        labels[idx],
        fontsize=28,
        horizontalalignment='center',
        verticalalignment='center',
        transform=axs[idx].transAxes,
        bbox=dict(boxstyle='round', facecolor='skyblue', alpha=0.5),
    )

    # filling of spaces between scans (shadowing)
    if normalized_freq:
        axs[idx].fill_between(ky_original, gamma1_down / ky_down, gamma1_up / ky_up, facecolor='b', alpha=0.1)
    else:
        axs[idx].fill_between(ky_original, gamma1_down, gamma1_up, facecolor='b', alpha=0.1)

    if separate_freq_plot:
        if normalized_freq:
            axs2[idx].fill_between(ky_original, freq1_down / ky_down, freq1_up / ky_up, facecolor='b', alpha=0.1)
        else:
            axs2[idx].fill_between(ky_original, freq1_down, freq1_up, facecolor='b', alpha=0.1)


plt.tight_layout()
