# -*-Python-*-
# Created by pvaezi at 2018/01/12 11:30

"""
This script plots the input probability distribution and forward
propagated distribution of QoI (quantity of interest) obtained
via Probabilistic Collocation Method.

----------------------
"""

import chaospy as cp
import numpy as np
import builtins
from builtins import min, max
from scipy import stats
from pylab import rcParams
from sklearn import metrics

# configure plot parameters
rcParams['font.size'] = 20
rcParams['lines.linewidth'] = 3
rcParams['axes.linewidth'] = 3
rcParams['axes.labelsize'] = 20
rcParams['xtick.labelsize'] = 20
rcParams['ytick.labelsize'] = 20
rcParams['figure.figsize'] = (10, 8)

# adjusted R^2 for the goodness of fit
def adj_r2_score(design_rank, y, yhat):
    """Adjusted R2 for explicit ordinary least squares including an intercept."""
    y, yhat = np.asarray(y, dtype=float).ravel(), np.asarray(yhat, dtype=float).ravel()
    if y.size != yhat.size or design_rank < 1 or y.size <= design_rank:
        raise ValueError('Adjusted R2 requires matching data and positive residual degrees of freedom')
    if not np.all(np.isfinite(y)) or not np.all(np.isfinite(yhat)):
        raise ValueError('Adjusted R2 requires finite data')
    return 1.0 - (y.size - 1.0) * (1.0 - metrics.r2_score(y, yhat)) / (y.size - design_rank)


def fit_cp_least_squares(P, nodes, data):
    """Fit the evaluated chaos basis using explicit unregularized least squares.

    This avoids assuming a particular Chaospy default solver or regularization.
    The basis must include its constant term and be identifiable from samples.
    """
    nodes = np.atleast_2d(np.asarray(nodes, dtype=float))
    y = np.asarray(data, dtype=float).ravel()
    design = np.asarray(P(*nodes), dtype=float).reshape(len(P), nodes.shape[1]).T
    if y.size != design.shape[0] or not np.all(np.isfinite(design)) or not np.all(np.isfinite(y)):
        raise ValueError('Finite basis/sample values and matching sample counts are required')
    if not np.any(np.all(np.isclose(design, 1.0), axis=0)):
        raise ValueError('The polynomial basis must include a constant term')
    coefficients, _, rank, _ = np.linalg.lstsq(design, y, rcond=None)
    if rank != design.shape[1] or y.size <= rank:
        raise ValueError('Polynomial basis is rank deficient or has no residual degrees of freedom')
    polynomial = builtins.sum(float(c) * term for c, term in zip(coefficients, P))
    return polynomial, int(rank), design @ coefficients


def uq_species_groups(species, combine_ions):
    if not species:
        raise ValueError('No species in UQ results')
    if not combine_ions:
        return [(name, [index]) for index, name in enumerate(species)]
    electrons = [i for i, name in enumerate(species) if name == 'elec']
    ions = [i for i, name in enumerate(species) if name != 'elec']
    return ([('elec', electrons)] if electrons else []) + ([('ions', ions)] if ions else [])


def experimental_flux_channel(quantity, species):
    # TGYRO total ion targets must not be assigned to an individual impurity.
    return {('Gam/Gam_GB', 'elec'): 'pflux_e_target',
            ('Q/Q_GB', 'elec'): 'eflux_e_target',
            ('Q/Q_GB', 'ions'): 'eflux_i_target',
            ('Pi/Pi_GB', 'ions'): 'mflux_target'}.get((quantity, species))


def tgyro_radius_index(output, radius, use_rho):
    key = 'rho' if use_rho else 'r/a'
    grid = np.asarray(output[key], dtype=float)
    if grid.ndim > 1:
        grid = grid[0]  # Match the iteration selected for target fluxes below.
    grid = grid.ravel()
    if grid.size == 0 or not np.any(np.isfinite(grid)):
        raise ValueError('No finite TGYRO radius coordinates')
    distances = np.where(np.isfinite(grid), np.abs(grid - float(radius)), np.inf)
    return int(np.argmin(distances))


