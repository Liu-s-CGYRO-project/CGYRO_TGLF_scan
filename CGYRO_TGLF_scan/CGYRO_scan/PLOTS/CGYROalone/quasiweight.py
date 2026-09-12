"""Compare flux spectra with field amplitude; species settings are 1-based.

For i_field=-1, total flux is compared with phi amplitude. Potentials with
different units are not added together.
"""
import numpy as np
import matplotlib.pyplot as plt

def _flux_spectrum(case, channel_name, species, field):
    data = case['flux_ky'][channel_name].isel(species=species)
    data = data.sum(dim='field') if field == -1 else data.isel(field=field)
    values = np.asarray(data)
    if values.ndim != 2:
        raise ValueError('Expected flux spectrum with ky and time axes')
    return values

def _ratio(numerator, denominator):
    numerator, denominator = np.broadcast_arrays(numerator, denominator)
    return np.divide(numerator, denominator, out=np.full(numerator.shape, np.nan),
                     where=np.isfinite(denominator) & (denominator != 0))

settings = root['SETTINGS']['PLOTS']['nl']
case_name = settings['case_t_trace']
case = root['OUTPUTS']['NonLinear'][case_name]
channels = settings['channel']
field = int(settings['i_field'])
if field not in (-1, 0, 1, 2):
    raise ValueError('i_field must be -1 (total), 0, 1 or 2')
field_names = {-1: 'total', 0: 'phi', 1: 'apar', 2: 'bpar'}
reference_field = 0 if field == -1 else field
reference_name = field_names[reference_field]
ky = np.abs(np.asarray(case['kyrhos']))
if len(ky) < 2 or not np.allclose(np.diff(ky), np.diff(ky)[0]) or np.diff(ky)[0] <= 0:
    raise ValueError('This comparison requires a uniform increasing ky grid')
dky = ky[1]-ky[0]
n_time = int(case['n_time'])
case_index = list(settings['case_plot']).index(case_name) if case_name in settings['case_plot'] else 0
window_setting = np.asarray(settings['t_ave'])
end_setting = np.asarray(settings.get('t_end', 1.0))
window = float(window_setting if window_setting.ndim == 0 else window_setting[case_index])
end = float(end_setting if end_setting.ndim == 0 else end_setting[case_index])
if not 0 < window <= end <= 1:
    raise ValueError('Expected 0 < t_ave <= t_end <= 1')
indices = np.arange(int((end-window)*n_time), int(end*n_time))
if len(indices) < 2:
    raise ValueError('At least two time samples are required')

case.getbigfield()
field_k, _ = case.kxky_select(0, reference_field, 'phi', 0)
# This is an amplitude spectrum, not time-averaged field power.
amplitude = np.sum(np.abs(field_k), axis=0)/case.rho
amplitude_samples = np.take(amplitude, indices, axis=-1)
amplitude_mean = np.mean(amplitude_samples, axis=-1)
amplitude_std = np.std(amplitude_samples, axis=-1)
fig, axes = plt.subplots(2, len(channels), squeeze=False)
channel_fields = {'Q': 'energy', 'G': 'particle', 'Gamma': 'particle', 'P': 'momentum', 'Pi': 'momentum'}
for column, channel in enumerate(channels):
    quantity, species_text = channel.rsplit('_', 1)
    species = int(species_text)-1
    if species < 0:
        raise ValueError('Species settings are 1-based')
    flux = _flux_spectrum(case, channel_fields[quantity], species, field)
    samples = np.take(flux, indices, axis=-1)
    mean = np.mean(samples, axis=-1)/dky
    std = np.std(samples, axis=-1)/dky
    scale_denominator = np.mean(amplitude_mean)
    scale = float(np.mean(mean)/scale_denominator) if scale_denominator != 0 else np.nan
    ax = axes[0, column]
    ax.errorbar(ky, mean, std, label=channel+' '+field_names[field])
    if np.isfinite(scale):
        ax.errorbar(ky, scale*amplitude_mean, abs(scale)*amplitude_std,
                    label='scaled '+reference_name+' amplitude')
    ax.set_title(case_name)
    ax.legend()
    ax = axes[1, column]
    ratio = _ratio(mean, amplitude_mean)
    ax.plot(ky, ratio, '-o', label=channel+'/'+reference_name+' amplitude')
    ax.plot(ky, _ratio(ratio, ky), '-s', label=channel+'/(ky '+reference_name+' amplitude)')
    ax.legend()
    for ax in axes[:, column]:
        ax.set_xlabel('ky rho_s')
        if root['SETTINGS']['PLOTS']['ilogx'] == 1:
            ax.set_xscale('log')
            ax.set_xlim(ky[ky > 0].min(), ky.max())
