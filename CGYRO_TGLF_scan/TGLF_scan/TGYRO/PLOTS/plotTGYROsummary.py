# -*-Python-*-
# Created by cholland at 2015/03/17 12:25

defaultVars(exp_profiles=input_gacode, input=root['INPUTS']['input.tgyro'], output=root['OUTPUTS']['output'])

if output['eflux_e_tot'].shape[0] > 1:
    iteration = output['eflux_e_tot'].shape[0] - 1
else:
    iteration = 0
idx = -1

fig, axs = subplots(4, 2, sharex=True, squeeze=False, sharey=False, num=gcf().number)
fig.suptitle(
    '%s %d %d ms iteration %d'
    % (
        tokamak(root['SETTINGS']['EXPERIMENT']['device']),
        root['SETTINGS']['EXPERIMENT']['shot'],
        root['SETTINGS']['EXPERIMENT']['time'],
        iteration,
    )
)

axs.flat[0].set_title('Profiles')
axs.flat[1].set_title('Fluxes')

# setup experimental profiles and fluxes from input.gacode
Ti_exp = exp_profiles['Ti_1']
Te_exp = exp_profiles['Te']
ne_exp = exp_profiles['ne']
Romega_exp = (exp_profiles['rmin'] + exp_profiles['rmaj']) * exp_profiles['omega0']  # m/s
exp_rho = exp_profiles['rho']
exp_rmin = exp_profiles['rmin']
exp_rmin = exp_rmin / max(exp_rmin)
polflux = exp_profiles['polflux']  # in case we ever need it
exp_psin = (polflux - polflux[0]) / (polflux[exp_profiles['N_EXP'] - 1] - polflux[0])
exp_volp = np.array(exp_profiles['volp'], copy=True)  # m^2
exp_volp[0] = 1.0  # fix for div by 0

if 'input.gacode_base' in PROFILES_GEN['OUTPUTS']:
    exp_volp = np.array(PROFILES_GEN['OUTPUTS']['input.gacode_base']['volp'], copy=True)  # m^2
    exp_volp[0] = 1.0  # fix for div by 0
elif 'input.gacode' in PROFILES_GEN['OUTPUTS']:
    exp_volp = np.array(PROFILES_GEN['OUTPUTS']['input.gacode']['volp'], copy=True)  # m^2
    exp_volp[0] = 1.0  # fix for div by 0
else:
    exp_volp = 1.0
exp_G_beam = exp_profiles['flow_beam'] / exp_volp  # kW/eV/m**2
exp_G_wall = exp_profiles['flow_wall'] / exp_volp  # kW/eV/m**2
exp_Q_i = exp_profiles['pow_i'] / exp_volp * 1e2  # MW/m**2*1e2 -> W/cm**2
exp_Q_e = exp_profiles['pow_e'] / exp_volp * 1e2  # MW/m**2*!e2 -> W/cm**2
exp_Pi_i = exp_profiles['flow_mom'] / exp_volp
# turn particle flux into convective energy flux Qe,conv = 1.5*Te*Gamma
exp_G_beam *= 1.5 * Te_exp * 1e2  # kW/eV/m**2 -> MW/m**2*1e2 -> W/cm**2
exp_G_wall *= 1.5 * Te_exp * 1e2  # kW/eV/m**2 -> MW/m**2*1e2 -> W/cm**2
exp_G_tot = exp_G_beam + exp_G_wall

Q_gB = output['Q_GB'][iteration, :] * 1e2  # MW/m**2 -> W/cm**2
Pi_gB = output['Pi_GB'][iteration, :]  # J/m**2 = N/m


if input is None or input['TGYRO_USE_RHO'] == 1:
    xtitle = 'rho'
    x_exp = exp_rho
    x_tgyro = output.sprofile('rho', x=xtitle)
    x0 = output['rho'][iteration, :]
else:
    xtitle = 'r/a'
    x_exp = exp_rmin
    x_tgyro = output.sprofile('r/a', x=xtitle)
    x0 = output['r/a'][iteration, :]

# plot Ti
sca(axs.flat[0])
gca().set_ylabel('$T_i$ (keV)')
y0 = output['ti1'][iteration, :]
plot(x0, y0, marker='o', ls='', color='red')
Ti_tgyro = output.sprofile('ti1', x=xtitle)[:, idx]
plot(x_tgyro, Ti_tgyro, ls='-', label='model', color='red')
plot(x_exp, Ti_exp, label='expt.', ls='--', color='black')
legend(loc='best').draggable(True)

# plot Qi
sca(axs.flat[1])
gca().set_ylabel('$Q_i$ (W/$cm^2$)')
plot(x_exp, exp_Q_i, label='power balance', ls='--', color='black')
plot(x0, output['eflux_i_target'][iteration, :] * Q_gB, ls='-', color='black', label='target')
plot(x0, output['eflux_i_tot'][iteration, :] * Q_gB, ls='-', marker='o', color='red', label='model (tot)')
Qi_neo = output['eflux_i1_neo'][iteration, :]
plot(x0, Qi_neo * Q_gB, ls='-', marker='o', color='blue', label='neoclassical')
# legend(loc='best').draggable(True)

