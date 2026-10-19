"""Transfer_tool plots using explicit arrays and the original analytic estimates.

No solver is started and no input parameter is written by these functions.
The estimate plots retain the legacy models; they are not stability calculations.
"""
from OMFITlib_plot_style import plot_context
from builtins import all, any, dict, enumerate, float, int, len, list, max, next, range, set, sorted, str, sum, tuple, zip
import re
import numpy as np
import matplotlib.pyplot as plt
from OMFITlib_transfer_particles import species
from OMFITlib_transfer_plot_data import (CATALOG, alpha, data_issues, equilibrium_input, get, initialize,
    local_ion_types, local_rows, local_values, parameter_rows, selected_profile, shear, state_input, vector)

QE, MP = 1.6e-19, 1.67e-27
TITLES = dict(profile='Profiles and gradients', fastion='Fast ions', normpara='Normalization and characteristic frequencies',
              pltcrit='ITG / ETG threshold estimates', mtm='MTM frequency estimate', kbmbae='KBM / BAE estimate',
              view12='Equilibrium and current', source='Heating and particle sources', powerbalance='Power balance')


def divide(numerator, denominator):
    top, bottom = np.broadcast_arrays(np.asarray(numerator, dtype=float), np.asarray(denominator, dtype=float))
    result = np.full(top.shape, np.nan)
    np.divide(top, bottom, out=result, where=np.isfinite(bottom) & (np.abs(bottom) > 1e-30))
    return result


def gradient(values, radial_grid):
    return divide(np.gradient(values), np.gradient(radial_grid))


def panels(root, name, shape, size=None):
    rows, columns = shape
    figure, axes = plt.subplots(rows, columns, figsize=size or (5 * columns, 3.4 * rows), squeeze=False)
    figure.suptitle(TITLES[name])
    options = initialize(root)
    for axis in axes.flat:
        axis.set_xlabel(r'$\rho$')
        axis.set_xlim(float(options['minimum']), float(options['maximum']))
        axis.grid(True, alpha=0.16)
        axis.tick_params(labelsize=10)
    figure.subplots_adjust(left=0.08, right=0.96, bottom=0.09, top=0.90, hspace=0.50, wspace=0.35)
    return figure, list(axes.flat)


def line(axis, x, y, label=None, points=False):
    x, y = np.asarray(x), np.asarray(y)
    if x.ndim != 1 or y.shape != x.shape:
        raise ValueError('绘图横纵坐标长度不一致')
    if not np.any(np.isfinite(x) & np.isfinite(y)):
        absent(axis, 'Undefined for these input values')
        return
    axis.plot(x, y, '-o' if points else '-', linewidth=1.6, markersize=3, label=label)
    if label:
        axis.legend(fontsize=9)


def absent(axis, text):
    axis.text(0.5, 0.5, text, transform=axis.transAxes, ha='center', va='center')


def profile_data(root):
    profile = selected_profile(root)
    rho = vector(profile, 'rho')
    rmin = vector(profile, 'rmin', len(rho))
    if np.any(np.diff(rho) <= 0) or np.any(np.diff(rmin) <= 0) or rmin[-1] <= 0:
        raise ValueError('剖面 rho / rmin 必须严格递增，边界小半径必须为正')
    return profile, rho, rmin, species(profile)


