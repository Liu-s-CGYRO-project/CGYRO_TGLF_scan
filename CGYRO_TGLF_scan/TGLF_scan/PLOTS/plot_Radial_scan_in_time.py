# -*-Python-*-
# Created by grierson at 08 Sep 2017  10:23

"""
This script plots the results of a radial scan for multiple times

defaultVars parameters
----------------------

"""
def growth_rate_color_limit(growth_rate):
    values = np.asarray(growth_rate, dtype=float)
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        raise ValueError('No finite growth rate for the time-average contour')
    vmax = float(np.max(np.abs(finite)))
    return vmax if vmax > 0 else 0.1


defaultVars(overlay=False)

rhos = root['SETTINGS']['PHYSICS']['rho_scan']
times = np.array(list(root['Experimental_spectra_in_time'][rhos[0]].keys()))
nrho = len(rhos)
nt = len(times)
nky = len(root['Experimental_spectra_in_time'][rhos[0]][times[0]]['eigenvalue_spectrum']['ky'])
kys = np.zeros((nrho, nt, nky))
freq1 = np.zeros((nrho, nt, nky))
gamma1 = np.zeros((nrho, nt, nky))
freq2 = np.zeros((nrho, nt, nky))
gamma2 = np.zeros((nrho, nt, nky))
for i, rho in enumerate(rhos):
    for j, t in enumerate(times):
        kys[i, j, :] = root['Experimental_spectra_in_time'][rho][t]['eigenvalue_spectrum']['ky']
        freq1[i, j, :] = root['Experimental_spectra_in_time'][rho][t]['eigenvalue_spectrum']['freq(1)']
        freq2[i, j, :] = root['Experimental_spectra_in_time'][rho][t]['eigenvalue_spectrum']['freq(2)']
        gamma1[i, j, :] = root['Experimental_spectra_in_time'][rho][t]['eigenvalue_spectrum']['gamma(1)']
        gamma2[i, j, :] = root['Experimental_spectra_in_time'][rho][t]['eigenvalue_spectrum']['gamma(2)']

# Plot the time evolution
fn = FigureNotebook('In Time')
nm = matplotlib.colors.Normalize(times.min(), times.max())
sm = matplotlib.cm.ScalarMappable(cmap=None, norm=nm)
sm.set_array(times)
for i, rho in enumerate(rhos):
    fig, ax = fn.subplots(label=rho, nrows=2, ncols=2, sharex=True, sharey='row')
    plotc(kys[i, :, :].T, gamma1[i, :, :].T, ax=ax[0, 0])
    cb = fig.colorbar(sm, ax=ax[0, 0], use_gridspec=True)
    cb.set_label('Time [ms]')

    plotc(kys[i, :, :].T, gamma2[i, :, :].T, ax=ax[0, 1])
    cb = fig.colorbar(sm, ax=ax[0, 1], use_gridspec=True)
    cb.set_label('Time [ms]')

    plotc(kys[i, :, :].T, freq1[i, :, :].T, ax=ax[1, 0])
    ax[1, 0].axhline(color='black', ls='dashed')
    cb = fig.colorbar(sm, ax=ax[1, 0], use_gridspec=True)
    cb.set_label('Time [ms]')

    plotc(kys[i, :, :].T, freq2[i, :, :].T, ax=ax[1, 1])
    ax[1, 1].axhline(color='black', ls='dashed')
    cb = fig.colorbar(sm, ax=ax[1, 1], use_gridspec=True)
    cb.set_label('Time [ms]')

    try:
        ax[0, 0].set_yscale('log')
    except Exception as _exc:
        ax[0, 0].set_yscale('linear')
    ax[1, 0].set_yscale('symlog')
    ax[1, 0].set_xscale('log')

    ax[0, 0].legend(['$\\gamma (c_s/a)$'], loc='best').draggable()
    ax[0, 1].legend(['$\\gamma (c_s/a)$'], loc='best').draggable()
    ax[1, 0].legend(['$\\omega (c_s/a)$'], loc='best').draggable()
    ax[1, 1].legend(['$\\omega (c_s/a)$'], loc='best').draggable()
    ax[0, 0].set_title('Most Unstable Mode')
    ax[0, 1].set_title('First Sub-Dominant Mode')
    ax[1, 0].set_xlabel('$k_\\theta \\rho_S$')
    ax[1, 1].set_xlabel('$k_\\theta \\rho_S$')

