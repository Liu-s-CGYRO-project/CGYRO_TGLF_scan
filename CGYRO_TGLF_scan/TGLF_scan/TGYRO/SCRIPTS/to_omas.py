# -*-Python-*-
# Created by meneghini at 27 Sep 2018  20:36

"""
This script generates an ODS from the OUTPUT input.gacode and the D_and_v analysis of the latest TGYRO run
"""

from omas.omas_physics import search_in_array_structure

defaultVars(ods=ODS(), ip=None, time_index=0, update=['core_profiles', 'core_sources'])

if ip is None:
    ip = root['OUTPUTS']['input.gacode']
    tgyro_save = True
else:
    tgyro_save = False

# start from ODS generated from input.gacode that is output by TGYRO
root['OUTPUTS']['ods'] = ip.to_omas(ods, time_index=time_index, update=update)

### Add momentum, particle and energy fluxes from TGYRO to omas [mks]
model_list = [("neo", 5), ("tur", 6), ("tot", 1), ("target", 2), ("power_balance", 2)]

GB_particle_flux = root['OUTPUTS']['output']['Gamma_GB'][-1] * 1e19  # last iteration
GB_energy_flux = root['OUTPUTS']['output']['Q_GB'][-1] * 1e6
GB_momentum_flux = root['OUTPUTS']['output']['Pi_GB'][-1]

ods['core_transport.ids_properties.comment'] = "TGYRO"

if "equilibrium.time" in ods:
    ods['core_transport.time'] = [ods["equilibrium.time"][time_index]]
else:
    ods['core_transport.time'] = [0.0]

for m_index, (model, model_index) in enumerate(model_list):
    identifier = {'identifier.name': model + "_TGYRO"}
    ods['core_transport']['model'][m_index].update(identifier)
    ods['core_transport']['model'][m_index]['identifier']['index'] = model_index

    mod1d = ods['core_transport']['model'][m_index]['profiles_1d'][time_index]

    if model == "power_balance":
        # Power_balance from profiles
        mod1d['grid_flux']['rho_tor_norm'] = copy.deepcopy(root['PROFILES_GEN']['OUTPUTS']['input.gacode']['rho'])
        volp = copy.deepcopy(root['PROFILES_GEN']['OUTPUTS']['input.gacode']['volp'])
        volp[np.where(volp == 0.0)] = np.finfo(float).eps  # prevent divide by 0
        mod1d['total_ion_energy']['flux'] = root['PROFILES_GEN']['OUTPUTS']['input.gacode']['pow_i'] / volp * 1e6  # input.gacode MW -> W
        mod1d['electrons']['energy']['flux'] = root['PROFILES_GEN']['OUTPUTS']['input.gacode']['pow_e'] / volp * 1e6  # input.gacode MW -> W
        mod1d['momentum_tor']['flux'] = root['PROFILES_GEN']['OUTPUTS']['input.gacode']['flow_mom'] / volp
        continue  # skip the rest for power_balance

    mod1d['grid_flux']['rho_tor_norm'] = root['OUTPUTS']['output']['rho'][-1]

    if model == "tot" or model == "target":
        mod1d['total_ion_energy']['flux'] = root['OUTPUTS']['output']['eflux_i_' + model][-1] * GB_energy_flux
        mod1d['momentum_tor']['flux'] = root['OUTPUTS']['output']['mflux_' + model][-1] * GB_momentum_flux

    else:
        for ion in range(len(root['OUTPUTS']['input.gacode']['IONS'])):
            if model != "target":
                mod1d['ion'][ion]['energy']['flux'] = (
                    root['OUTPUTS']['output']['eflux_i' + str(ion + 1) + "_" + str(model)][-1] * GB_energy_flux
                )
                mod1d['ion'][ion]['momentum']['radial']['flux'] = (
                    root['OUTPUTS']['output']['mflux_i' + str(ion + 1) + "_" + str(model)][-1] * GB_momentum_flux
                )
            mod1d['ion'][ion]['particles']['flux'] = (
                root['OUTPUTS']['output']['pflux_i' + str(ion + 1) + "_" + str(model)][-1] * GB_particle_flux
            )

    mod1d['electrons']['energy']['flux'] = root['OUTPUTS']['output']['eflux_e_' + str(model)][-1] * GB_energy_flux
    mod1d['electrons']['particles']['flux'] = root['OUTPUTS']['output']['pflux_e_' + str(model)][-1] * GB_particle_flux


### Transport coeff
if 'D_and_v' in root['OUTPUTS']:
    D_and_v = root['OUTPUTS']['D_and_v']

    n_id = int([x for x in list(D_and_v.keys()) if '_neo_' in x][0].split('_')[-1][1:])
    ion_symbol, ion_Z, ion_A, ion_therm = ip['IONS'][n_id]

    # select model_index based on identifier.name
    model = {'identifier.name': 'omas_tgyro'}
    model_index = search_in_array_structure(ods['core_transport.model'], model)[0]
    ods['core_transport.model'][model_index].update(model)

    # shortcuts
    profiles_ion = ods['core_profiles.profiles_1d'][time_index]['ion']
    transport_ion = ods['core_transport.model'][model_index]['profiles_1d'][time_index]['ion']

    # copy all ion labels and elements so that we can keep the same ordering in core_transport as in core_profiles
    if not len(transport_ion):
        for ion_index in profiles_ion:
            for item in ['label', 'element']:
                transport_ion[ion_index][item] = profiles_ion[ion_index][item]

    # identify impurity ion for which D_and_v calculation was carried out
    ion_index = list(omas.omas_physics.search_ion(profiles_ion, ion_symbol, ion_Z, ion_A).keys())[0]

    # add D and v information
    coordsio = {}
    coordsio['core_transport.model.%d.profiles_1d.%d.grid_d.rho_tor_norm' % (model_index, time_index)] = D_and_v['rho']
    coordsio['core_transport.model.%d.profiles_1d.%d.grid_v.rho_tor_norm' % (model_index, time_index)] = D_and_v['rho']
    with omas_environment(ods, coordsio=coordsio):
        transport_ion[ion_index]['particles']['d'] = D_and_v['D_blend_i%d' % n_id]
        transport_ion[ion_index]['particles']['v'] = D_and_v['v_blend_i%d' % n_id]

    print('Added D_and_v information to ODS')

# save the run since we have updated the OUTPUTS folder
if tgyro_save:
    root['SCRIPTS']['saveTGYRO'].run()