def plot_profile(root):
    profile, rho, rmin, ions = profile_data(root)
    rows = local_rows(root) if initialize(root)['profile'] == 'generated' else []
    if rows and any(row['rho'] is None for row in rows):
        rows = []
    _, axes = panels(root, 'profile', (3, 3), (15, 10))
    a = rmin[-1]
    for ion in ions:
        index = str(ion['index'])
        temperature = vector(profile, 'Ti_' + index, len(rho))
        density = vector(profile, 'ni_' + index, len(rho))
        caption = ion['name'] + ' (' + index + ')'
        line(axes[0], rho, temperature, caption)
        line(axes[1], rho, density, caption)
        line(axes[3], rho, -a * divide(gradient(temperature, rmin), temperature), caption)
        line(axes[4], rho, -a * divide(gradient(density, rmin), density), caption)
    te, ne = vector(profile, 'Te', len(rho)), vector(profile, 'ne', len(rho))
    line(axes[0], rho, te, 'electron')
    line(axes[1], rho, ne, 'electron')
    raw = get(root, ('INPUTS', 'rawdata.txt'), {})
    for axis, prefix, factor in ((axes[0], 'Ti', 1.0), (axes[0], 'Te', 1.0), (axes[1], 'ne', 1e-19)):
        keys = [prefix + suffix for suffix in ('_rho', '_data', '_err')]
        if all(key in raw for key in keys):
            coordinates, measurements, errors = [np.array(raw[key], dtype=float, copy=True) for key in keys]
            if coordinates.ndim == 1 and coordinates.shape == measurements.shape == errors.shape:
                axis.errorbar(coordinates, measurements * factor, yerr=errors * factor,
                              fmt='.', alpha=0.5, label=prefix + ' measured')
                axis.legend(fontsize=9)
    q = vector(profile, 'q', len(rho))
    line(axes[2], rho, q, 'q')
    line(axes[3], rho, -a * divide(gradient(te, rmin), te), 'electron')
    line(axes[4], rho, -a * divide(gradient(ne, rmin), ne), 'electron')
    line(axes[5], rho, divide(rmin * gradient(q, rmin), q), 'profile')
    if 'omega0' in profile:
        line(axes[6], rho, vector(profile, 'omega0', len(rho)) / (2 * np.pi * 1e3), 'ExB')
    else:
        absent(axes[6], 'omega0 unavailable')
    for ion in ions:
        key = 'vtor_' + str(ion['index'])
        if key in profile and 'rmaj' in profile:
            line(axes[6], rho, divide(vector(profile, key, len(rho)), vector(profile, 'rmaj', len(rho))) /
                 (2 * np.pi * 1e3), ion['name'] + ' toroidal')
    if 'ptot' in profile:
        line(axes[7], rho, vector(profile, 'ptot', len(rho)) / 1e3)
    else:
        absent(axes[7], 'ptot unavailable')
    if rows:
        radial = np.array([float(row['rho']) for row in rows])
        line(axes[3], radial, local_values(rows, 'RLTS_1'), 'local electron', True)
        line(axes[5], radial, np.array([shear(row) for row in rows]), 'local', True)
        if all('VEXB_SHEAR' in row['input'] for row in rows):
            line(axes[8], radial, local_values(rows, 'VEXB_SHEAR'), points=True)
        else:
            absent(axes[8], 'VEXB_SHEAR unavailable')
        _, details = panels(root, 'profile', (1, 3))
        for axis, values, label in zip(details, (local_values(rows, 'BETAE'), local_values(rows, 'XNUE'),
                                                np.array([alpha(row) for row in rows])),
                                       (r'$\beta_e$', r'$\nu$', r'$\alpha$')):
            line(axis, radial, values, points=True)
            axis.set_title(label)
    else:
        absent(axes[8], 'Local ExB shear: generate radial inputs first')
    for axis, title in zip(axes, ('Temperature (keV)', r'Density ($10^{19}$ m$^{-3}$)',
                                 'q', 'a/LT', 'a/Ln', 'Magnetic shear',
                                 'Rotation (kHz)', 'Pressure (kPa)', 'Local ExB shear')):
        axis.set_title(title)


