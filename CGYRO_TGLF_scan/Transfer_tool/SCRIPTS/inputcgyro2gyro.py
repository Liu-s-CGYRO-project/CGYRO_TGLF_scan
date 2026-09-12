# this script is used to transform the input.cgyro to input.gyro
import os
template = root['SETTINGS']['SETUP'].get('input_gyro_template', '')
if not template or not os.path.isfile(os.path.expanduser(template)):
    raise ValueError('Set SETTINGS.SETUP.input_gyro_template to a readable input.gyro template for your GACODE version')
template = os.path.abspath(os.path.expanduser(template))
p_tgyro=len(root['INPUTS']['input.tgyro']['DIR'])
for m in arange(1,p_tgyro+1):
    # root['OUTPUTS']['TGYRO']['CGYRO']['input.gyro_'+str(m)]=OMFITgacode(template)
    # inputcgyro=root['OUTPUTS']['TGYRO']['CGYRO']['input.cgyro_'+str(m)]
    # inputgyro=root['OUTPUTS']['TGYRO']['GYRO']['out.gyro.localdump_'+str(m)]
    root['OUTPUTS']['Profiles_gen']['input.gyro_'+str(m)]=OMFITgacode(template)
    inputcgyro=root['OUTPUTS']['Profiles_gen']['input.cgyro_'+str(m)]
    inputgyro=root['OUTPUTS']['Profiles_gen']['input.gyro_'+str(m)]
    inputgyro['RADIAL_PROFILE_METHOD']=5
    inputgyro['RADIUS']=inputcgyro['RMIN']
    inputgyro['ASPECT_RATIO']=inputcgyro['RMAJ']
    inputgyro['SHIFT']=inputcgyro['SHIFT']
    inputgyro['KAPPA']=inputcgyro['KAPPA']
    inputgyro['S_KAPPA']=inputcgyro['S_KAPPA']
    inputgyro['DELTA']=inputcgyro['DELTA']
    inputgyro['S_DELTA']=inputcgyro['S_DELTA']
    inputgyro['ZETA']=inputcgyro['ZETA']
    inputgyro['S_ZETA']=inputcgyro['S_ZETA']
    inputgyro['ZMAG']=inputcgyro['ZMAG']
    inputgyro['DZMAG']=inputcgyro['DZMAG']
    # magnetic profile
    inputgyro['SAFETY_FACTOR']=inputcgyro['Q']
    inputgyro['SHEAR']=inputcgyro['S']
    inputgyro['BTCCW']=inputcgyro['BTCCW']
    inputgyro['IPCCW']=inputcgyro['IPCCW']
    # inputcgyro['IPCCW']=-1
    # inputgyro['UDSYMMETRY_FLAG']=inputcgyro['UDSYMMETRY_FLAG']
    # control parameters, use the default
    #### not listed here
    # fields
    inputgyro['N_FIELD']=inputcgyro['N_FIELD']
    inputgyro['BETAE_UNIT']=inputcgyro['BETAE_UNIT']
    # inputgyro['GEO_BETAPRIME_SCALE']=inputcgyro['BETA_STAR_SCALE']
    # inputgyro['LAMBDA_DEBYE']=inputcgyro['LAMBDA_DEBYE']
    # numerical resolution, use the default
    # numerical dissipation, use the default
    # time stepping, use the default,
    # collisions model, use the default
    inputgyro['NU_EI']=inputcgyro['NU_EE']
    n_s=inputcgyro['N_SPECIES']
    inputgyro['Z']=inputcgyro['Z_1']
    inputgyro['MU']=1./inputcgyro['MASS_1']**0.5
    inputgyro['NI_OVER_NE']=inputcgyro['DENS_1']
    inputgyro['TI_OVER_TE']=inputcgyro['TEMP_1']
    inputgyro['DLNNDR']=inputcgyro['DLNNDR_1']
    inputgyro['DLNTDR']=inputcgyro['DLNTDR_1']
    for k in arange(2,n_s):
        inputgyro['Z_' + str(k)]=inputcgyro['Z_'+str(k)]
        inputgyro['MU_' + str(k)] =1./inputcgyro['MASS_'+str(k)]**0.5
        inputgyro['NI_OVER_NE_' + str(k)]=inputcgyro['DENS_'+str(k)]
        inputgyro['TI_OVER_TE_' + str(k)]=inputcgyro['TEMP_'+str(k)]
        inputgyro['DLNNDR_' + str(k)]=inputcgyro['DLNNDR_'+str(k)]
        inputgyro['DLNTDR_' + str(k)]=inputcgyro['DLNTDR_'+str(k)]
    # # inputcgyro['Z_'+str(n_s)]=-1
    # inputcgyro['MASS_'+str(n_s)]=1./inputgyro['MU_ELECTRON']**2
    # inputcgyro['DENS_'+str(n_s)]=1
    # inputcgyro['TEMP_'+str(n_s)]=1
    inputgyro['DLNNDR_ELECTRON']=inputcgyro['DLNNDR_'+str(n_s)]
    inputgyro['DLNTDR_ELECTRON']=inputcgyro['DLNTDR_'+str(n_s)]
    # inputcgyro['Z_EFF']=inputgyro['Z_EFF']
    # rotation physics
    inputgyro['GAMMA_E']=inputcgyro['GAMMA_E']
    inputgyro['GAMMA_P']=inputcgyro['GAMMA_P']
    inputgyro['MACH']=inputcgyro['MACH']
    # drift kinetic electrons
    inputgyro['ELECTRON_METHOD'] = 2
