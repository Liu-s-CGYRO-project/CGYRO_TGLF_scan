# -*-Python-*-
# Created by snoepg at 20 Jul 2017  16:45


D_and_v = None
if 'D_and_v' in root['OUTPUTS']:
    D_and_v = root['OUTPUTS']['D_and_v']

defaultVars(
    D_and_v=D_and_v,
    figure_name='Diffusion and pinch coefficients',
    hide_tur_neo_axis_ped=True,
    STRAHL_like_DV=root['SETTINGS']['PHYSICS']['STRAHL_like_DV'],
)
lw = 3
rho = np.copy(D_and_v['rho'])
n_id = D_and_v['n_id']  # number of the modified ion
ion_name = D_and_v['ion_name']  # number of the modified ion
trace_imp = scratch.get('add_trace_impurity', False)

if STRAHL_like_DV:
    # apply coordinate transformation from r_minor->r_V
    D_and_v = copy.deepcopy(D_and_v)
    for item in D_and_v:
        if item.startswith('D_'):
            D = D_and_v[item]
            if 'chi' in item:  # dimensionaless transport coeffs
                # change in chi_eff is compensating one correction by drV_drm
                v = D_and_v['aV' + item[1:]] / D_and_v['drV_drm']
                D /= D_and_v['drV_drm']
            else:
                v = D_and_v['v' + item[1:]]

            # correction for r_minor->r_V coordinate transformation
            # correction for poloidal asymmetries
            v = (v + D * D_and_v['V_conv'] / D_and_v['a'] * D_and_v['drV_drm']) * D_and_v['n_ratio'] * D_and_v['drV_drm']
            D = D * D_and_v['drV_drm'] ** 2 * D_and_v['n_ratio']
            D_and_v[item] = D
            D_and_v['v' + item[1:]] = v

        if item.startswith('n_'):
            D_and_v[item] /= D_and_v['n_ratio']  # flux surface averaged density

mask = zeros_like(rho, dtype=bool)
if hide_tur_neo_axis_ped:
    mask = (rho < D_and_v['axis_core_rho']) | (rho > D_and_v['core_ped_rho'])
rho[0] = nan  # do not plot extrapolated onaxis value


def masking(D_and_v, item):
    if 'neo' in item or 'tur' in item:
        return np.ma.masked_array(D_and_v[item], mask=mask)
    else:
        return D_and_v[item]


fn = FigureNotebook(0, name=figure_name)
fig, ax = fn.subplots(1, 1, label='Diffusion', sharex=False)
for item in D_and_v:
    if item.startswith('D_') and 'chi' not in item:
        (p,) = ax.plot(rho, masking(D_and_v, item), label=item, lw=lw)
        ax.plot(rho, D_and_v[item], lw=1, c=p.get_color())

ax.axhline(0.0, ls='--', color='black')
ax.legend(loc=0).draggable(True)
ax.set_title('Diffusion coefficient')
ax.set_xlabel('$\\rho$')
ax.set_ylabel('$D_{%s}$ [m$^2$ s$^{-1}$]' % ion_name)
ax.axvline(D_and_v['axis_core_rho'], color='k', ls='--')
ax.axvline(D_and_v['core_ped_rho'], color='k', ls='--')
ax.set_ylim(0.05, min(ax.get_ylim()[1], 100))
ax.set_xlim(0, 1)
ax.set_yscale('log')
ax.grid(True)

fig, ax = fn.subplots(1, 1, label='Pinch', sharex=False)
for item in D_and_v:
    if item.startswith('v_') and 'chi' not in item:
        (p,) = ax.plot(rho, masking(D_and_v, item), label=item, lw=lw)
        ax.plot(rho, D_and_v[item], c=p.get_color())

ax.axhline(0.0, ls='--', color='black')
ax.legend(loc=0).draggable(True)
ax.set_title('Convective velocity')
ax.set_xlabel('$\\rho$')
ax.set_ylabel('$v_{%s}$ [m s$^{-1}$]' % ion_name)
ax.axvline(D_and_v['axis_core_rho'], color='k', ls='--')
ax.axvline(D_and_v['core_ped_rho'], color='k', ls='--')
ax.set_xlim(0, 1)
ax.grid(True)
ylim = ax.get_ylim()
ax.set_ylim(max(-50, ylim[0]), min(50, ylim[-1]))

if 'v_blend_i%d' % n_id in D_and_v:
    ymin, ymax = ax.get_ylim()
    yrange = np.ptp(D_and_v['v_tur_i%d' % n_id])
    ymin = max(D_and_v['v_blend_i%d' % n_id].min() - yrange / 10, ymin)
    ymax = min(D_and_v['v_blend_i%d' % n_id].max() + yrange / 10, ymax)
    ax.set_ylim(ymin, ymax)