def plot_fastion(root):
    profile, rho, rmin, ions = profile_data(root)
    fast = [ion for ion in ions if ion['kind'] == 'fast']
    ne, te = vector(profile, 'ne', len(rho)), vector(profile, 'Te', len(rho))
    nt_all, nt_fast = ne * te, np.zeros_like(ne)
    for ion in ions:
        suffix = str(ion['index'])
        nt = vector(profile, 'ni_' + suffix, len(rho)) * vector(profile, 'Ti_' + suffix, len(rho))
        nt_all = nt_all + nt
        if ion['kind'] == 'fast':
            nt_fast += nt
    _, axes = panels(root, 'fastion', (2, 3))
    line(axes[0], rho, ne, 'electron')
    line(axes[1], rho, te, 'electron')
    for ion in fast:
        suffix = str(ion['index'])
        density = vector(profile, 'ni_' + suffix, len(rho))
        temperature = vector(profile, 'Ti_' + suffix, len(rho))
        label = ion['name'] + ' (' + suffix + ')'
        line(axes[0], rho, density, label)
        line(axes[1], rho, temperature, label)
        line(axes[3], rho, -rmin[-1] * divide(gradient(density, rmin), density), label)
        line(axes[4], rho, -rmin[-1] * divide(gradient(temperature, rmin), temperature), label)
        if 'q' in profile and 'rmaj' in profile:
            frequency = divide(np.sqrt(temperature * 1e3 * QE / (MP * ion['mass'])),
                               np.abs(vector(profile, 'q', len(rho))) * vector(profile, 'rmaj', len(rho)))
            line(axes[5], rho, frequency / (2 * np.pi * 1e3), label)
    if 'ptot' in profile:
        pressure = vector(profile, 'ptot', len(rho))
        line(axes[2], rho, pressure / 1e3, 'total')
        line(axes[2], rho, pressure * divide(nt_fast, nt_all) / 1e3, 'fast')
    else:
        line(axes[2], rho, divide(nt_fast, nt_all), 'fast / total nT')
    for axis, title in zip(axes, ('Density', 'Temperature (keV)', 'Pressure (kPa) / nT fraction',
                                 'a/Ln (fast)', 'a/LT (fast)', 'Transit frequency (kHz)')):
        axis.set_title(title)
    rows = local_rows(root) if initialize(root)['profile'] == 'generated' else []
    local_types = [local_ion_types(root, row) for row in rows]
    if rows and not any(row['rho'] is None or types is None for row, types in zip(rows, local_types)):
        radial = np.array([float(row['rho']) for row in rows])
        beta_e = local_values(rows, 'BETAE')
        beta_f, drive_f = np.zeros_like(beta_e), np.zeros_like(beta_e)
        for index, row in enumerate(rows):
            value = row['input']
            for ion in local_types[index]:
                if ion['kind'] != 'fast':
                    continue
                suffix = str(ion['index'])
                beta = beta_e[index] * float(value['AS_' + suffix]) * float(value['TAUS_' + suffix])
                beta_f[index] += beta
                drive_f[index] += beta * (float(value['RLNS_' + suffix]) + float(value['RLTS_' + suffix]))
        _, details = panels(root, 'fastion', (1, 2))
        line(details[0], radial, beta_e, 'electron', True)
        line(details[0], radial, beta_f, 'fast', True)
        line(details[1], radial, beta_e * (local_values(rows, 'RLNS_1') + local_values(rows, 'RLTS_1')), 'electron', True)
        line(details[1], radial, drive_f, 'fast', True)
        details[0].set_title('Local beta')
        details[1].set_title('Beta-weighted pressure gradient')


def scales(root):
    profile, rho, rmin, ions = profile_data(root)
    rows = local_rows(root)
    radial = np.array([float(row['rho']) for row in rows])
    if np.any(radial < rho[0]) or np.any(radial > rho[-1]):
        raise ValueError('生成半径超出所选剖面范围')
    fields = {key: local_values(rows, key) for key in ('Q_LOC', 'RMIN_LOC', 'RMAJ_LOC', 'KAPPA_LOC',
              'S_KAPPA_LOC', 'DRMAJDX_LOC', 'BETAE', 'MASS_2', 'TAUS_2', 'RLTS_1', 'RLTS_2', 'RLNS_1', 'XNUE', 'ZEFF')}
    temperature = np.interp(radial, rho, vector(profile, 'Te', len(rho)))
    mass = fields['MASS_2']
    if np.any(mass <= 0) or np.any(temperature <= 0):
        raise ValueError('温度和参考离子质量必须为正')
    cs = np.sqrt(temperature * 1e3 * QE / (2 * MP * mass))
    a = rmin[-1]
    bt = float(profile['BT_EXP'])
    bunit = bt * fields['KAPPA_LOC'] * (1 + fields['S_KAPPA_LOC'] / 2 -
            0.5 * fields['DRMAJDX_LOC'] * divide(fields['RMIN_LOC'], fields['RMAJ_LOC']))
    charge = np.array([float(row['input']['ZS_2']) for row in rows])
    rhostar = divide(2 * MP * mass * cs, QE * bunit * charge * a)
    mass_density = np.array([sum(float(row['input']['MASS_' + str(i)]) * float(row['input']['AS_' + str(i)])
                            for i in range(1, int(row['input']['NS']) + 1)) for row in rows])
    va = np.sqrt(divide(2, fields['BETAE'] * mass_density)) * cs
    omega_ti = divide(np.sqrt(2 * fields['TAUS_2']) * cs / a, fields['Q_LOC'] * fields['RMAJ_LOC'])
    omega_gam = omega_ti * fields['Q_LOC'] * np.sqrt(1.75 + divide(1, fields['TAUS_2'])) * np.sqrt(
        (1 + divide(1, 2 * fields['Q_LOC'] ** 2)) * divide(2, fields['KAPPA_LOC'] ** 2 + 1))
    omega0 = np.interp(radial, rho, vector(profile, 'omega0', len(rho)))
    ky = float(initialize(root)['ky'])
    n = divide(ky * fields['RMIN_LOC'], rhostar * fields['Q_LOC'])
    return dict(profile=profile, ions=ions, rows=rows, rho=radial, fields=fields, cs=cs, a=a,
                bt=bt, bunit=bunit, rhostar=rhostar, va=va, omega_ti=omega_ti,
                omega_gam=omega_gam, omega0=omega0, ky=ky, n=n)


