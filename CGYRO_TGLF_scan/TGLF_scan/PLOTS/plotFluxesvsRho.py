# -*-Python-*-
# Created by thomek at 20 Jun 2016  09:29


rho = root['tgyro_output']['rho'][0]
expGm = root['tgyro_output']['pflux_e_target'][0]
expQe = root['tgyro_output']['eflux_e_target'][0]
expQi = root['tgyro_output']['eflux_i_target'][0]
expPi = root['tgyro_output']['mflux_target'][0]
fig, (ax1, ax2, ax3) = subplots(3, sharex=True)
fig.suptitle('Fluxes in gyroBohm units', fontsize=22)
ax1.plot(rho, expGm)
ax1.axis([0, 1, 0, 2])
ax1.set_ylabel(r'$\Gamma$', fontsize=20)
ax2.plot(rho, expQe, label='elec')
ax2.axis([0, 1, 0, 10])
ax2.plot(rho, expQi, label='ion')
ax2.set_ylabel('Q', fontsize=20)
ax2.legend().draggable(True)
ax3.plot(rho, expPi)
ax3.axis([0, 1, 0, -6])
ax3.set_ylabel(r'$\Pi$', fontsize=20)
xlabel(r'$\rho$', fontsize=20)
