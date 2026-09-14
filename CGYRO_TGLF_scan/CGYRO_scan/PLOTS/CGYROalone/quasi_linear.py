import numpy as np
import sys

from OMFITlib_cgyro_read import *

with open(root['PLOTS']['CGYROalone']['assist']['getglobal.py'].filename, 'r') as _helper_source:
    exec(compile(_helper_source.read(), _helper_source.name, 'exec'), globals())

icgyro = root['SETTINGS']['SETUP']['icgyro']
if icgyro == 1:
	root['PLOTS']['CGYROalone']['assist']['collect.py'].run()
else:
	root['PLOTS']['CGYROalone']['assist']['collect_gyro.py'].run()

# Apply after collection as that task may load its own general NL selection.
case_plot = list(pltnl.get('quasilinear_cases', case_plot))
n_case = len(case_plot)
if not n_case:
    raise ValueError('No nonlinear cases selected for quasilinear comparison')

labd = [f'--{c}' for c in _CGYRO_LINE_CODES]


def _get_ql_dataarray(name):
    return root['QLW'][name]


def _load_qlw_if_needed():
    # Rebuild from this project's current selected OUTPUTScan; never use a
    # process-global cache from a different project or earlier selection.
    root['PLOTS']['CGYROscan']['qlflux.py'].run()


def _resolve_linear_range(case_name, casek, weight_arr):
    mapping = pltnl.get('linear_range_by_case', {})
    if case_name not in mapping:
        raise ValueError('Set PLOTS/nl/linear_range_by_case for ' + case_name + '; no implicit isotope/range mapping is safe')
    values = np.asarray(weight_arr.coords['nRange'].data)
    matches = np.flatnonzero(np.isclose(values, float(mapping[case_name]), rtol=1.e-10, atol=1.e-12))
    if len(matches) != 1:
        raise ValueError('Configured linear range must identify exactly one point: ' + case_name)
    index = int(matches[0])
    generated = casek['input.cgyro.gen' if icgyro else 'input.gyro.gen']
    for per_ky in root['QLW']['source_inputs']:
        source = per_ky[index]
        if icgyro:
            ns = int(generated['N_SPECIES'])
            keys = ['N_SPECIES', 'N_FIELD'] + [prefix + str(i + 1) for prefix in ('MASS_', 'Z_', 'DENS_', 'TEMP_') for i in range(ns)]
            for key in keys:
                if key not in source or not np.isclose(float(source[key]), float(generated[key]), rtol=1.e-6, atol=1.e-10):
                    raise ValueError('Linear/nonlinear input mismatch for %s: %s' % (case_name, key))
    return index


def _get_case_field_count(casek):
	if icgyro == 1:
		try:
			return min(len(casek['field_tags']), 3)
		except:
			return min(casek['n_field'], 3)
	try:
		return min(len(casek['tagfieldtext']), 3)
	except:
		return min(len(casek['tagfield']) - 1, 3)


def _get_phi_intensity(casek, i_field, theta=0., i_theta_plot=0):
	if i_field < 0:
		n_field_case = _get_case_field_count(casek)
		intensity = np.zeros(len(casek.ky))
		for field_idx in range(n_field_case):
			if icgyro == 1:
				casek.get_phi_n(i_field=field_idx, theta=theta)
			else:
				casek.get_phi_n(i_field=field_idx, i_theta_plot=i_theta_plot)
			intensity = intensity + abs(np.asarray(casek.phi_n_ave))
		return intensity

	if icgyro == 1:
		casek.get_phi_n(i_field=i_field, theta=theta)
	else:
		casek.get_phi_n(i_field=i_field, i_theta_plot=i_theta_plot)
	return abs(np.asarray(casek.phi_n_ave))


def _get_ql_weight(weight_arr, i_species, i_field, range_index):
	if i_field < 0:
		selected = weight_arr.isel(n_species=i_species, nRange=range_index).sum(dim='n_field')
	else:
		selected = weight_arr.isel(n_species=i_species, n_field=i_field, nRange=range_index)
	ky_weight = np.asarray(selected.coords['num_ky'].data)
	weight_value = np.asarray(selected.data)
	return ky_weight, weight_value


def _interp_weight(ky_target, ky_source, weight_source):
	return np.interp(ky_target, ky_source, weight_source, left=np.nan, right=np.nan)


_load_qlw_if_needed()
ql_weight_map = {
	'Gamma': _get_ql_dataarray('Gamma'),
	'Q': _get_ql_dataarray('Q'),
	'Pi': _get_ql_dataarray('Pi'),
}
flux_attr_map = {'Gamma': 'Gamma_n_ave', 'Q': 'Q_n_ave', 'Pi': 'Pi_n_ave'}
ylabel_map = {'Gamma': '$\\Gamma$', 'Q': '$Q$', 'Pi': '$\\Pi$'}

i_field = int(pltnl['i_field'])
theta = 0.
i_theta_plot = 0

quasi_linear_flux = {}
nonlinear_flux = {}
quasi_linear_ratio = {}