def plot_normalization(root):
    data = scales(root)
    x, f, a = data['rho'], data['fields'], data['a']
    _, axes = panels(root, 'normpara', (2, 4))
    values = (data['cs'] / a / (2 * np.pi * 1e3), data['rhostar'], data['bunit'],
              data['va'], divide(data['va'], f['Q_LOC'] * f['RMAJ_LOC'] * a) / (2 * np.pi * 1e3),
              data['n'], data['n'] * data['omega0'] / (2 * np.pi * 1e3), data['omega_gam'] / (2 * np.pi * 1e3))
    titles = ('cs/a (kHz)', r'$\rho_{s,unit}/a$', 'Bunit (T)', 'Alfven speed (m/s)',
              'Alfven frequency (kHz)', 'Toroidal n (ky={:g})'.format(data['ky']), 'Doppler shift (kHz)', 'GAM / TAE / RSAE (kHz)')
    for axis, y, title in zip(axes, values, titles):
        line(axis, x, y, points=True)
        axis.set_title(title)
    line(axes[2], x, np.full_like(x, data['bt']), 'Bt')
    fast = [ion for ion in data['ions'] if ion['kind'] == 'fast']
    if fast:
        ratio_axis = axes[3].twinx()
        profile = data['profile']
        rho = vector(profile, 'rho')
        for ion in fast:
            temperature = np.interp(x, rho, vector(profile, 'Ti_' + str(ion['index']), len(rho)))
            velocity = np.sqrt(temperature * 1e3 * QE / (MP * ion['mass']))
            line(ratio_axis, x, divide(velocity, data['va']), ion['name'] + ' / VA', True)
        ratio_axis.set_ylabel('Vfast / VA')
    omega_a = divide(data['va'], f['Q_LOC'] * f['RMAJ_LOC'] * a)
    ellipticity = divide(f['KAPPA_LOC'] ** 2 - 1, f['KAPPA_LOC'] ** 2 + 1)
    factor = divide(np.abs(2 - np.sqrt(1 + 0.75 * ellipticity ** 2)), np.sqrt(1 - ellipticity ** 2 / 4))
    line(axes[7], x, omega_a / (4 * np.pi * 1e3), 'TAE', True)
    line(axes[7], x, omega_a * factor / (4 * np.pi * 1e3), 'TAE shape correction', True)
    omega_grad = divide(data['cs'] / a, f['RMAJ_LOC']) * np.sqrt(2 * f['RMIN_LOC'] * (
        divide(f['RLTS_1'], 1 + f['TAUS_2']) + divide(f['RLTS_2'], 1 + divide(1, f['TAUS_2']))) *
        (1 - divide(1, f['Q_LOC'] ** 2)) * divide(2, f['KAPPA_LOC'] ** 2 + 1))
    line(axes[7], x, np.sqrt(data['omega_gam'] ** 2 + omega_grad ** 2) / (2 * np.pi * 1e3), 'RSAE minimum', True)


