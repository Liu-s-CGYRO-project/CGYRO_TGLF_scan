# -*-Python-*-
# Created by smithsp at 31 Mar 2017  11:04

"""
This script plots the growth rates vs ky and radius for the
experimental parameters.

"""
import matplotlib.colors
import numpy as np


def symmetric_contour_scale(data, linthresh, requested_vmax=None):
    """Strictly increasing finite levels, also for weak or identically zero spectra."""
    values = np.asarray(data, dtype=float)
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        raise ValueError('Contour requires at least one finite spectrum value')
    vmax = float(np.max(np.abs(finite))) if requested_vmax is None else float(requested_vmax)
    if not np.isfinite(vmax) or vmax < 0 or (requested_vmax is not None and vmax == 0):
        raise ValueError('Requested contour vmax must be finite and positive')
    if vmax == 0:
        vmax = float(linthresh)
    if vmax <= linthresh:
        levels = np.linspace(-vmax, vmax, 101)
    else:
        positive = np.geomspace(linthresh, vmax, 50)
        levels = np.concatenate((-positive[::-1], [0.0], positive))
    norm = matplotlib.colors.SymLogNorm(linthresh, vmin=-vmax, vmax=vmax)
    return levels, norm


defaultVars(plot_freq=False, gamma_vmax=None, omega_vmax=None)
# Settings for the symlognorm, these were the existing defaults,
gamma_lin_thresh = 0.1
omega_lin_thresh = 1.0
# rho values,
r = array(root['Experimental_spectra'].KEYS())
ky = root['Experimental_spectra']['eigenvalue_spectrum']['ky']
r = np.tile(r, (ky.shape[0], 1))

gamma = []
omega = []
# determine number of modes ahead of time instead of trial-and-error.
n_modes = len(root['Experimental_spectra']['eigenvalue_spectrum']['mode_num'])
for i in range(n_modes):
    gamma.append(root['Experimental_spectra']['eigenvalue_spectrum']['gamma(%d)' % (i + 1)])
    omega.append(root['Experimental_spectra']['eigenvalue_spectrum']['freq(%d)' % (i + 1)])

figlabel = ['Growth rate * sign(freq.)', 'Freq.']
nrow = 2 if plot_freq else 1
# the +1 on the columns is so we can include the colorbar axes in the subplotgrid.
# the only downside to this is that we can no longer use sharex=True, sharey=True
fig, axs = subplots(
    nrow,
    n_modes + 1,
    squeeze=False,
    figsize=(10.5, 6),
    gridspec_kw={'width_ratios': [10] * n_modes + [1]},
)
# selectivley share x, y axes amongst the plots,
axs_f = np.atleast_2d(axs)[:, :-1].flatten()
for i in range(1, len(axs_f)):
    axs_f[i].sharex(axs_f[0])
    axs_f[i].sharey(axs_f[0])

GOmega = np.sign(array(omega)) * array(gamma)

# loop over rows of the figure,
for fi, (figlab, dat) in enumerate(zip(figlabel, [gamma, omega][:nrow])):
    # loop over modes,
    for di, d in enumerate(dat):
        ax = axs[fi, di]
        if fi == 0:
            # if only plotting growthrate (default)
            gomega = d * sign(array(omega[di]))
            # print(sign(array(omega[di])).max(), sign(array(omega[di])).min())
            glvls, cnorm = symmetric_contour_scale(GOmega, gamma_lin_thresh, gamma_vmax)
            CSg = ax.contourf(r, ky, np.ma.masked_invalid(gomega), levels=glvls, norm=cnorm, cmap='RdBu_r')
            ax.set_title('Mode %s' % (di + 1))
        else:
            # if also plotting the real freuqency,
            olvls, cnorm = symmetric_contour_scale(omega, omega_lin_thresh, omega_vmax)
            CSo = ax.contourf(r, ky, np.ma.masked_invalid(d), levels=olvls, norm=cnorm, cmap='RdBu_r')

        rlab = 'rmin/a'
        if root['TGYRO']['INPUTS']['input.tgyro']['TGYRO_USE_RHO']:
            rlab = r'$\rho$'
        ax.set_xlabel(rlab)
        ax.set_ylabel(r'$k_y$ ($k_\theta\rho_s$)')
        ax.set_yscale('log')

fig.tight_layout()
autofmt_sharexy(fig=fig)
# make room to move the colorbar over...
fig.subplots_adjust(right=0.9)


def generate_symlog_ticks(thresh, high, num):
    if high <= thresh:
        return np.linspace(-high, high, 5)
    positive = np.unique(np.r_[thresh, np.geomspace(thresh, high, num)])
    return np.r_[-positive[::-1], 0.0, positive]


cbar_kwargs = dict(aspect=10, format=matplotlib.ticker.LogFormatterMathtext())
if nrow == 2:
    # to properly generate ticks we need to do it manually.
    # this is another problem with the SymLogNorm.
    g_ticks = generate_symlog_ticks(gamma_lin_thresh, max(glvls), 3)
    cax = axs[0, -1]
    cb = colorbar(CSg, ticks=g_ticks, cax=cax, **cbar_kwargs)
    cb.set_label(r'Growth rate * sign(freq.) [$c_s/a$]')
    l, b, w, h = cax.get_position().bounds
    cax.set_position([l + 0.01, b, w, h])

    # cax = fig.add_axes([right, bottom, 0.05, 0.5 - bottom])
    o_ticks = generate_symlog_ticks(omega_lin_thresh, max(olvls), 3)
    cax = axs[1, -1]
    cb = colorbar(CSo, cax=cax, ticks=o_ticks, **cbar_kwargs)
    cb.set_label(r'Freq. [$c_s/a$]')
    l, b, w, h = cax.get_position().bounds
    cax.set_position([l + 0.01, b, w, h])
elif nrow == 1:
    g_ticks = generate_symlog_ticks(gamma_lin_thresh, max(glvls), 3)
    cax = axs[0, -1]
    cb = fig.colorbar(CSg, cax=cax, ticks=g_ticks, **cbar_kwargs)  # ,format='$10^{%g')
    cb.set_label(r'Growth rate * sign(freq.) [$c_s/a$]')
    l, b, w, h = cax.get_position().bounds
    cax.set_position([l + 0.01, b, w, h])
