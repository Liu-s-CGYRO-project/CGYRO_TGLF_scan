# -*-Python-*-
# Created by grierson at 03  Aug 2016  17:13

defaultVars(iteration_step=None)

runs = root['RUN_DB']

fig, ax = plt.subplots(2, 4)

for ip, ipkey, opkey, lpkey, ptex, pname, punits, pscale in zip(
    range(4),
    ['Te', 'Ti_1', 'ne', 'omega0'],
    ['te', 'ti1', 'ne', 'w0'],
    ['te', 'ti1', 'ne', 'a*gamma_e/cs'],
    ['T_e', 'T_i', 'n_e', '\\omega_0'],
    ['Electron Temperature', 'Ion Temperature', 'Electron Density', 'Toroidal Rotation'],
    ['keV', 'keV', 'e19m**-3', 'rad/s'],
    [1.0, 1.0, 1e-13, 1.0],
):

    ylim = None
    for i, run in enumerate(scratch['plot_runids']):
        input = root['RUN_DB'][run]['PROFILES_GEN']['input.gacode']
        output = root['RUN_DB'][run]['OUTPUTS']['output']
        a = np.max(input['rmin'])

        # Conditional for a zero iteration run
        nit = len(output['convergence']) - 1
        if nit == 0:
            printi('Not plotting {}: 0 iterations'.format(run))
            continue
        if iteration_step is not None:
            input_new = list(root['RUN_DB'][run]['OUTPUTS']['output']['input_gacode_evolution'].values())[iteration_step]
        elif 'input.gacode' in root['RUN_DB'][run]['OUTPUTS']:
            input_new = root['RUN_DB'][run]['OUTPUTS']['input.gacode']
        else:
            input_new = None

        # Profiles in rho
        if i == 0:
            ax[0, ip].plot(input['rho'], input[ipkey], color='grey', label='Target', linewidth=2)  # Legend label
        else:
            ax[0, ip].plot(input['rho'], input[ipkey], color='grey')
        if input_new is not None:
            ax[0, ip].plot(input_new['rho'], input_new[ipkey], label=run, linewidth=2)

        # a/L_X in rho
        if ipkey == 'omega0':
            cs = np.sqrt(input['Te'] * 1e3 * scipy.constants.e / 2.0 / scipy.constants.m_p)
            der = -(input['rmin'] / input['q']) * deriv(input['rmin'], input['omega0'])
            aol = a * der / cs
            aolt = output['a*gamma_e/cs']
            ylab = '$a\\gamma_E/c_s$'
        else:
            aol = -a * deriv(input['rmin'], input[ipkey]) / input[ipkey]
            aolt = output['a/L{}'.format(lpkey)]
            ylab = '$a/L{}$'.format(lpkey)
        # Setting good limits
        if ylim is None:
            ylim = [np.floor(np.min(aolt)), np.ceil(np.max(aolt))]
            if ylim[1] <= 1.0:
                ylim = [np.floor(np.min(aolt)), np.ceil(np.max(aolt) * 10.0) / 10.0]
        else:
            ylim2 = [np.floor(np.min(aolt)), np.ceil(np.max(aolt))]
            if ylim2[1] <= 1.0:
                ylim2 = [np.floor(np.min(aolt)), np.ceil(np.max(aolt) * 10.0) / 10.0]
            if ylim2[0] < ylim[0]:
                ylim[0] = ylim2[0]
            if ylim2[1] > ylim[1]:
                ylim[1] = ylim2[1]
        ax[1, ip].plot(input['rho'], aol, color='grey', linewidth=2)
        ax[1, ip].plot(output['rho'][nit, :], aolt[nit, :], label=run, linewidth=2)

    # Labels for profiles
    ax[0, ip].set_title(pname)
    ax[0, ip].set_ylabel('${}$'.format(ptex))
    ax[0, 0].legend(loc='best').draggable(True)

    # Labels for a/L_X
    ax[1, ip].set_title('Norm. Inverse Scale Length')
    ax[1, ip].set_xlabel('$\\rho$')
    ax[1, ip].set_ylim(ylim)
    ax[1, ip].set_ylabel(ylab)