def plot_mtm(root):
    data = scales(root)
    x, f, ky, n = data['rho'], data['fields'], data['ky'], data['n']
    frequency = ky * (f['RLNS_1'] + f['RLTS_1']) * data['cs'] / data['a'] / (2 * np.pi * 1e3)
    doppler = n * data['omega0'] / (2 * np.pi * 1e3)
    ratio = divide(data['bunit'], data['bt'])
    ky_per_n = divide(ky, n)
    for harmonic in (1, None):
        divisor = n if harmonic == 1 else np.ones_like(n)
        figure, axes = panels(root, 'mtm', (2, 3))
        figure.suptitle('MTM estimate · ' + ('n=1' if harmonic == 1 else 'ky={:g}'.format(ky)))
        diamagnetic = divide(frequency * ratio, divisor)
        shift = divide(doppler, divisor)
        line(axes[0], x, diamagnetic, 'diamagnetic', True)
        line(axes[1], x, diamagnetic, 'diamagnetic', True)
        line(axes[1], x, diamagnetic + np.abs(shift), '+ rotation')
        line(axes[1], x, diamagnetic - np.abs(shift), '- rotation')
        wavelength = divide(2 * np.pi * data['rhostar'] * data['a'], ky_per_n if harmonic == 1 else ky)
        line(axes[2], x, np.abs(wavelength), points=True)
        line(axes[3], x, shift, points=True)
        line(axes[4], x, ky_per_n if harmonic == 1 else n, points=True)
        best = divide(f['ZEFF'] * f['XNUE'], (f['RLNS_1'] + f['RLTS_1']) * ratio)
        line(axes[5], x, divide(best, ky_per_n) if harmonic == 1 else best, points=True)
        for axis, title in zip(axes, ('Diamagnetic frequency (kHz)', 'Laboratory frequency (kHz)',
                                      'Poloidal wavelength (m)', 'Doppler shift (kHz)',
                                      'ky for n=1' if harmonic == 1 else 'Toroidal n', 'Collision matching estimate')):
            axis.set_title(title)


def plot_critical(root):
    profile, rho, rmin, ions = profile_data(root)
    rows = local_rows(root)
    radial = np.array([float(row['rho']) for row in rows])
    ne, te = vector(profile, 'ne', len(rho)), vector(profile, 'Te', len(rho))
    ion = next((ion for ion in ions if ion['kind'] == 'therm'), ions[0])
    ti = vector(profile, 'Ti_' + str(ion['index']), len(rho))
    q, rmaj = np.abs(vector(profile, 'q', len(rho))), vector(profile, 'rmaj', len(rho))
    zeff, kappa = vector(profile, 'z_eff', len(rho)), vector(profile, 'kappa', len(rho))
    s, eps = divide(rmin * gradient(q, rmin), q), divide(rmin, rmaj)
    mu = divide(2.1 * rmaj * ne, te ** 1.5 * ti ** 0.5)
    rln = max(6, np.max(divide(rmaj * gradient(ne, rmin), ne)))
    fast_density = sum((vector(profile, 'ni_' + str(i['index']), len(rho))
                        for i in ions if i['kind'] == 'fast'), np.zeros_like(ne))
    taub = divide(ti, te) * (1 - divide(fast_density, ne))
    # Original f/g/h threshold expressions; invalid model domains remain gaps.
    f = 1 - 0.2 * np.sqrt(zeff) * s ** (-0.7) * (14 * eps ** 1.3 * mu ** (-0.2) - 1)
    g = (0.7 + 0.6 * s - 0.2 * rln) ** 2 + 0.4 + 0.3 * rln - 0.8 * s + 0.2 * s ** 2
    h = 1.5 * (1 + divide(2.8, q ** 2)) ** 0.26 * zeff ** 0.7 * np.sqrt(taub)
    itg = divide(f * g * h * rmin[-1], rmaj)
    tau = divide(zeff * te, ti)
    etg = (1 + tau) * (1.33 + divide(1.91 * s, q)) * (1 - 1.5 * eps) * (1 + 0.3 * gradient(kappa, eps))
    _, axes = panels(root, 'pltcrit', (2, 2))
    for column, prediction, key, title in ((0, itg, 'RLTS_' + str(ion['index'] + 1), 'ITG'), (1, etg, 'RLTS_1', 'ETG')):
        actual = local_values(rows, key)
        line(axes[column], rho, prediction, 'analytic threshold')
        line(axes[column], radial, actual, 'input gradient', True)
        line(axes[column + 2], radial, divide(actual, np.interp(radial, rho, prediction)), 'input / threshold', True)
        axes[column + 2].axhline(1, color='0.5', linestyle='--')
        axes[column].set_title(title + ' · a/LT')
        axes[column + 2].set_title(title + ' · threshold ratio')