# Plot the mean and standard deviation
fn = FigureNotebook('Time Average')
for i, rho in enumerate(rhos):
    kys_tav = np.mean(kys[i, :, :], axis=0)
    gamma1_tav = np.mean(gamma1[i, :, :], axis=0)
    gamma1_std = np.std(gamma1[i, :, :], axis=0)
    gamma2_tav = np.mean(gamma2[i, :, :], axis=0)
    gamma2_std = np.std(gamma2[i, :, :], axis=0)
    freq1_tav = np.mean(freq1[i, :, :], axis=0)
    freq1_std = np.std(freq1[i, :, :], axis=0)
    freq2_tav = np.mean(freq2[i, :, :], axis=0)
    freq2_std = np.std(freq2[i, :, :], axis=0)

    fig, ax = fn.subplots(label=rho, nrows=2, ncols=2, sharex=True, sharey='row')
    if overlay:
        ax[0, 0].plot(kys[i, :, :].T, gamma1[i, :, :].T, color='black', alpha=0.5)
        ax[0, 1].plot(kys[i, :, :].T, gamma2[i, :, :].T, color='black', alpha=0.5)
        ax[1, 0].plot(kys[i, :, :].T, freq1[i, :, :].T, color='black', alpha=0.5)
        ax[1, 1].plot(kys[i, :, :].T, freq2[i, :, :].T, color='black', alpha=0.5)
    uband(kys_tav, uarray(gamma1_tav, gamma1_std), ax=ax[0, 0], label='$\\gamma (c_s/a)$')
    uband(kys_tav, uarray(gamma2_tav, gamma2_std), ax=ax[0, 1], label='$\\gamma (c_s/a)$')
    uband(kys_tav, uarray(freq1_tav, freq1_std), ax=ax[1, 0], label='$\\omega (c_s/a)$')
    ax[1, 0].axhline(0.0, color='black', ls='dashed')
    uband(kys_tav, uarray(freq2_tav, freq2_std), ax=ax[1, 1], label='$\\omega (c_s/a)$')
    ax[1, 1].axhline(0.0, color='black', ls='dashed')

    try:
        ax[0, 0].set_yscale('log')
    except Exception as _exc:
        ax[0, 0].set_yscale('linear')

    ax[1, 0].set_yscale('symlog')
    # Set shared x axis
    ax[1, 0].set_xscale('log')
    # Labels
    for axf in ax.flatten():
        axf.legend(loc='best').draggable()
    ax[0, 0].set_title('Most Unstable Mode')
    ax[0, 1].set_title('First Sub-Dominant Mode')
    ax[1, 0].set_xlabel('$k_\\theta \\rho_S$')
    ax[1, 1].set_xlabel('$k_\\theta \\rho_S$')

# Contour plot
gamma_sgn = np.mean(gamma1, axis=1) * sign(np.mean(freq1, axis=1))
gamma_vmax = growth_rate_color_limit(gamma_sgn)
ky_mean = np.mean(kys, axis=1)
rho2D = np.tile(np.array(rhos), (ky_mean.shape[1], 1)).T
fig, ax = plt.subplots()
CF = ax.contourf(
    rho2D,
    ky_mean,
    np.ma.masked_invalid(gamma_sgn),
    100,
    norm=matplotlib.colors.SymLogNorm(1e-1, vmin=-gamma_vmax, vmax=gamma_vmax),
    cmap='RdBu_r',
)
ax.set_yscale('log')
ax.set_xlabel('$\\rho$')
ax.set_ylabel('$k_\\perp \\rho_s$')

top = 0.9
bottom = 0.15
right = 0.75
fig.subplots_adjust(right=right, top=top, bottom=bottom)
right = right + 0.02
cax = fig.add_axes([right, bottom, 0.05, top - bottom])
cb = colorbar(CF, cax=cax)
cb.set_label('Growth rate * Sign(frequency)')