# obtaining the best order of chaos polynomial
# setting max_poly_order to avoid high variance fit
def calc_cp_order(prange, rv, rv_proxy, data, max_poly_order=6):
    nodes = rv_proxy.inv(rv.fwd(prange))
    best_cp_order, best_adj_r2 = None, -np.inf
    for order in range(1, min(np.asarray(prange).shape[-1] - 1, max_poly_order) + 1):
        P = cp.orth_ttr(order, rv_proxy, normed=False)
        try:
            _, rank, prediction = fit_cp_least_squares(P, nodes, data)
            score = adj_r2_score(rank, data, prediction)
        except ValueError as exc:
            print('Skipping CP order {}: {}'.format(order, exc))
            continue
        print('CP order: {}, design rank: {}, adjusted R2: {}'.format(order, rank, score))
        if np.isfinite(score) and score > best_adj_r2:
            best_adj_r2, best_cp_order = score, order
    if best_cp_order is None:
        raise ValueError('No identifiable polynomial candidate with positive residual degrees of freedom')
    print('Best CP order: {}, adjusted R2: {}'.format(best_cp_order, best_adj_r2))
    return best_cp_order


combine_ions = root['TGLF']['SETTINGS']['PHYSICS']['combine_ions']
param = np.array(root['TGLF']['SETTINGS']['PHYSICS']['scanParameters'])
parameterRange = root['TGLF']['SETTINGS']['PHYSICS']['UQInputSamples']

# TODO: figure out a way to save chaospy objects
# acutal input probability distribution
rv = root['TGLF']['INPUTS']['rv']
print('Joint probability: ')
print(rv)
# standard normalized input probabilty distribution
# will be used to forward propagate the probabilities
rv_proxy = root['TGLF']['INPUTS']['rvprox']
print('Joint normalized probability: ')
print(rv_proxy)

rho = root['SETTINGS']['PHYSICS']['rho']
scanResults = 'UQResults'

# get exp input data
if root['SETTINGS']['PHYSICS']['exp_prob']:
    input_exp_data = []
    for p in param:
        exp_data = []
        for kkk in root['MULTI']['input.tglf'].keys():
            exp_data.append(root['MULTI']['input.tglf'][kkk][rho][p])
        input_exp_data.append(exp_data)

results = root[scanResults][rho]
species = [k[0] for k in results['_'.join(param)][results['_'.join(param)].keys()[0]]]
what = ['Gam/Gam_GB', 'Q/Q_GB', 'Pi/Pi_GB']
output = root['tgyro_output']

# find out the index of mean base case run from the UQResults subtree
mean_index = -1
mean_value = cp.E(rv)
mean_value = [str(element) for element in np.ravel(np.array(mean_value))]
mean_value = '_'.join(mean_value)
print('Mean base case: ', mean_value)
if mean_value in results['_'.join(param)].keys():
    mean_index = results['_'.join(param)].keys().index(mean_value)
print('Mean base case run index: ', mean_index)

# -- Modification to be consistent with the x-axis used in the tgyro simulation (rho or r/a)
use_rho = bool(root['TGYRO']['INPUTS']['input.tgyro']['TGYRO_USE_RHO'])
rho_ind = tgyro_radius_index(output, rho, use_rho)

expGm = output['pflux_e_target'][0, rho_ind]
expQe = output['eflux_e_target'][0, rho_ind]
expQi = output['eflux_i_target'][0, rho_ind]
expPi = output['mflux_target'][0, rho_ind]
gbGm = nan
gbQ = nan
gbPi = nan

labels = {'Gam/Gam_GB': r'$\Gamma/\Gamma_{GB}$', 'Q/Q_GB': r'$Q/Q_{GB}$', 'Pi/Pi_GB': r'$\Pi/\Pi_{GB}$'}

# tgyro notations for flux
# Experimental channels are mapped explicitly by quantity and grouped species.

species = [k[0] for k in results['_'.join(param)][results['_'.join(param)].keys()[0]]]

color_arr = ['red', 'blue', 'green', 'purple', 'orange', 'yellow']

fn = FigureNotebook(0, 'TGLF Scan UQ')