# plot Te
sca(axs.flat[2])
gca().set_ylabel('$T_e$ (keV)')
y0 = output['te'][iteration, :]
plot(x0, y0, marker='o', ls='', color='red')
Te_tgyro = output.sprofile('te', x=xtitle)[:, idx]
plot(x_tgyro, Te_tgyro, ls='-', label='model', color='red')
plot(x_exp, Te_exp, label='expt.', ls='--', color='black')

# plot Qe
sca(axs.flat[3])
gca().set_ylabel('$Q_e$ (W/$cm^2$)')
plot(x_exp, exp_Q_e, label='power balance', ls='--', color='black')
legend(loc='best').draggable(True)
plot(x0, output['eflux_e_target'][iteration, :] * Q_gB, ls='-', color='black', label='target')
plot(x0, output['eflux_e_tot'][iteration, :] * Q_gB, ls='-', marker='o', color='red', label='model (tot)')
plot(x0, output['eflux_e_neo'][iteration, :] * Q_gB, ls='-', marker='o', color='blue', label='neoclassical')
legend(loc='best').draggable(True)

# plot ne
sca(axs.flat[4])
gca().set_ylabel('$n_e$ ($10^{19}/m^3$)')
y0 = output['ne'][iteration, :] / 1e13
plot(x0, y0, marker='o', ls='', color='red')
ne_tgyro = output.sprofile('ne', x=xtitle)[:, idx] / 1e13
plot(x_tgyro, ne_tgyro, ls='-', label='model', color='red')
plot(x_exp, ne_exp, label='expt.', ls='--', color='black')

# plot Qe,conv = 1.5*Te*Ge
sca(axs.flat[5])
gca().set_ylabel('$Q_{e,conv} = 1.5*T_e*\Gamma_e$ (W/$cm^2$)')
if root['INPUTS']['input.tgyro']['LOC_PFLUX_METHOD'] == 3:
    plot(x_exp, exp_G_tot, label='PB: beam+wall', ls='--', color='black')
    plot(x_exp, exp_G_beam, label='PB: beam', ls='-.', color='grey')
    plot(x_exp, exp_G_wall, label='PB: wall', ls=':', color='grey')
elif root['INPUTS']['input.tgyro']['LOC_PFLUX_METHOD'] == 2:
    plot(x_exp, exp_G_beam, label='PB: beam', ls='--', color='black')
elif root['INPUTS']['input.tgyro']['LOC_PFLUX_METHOD'] == 1:
    plot(x_exp, 0.0 * exp_G_beam, ls='--', color='black')
plot(x0, 1.5 * output['pflux_e_target'][iteration, :] * Q_gB, ls='-', color='black')
plot(x0, 1.5 * output['pflux_e_tot'][iteration, :] * Q_gB, ls='-', marker='o', color='red')
plot(x0, 1.5 * output['pflux_e_neo'][iteration, :] * Q_gB, ls='-', marker='o', color='blue')
legend(loc='best').draggable(True)

# plot R*omega
sca(axs.flat[6])
gca().set_xlabel(xtitle)
gca().set_ylabel('R*$\Omega_0$ (km/s)')
y0 = output['M=wR/cs'][iteration, :] * output['c_s'][iteration, :]
plot(x0, y0 / 1e3, marker='o', ls='', color='red')
plot(x_exp, Romega_exp / 1e3, label='expt.', ls='--', color='black')

# plot Pi_i
sca(axs.flat[7])
gca().set_ylabel('$\Pi_i$ (N/m)')
plot(x_exp, exp_Pi_i, label='power balance', ls='--', color='black')
plot(x0, output['mflux_target'][iteration, :] * Pi_gB, ls='-', color='black', label='target')
plot(x0, output['mflux_tot'][iteration, :] * Pi_gB, ls='-', marker='o', color='red', label='model (tot)')
Pi_neo = output['mflux_i1_neo'][iteration, :]
plot(x0, Pi_neo * Pi_gB, ls='-', marker='o', color='blue', label='neoclassical')
cornernote('%s' % ((root['SETTINGS']['EXPERIMENT']['runid'])), '', ax=axs.flat[7])

# plot(x_exp, exp_Q_i+exp_Q_e,label='power balance',ls='--',color='black')
# plot(x0,(output['eflux_i_target'][iteration,:] + output['eflux_e_target'][iteration,:])*Q_gB*1.76, ls='-',color='black',label='target')


# Calculate metrics
# sca(axs.flat[8])
# plot(x_exp, Ti_exp,color='black')
# plot(x_tgyro, Ti_tgyro, color='red')
# Ti_exp_interp = interp1d(x
