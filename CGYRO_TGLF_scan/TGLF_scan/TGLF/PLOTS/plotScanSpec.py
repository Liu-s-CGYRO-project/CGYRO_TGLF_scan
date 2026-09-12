# -*-Python-*-
# Created by grierson at 04 Oct 2016  17:37

defaultVars(
    param=root['SETTINGS']['PHYSICS']['scanParameter'],
    results='scanResults',
    TGLF_scan=True,
    mode_num=1,
    plot_settings=None,
)

if plot_settings is None:
    plot_settings = root['SETTINGS'].get('PLOTS', {})

results = results + '_spectra'
vals = list(root[results][param].keys())
quench = root[results][param][vals[0]]['input.tglf']['ALPHA_QUENCH']
colors = mpl.cm.rainbow(linspace(0, 1, len(vals)))

fn = FigureNotebook(0, 'TGLF Spectra')

fig, ax = fn.subplots(nrows=2, ncols=2, label='Eigenvalue', sharex=True, sharey='row')
for i, v in enumerate(vals):
    evs = root[results][param][v]['eigenvalue_spectrum']
    if plot_settings.get('Divided ky', False):
        ax[0, 0].plot(evs['ky'], evs['gamma(1)']/evs['ky'], color=colors[i])
        ax[0, 1].plot(evs['ky'], evs['gamma(2)']/evs['ky'], color=colors[i])
        ax[1, 0].plot(evs['ky'], evs['freq(1)']/evs['ky'], color=colors[i])
        ax[1, 1].plot(evs['ky'], evs['freq(2)']/evs['ky'], color=colors[i])
    else:
        ax[0, 0].plot(evs['ky'], evs['gamma(1)'], color=colors[i])
        ax[0, 1].plot(evs['ky'], evs['gamma(2)'], color=colors[i])
        ax[1, 0].plot(evs['ky'], evs['freq(1)'], color=colors[i])
        ax[1, 1].plot(evs['ky'], evs['freq(2)'], color=colors[i])
if plot_settings.get('Use_x_log', False):
    ax[0, 0].set_xscale('log')
if plot_settings.get('Use_y_log', False):
    ax[0, 0].set_yscale('log')
    ax[1, 0].set_yscale('symlog')
ax[1, 0].axhline(0, linestyle='dashed', color='black')
ax[1, 1].axhline(0, linestyle='dashed', color='black')
ax[1, 0].text(0.05, 0.95, 'elec ($\omega>0$)', transform=ax[1, 0].transAxes)
ax[1, 0].text(0.05, 0.05, 'ion ($\omega<0$)', transform=ax[1, 0].transAxes)
ax[1, 1].text(0.05, 0.95, 'elec ($\omega>0$)', transform=ax[1, 1].transAxes)
ax[1, 1].text(0.05, 0.05, 'ion ($\omega<0$)', transform=ax[1, 1].transAxes)
ax[0, 0].set_title('Most Unstable')
ax[0, 1].set_title('Sub-dominant')
for i in range(2):
    ax[1, i].set_xlabel('ky')
if quench == 0.0:
    if plot_settings.get('Divided ky', False):
        ax[0, 0].set_ylabel('$\\gamma/k_y (c_s/a)$')
    else:
        ax[0, 0].set_ylabel('$\\gamma (c_s/a)$')
else:
    if plot_settings.get('Divided ky', False):
        ax[0, 0].set_ylabel('$\\gamma_{eff}/k_y (c_s/a)$')
    else:
        ax[0, 0].set_ylabel('$\\gamma_{eff} (c_s/a)$')
    
if plot_settings.get('Divided ky', False):
    ax[1, 0].set_ylabel('$\\omega/k_y (c_s/a)$')
else:
    ax[1, 0].set_ylabel('$\\omega (c_s/a)$')

vals0 = vals[0]
for field in root[results][param][vals0]['potential_spectrum']:
    if field == 'ky':
        continue
    fig, ax = fn.subplots(label=field.title())
    for i, v in enumerate(vals):
        spec = root[results][param][v]['potential_spectrum']
        if TGLF_scan:
            spec = spec.sel(mode_num=mode_num)
        ax.plot(spec['ky'], spec[field], color=colors[i])
    ax.set_xscale('log')
    ax.set_yscale('log')
    ax.set_title('%s Spectrum' % field.title())
    ax.set_xlabel('ky')

# In a scan assume that all runs have same number of species and fields
fs_txt = "flux_spectrum"
if TGLF_scan:
    fs_txt = "sum_" + fs_txt

fs = root[results][param][vals[0]][fs_txt]
ns = fs.n_species
nf = fs.n_fields
for chan in fs:
    if chan in fs.dims:
        continue
    fig, ax = fn.subplots(nrows=ns, ncols=nf, label=chan, sharex=True, sharey='row', squeeze=False)
    for i, v in enumerate(vals):
        fs = root[results][param][v][fs_txt]
        # for k in fs.labels:
        for s in range(ns):
            for f in range(nf):
                ax[s, f].plot(fs['ky'], fs[chan].isel(species=s, field=f), color=colors[i])
    for f in range(nf):
        ax[0, f].set_title(['$\phi$', '$B_{\perp}$', '$B_{\parallel}$'][f])
        ax[-1, f].set_xlabel('ky')
        for s in range(ns):
            ax[s, f].axhline(0, linestyle='dashed', color='black')
    for s in range(ns):
        ax[s, 0].set_ylabel(fs.spec_labels[s])
    ax[-1, -1].set_xscale('log')
