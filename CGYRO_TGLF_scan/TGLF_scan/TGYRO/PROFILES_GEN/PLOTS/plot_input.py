# -*-Python-*-
# Created by grierson at 05 Jan 2020  07:42
# Modified by galinaavdeeva at 09 Sep 2022  21:56


"""
This script produces a more legible plotting of input.gacode more akin to what you would show in a publication, rather than plotting simply everything.

defaultVars parameters

:param inp: location of input.gacode files to plot (Exp: root['OUTPUTS']['input.gacode'] - to plot input ; ['TGYRO_GACODE']['RUN_DB']['id']['OUTPUTS']['input.gacode'] - to plot TGYRO output)

:param rho_max: vertical line at particular rho locations; useful to check the data for TGYRO boundary ( Exp: 0.7 or ['TGYRO_GACODE']['INPUTS']['input.tgyro']['TGYRO_RMAX'])

"""

defaultVars(inp=root['OUTPUTS']['input.gacode'])

# Some basic parameter plots

ions = inp['IONS']

fig, ax = plt.subplots(nrows=2, ncols=4, sharex=True, figsize=(15, 10))
# Densities
ax[0, 0].plot(inp['rho'], inp['ne'], label='ne')
for k in ions.keys():
    if ions[k][3] == 'therm':
        ax[0, 0].plot(inp['rho'], inp['ni_{}'.format(k)] * ions[k][1], label='$Z_{} n_{}$'.format(ions[k][0], ions[k][0]))
    elif ions[k][3] == 'fast':
        sub = '{}f'.format(ions[k][0])
        ax[0, 0].plot(inp['rho'], inp['ni_{}'.format(k)], label='$n_{}$'.format(sub))
ax[0, 0].set_title('Densities')


# Temperatures
ax[0, 1].plot(inp['rho'], inp['Te'], label='Te')
ax[0, 1].plot(inp['rho'], inp['Ti_1'], label='Ti')

# Rotation
ax[0, 2].plot(inp['rho'], inp['omega0'], label='omega0')

# Equilibrium
ax[0, 3].plot(inp['rho'], abs(inp['q']), label='q')
ax[0, 3].axhline(1.0, ls='dashed')

# Density scale lengths
ax[1, 0].plot(inp['rho'], inp['dlnnedr'], label='a/Lne')
ax[1, 0].plot(inp['rho'], inp['dlnnidr_1'], label='a/Ln{}'.format(ions[1][0]))


# Temperature scale lengths
ax[1, 1].plot(inp['rho'], inp['dlntedr'], label='a/LTe')
ax[1, 1].plot(inp['rho'], inp['dlntidr_1'], label='a/LTi')

# Rotation scale Lengths
ax[1, 2].plot(inp['rho'], inp['gamma_e'], label='gamma_e')
ax[1, 2].set_ylim([0, 5e4])
ax122 = ax[1, 2].twinx()
ax122.plot(inp['rho'], inp['gamma_p'], label='gamma_p', color='g')
ax122.set_ylim([-1e6, 0])
ax122.legend(loc=2)

# Equilibrium scale lengths
ax[1, 3].plot(inp['rho'], inp['s'], label='s')
# ax[1,3].set_ylim([0,3])

axf = ax.flatten()
for axx in axf:
    axx.axhline(0.0, ls='dashed')

    axx.legend()
for i in range(4):
    ax[1, i].set_xlabel('$\\rho$')