def plot_kbm_bae(root):
    data = scales(root)
    x, f, rows = data['rho'], data['fields'], data['rows']
    local_types = [local_ion_types(root, row) for row in rows]
    if any(types is None for types in local_types):
        raise ValueError('局部粒子已合并，无法将热 / 快离子驱动分别对应；请使用保留粒子的生成结果')
    thermal, fast = np.zeros_like(x), np.zeros_like(x)
    for index, row in enumerate(rows):
        value = row['input']
        for ion in local_types[index]:
            suffix = str(ion['index'])
            pressure_gradient = float(value['AS_' + suffix]) * float(value['TAUS_' + suffix]) * (
                float(value['RLNS_' + suffix]) + float(value['RLTS_' + suffix]))
            (fast if ion['kind'] == 'fast' else thermal)[index] += pressure_gradient
    omega_ti = divide(np.sqrt(2 * f['TAUS_2']), f['Q_LOC'] * f['RMAJ_LOC'])
    omega_gam = f['Q_LOC'] * np.sqrt(1.75 + divide(1, f['TAUS_2'])) * np.sqrt(
        (1 + divide(1, 2 * f['Q_LOC'] ** 2)) * divide(2, f['KAPPA_LOC'] ** 2 + 1)) * omega_ti
    ky_max = divide(omega_gam, thermal)
    omega_star = data['ky'] * thermal
    _, axes = panels(root, 'kbmbae', (2, 3))
    line(axes[0], x, omega_ti, 'ion transit', True)
    line(axes[0], x, divide(f['Q_LOC'] * data['rhostar'] * thermal, f['RMIN_LOC']), 'pressure drift, n=1', True)
    line(axes[1], x, omega_gam, 'GAM', True)
    line(axes[1], x, omega_star, 'thermal pressure drift', True)
    if np.any(fast):
        line(axes[1], x, data['ky'] * fast, 'fast pressure drift', True)
    line(axes[2], x, ky_max, 'estimated ky', True)
    axes[2].axhline(data['ky'], color='0.5', linestyle='--', label='selected ky')
    line(axes[3], x, divide(ky_max * f['RMIN_LOC'], data['rhostar'] * f['Q_LOC']), points=True)
    line(axes[4], x, divide(omega_star * omega_gam, omega_ti ** 2), points=True)
    line(axes[5], x, divide(ky_max * (f['RLNS_1'] + f['RLTS_2']), omega_ti ** 2), points=True)
    for axis in axes[4:]:
        axis.axhline(1, color='0.5', linestyle='--')
    for axis, title in zip(axes, ('Resonance (cs/a)', 'Frequencies (cs/a)', 'Estimated ky',
                                 'Corresponding toroidal n', 'Pressure / BAE criterion', 'Maximum-drive estimate')):
        axis.set_title(title)


def nc_value(dataset, key, index=-1):
    if dataset is None or key not in dataset:
        raise ValueError('数据缺少 ' + key)
    value = dataset[key]
    values = np.array(value['data'] if hasattr(value, 'get') and 'data' in value else value, dtype=float, copy=True)
    if values.ndim > 1:
        values = values[index]
    if values.ndim != 1 or not np.all(np.isfinite(values)):
        raise ValueError(key + ' 的数据形状或数值无效')
    return values


def nc_radius(dataset, values):
    if 'rho' in dataset:
        grid = nc_value(dataset, 'rho')
        if len(grid) == len(values):
            return grid
    return np.linspace(0, 1, len(values))


