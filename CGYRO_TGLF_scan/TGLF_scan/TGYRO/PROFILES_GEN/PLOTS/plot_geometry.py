# -*-Python-*-


"""
This script can be used to plot any list of items from input.gacode, e.g. main equlibrium parameters. 
If inputs is a list of locations, several input.gacode files can be compared

defaultVars parameters

:param inputs: list of locations of input.gacode files to plot (Exp: root['OUTPUTS']['input.gacode']) 
- to plot input ; ['TGYRO_GACODE']['RUN_DB']['id']['OUTPUTS']['input.gacode'] - to plot TGYRO output)
variables_list: list of variables to plot

"""

defaultVars(inputs=[root['OUTPUTS']['input.gacode']], variables_list=['s', 'kappa', 'delta', 'skappa', 'sdelta', 'zeta', 'bunit', 'q'])

# description of these variables in https://fusion.gat.com/theory/Gyrogeometry#Equilibria
labels_input_list = arange(1, len(inputs) + 1, 1)  # list should be filled out if different input.gacode files are compared
labels_var_list = variables_list  # user defined labels for the legend


# Calculate number of columns based on the number of variables to plots
cols = len(variables_list) // 2

fig, axx = plt.subplots(nrows=2, ncols=cols, sharex=True, figsize=(5 * cols, 10))


for n, inp in enumerate(inputs):

    for index, item in enumerate(variables_list):

        ax = axx.flat[index]
        label = f"{labels_input_list[n]}" + ' ' + f"{labels_var_list [index]}"
        if item == 'q':
            y = abs(inp[item])
        else:
            y = inp[item]
        ax.plot(inp['rho'], y, label=label)
        ax.legend().draggable()
        ax.set_ylim(min(y), max(y) * 1.1)
        if index >= cols:
            ax.set_xlabel(r'$\rho$')

fig.tight_layout()