# plot input probability distributions and samplings
fig, axs = fn.subplots(nrows=1, ncols=1, label="Input Parameter(s)")
nrows = 1
prange = root['TGLF']['SETTINGS']['PHYSICS']['UQInputSamples']
# Showing 1D distribution for 1D input parameter
if len(param) == 1:
    prangedistance = max(prange[0]) - min(prange[0])
    prangemin = min(prange[0]) - prangedistance
    prangemax = max(prange[0]) + prangedistance
    prange_wide = np.linspace(prangemin, prangemax, 1000)
    fine_prange = np.linspace(np.min(prange), np.max(prange), 1000)
    axs.plot(prange_wide, rv.pdf(prange_wide), '--', color='red')
    axs.plot(fine_prange, rv.pdf(fine_prange), '-', color='red')
    if 'input_exp_data' in locals():
        axs.scatter(input_exp_data[0], np.array(input_exp_data[0]) * 0.0, marker='s', s=50, c='k', edgecolors='none', label='Exp')
    axs.scatter(prange, prange * 0.0, c='red', edgecolors='none', s=30, label='Samples')
    if mean_index != -1:
        axs.scatter(prange[0][mean_index], prange[0][mean_index] * 0.0, c='red', edgecolors='none', s=150)
    axs.set_xlabel(param[0])
    axs.set_ylabel('P_{' + param[0] + '}')
    axs.set_xlim(prangemin, prangemax)
    axs.set_ylim(bottom=0.0)
    axs.legend()
    nrows = 2
# Showing 2D distribution contour for 2D input parameters
elif len(param) == 2:
    prangedistancex = max(prange[0]) - min(prange[0])
    prangeminx = min(prange[0]) - prangedistancex
    prangemaxx = max(prange[0]) + prangedistancex
    prangedistancey = max(prange[1]) - min(prange[1])
    prangeminy = min(prange[1]) - prangedistancey
    prangemaxy = max(prange[1]) + prangedistancey
    xx = np.linspace(prangeminx, prangemaxx, 1000)
    yy = np.linspace(prangeminy, prangemaxy, 1000)
    XX, YY = np.meshgrid(xx, yy)
    # Pack X and Y into a single 3-dimensional array
    pos = np.empty(XX.shape + (2,))
    pos[:, :, 0] = XX
    pos[:, :, 1] = YY
    mu = cp.E(rv)
    Sigma = cp.Cov(rv)
    n = mu.shape[0]
    Sigma_det = np.linalg.det(Sigma)
    Sigma_inv = np.linalg.inv(Sigma)
    N = np.sqrt((2 * np.pi) ** n * Sigma_det)
    # This einsum call calculates (x-mu)T.Sigma-1.(x-mu) in a vectorized
    # way across all the input variables.
    fac = np.einsum('...k,kl,...l->...', pos - mu, Sigma_inv, pos - mu)
    ZZ = np.exp(-fac / 2.0) / N
    axs.contourf(XX, YY, ZZ)
    if root['SETTINGS']['PHYSICS']['exp_prob']:
        axs.scatter(input_exp_data[0], input_exp_data[1], s=50, marker='s', c='k', edgecolors='none', label='Exp')
    axs.scatter(prange[0], prange[1], c='red', edgecolors='none', label='Samples', s=30)
    if mean_index != -1:
        axs.scatter(prange[0][mean_index], prange[1][mean_index], c='red', edgecolors='none', s=150)
    axs.set_xlabel('P_{' + param[0] + '}')
    axs.set_ylabel('P_{' + param[1] + '}')
    axs.set_xlim(prangeminx, prangemaxx)
    axs.set_ylim(prangeminy, prangemaxy)
    axs.legend()
# Omitting visualization for 3D+ input parameters