def plot_equilibrium(root):
    gfile = equilibrium_input(root)
    dataset = get(root, ('INPUTS', 'trpltout.nc'))
    transient = dataset is not None
    dataset = dataset if transient else state_input(root)
    current_keys = ('curden', 'curohm', 'curboot', 'currf', 'curbeam')
    currents = [nc_value(dataset, key) / (1e2 if transient else 1e6) for key in current_keys]
    current_rho = nc_radius(dataset, currents[0])
    q = np.array(gfile['QPSI'], dtype=float, copy=True)
    psi = np.linspace(0, 1, len(q))
    cumulative = np.concatenate(([0.0], np.cumsum((np.abs(q[:-1]) + np.abs(q[1:])) / 2)))
    toroidal = np.sqrt(divide(cumulative, cumulative[-1]))
    pressure = np.array(gfile['PRES'], dtype=float, copy=True)
    _, axes = panels(root, 'view12', (2, 3))
    grid_r, grid_z = np.meshgrid(gfile['AuxQuantities']['R'], gfile['AuxQuantities']['Z'])
    levels = np.sort(np.linspace(float(gfile['SIMAG']), float(gfile['SIBRY']), 16))
    axes[0].contourf(grid_r, grid_z, gfile['PSIRZ'], levels=levels)
    axes[0].plot(gfile['RBBBS'], gfile['ZBBBS'], color='tab:red')
    axes[0].plot(gfile['RLIM'], gfile['ZLIM'], color='0.3')
    axes[0].set_aspect('equal', adjustable='box')
    axes[0].set_xlim(np.min(grid_r), np.max(grid_r))
    axes[0].set_xlabel('R (m)')
    axes[0].set_ylabel('Z (m)')
    for values, label in zip(currents, ('total', 'ohmic', 'bootstrap', 'RF', 'beam')):
        line(axes[1], current_rho, values, label)
    axes[1].set_ylabel(r'MA m$^{-2}$')
    line(axes[2], toroidal, np.abs(q))
    totals_keys = ('totboot', 'totohm', 'totb', 'totrf') if transient else ('totboot_cur', 'totohm_cur', 'totbeam_cur', 'totrf_cur')
    totals = []
    for key in totals_keys:
        item = dataset[key]
        raw = np.asarray(item['data'] if hasattr(item, 'get') and 'data' in item else item, dtype=float)
        totals.append(float(raw.reshape(-1)[-1]))
    # Signed current components are visible even when a pie chart cannot represent them.
    axes[3].bar(('bootstrap', 'ohmic', 'beam', 'RF'), totals)
    axes[3].set_xlim(-0.6, 3.6)
    axes[3].set_xlabel('Current component')
    axes[3].set_ylabel('A' if not transient else 'Original integrated-current units')
    electric = nc_value(dataset, 'etor') / (1e2 if transient else 1e6)
    line(axes[4], nc_radius(dataset, electric), electric)
    line(axes[5], toroidal, pressure / 1e3)
    for axis, title in zip(axes, ('Flux surfaces', 'Current density', 'q', 'Integrated current', 'Toroidal electric field', 'Pressure (kPa)')):
        axis.set_title(title)


def plot_sources(root):
    state = state_input(root)
    transient = get(root, ('INPUTS', 'trpltout.nc'))
    dataset = transient if transient is not None else state
    profiles = get(root, ('INPUTS', 'input.profiles'))
    # Preserve the original source-channel conventions and signs.
    keys = ('qbeame', 'qrfeiv', 'qfusev', 'qohm', 'qrad', 'qdelten', 'qbeami', 'qrfiiv', 'qfusiv', 'storqueb') if transient is not None else (
            'qbeame', 'qrfe', 'qfuse', 'qohm', 'qrad', 'qdelt', 'qbeami', 'qrfi', 'qfuse', 'storque')
    if transient is None and 'qfusi' in state:
        keys = keys[:8] + ('qfusi',) + keys[9:]
    beam_e, rf_e, fusion_e, ohm, rad, exchange, beam_i, rf_i, fusion_i, torque = [nc_value(dataset, key) for key in keys]
    _, axes = panels(root, 'source', (2, 4))
    for axis, channels in ((axes[0], ((beam_e, 'beam'), (rf_e, 'RF'), (-rad, 'radiation'), (ohm, 'ohmic'),
                                     (-exchange, 'exchange'), (beam_e + rf_e + fusion_e + ohm + rad - exchange, 'total'))),
                            (axes[1], ((beam_i, 'beam'), (rf_i, 'RF'), (exchange, 'exchange'),
                                     (beam_i + rf_i + fusion_i + exchange, 'total')))):
        for values, label in channels:
            line(axis, nc_radius(dataset, values), values, label)
        axis.set_ylabel(r'MW m$^{-3}$')
    wall, beam = nc_value(state, 'sion', 0), nc_value(state, 'sbeam')
    line(axes[2], nc_radius(state, wall), wall, 'wall')
    line(axes[2], nc_radius(state, beam), beam, 'beam')
    line(axes[3], nc_radius(dataset, torque), torque, 'beam')
    if transient is not None:
        power_e = [nc_value(dataset, key) for key in ('pwrbme', 'prfe', 'pfuse', 'pohm', 'prad', 'pdelten')]
        power_i = [nc_value(dataset, key) for key in ('pwrbmi', 'prfi', 'pfusi')]
        for axis, channels in ((axes[4], tuple(zip(power_e, ('beam', 'RF', 'fusion', 'ohmic', 'radiation', 'exchange')))),
                                (axes[5], tuple(zip(power_i, ('beam', 'RF', 'fusion'))) + ((-power_e[-1], 'exchange'),))):
            for values, label in channels:
                line(axis, nc_radius(dataset, values), values / 1e6, label)
        total_e, total_i = sum(power_e), sum(power_i) - power_e[-1]
        line(axes[4], nc_radius(dataset, total_e), total_e / 1e6, 'total')
        line(axes[5], nc_radius(dataset, total_i), total_i / 1e6, 'total')
    else:
        for axis, key in ((axes[4], 'pow_e'), (axes[5], 'pow_i')):
            values = vector(profiles, key)
            line(axis, nc_radius(profiles, values), values, 'total')
    for key, label in (('flow_wall', 'wall'), ('flow_beam', 'beam')):
        values = vector(profiles, key)
        line(axes[6], nc_radius(profiles, values), values, label)
    values = vector(profiles, 'flow_mom')
    line(axes[7], nc_radius(profiles, values), values)
    for axis, title in zip(axes, ('Electron heating', 'Ion heating', 'Particle source', 'Torque density',
                                 'Electron power (MW)', 'Ion power (MW)', 'Integrated particle source', 'Integrated torque')):
        axis.set_title(title)


