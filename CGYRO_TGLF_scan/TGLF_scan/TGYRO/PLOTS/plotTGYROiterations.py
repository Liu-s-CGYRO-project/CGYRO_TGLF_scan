# -*-Python-*-
# Created by smithsp at 2013/06/14 11:03

defaultVars(match_str='', output=root['OUTPUTS']['output'])


candidate_keys = {
    'profile': ['ne', 'ni', 'ni2', 'ni3', 'ni4', 'ni5', 'te', 'ti', 'Ti2', 'Ti3', 'Ti4', 'Ti5'],
    'scale_len': [
        'a/Lne',
        'a/Lni',
        'a/Lni2',
        'a/Lni3',
        'a/Lni4',
        'a/Lni5',
        'a/Lp',
        'a/LTe',
        'a/LTi',
        'a/LTi2',
        'a/LTi3',
        'a/LTi4',
        'a/LTi5',
    ],
    'power': ['p_alpha', 'p_brem', 'p_e', 'p_e_aux', 'p_exch', 'p_expwd', 'p_i', 'p_i_aux'],
    'eflux_neo_tur': [
        'eflux_e_neo',
        'eflux_i_neo',
        'eflux_i_neo2',
        'eflux_i_neo3',
        'eflux_i_neo4',
        'eflux_i_neo5',
        'eflux_e_tur',
        'eflux_i_tur',
        'eflux_i_tur2',
        'eflux_i_tur3',
        'eflux_i_tur4',
        'eflux_i_tur5',
    ],
    'pflux_neo_tur': [
        'pflux_e_neo',
        'pflux_i_neo',
        'pflux_i_neo2',
        'pflux_i_neo3',
        'pflux_i_neo4',
        'pflux_i_neo5',
        'pflux_e_tur',
        'pflux_i_tur',
        'pflux_i_tur2',
        'pflux_i_tur3',
        'pflux_i_tur4',
        'pflux_i_tur5',
    ],
    'mflux_neo_tur': [
        'mflux_e_neo',
        'mflux_i_neo',
        'mflux_i_neo2',
        'mflux_i_neo3',
        'mflux_i_neo4',
        'mflux_i_neo5',
        'mflux_e_tur',
        'mflux_i_tur',
        'mflux_i_tur2',
        'mflux_i_tur3',
        'mflux_i_tur4',
        'mflux_i_tur5',
    ],
    'flux_tot_target': [
        'eflux_e_target',
        'pflux_e_target',
        'eflux_i_target',
        'mflux_target',
        'eflux_e_tot',
        'pflux_e_tot',
        'eflux_i_tot',
        'mflux_tot',
    ],
    'geometry': [
        '<|grad_r|>',
        'b_unit',
        's_kappa',
        'kappa',
        's_delta',
        'delta',
        'r/a',
        'rho',
        'shift',
        'q',
        'dzmag',
        's_zeta',
        'zeta',
        'zmag/a',
        'volume',
        'rmaj/a',
        'rmin',
        's',
        'd(vol)/dr',
    ],
    'norms': ['betae_unit', 'c_s', 'Chi_GB', 'Gamma_GB', 'Pi_GB', 'Q_GB', 'ti/te', 'M=wR/cs'],
    'diffusivities': [
        'chie_neo',
        'chii_neo',
        'chii_neo2',
        'chii_neo3',
        'chii_neo4',
        'chii_neo5',
        'chie_tur',
        'chii_tur',
        'chii_tur2',
        'chii_tur3',
        'chii_tur4',
        'chii_tur5',
    ],
    'Ds': ['De_neo', 'Di_neo', 'Di_neo2', 'Di_neo3', 'Di_neo4', 'Di_neo5', 'De_tur', 'Di_tur', 'Di_tur2', 'Di_tur3', 'Di_tur4', 'Di_tur5'],
    'expwd': ['expwd_e_tur', 'expwd_i_tur', 'expwd_i_tur2', 'expwd_i_tur3', 'expwd_i_tur4', 'expwd_i_tur5'],
}
existing_keys = {}
for k, v in candidate_keys.items():
    existing_keys[k] = []
    for key in v:
        if key in output:
            existing_keys[k].append(key)

for k in existing_keys:
    if k == 'geometry' or k == 'diffusivities' or k == 'Ds':
        continue
    n = len(existing_keys[k])
    if n == 0:
        continue
    nr = 2
    nc = (n + nr - 1) // nr
    tit = 'Iteration trajectory for %s' % k
    close(tit)
    fig, axs = subplots(nr, nc, num=tit, sharex=True, squeeze=False)
    fig.suptitle(tit)
    # print k,len(existing_keys[k]),len(axs.flat),zip(tuple(existing_keys[k]),axs.flat)[1]
    for ki, key in enumerate(existing_keys[k]):
        # print key,ax
        ax = axs.flat[ki]
        sca(axs.flat[ki])
        ax.text(0.5, 0.95, key, transform=ax.transAxes, ha='center', va='top')
        plotc(output[key])
