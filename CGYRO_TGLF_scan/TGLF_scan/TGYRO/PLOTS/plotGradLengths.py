# -*-Python-*-
# Created by avdeevag at 14 Sep 2022  10:42


"""

This script is similar to compare plots, but with more flexibility. Can iterate over different modules
Gradients are properly normilized

defaultVars parameters:

scans: RUN_DB outputs

labels : user defined lables for each item in scans. Can also be left empty, e.g. ['','']

measures: list of TGYRO outputs to plot - RESULTS OF PREDICTION
exp_output: list of input.gacode variables to plot  - TARGET (EXPERIMENTAL )VALUES
y_labels: list of y-axis labels, should be equal to len(measures)
plot_subplot: True or False
linestyles, colors, linewidths: lists can be specified by used
"""


defaultVars(
    run_db=scratch.get('plot_runids', []),  # RUN_DB outputs
    labels=scratch.get('plot_runids', []),
    measures=['te', 'ti1', 'a/Lte', 'a/Lti1'],  # Results of prediction: list of tgyro output to plot : eg Te, Ti, a/Lti1
    exp_output=['Te', 'Ti_1', 'dlntedr', 'dlntidr_1'],  # Experimental values: list of input.gacode variables to plot
    y_label=['$T_e$ [keV]', '$T_i$ [keV]', r'$a/L_{T_e}$', r'$a/L_{T_i}$'],
    plot_subplots=True,  # use False  if want to plot each measures at separate plot
    linestyles=None,  # list of linestyles, to use default settings set None to this field
    colors=None,  # list of colors, to use default settings set None to this field
    linewidths=None,  # list of linewidths, to use default settings set None to this field
)


if linestyles is None:
    linestyles = ['-'] * len(run_db)
if colors is None:
    colors = cm.rainbow(np.linspace(0, 1, len(run_db)))
if linewidths is None:
    linewidths = [2] * len(run_db)

if not measures or not run_db:
    raise OMFITexception('Select at least one quantity and one run to plot')
cols = max(1, (len(measures) + 1) // 2)
if plot_subplots:
    fig, axx = plt.subplots(2, ncols=cols, sharex=True, figsize=(5 * cols, 8), squeeze=False)
    for unused_ax in axx.flat[len(measures):]:
        unused_ax.set_visible(False)


for index, val in enumerate(measures):

    if not plot_subplots:
        fig, ax = plt.subplots(1, 1)
        raw = 1
    else:
        ax = axx.flat[index]

    for n, run_id in enumerate(run_db):

        linestyle = linestyles[n]

        color = colors[n]

        lw = linewidths[n]

        Exp = root['PROFILES_GEN']['OUTPUTS']['input.gacode'][exp_output[index]]

        if root['RUN_DB'][run_id]['INPUTS']['input.tgyro']['TGYRO_USE_RHO'] != 1:
            rho = root['PROFILES_GEN']['OUTPUTS']['input.gacode']['rmin'] / max(root['PROFILES_GEN']['OUTPUTS']['input.gacode']['rmin'])
            xlabel = 'r/a'
        else:
            rho = root['PROFILES_GEN']['OUTPUTS']['input.gacode']['rho']
            xlabel = r'$\rho$'
        if 'dlnt' in exp_output[index]:

            a = np.max(root['PROFILES_GEN']['OUTPUTS']['input.gacode']['rmin'])
            Exp = Exp * a  # need integration for gradeints
        # aol = -a * deriv(a, Te) / Te

        if n == 0:
            ax.plot(rho, Exp, linestyle='-', lw=5, color='grey', label='Experimental values')

        TGYRO_out = root['RUN_DB'][run_id]['OUTPUTS']['output'][val]
        if root['RUN_DB'][run_id]['INPUTS']['input.tgyro']['TGYRO_USE_RHO'] != 1:
            rho = root['RUN_DB'][run_id]['OUTPUTS']['output']['r/a']
        else:
            rho = root['RUN_DB'][run_id]['OUTPUTS']['output']['rho']
        # start plotting from [1] as do not want to plot point 0
        ax.plot(rho[-1][1:], TGYRO_out[-1][1:], linestyle=linestyle, marker='o', color=color, label=labels[n], lw=lw)
        # plot legend only at the first subplot
        if index == 0:
            ax.legend()
        # show x labels only for the last raw of subplots
        if not plot_subplots or index >= cols:
            ax.set_xlabel(xlabel)
        ax.set_ylabel(f'{y_label[index]}')
ax.set_xlabel(xlabel)
fig.tight_layout()