species_groups = uq_species_groups(species, combine_ions)
for k, name in enumerate(what):
    fig, axs = fn.subplots(nrows=nrows, ncols=len(species_groups), label=name, sharex=False, sharey=False, squeeze=False)
    ax_ind = 0

    for t, species_indices in species_groups:
        samples = [np.array(results['_'.join(param)].across("['*'][%d]['%s']" % (index, name)))
                   for index in species_indices]
        data = np.sum(np.stack(samples), axis=0)

        quantity = name
        norm = 1.0
        if name == 'Gam/Gam_GB':
            if not isnan(gbGm):
                norm = gbGm
                labels[name] = labels[name].split('/')[0].rstrip('$') + '$'
                quantity = name.split('/')[0]
        elif name in ['Q/Q_GB', 'Q_low/Q_GB']:
            if t == 'elec':
                expQ = expQe
            else:
                expQ = expQi
            if not isnan(gbQ):
                norm = gbQ
                labels[name] = labels[name].split('/l')[0].rstrip('$') + '$'
                quantity = name.split('/')[0]
        elif name == 'Pi/Pi_GB':
            if not isnan(gbPi):
                norm = gbPi
                labels[name] = labels[name].split('/')[0].rstrip('$') + '$'
                quantity = name.split('/')[0]

        print(name, t)

        # FIX: making things compatible with uncertainties package
        data_clean = []
        for data_ind in range(len(data)):
            data_clean.append(unumpy.nominal_values(data[data_ind]))
        data = np.array(data_clean)

        # calculate the best CP fit to the simulated data
        best_cp_order = calc_cp_order(prange, rv, rv_proxy, data * norm)
        P = cp.orth_ttr(best_cp_order, rv_proxy, normed=False)
        u_hat, _, _ = fit_cp_least_squares(P, rv_proxy.inv(rv.fwd(prange)), data * norm)
        # getting out of samples range for plotting purposes
        datarange = max(data * norm) - min(data * norm)
        mindata = min(data * norm) - datarange
        maxdata = max(data * norm) + datarange
        qoi_range = np.linspace(min(data * norm), max(data * norm), 1000)
        qoi_range_wide = np.linspace(mindata, maxdata, 5000)
        # calculate QoI probability distribution using probability transformation
        qoi_dist = cp.QoI_Dist(u_hat, rv_proxy)

        # print out QoI statistics
        print('Expected Value: ' + str(cp.E(u_hat, rv_proxy)))  # expected value
        print('Standard Deviation: ' + str(cp.Std(u_hat, rv_proxy)))  # standard deviation

        # get experimental data extracted and constructing their PDFs
        channel = experimental_flux_channel(name, t)
        plot_exp_flux = root['SETTINGS']['PHYSICS']['exp_prob'] and channel is not None
        if plot_exp_flux:
            exp_data = []
            sign_convention = 1
            if name == 'Pi/Pi_GB':  # retain the existing TGYRO/TGLF toroidal sign convention
                sign_convention = -1
            for kkk in root['MULTI']['tgyro_output'].keys():
                sample_output = root['MULTI']['tgyro_output'][kkk]
                sample_rho_ind = tgyro_radius_index(sample_output, rho, use_rho)
                exp_data.append(sign_convention * sample_output[channel][0][sample_rho_ind])
            # fit a gaussian kernel density estimator to exp data
            exp_prob = stats.gaussian_kde(exp_data)
            # for plotting purposes
            exp_data_range = max(exp_data) - min(exp_data)
            exp_min = min(exp_data) - exp_data_range
            exp_max = max(exp_data) + exp_data_range
            exp_range = np.linspace(exp_min, exp_max, 1000)
            # Kolmogrov-Smirnov 2 samples test hypothesis testing
            print("Wasserstein distance: " + str(stats.wasserstein_distance(exp_data, qoi_dist.sample(10000, "M"))))
            print(
                "Normalized Wasserstein distance: "
                + str(stats.wasserstein_distance(exp_data, qoi_dist.sample(10000, "M")) / mean(exp_data))
            )
            print("2 samples D-stat:\n" + str(stats.ks_2samp(exp_data, qoi_dist.sample(1000))))
            print("D-crit (alpha=0.05):\n" + str(1.36 * np.sqrt((len(exp_data) + 1000.0) / (len(exp_data) * 1000.0))))
        print("------")

        if nrows == 2:
            # Showing QoI-input relation for 1D input parameter case only
            axs[0, ax_ind].scatter(prange[0], data * norm, c=color_arr[ax_ind % len(color_arr)], edgecolors='none', s=30, label='TGLF')
            if mean_index != -1:
                axs[0, ax_ind].scatter(prange[0][mean_index], data[mean_index] * norm, edgecolors='none', s=150, color=color_arr[ax_ind % len(color_arr)])
            if plot_exp_flux:
                axs[0, ax_ind].scatter(input_exp_data[0], exp_data, c='k', marker='s', s=50, edgecolors='none', label='Exp')
            axs[0, ax_ind].plot(prange_wide, u_hat(rv_proxy.inv(rv.fwd(prange_wide))), '--', color=color_arr[ax_ind % len(color_arr)])
            axs[0, ax_ind].plot(prange[0], u_hat(rv_proxy.inv(rv.fwd(prange[0]))), color=color_arr[ax_ind % len(color_arr)], label='CP fit')
            axs[0, ax_ind].set_ylabel(labels[name] + ' ' + t)
            axs[0, ax_ind].set_xlabel(param[0])
            axs[0, ax_ind].set_ylim(mindata, maxdata)
            axs[0, ax_ind].set_xlim(prangemin, prangemax)
            axs[0, ax_ind].legend()

            if plot_exp_flux:
                axs[1, ax_ind].plot(exp_range, exp_prob(exp_range), '-k', label='Exp')
            axs[1, ax_ind].plot(qoi_range_wide, qoi_dist.pdf(qoi_range_wide), '--', color=color_arr[ax_ind % len(color_arr)])
            axs[1, ax_ind].plot(qoi_range, qoi_dist.pdf(qoi_range), color=color_arr[ax_ind % len(color_arr)], label='TGLF')
            axs[1, ax_ind].scatter(data * norm, data * 0.0, c=color_arr[ax_ind % len(color_arr)], s=30, edgecolors='none')
            if mean_index != -1:
                axs[1, ax_ind].scatter(
                    data[mean_index] * norm, data[mean_index] * norm * 0.0, edgecolors='none', s=150, color=color_arr[ax_ind % len(color_arr)]
                )
            if plot_exp_flux:
                axs[1, ax_ind].scatter(exp_data, np.array(exp_data) * 0.0, s=50, marker='s', c='k', edgecolors='none')
            axs[1, ax_ind].set_xlabel(labels[name] + ' ' + t)
            axs[1, ax_ind].set_ylabel('P_{' + labels[name] + ' ' + t + '}')
            if plot_exp_flux:
                axs[1, ax_ind].set_xlim(min(exp_min, mindata), max(exp_max, maxdata))
            axs[1, ax_ind].legend()
            axs[1, ax_ind].set_ylim(bottom=0.0)
        else:
            if plot_exp_flux:
                axs[0, ax_ind].plot(exp_range, exp_prob(exp_range), '-k', label='Exp')
            axs[0, ax_ind].plot(qoi_range_wide, qoi_dist.pdf(qoi_range_wide), '--', color=color_arr[ax_ind % len(color_arr)])
            axs[0, ax_ind].plot(qoi_range, qoi_dist.pdf(qoi_range), color=color_arr[ax_ind % len(color_arr)], label='TGLF')
            axs[0, ax_ind].scatter(data * norm, data * 0.0, c=color_arr[ax_ind % len(color_arr)], s=30, edgecolors='none')
            if mean_index != -1:
                axs[0, ax_ind].scatter(
                    data[mean_index] * norm, data[mean_index] * norm * 0.0, edgecolors='none', s=150, color=color_arr[ax_ind % len(color_arr)]
                )
            if plot_exp_flux:
                axs[0, ax_ind].scatter(exp_data, np.array(exp_data) * 0.0, s=50, marker='s', c='k', edgecolors='none')
            axs[0, ax_ind].set_xlabel(labels[name] + ' ' + t)
            axs[0, ax_ind].set_ylabel('P_{' + labels[name] + ' ' + t + '}')
            if plot_exp_flux:
                axs[0, ax_ind].set_xlim(min(exp_min, mindata), max(exp_max, maxdata))
            axs[0, ax_ind].legend()
            axs[0, ax_ind].set_ylim(bottom=0.0)

        ax_ind = ax_ind + 1

# fig.tight_layout()