def plot_power_balance(root):
    result = get(root, ('OUTPUTS', 'TGYRO'))
    def values(key):
        data = np.array(result[key], dtype=float, copy=True)
        return data[0] if data.ndim > 1 else data
    rho = values('rho')[1:]
    keys = sorted(key for key in result.keys() if re.fullmatch(r'eflux_i\d+_neo', str(key)))
    if not keys:
        raise ValueError('TGYRO 缺少离子新经典通量')
    ion_neo = sum((values(key)[1:] for key in keys), np.zeros_like(rho))
    channels = ((values('pflux_e_target')[1:], values('pflux_e_neo')[1:]),
                (values('eflux_e_target')[1:], values('eflux_e_neo')[1:]),
                (values('eflux_i_target')[1:], ion_neo))
    factors = (divide(values('Chi_GB')[1:], values('a/Lte')[1:]),
               divide(values('Chi_GB')[1:], values('a/Lte')[1:]),
               divide(values('Chi_GB')[1:], values('a/Lti1')[1:]))
    _, axes = panels(root, 'powerbalance', (2, 3))
    for column, ((target, neo), factor) in enumerate(zip(channels, factors)):
        for data, label in ((target, 'target'), (neo, 'neoclassical'), (target - neo, 'remaining')):
            line(axes[column], rho, data, label, True)
            line(axes[column + 3], rho, data * factor, label, True)
    for axis, title in zip(axes, ('Particle flux (GB)', 'Electron heat flux (GB)', 'Ion heat flux (GB)',
                                 r'D (m$^2$/s)', r'Electron $\chi$ (m$^2$/s)', r'Ion $\chi$ (m$^2$/s)')):
        axis.set_title(title)


def draw(root, name):
    problems = data_issues(root, name)
    if problems:
        raise ValueError('；'.join(problems))
    if name == 'printinfo':
        print('nr  rho  a/LTi  a/LTe  a/Lne  shear  q  beta_e  nu  alpha')
        for row in parameter_rows(root):
            print('  '.join('{:.6g}'.format(float(value)) for value in row))
        return
    functions = dict(profile=plot_profile, fastion=plot_fastion, normpara=plot_normalization,
                     pltcrit=plot_critical, mtm=plot_mtm, kbmbae=plot_kbm_bae,
                     view12=plot_equilibrium, source=plot_sources, powerbalance=plot_power_balance)
    previous = set(plt.get_fignums())
    try:
        with plot_context(root), np.errstate(divide='ignore', invalid='ignore', over='ignore'):
            functions[name](root)
    except BaseException:
        for number in set(plt.get_fignums()) - previous:
            plt.close(number)
        raise