for channel_item in channel:
	kinetic_chan = channel_item.split('_')[0]
	species_index = int(channel_item.split('_')[1]) - 1
	weight_arr = ql_weight_map[kinetic_chan]
	species_labels = np.asarray(weight_arr.coords['n_species'].data)
	if species_index < 0 or species_index >= len(species_labels):
		raise IndexError('Requested species index out of range for ' + channel_item)

	species_name = str(species_labels[species_index])
	field_tag = 'sum over fields' if i_field < 0 else 'field ' + str(i_field)
	figure('quasi-linear ' + channel_item, figsize=[14, 10])
	ax_flux = subplot(2, 2, 1)
	ax_ratio = subplot(2, 2, 2)
	ax_intensity = subplot(2, 2, 3)
	ax_weight = subplot(2, 2, 4)

	quasi_linear_flux[channel_item] = {}
	nonlinear_flux[channel_item] = {}
	quasi_linear_ratio[channel_item] = {}

	for k_case in range(n_case):
		case_name = case_plot[k_case]
		casek = outputs[case_name]
		casek.get_flux_n(i_field=i_field, i_species=species_index)

		nonlinear_value = np.asarray(getattr(casek, flux_attr_map[kinetic_chan]))
		intensity_value = _get_phi_intensity(casek, i_field=i_field, theta=theta, i_theta_plot=i_theta_plot)
		range_index = _resolve_linear_range(case_name, casek, weight_arr)
		range_value = np.asarray(weight_arr.coords['nRange'].data)[range_index]
		ky_weight, weight_value = _get_ql_weight(weight_arr, species_index, i_field, range_index)
		ql_weight_interp = _interp_weight(casek.ky, ky_weight, weight_value)
		intensity_square = intensity_value**2
		quasi_linear_value = ql_weight_interp * intensity_square*casek.dky

		ratio_value = np.full(len(casek.ky), np.nan)
		valid = abs(nonlinear_value) > 0
		ratio_value[valid] = quasi_linear_value[valid] / nonlinear_value[valid]

		nonlinear_flux[channel_item][case_name] = {'ky': np.asarray(casek.ky), 'value': nonlinear_value}
		quasi_linear_flux[channel_item][case_name] = {
			'ky': np.asarray(casek.ky),
			'value': quasi_linear_value,
			'range_index': range_index,
			'range_value': range_value,
		}
		quasi_linear_ratio[channel_item][case_name] = {'ky': np.asarray(casek.ky), 'value': ratio_value}

		ax_flux.plot(casek.ky, nonlinear_value, lab[k_case], linewidth=lw, label=case_name + ' NL')
		ax_flux.plot(casek.ky, quasi_linear_value, labd[k_case], linewidth=lw, label=case_name + ' QL')
		ax_ratio.semilogy(casek.ky, ratio_value, labo[k_case], linewidth=lw, label=case_name)
		ax_intensity.plot(casek.ky, intensity_square, labo[k_case], linewidth=lw, label=case_name)
		ax_weight.plot(casek.ky, ql_weight_interp, labo[k_case], linewidth=lw, label=case_name)

	ax_flux.set_xscale(tick_scale[root['SETTINGS']['PLOTS']['ilogx']])
#	ax_flux.set_yscale('log')
	ax_flux.tick_params(labelsize=fs2)
#	ax_flux.set_xlabel('$k_y\\rho_s$', fontsize=fs1, family='serif')
#	ax_flux.set_ylabel(ylabel_map[kinetic_chan], fontsize=fs1, family='serif')
	ax_flux.set_title(channel_item +'(GB),' + field_tag, fontsize=fs3, family='serif')
	ax_flux.legend(loc=0, fontsize=fs2).set_draggable(True)

	ax_ratio.set_xscale(tick_scale[root['SETTINGS']['PLOTS']['ilogx']])
	ax_ratio.tick_params(labelsize=fs2)
	# ax_ratio.set_xlabel('$k_y\\rho_s$', fontsize=fs1, family='serif')
	ax_ratio.set_title('QL/NL Ratio', fontsize=fs3, family='serif')
	ax_ratio.legend(loc=0, fontsize=fs2).set_draggable(True)

	ax_intensity.set_xscale(tick_scale[root['SETTINGS']['PLOTS']['ilogx']])
	ax_intensity.set_yscale('log')
	ax_intensity.tick_params(labelsize=fs2)
	ax_intensity.set_xlabel('$k_y\\rho_s$', fontsize=fs1, family='serif')
	ax_intensity.set_title('$|\\phi/\\rho_s|^2$', fontsize=fs1, family='serif')
	ax_intensity.legend(loc=0, fontsize=fs2).set_draggable(True)

	ax_weight.set_xscale(tick_scale[root['SETTINGS']['PLOTS']['ilogx']])
	ax_weight.tick_params(labelsize=fs2)
	ax_weight.set_xlabel('$k_y\\rho_s$', fontsize=fs1, family='serif')
	ax_weight.set_title('$W_{QL}$', fontsize=fs1, family='serif')
	ax_weight.legend(loc=0, fontsize=fs2).set_draggable(True)

print('quasi-linear comparison done using QLW_* weights.')
