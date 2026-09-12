# -*-Python-*-
# Created by smithsp at 20 Jul 2017  10:55

"""
This script plots growth rate and frequency at a given ky vs scanned parameter

defaultVars parameters

:param ky: The wavenumber at which to plot the growthrate and frequency vs scanned parameter

:param param: The scanned parameter against which to plot

:param fig: matplotlib figure into which to plot

:param growth_rate_index: Which growth rate to plot (1 is most unstable)
----------------------

"""
defaultVars(ky=root['SETTINGS']['PHYSICS'].get('plot_ky', None), param=None, fig=None, growth_rate_index=1)

if param is None:
    if not len(root['scanResults_spectra']):
        printe('No scans exist to plot')
        OMFITx.End()
    param = list(root['scanResults_spectra'].keys())[0]

if ky is None:
    if not len(root['scanResults_spectra'][param]):
        printe('No scans of %s exist to plot' % param)
        OMFITx.End()
    key0 = list(root['scanResults_spectra'][param].keys())[0]
    ky = root['scanResults_spectra'][param][key0]['eigenvalue_spectrum']['ky']
    ky = ky[len(ky) // 2]

scan = root['scanResults_spectra'][param]
param_vals = list(scan.keys())
gamma = []
freq = []
for v in param_vals:
    spec = scan[v]['eigenvalue_spectrum']
    ind = closestIndex(spec['ky'], ky)
    if abs(spec['ky'][ind] - ky) / ky > 0.1:
        printw('Collecting growthrates that differ by more than 10% in wavenumber')
        printw('%s vs %s' % (spec['ky'][ind], ky))
    gamma.append(scan[v]['eigenvalue_spectrum']['gamma(%d)' % growth_rate_index][ind])
    freq.append(scan[v]['eigenvalue_spectrum']['freq(%d)' % growth_rate_index][ind])

if fig is None:
    fig = gcf()

ax1 = fig.use_subplot(2, 1, 1)
ax2 = fig.use_subplot(2, 1, 2)
ax1.plot(param_vals, gamma, label='$k_y=%s$' % ky)
ax2.plot(param_vals, freq, label='$k_y=%s$' % ky)
ax1.axvline(root['FILES']['input.tglf'][param], color='black', ls='--')
ax2.axvline(root['FILES']['input.tglf'][param], color='black', ls='--')
ax2.set_xlabel(param)
ax1.set_title('Growth rate and frequency vs %s' % param)
ax2.legend(loc='best')
ax1.set_ylabel(r'$\gamma$')
ax2.set_ylabel(r'$\omega$')
