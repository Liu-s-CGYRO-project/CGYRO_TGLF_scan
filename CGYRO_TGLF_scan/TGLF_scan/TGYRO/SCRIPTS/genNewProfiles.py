# -*-Python-*-
# Created by meneghini at 2013/04/03 10:11
#
# script used to merge GAprofiles input.gacode with relaxation parameter

profiles = copy.deepcopy(input_gacode)
n = len(profiles['ne'])

relax = root['SETTINGS']['PHYSICS']['relaxProfiles']
smth = int(11 * len(profiles['ne']) / 201.0)

if 'LOC_NE_FEEDBACK_FLAG' in root['INPUTS']['input.tgyro'] and root['INPUTS']['input.tgyro']['LOC_NE_FEEDBACK_FLAG']:
    ne = root['OUTPUTS']['output'].sprofile('ne', n, x='rho') / 1e13
    if ne.shape[1] == 0:
        raise OMFITexception('Can not form new input.gacode, because not ' 'enough iterations (perhaps you aborted early?)')
    ne += -ne[-1, -1] + profiles['ne'][: ne.shape[0]][-1]
    # adjustment because TGYRO base profile is slightly different from experimental one even if ['LOC_LOCK_PROFILE_FLAG']=1
    # plot(linspace(0,1,201)[:len(ne)],ne[:,-1])
    # plot(linspace(0,1,201),profiles['ne'])
    profiles['ne'][: ne.shape[0]] = profiles['ne'][: ne.shape[0]] * (1 - relax) + ne[:, -1] * relax
    # plot(linspace(0,1,201),profiles['ne'])
    if smth > 0:
        profiles['ne'][ne.shape[0] - smth // 2 : ne.shape[0] + smth // 2] = smooth(profiles['ne'], smth)[
            ne.shape[0] - smth // 2 : ne.shape[0] + smth // 2
        ]
    # plot(linspace(0,1,201),profiles['ne'])

    for spec in range(1, int(root['INPUTS']['input.tgyro']['LOC_N_ION']) + 1):
        if 'ni%d' % spec in root['OUTPUTS']['output']:
            ni = root['OUTPUTS']['output'].sprofile('ni%d' % spec, n, x='rho') / 1e13
        else:
            raise OMFITexception(
                'The tgyrodata class of your GACODE installation only loads the main ion data.'
                ' Please update your GACODE installation to the latest version'
            )
        if ni.shape[1]:
            ni += -ni[-1, -1] + profiles['ni_%d' % spec][: ni.shape[0]][-1]
            profiles['ni_%d' % spec][: ni.shape[0]] = profiles['ni_%d' % spec][: ni.shape[0]] * (1 - relax) + ni[:, -1] * relax
            if smth > 0:
                profiles['ni_%d' % spec][ni.shape[0] - smth // 2 : ni.shape[0] + smth // 2] = smooth(profiles['ni_%d' % spec], smth)[
                    ni.shape[0] - smth // 2 : ni.shape[0] + smth // 2
                ]

if 'LOC_TE_FEEDBACK_FLAG' in root['INPUTS']['input.tgyro'] and root['INPUTS']['input.tgyro']['LOC_TE_FEEDBACK_FLAG']:
    Te = root['OUTPUTS']['output'].sprofile('te', n, x='rho')
    if Te.shape[1]:
        Te += -Te[-1, -1] + profiles['Te'][: Te.shape[0]][-1]
        profiles['Te'][: Te.shape[0]] = profiles['Te'][: Te.shape[0]] * (1 - relax) + Te[:, -1] * relax
        if smth > 0:
            profiles['Te'][Te.shape[0] - smth // 2 : Te.shape[0] + smth // 2] = smooth(profiles['Te'], smth)[
                Te.shape[0] - smth // 2 : Te.shape[0] + smth // 2
            ]

if 'LOC_TI_FEEDBACK_FLAG' in root['INPUTS']['input.tgyro'] and root['INPUTS']['input.tgyro']['LOC_TI_FEEDBACK_FLAG']:
    for spec in range(1, int(root['INPUTS']['input.tgyro']['LOC_N_ION']) + 1):
        if 'TGYRO_THERM_FLAG%d' % spec in root['INPUTS']['input.tgyro'] and root['INPUTS']['input.tgyro']['TGYRO_THERM_FLAG%d' % spec]:
            if 'ti%d' % spec in root['OUTPUTS']['output']:
                Ti = root['OUTPUTS']['output'].sprofile('ti%d' % spec, n, x='rho')
            else:
                raise OMFITexception(
                    'The TGYROdata class of your GACODE installation only loads the main ion data.'
                    ' Please update your GACODE installation to the latest version'
                )
            if Ti.shape[1]:
                Ti += -Ti[-1, -1] + profiles['Ti_%d' % spec][: Ti.shape[0]][-1]
                profiles['Ti_%d' % spec][: Ti.shape[0]] = profiles['Ti_%d' % spec][: Ti.shape[0]] * (1 - relax) + Ti[:, -1] * relax
                if smth > 0:
                    profiles['Ti_%d' % spec][Ti.shape[0] - smth // 2 : Ti.shape[0] + smth // 2] = smooth(profiles['Ti_%d' % spec], smth)[
                        Ti.shape[0] - smth // 2 : Ti.shape[0] + smth // 2
                    ]

if root['INPUTS']['input.tgyro']['TGYRO_USE_RHO']:
    rho_max = root['INPUTS']['input.tgyro']['TGYRO_RMAX']
else:
    rho_max = interp(root['INPUTS']['input.tgyro']['TGYRO_RMAX'], profiles['rmin'] / profiles['rmin'].max(), profiles['rho'])

# enforce quasineutrality, total pressure, zeff
PROFILES_GEN['SCRIPTS']['enforce_quasineutrality'].run(input_gacode=profiles)

root['OUTPUTS']['input.gacode'] = profiles