fig, ax = fn.subplots(1, 1, label='v/D', sharex=False)
rho_exp = input_gacode['rho']
ni = 1
if not trace_imp:
    ni = input_gacode['ni_%d' % n_id]
    rmin = input_gacode['rmin']
    dnidrmin = np.gradient(ni, rmin)
    ax.plot(rho_exp, dnidrmin / ni, label='exp', color='black', lw=lw)
for item in D_and_v:
    if item.startswith('v_') and 'chi' not in item:
        (p,) = ax.plot(rho[~mask], safe_divide(D_and_v[item][~mask], D_and_v['D' + item[1:]][~mask]), lw=lw, label=item)
        ax.plot(rho, safe_divide(D_and_v[item], D_and_v['D' + item[1:]]), lw=1, c=p.get_color())

ax.axhline(0.0, ls='--', color='black')
ax.legend(loc=0).draggable(True)
ax.set_title('Pinch/Diffusion ratio')
ax.set_xlabel('$\\rho$')
ax.set_ylabel('v/D [m$^{-1}$]')
ax.axvline(D_and_v['axis_core_rho'], color='k', ls='--')
ax.axvline(D_and_v['core_ped_rho'], color='k', ls='--')
ax.set_xlim(0, 1)
ax.grid(True)
ylim = ax.get_ylim()
ax.set_ylim(max(-10, ylim[0]), min(10, ylim[-1]))
fig, ax = fn.subplots(1, 1, label='D/chi_eff', sharex=False)
for item in D_and_v:
    if item.startswith('D') and 'chi' in item:
        (p,) = ax.plot(rho, masking(D_and_v, item), label=item, lw=lw)
        ax.plot(rho, D_and_v[item], lw=1, c=p.get_color())

ax.axhline(0.0, ls='--', color='black')
ax.legend(loc=0).draggable(True)
ax.set_title('Diffusion/ effective heat convection coeff.')
ax.set_xlabel('$\\rho$')
ax.set_ylabel('$D_{%s}/\chi_i$ [-]' % ion_name)
ax.axvline(D_and_v['axis_core_rho'], color='k', ls='--')
ax.axvline(D_and_v['core_ped_rho'], color='k', ls='--')
ax.set_ylim(0, None)
ax.set_xlim(0, 1)
ax.grid(True)

fig, ax = fn.subplots(1, 1, label='aV/chi_eff', sharex=False)
a = D_and_v['a']

for item in D_and_v:
    if item.startswith('aV') and 'chi' in item:
        (p,) = ax.plot(rho, masking(D_and_v, item), label=item, lw=lw)
        ax.plot(rho, D_and_v[item], lw=1, c=p.get_color())

ax.axhline(0.0, ls='--', color='black')
ax.legend(loc=0).draggable(True)
ax.set_title('Pinch over/ effective heat convection coeff.')
ax.set_xlabel('$\\rho$')
ax.set_ylabel('$aV_{%s}/\chi_i$ [-]' % ion_name)
ax.axvline(D_and_v['axis_core_rho'], color='k', ls='--')
ax.axvline(D_and_v['core_ped_rho'], color='k', ls='--')
ax.set_xlim(0, 1)
ax.grid(True)
ylim = ax.get_ylim()
ax.set_ylim(max(-10, ylim[0]), min(10, ylim[-1]))

fig, ax = fn.subplots(1, 1, label='Gamma=0 profiles', sharex=False)
if not trace_imp:
    ax.plot(rho_exp, ni, color='black', label=ion_name + ' (input.gacode)', lw=lw)

ne = input_gacode['ne']
ax.plot(rho_exp, ne / mean(ne) * mean(ni), color='gray', label='$n_e$ (scaled)', lw=lw)

for item in D_and_v:
    if item.startswith('n_'):
        if 'blend' in item:
            n0 = masking(D_and_v, item)
            ax.plot(rho, n0 / mean(n0) * mean(ni), label=ion_name + ' blend', lw=lw, c=p.get_color())

ax.legend(loc=0).draggable(True)

ax.set_title('Zero flux density profiles')
ax.set_xlabel('$\\rho$')
ylabel = r'$\langle n \rangle$' if STRAHL_like_DV else '$ n_{LFS}$'
ax.set_ylabel(ylabel + ' [10$^{19}$ m$^{-3}$]')
ax.axvline(D_and_v['axis_core_rho'], color='k', ls='--')
ax.axvline(D_and_v['core_ped_rho'], color='k', ls='--')
ax.set_ylim(0, None)
ax.set_xlim(0, 1)
ax.set_ylim(0, mean(ni) * 2)
