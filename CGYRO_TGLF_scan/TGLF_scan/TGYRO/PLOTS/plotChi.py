# -*-Python-*-
# Created by todstrcil at 29 Apr 2018  12:04


from OMFITlib_general import calc_heat_conductivity

chi = calc_heat_conductivity()


fn = FigureNotebook(0, 'Heat Transport')


fig, ax = fn.subplots(label='chi_i')
if 'chi_i_tglf_scan' in chi:
    ax.plot(chi['rho_scan'], chi['chi_i_tglf'], 'r.-', label='TGLF scan')
ax.plot(chi['rho_tgyro'], chi['chi_i_neo'], 'Db--', label='NEO', markerfacecolor='w')
ax.plot(chi['rho_tgyro'], chi['chi_i_exp_target'], 'k.-', label='TGYRO target')
ax.plot(chi['rho_input'], chi['chi_i_exp'], 'y-', label='input.gacode')
ax.plot(chi['rho_tgyro'], chi['chi_i_tglf'], 'or--', label='TGLF')

ax.legend(loc='upper left')
ax.set_xlim(0, 1)
ax.set_ylim(0.1, 20)
ax.set_yscale('log')
ax.set_xlabel(r'$\rho$')
ax.set_ylabel(' $\chi_i\ \mathrm{[m^2/s]}$', fontsize=15)
ax.grid('on')


fig, ax = fn.subplots(label='chi_e')
if 'chi_e_tglf_scan' in chi:
    ax.plot(chi['rho_scan'], chi['chi_e_tglf_scan'], 'r.-', label='TGLF+NEO')
ax.plot(chi['rho_tgyro'], chi['chi_e_neo'], 'Db--', label='NEO', markerfacecolor='w')
ax.plot(chi['rho_tgyro'], chi['chi_e_exp_target'], 'k.-', label='TGYRO target')
ax.plot(chi['rho_input'], chi['chi_e_exp'], 'y-', label='input.gacode')
ax.plot(chi['rho_tgyro'], chi['chi_e_tglf'], 'or--', label='TGYRO')


ax.legend(loc='upper left')
ax.set_xlim(0, 1)
ax.set_ylim(0.1, 20)
ax.set_yscale('log')
ax.set_xlabel(r'$\rho$', fontsize=15)
ax.set_ylabel(' $\chi_e\ \mathrm{[m^2/s]}$', fontsize=15)
ax.grid('on')


fig, ax = fn.subplots(label='Qi')

if 'Qi_tglf_scan' in chi:
    ax.plot(chi['rho_scan'], chi['Qi_tglf_scan'] / 1e3, label='NEO+TGLF')  # W/m^-2
ax.plot(chi['rho_tgyro'], chi['Qi_neo'] / 1e3, 'Db--', label='NEO')  # W/m^-2
ax.plot(chi['rho_tgyro'], chi['Qi_exp_target'] / 1e3, 'k.-', label='eflux_i_target')
ax.plot(chi['rho_input'], chi['Qi_exp'] / 1e3, 'y-', label='input.profile:pow_i')  # almost identical to TRANSP profile
ax.plot(chi['rho_input'], chi['Qie_exp'] / 1e3, 'r-', label='input.profile:pow_ei')  # almost identical to TRANSP profile

ax.plot(chi['rho_tgyro'], chi['Qi_tglf'] / 1e3, 'or--', label='eflux_i_tot')  # W/m^-2
ax.legend(loc='best')
ax.set_xlabel(r'$\rho_{tor}$')
ax.set_ylabel(r'$Q_i$ [kW/m$^2$]')
ax.set_ylim(0, None)


fig, ax = fn.subplots(label='Qe')

if 'Qe_tglf_scan' in chi:
    ax.plot(chi['rho_scan'], chi['Qe_tglf_scan'] / 1e3, 'r.-', label='TGLF+NEO')  # W/m^-2
ax.plot(chi['rho_tgyro'], chi['Qe_neo'] / 1e3, 'Db--', label='NEO')  # W/m^-2

ax.plot(chi['rho_tgyro'], chi['Qe_exp_target'] / 1e3, 'k.-', label='eflux_e_target')  # W/m^-2
ax.plot(chi['rho_input'], chi['Qe_exp'] / 1e3, 'y-', label='input.profile:pow_e')  # almost identical to TRANSP profile
ax.plot(chi['rho_input'], chi['Qie_exp'] / 1e3, 'r-', label='input.profile:pow_ei')  # almost identical to TRANSP profile
ax.plot(chi['rho_tgyro'], chi['Qe_tglf'] / 1e3, 'or--', label='eflux_e_tot')  # W/m^-2
ax.set_xlabel(r'$\rho_{tor}$')
ax.set_ylabel(r'$Q_e$ [kW/m$^2$]')
ax.set_ylim(0, None)
ax.legend(loc='best')
