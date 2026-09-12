#-*-Python-*-
# Created by liujy at 09 Apr 2025  16:26

import numpy as np
import scipy.linalg

CGYRO = root['Transfer_file']['input.cgyro']
TGLF = root['Transfer_file']['input.tglf']
inputgacode = root['Transfer_file']['input.gacode']

def _build_convert_tglf_to_cgyro(CGYRO,TGLF,inputgacode):
    CGYRO.clear()
    CGYRO['N_ENERGY'] = 8
    CGYRO['N_XI'] = 16
    CGYRO['N_THETA'] = 24
    CGYRO['N_RADIAL'] = 16
    CGYRO['N_TOROIDAL'] = 1
    CGYRO['NONLINEAR_FLAG'] = 0
    CGYRO['BOX_SIZE'] = 1
    CGYRO['KY'] = 0.3
    CGYRO['DELTA_T'] = 0.01
    CGYRO['MAX_TIME'] = 100
    CGYRO['PRINT_STEP'] = 100

    CGYRO['RMIN'] = TGLF['RMIN_LOC']
    CGYRO['RMAJ'] = TGLF['RMAJ_LOC']
    CGYRO['EQUILIBRIUM_MODEL'] = 2
    CGYRO['SHIFT'] = TGLF['DRMAJDX_LOC']
    CGYRO['ZMAG'] = TGLF['ZMAJ_LOC']
    CGYRO['DZMAG'] = TGLF['DZMAJDX_LOC']
    CGYRO['Q'] = abs(TGLF['Q_LOC'])
    CGYRO['KAPPA'] = TGLF['KAPPA_LOC']
    CGYRO['S_KAPPA'] = TGLF['S_KAPPA_LOC']
    CGYRO['DELTA'] = TGLF['DELTA_LOC']
    CGYRO['S_DELTA'] = TGLF['S_DELTA_LOC']
    CGYRO['ZETA'] = TGLF['ZETA_LOC']
    CGYRO['S_ZETA'] = TGLF['S_ZETA_LOC']
    CGYRO['BTCCW'] = TGLF['SIGN_BT']
    CGYRO['IPCCW'] = TGLF['SIGN_IT']
    CGYRO['NU_EE'] = TGLF['XNUE']
    CGYRO['LAMBDA_STAR'] = TGLF['DEBYE']
    CGYRO['BETAE_UNIT'] = TGLF['BETAE']
    CGYRO['N_SPECIES'] = TGLF['NS']

    expro_n_exp = inputgacode['N_EXP']
    expro_rmin = inputgacode['rmin']
    rmin_exp = inputgacode['rmin']
    a_meters = rmin_exp[-1]
    rmin_exp = rmin_exp/a_meters
    rmin = CGYRO['RMIN']
    expro_rhos = inputgacode['rhos']

    for i in range(TGLF['NS']):
        if i == 0:
            expro_ne = inputgacode['ne']
            expro_dlnndr = bound_deriv(-np.log(expro_ne),expro_rmin,expro_n_exp)
            expro_sdlnndr = bound_deriv(expro_ne*expro_dlnndr,expro_rmin,expro_n_exp)
            expro_sdlnndr = expro_sdlnndr/expro_ne*expro_rhos
            expro_te = inputgacode['Te']
            expro_dlntdr = bound_deriv(-np.log(expro_te),expro_rmin,expro_n_exp)
            expro_sdlntdr = bound_deriv(expro_te*expro_dlntdr,expro_rmin,expro_n_exp)
            expro_sdlntdr = expro_sdlntdr/expro_te*expro_rhos
            sdlnndr_exp = expro_sdlnndr*a_meters
            sdlntdr_exp = expro_sdlntdr*a_meters

            dlnndr_exp = expro_dlntdr*a_meters
            dlnndr_loc = cub_spline1(rmin_exp,dlnndr_exp,expro_n_exp,rmin)
            sdlnndr_loc = cub_spline1(rmin_exp,sdlnndr_exp,expro_n_exp,rmin)
            sdlntdr_loc = cub_spline1(rmin_exp,sdlntdr_exp,expro_n_exp,rmin)
            CGYRO['Z_'+str(TGLF['NS'])] = TGLF['ZS_'+str(i+1)]
            CGYRO['MASS_'+str(TGLF['NS'])] = TGLF['MASS_'+str(i+1)]
            CGYRO['DENS_'+str(TGLF['NS'])] = TGLF['AS_'+str(i+1)]
            CGYRO['TEMP_'+str(TGLF['NS'])] = TGLF['TAUS_'+str(i+1)]
            CGYRO['DLNNDR_'+str(TGLF['NS'])] = TGLF['RLNS_'+str(i+1)]
            CGYRO['DLNTDR_'+str(TGLF['NS'])] = TGLF['RLTS_'+str(i+1)]
            CGYRO['SDLNNDR_'+str(TGLF['NS'])] = sdlnndr_loc
            CGYRO['SDLNTDR_'+str(TGLF['NS'])] = sdlntdr_loc

        else:
            expro_ni = inputgacode['ni_'+str(i)]
            expro_dlnndr = bound_deriv(-np.log(expro_ni),expro_rmin,expro_n_exp)
            expro_sdlnndr = bound_deriv(expro_ni*expro_dlnndr,expro_rmin,expro_n_exp)
            expro_sdlnndr = expro_sdlnndr/expro_ni*expro_rhos
            expro_ti = inputgacode['Ti_'+str(i)]
            expro_dlntdr = bound_deriv(-np.log(expro_ti),expro_rmin,expro_n_exp)
            expro_sdlntdr = bound_deriv(expro_ti*expro_dlntdr,expro_rmin,expro_n_exp)
            expro_sdlntdr = expro_sdlntdr/expro_ti*expro_rhos
            sdlnndr_exp = expro_sdlnndr*a_meters
            sdlntdr_exp = expro_sdlntdr*a_meters
            sdlnndr_loc = cub_spline1(rmin_exp,sdlnndr_exp,expro_n_exp,rmin)
            sdlntdr_loc = cub_spline1(rmin_exp,sdlntdr_exp,expro_n_exp,rmin)

            CGYRO['Z_'+str(i)] = TGLF['ZS_'+str(i+1)]
            CGYRO['MASS_'+str(i)] = TGLF['MASS_'+str(i+1)]
            CGYRO['DENS_'+str(i)] = TGLF['AS_'+str(i+1)]
            CGYRO['TEMP_'+str(i)] = TGLF['TAUS_'+str(i+1)]
            CGYRO['DLNNDR_'+str(i)] = TGLF['RLNS_'+str(i+1)]
            CGYRO['DLNTDR_'+str(i)] = TGLF['RLTS_'+str(i+1)]
            CGYRO['SDLNNDR_'+str(i)] = sdlnndr_loc
            CGYRO['SDLNTDR_'+str(i)] = sdlntdr_loc


    # expro_zmag = inputgacode['zmag']
    # expro_dzmag = bound_deriv(expro_zmag,expro_rmin,expro_n_exp)
    # dzmag_loc = cub_spline1(rmin_exp,expro_dzmag,expro_n_exp,rmin)
    # CGYRO['DZMAG'] = dzmag_loc

    expro_q = inputgacode['q']
    temp = bound_deriv(np.log(abs(expro_q)),expro_rmin,expro_n_exp)
    expro_s = expro_rmin*temp
    s_loc = cub_spline1(rmin_exp,expro_s,expro_n_exp,rmin)
    CGYRO['S'] = s_loc

    for i in range(0,7):
        if i>=3:
            expro_shape_sin = inputgacode['shape_sin'+str(i)]
            shape_sin_loc = cub_spline1(rmin_exp,expro_shape_sin,expro_n_exp,rmin)
            CGYRO['SHAPE_SIN'+str(i)] = shape_sin_loc
            temp = bound_deriv(expro_shape_sin,expro_rmin,expro_n_exp)
            expro_shape_ssin = expro_rmin*temp
            shape_s_sin_loc = cub_spline1(rmin_exp,expro_shape_ssin,expro_n_exp,rmin)
            CGYRO['SHAPE_S_SIN'+str(i)] = shape_s_sin_loc

        expro_shape_cos = inputgacode['shape_cos'+str(i)]
        shape_cos_loc = cub_spline1(rmin_exp,expro_shape_cos,expro_n_exp,rmin)
        CGYRO['SHAPE_COS'+str(i)] = shape_cos_loc
        temp = bound_deriv(expro_shape_cos,expro_rmin,expro_n_exp)
        expro_shape_scos = expro_rmin*temp
        shape_s_cos_loc = cub_spline1(rmin_exp,expro_shape_scos,expro_n_exp,rmin)
        CGYRO['SHAPE_S_COS'+str(i)] = shape_s_cos_loc


    expro_w0 = inputgacode['omega0']
    expro_rmaj = inputgacode['rmaj']
    expro_te = inputgacode['Te']
    expro_mass_deuterium = 3.34358e-24
    mp = expro_mass_deuterium/2
    c  = 2.9979e10
    e  = 4.8032e-10
    expro_w0p = bound_deriv(expro_w0,expro_rmin,expro_n_exp)
    gamma_e_exp = -expro_w0p*(a_meters*rmin_exp)/expro_q
    gamma_p_exp = -expro_w0p*expro_rmaj
    mach_exp = expro_w0*expro_rmaj
    gamma_e_loc = cub_spline1(rmin_exp,gamma_e_exp,expro_n_exp,rmin)
    gamma_p_loc = cub_spline1(rmin_exp,gamma_p_exp,expro_n_exp,rmin)
    mach_loc = cub_spline1(rmin_exp,mach_exp,expro_n_exp,rmin)
    expro_cs = sqrt(1.622*10**(-12)*(1000*expro_te)/(2.0*mp))


    cs_loc = cub_spline1(rmin_exp,expro_cs,expro_n_exp,rmin)
    gamma_e = gamma_e_loc*a_meters/cs_loc
    gamma_p = gamma_p_loc*a_meters/cs_loc
    mach = mach_loc*a_meters/cs_loc
    CGYRO['GAMMA_E'] = gamma_e
    CGYRO['GAMMA_P'] = gamma_p
    CGYRO['MACH'] = mach
    CGYRO['ROTATION_MODEL'] = 2
    CGYRO['COLLISION_MODEL'] = 4
    CGYRO['N_FIELD'] = 2



def convert_cgyro_to_tglf(CGYRO,TGLF):
    TGLF.clear()
    TGLF['RMIN_LOC'] = CGYRO['RMIN']
    TGLF['RMAJ_LOC'] = CGYRO['RMAJ']
    TGLF['DRMAJDX_LOC'] = CGYRO['SHIFT']
    TGLF['ZMAJ_LOC'] = CGYRO['ZMAG']
    TGLF['DZMAJDX_LOC'] = CGYRO['DZMAG']
    TGLF['Q_LOC'] = abs(CGYRO['Q'])
    TGLF['Q_PRIME_LOC'] = (CGYRO['Q']/CGYRO['RMIN'])**2*CGYRO['S']
    TGLF['KAPPA_LOC'] = CGYRO['KAPPA']
    TGLF['S_KAPPA_LOC'] = CGYRO['S_KAPPA']
    TGLF['DELTA_LOC'] = CGYRO['DELTA']
    TGLF['S_DELTA_LOC'] = CGYRO['S_DELTA']
    TGLF['ZETA_LOC'] = CGYRO['ZETA']
    TGLF['S_ZETA_LOC'] = CGYRO['S_ZETA']
    TGLF['SIGN_BT'] = CGYRO['BTCCW']
    TGLF['SIGN_IT'] = CGYRO['IPCCW']
    TGLF['XNUE'] = CGYRO['NU_EE']
    TGLF['DEBYE'] = CGYRO['LAMBDA_STAR']
    TGLF['BETAE'] = CGYRO['BETAE_UNIT']

    if TGLF['Q_LOC']<0:
        TGLF['VEXB_SHEAR'] = TGLF['SIGN_IT']*CGYRO['GAMMA_E']
    else:
        TGLF['VEXB_SHEAR'] = -TGLF['SIGN_IT']*CGYRO['GAMMA_E']
    TGLF['NS'] = CGYRO['N_SPECIES']
    Zeff_Denominator = 0
    Zeff_Numerator = 0
    beta_star_loc = 0
    for i in range(TGLF['NS']):
        if i == 0:
            TGLF['ZS_'+str(i+1)] = CGYRO['Z_'+str(TGLF['NS'])]
            TGLF['MASS_'+str(i+1)] = CGYRO['MASS_'+str(TGLF['NS'])]
            TGLF['AS_'+str(i+1)] = CGYRO['DENS_'+str(TGLF['NS'])]
            TGLF['TAUS_'+str(i+1)] = CGYRO['TEMP_'+str(TGLF['NS'])]
            TGLF['RLNS_'+str(i+1)] = CGYRO['DLNNDR_'+str(TGLF['NS'])]
            TGLF['RLTS_'+str(i+1)] = CGYRO['DLNTDR_'+str(TGLF['NS'])]
            TGLF['VPAR_SHEAR_'+str(i+1)] = -TGLF['SIGN_IT']*CGYRO['GAMMA_P']
            TGLF['VPAR_'+str(i+1)] = -TGLF['SIGN_IT']*CGYRO['MACH']
        else:
            TGLF['ZS_'+str(i+1)] = CGYRO['Z_'+str(i)]
            TGLF['MASS_'+str(i+1)] = CGYRO['MASS_'+str(i)]
            TGLF['AS_'+str(i+1)] = CGYRO['DENS_'+str(i)]
            TGLF['TAUS_'+str(i+1)] = CGYRO['TEMP_'+str(i)]
            TGLF['RLNS_'+str(i+1)] = CGYRO['DLNNDR_'+str(i)]
            TGLF['RLTS_'+str(i+1)] = CGYRO['DLNTDR_'+str(i)]
            TGLF['VPAR_SHEAR_'+str(i+1)] = -TGLF['SIGN_IT']*CGYRO['GAMMA_P']
            TGLF['VPAR_'+str(i+1)] = -TGLF['SIGN_IT']*CGYRO['MACH']
            Zeff_Denominator = Zeff_Denominator + TGLF['ZS_'+str(i+1)]*TGLF['AS_'+str(i+1)]
            Zeff_Numerator = Zeff_Numerator + TGLF['ZS_'+str(i+1)]**2*TGLF['AS_'+str(i+1)]
        beta_star_loc = beta_star_loc + TGLF['AS_'+str(i+1)]*TGLF['TAUS_'+str(i+1)]*(TGLF['RLNS_'+str(i+1)]+TGLF['RLTS_'+str(i+1)])
    beta_star_loc = beta_star_loc * TGLF['BETAE']
    Zeff = Zeff_Numerator/Zeff_Denominator
    TGLF['ZEFF'] = Zeff
    P_PRIME_LOC=(abs(TGLF['Q_LOC'])/TGLF['RMIN_LOC'])*(-beta_star_loc/(8*np.pi))
    TGLF['P_PRIME_LOC'] = P_PRIME_LOC

    if CGYRO['N_FIELD'] == 1:
        TGLF['USE_BPER'] = False
        TGLF['USE_BPAR'] = False
    elif CGYRO['N_FIELD'] == 2:
        TGLF['USE_BPER'] = True
        TGLF['USE_BPAR'] = False
    elif CGYRO['N_FIELD'] == 3:
        TGLF['USE_BPER'] = True
        TGLF['USE_BPAR'] = True

    TGLF['UNITS'] = 'CGYRO'
    TGLF['USE_TRANSPORT_MODEL'] = True
    TGLF['GEOMETRY_FLAG'] = 1
    TGLF['USE_MHD_RULE'] = False
    TGLF['USE_BISECTION'] = True
    TGLF['USE_INBOARD_DETRAPPED'] = False
    TGLF['USE_AVE_ION_GRID'] = True

    TGLF['SAT_RULE'] = 2
    TGLF['KYGRID_MODEL'] = 4
    TGLF['XNU_MODEL'] = 3
    TGLF['VPAR_MODEL'] = 0
    TGLF['VPAR_SHEAR_MODEL'] = 1
    TGLF['KY'] = CGYRO['KY']
    TGLF['IFLUX'] = True
    TGLF['IBRANCH'] = -1
    TGLF['NMODES'] = 6
    TGLF['NBASIS_MAX'] = 6
    TGLF['NBASIS_MIN'] = 2
    TGLF['NXGRID'] = 16
    TGLF['NKY'] = 19
    TGLF['ADIABATIC_ELEC'] = False
    TGLF['ALPHA_MACH'] = 0
    TGLF['ALPHA_E'] = 1
    TGLF['ALPHA_P'] = 1
    TGLF['ALPHA_QUENCH'] = 0
    TGLF['ALPHA_ZF'] = 1
    TGLF['XNU_FACTOR'] = 1
    TGLF['DEBYE_FACTOR'] = 1
    TGLF['ETG_FACTOR'] = 1.25
    TGLF['RLNP_CUTOFF'] = 18
    TGLF['WRITE_WAVEFUNCTION_FLAG'] = 0
    TGLF['WIDTH'] = 1.65
    TGLF['WIDTH_MIN'] = 0.3
    TGLF['FIND_WIDTH'] = True
    TGLF['NWIDTH'] = 21
    TGLF['DAMP_PSI'] = 0
    TGLF['DAMP_SIG'] = 0
    TGLF['PARK'] = 1
    TGLF['GHAT'] = 1
    TGLF['GCHAT'] =1
    TGLF['WD_ZERO'] = 0.1
    TGLF['LINSKER_FACTOR'] = 0
    TGLF['GRADB_FACTOR'] = 0
    TGLF['FILTER'] = 2
    TGLF['THETA_TRAPPED'] = 0.7
    TGLF['NN_MAX_ERROR'] = -1


def _build_convert_outtglf_to_cgyro(CGYRO,TGLF,inputgacode):
    CGYRO.clear()
    CGYRO['N_ENERGY'] = 8
    CGYRO['N_XI'] = 16
    CGYRO['N_THETA'] = 24
    CGYRO['N_RADIAL'] = 16
    CGYRO['N_TOROIDAL'] = 1
    CGYRO['NONLINEAR_FLAG'] = 0
    CGYRO['BOX_SIZE'] = 1
    CGYRO['KY'] = 0.3
    CGYRO['DELTA_T'] = 0.01
    CGYRO['MAX_TIME'] = 100
    CGYRO['PRINT_STEP'] = 100

    CGYRO['RMIN'] = TGLF['RMIN_LOC']
    CGYRO['RMAJ'] = TGLF['RMAJ_LOC']
    CGYRO['SHIFT'] = TGLF['DRMAJDX_LOC']
    CGYRO['ZMAG'] = TGLF['ZMAJ_LOC']
    CGYRO['DZMAG'] = TGLF['DZMAJDX_LOC']
    CGYRO['Q'] = abs(TGLF['Q_LOC'])
    CGYRO['S'] =  TGLF['SHAT_SA']
    CGYRO['KAPPA'] = TGLF['KAPPA_LOC']
    CGYRO['S_KAPPA'] = TGLF['S_KAPPA_LOC']
    CGYRO['DELTA'] = TGLF['DELTA_LOC']
    CGYRO['S_DELTA'] = TGLF['S_DELTA_LOC']
    CGYRO['ZETA'] = TGLF['ZETA_LOC']
    CGYRO['S_ZETA'] = TGLF['S_ZETA_LOC']
    CGYRO['BTCCW'] = TGLF['SIGN_BT']
    CGYRO['IPCCW'] = TGLF['SIGN_IT']
    CGYRO['NU_EE'] = TGLF['XNUE']
    CGYRO['LAMBDA_STAR'] = TGLF['DEBYE']
    CGYRO['BETAE_UNIT'] = TGLF['BETAE']
    CGYRO['N_SPECIES'] = TGLF['NS']

    for i in range(0,7):
        if i>=3:
            CGYRO['SHAPE_SIN'+str(i)] = TGLF['SHAPE_SIN'+str(i)]
            CGYRO['SHAPE_S_SIN'+str(i)] = TGLF['SHAPE_S_SIN'+str(i)]
        CGYRO['SHAPE_COS'+str(i)] = TGLF['SHAPE_COS'+str(i)]
        CGYRO['SHAPE_S_COS'+str(i)] = TGLF['SHAPE_S_COS'+str(i)]

    expro_n_exp = inputgacode['N_EXP']
    expro_rmin = inputgacode['rmin']
    rmin_exp = inputgacode['rmin']
    a_meters = rmin_exp[-1]
    rmin_exp = rmin_exp/a_meters
    rmin = CGYRO['RMIN']
    expro_q = inputgacode['q']
    temp = bound_deriv(np.log(abs(expro_q)),expro_rmin,expro_n_exp)
    expro_s = expro_rmin*temp
    s_loc = cub_spline1(rmin_exp,expro_s,expro_n_exp,rmin)
    CGYRO['S'] = s_loc

    for i in range(0,7):
        if i>=3:
            expro_shape_sin = inputgacode['shape_sin'+str(i)]
            shape_sin_loc = cub_spline1(rmin_exp,expro_shape_sin,expro_n_exp,rmin)
            CGYRO['SHAPE_SIN'+str(i)] = shape_sin_loc
            temp = bound_deriv(expro_shape_sin,expro_rmin,expro_n_exp)
            expro_shape_ssin = expro_rmin*temp
            shape_s_sin_loc = cub_spline1(rmin_exp,expro_shape_ssin,expro_n_exp,rmin)
            CGYRO['SHAPE_S_SIN'+str(i)] = shape_s_sin_loc

        expro_shape_cos = inputgacode['shape_cos'+str(i)]
        shape_cos_loc = cub_spline1(rmin_exp,expro_shape_cos,expro_n_exp,rmin)
        CGYRO['SHAPE_COS'+str(i)] = shape_cos_loc
        temp = bound_deriv(expro_shape_cos,expro_rmin,expro_n_exp)
        expro_shape_scos = expro_rmin*temp
        shape_s_cos_loc = cub_spline1(rmin_exp,expro_shape_scos,expro_n_exp,rmin)
        CGYRO['SHAPE_S_COS'+str(i)] = shape_s_cos_loc

    CGYRO['ROTATION_MODEL'] = 2
    if TGLF['Q_LOC']<0:
        CGYRO['GAMMA_E'] = TGLF['VEXB_SHEAR']/TGLF['SIGN_IT']
    else:
        CGYRO['GAMMA_E'] = TGLF['VEXB_SHEAR']/-TGLF['SIGN_IT']
    CGYRO['GAMMA_P'] = TGLF['VPAR_SHEAR_1']/-TGLF['SIGN_IT']
    CGYRO['MACH'] = TGLF['VPAR_1']/-TGLF['SIGN_IT']
    CGYRO['COLLISION_MODEL'] = 4

    if TGLF['USE_BPER'] == False:
        CGYRO['N_FIELD'] = 1
    elif TGLF['USE_BPAR'] == False:
        CGYRO['N_FIELD'] = 2
    else:
        CGYRO['N_FIELD'] = 3


    expro_rhos = inputgacode['rhos']

    for i in range(TGLF['NS']):
        if i == 0:
            expro_ne = inputgacode['ne']
            expro_dlnndr = bound_deriv(-np.log(expro_ne),expro_rmin,expro_n_exp)
            expro_sdlnndr = bound_deriv(expro_ne*expro_dlnndr,expro_rmin,expro_n_exp)
            expro_sdlnndr = expro_sdlnndr/expro_ne*expro_rhos
            expro_te = inputgacode['Te']
            expro_dlntdr = bound_deriv(-np.log(expro_te),expro_rmin,expro_n_exp)
            expro_sdlntdr = bound_deriv(expro_te*expro_dlntdr,expro_rmin,expro_n_exp)
            expro_sdlntdr = expro_sdlntdr/expro_te*expro_rhos
            sdlnndr_exp = expro_sdlnndr*a_meters
            sdlntdr_exp = expro_sdlntdr*a_meters

            dlnndr_exp = expro_dlntdr*a_meters
            dlnndr_loc = cub_spline1(rmin_exp,dlnndr_exp,expro_n_exp,rmin)
            sdlnndr_loc = cub_spline1(rmin_exp,sdlnndr_exp,expro_n_exp,rmin)
            sdlntdr_loc = cub_spline1(rmin_exp,sdlntdr_exp,expro_n_exp,rmin)
            CGYRO['Z_'+str(TGLF['NS'])] = TGLF['ZS_'+str(i+1)]
            CGYRO['MASS_'+str(TGLF['NS'])] = TGLF['MASS_'+str(i+1)]
            CGYRO['DENS_'+str(TGLF['NS'])] = TGLF['AS_'+str(i+1)]
            CGYRO['TEMP_'+str(TGLF['NS'])] = TGLF['TAUS_'+str(i+1)]
            CGYRO['DLNNDR_'+str(TGLF['NS'])] = TGLF['RLNS_'+str(i+1)]
            CGYRO['DLNTDR_'+str(TGLF['NS'])] = TGLF['RLTS_'+str(i+1)]
            CGYRO['SDLNNDR_'+str(TGLF['NS'])] = sdlnndr_loc
            CGYRO['SDLNTDR_'+str(TGLF['NS'])] = sdlntdr_loc

        else:
            expro_ni = inputgacode['ni_'+str(i)]
            expro_dlnndr = bound_deriv(-np.log(expro_ni),expro_rmin,expro_n_exp)
            expro_sdlnndr = bound_deriv(expro_ni*expro_dlnndr,expro_rmin,expro_n_exp)
            expro_sdlnndr = expro_sdlnndr/expro_ni*expro_rhos
            expro_ti = inputgacode['Ti_'+str(i)]
            expro_dlntdr = bound_deriv(-np.log(expro_ti),expro_rmin,expro_n_exp)
            expro_sdlntdr = bound_deriv(expro_ti*expro_dlntdr,expro_rmin,expro_n_exp)
            expro_sdlntdr = expro_sdlntdr/expro_ti*expro_rhos
            sdlnndr_exp = expro_sdlnndr*a_meters
            sdlntdr_exp = expro_sdlntdr*a_meters
            sdlnndr_loc = cub_spline1(rmin_exp,sdlnndr_exp,expro_n_exp,rmin)
            sdlntdr_loc = cub_spline1(rmin_exp,sdlntdr_exp,expro_n_exp,rmin)

            CGYRO['Z_'+str(i)] = TGLF['ZS_'+str(i+1)]
            CGYRO['MASS_'+str(i)] = TGLF['MASS_'+str(i+1)]
            CGYRO['DENS_'+str(i)] = TGLF['AS_'+str(i+1)]
            CGYRO['TEMP_'+str(i)] = TGLF['TAUS_'+str(i+1)]
            CGYRO['DLNNDR_'+str(i)] = TGLF['RLNS_'+str(i+1)]
            CGYRO['DLNTDR_'+str(i)] = TGLF['RLTS_'+str(i+1)]
            CGYRO['SDLNNDR_'+str(i)] = sdlnndr_loc
            CGYRO['SDLNTDR_'+str(i)] = sdlntdr_loc







def _commit_cgyro_conversion(target, source, profiles, builder):
    """Build and validate first, so invalid inputs cannot clear the old target."""
    ns = int(source['NS'])
    if ns < 2 or ns != source['NS']:
        raise ValueError('NS must include at least one ion and one electron')
    pending = {}
    builder(pending, source, profiles)
    for species in range(1, ns + 1):
        for field in ('Z', 'MASS', 'DENS', 'TEMP', 'DLNNDR', 'DLNTDR', 'SDLNNDR', 'SDLNTDR'):
            key = '{}_{}'.format(field, species)
            if key not in pending or not np.isfinite(pending[key]):
                raise ValueError('Missing or non-finite converted parameter: ' + key)
    for key, value in pending.items():
        if isinstance(value, (float, np.floating)) and not np.isfinite(value):
            raise ValueError('Non-finite converted parameter: ' + key)
    target.clear()
    target.update(pending)


def convert_tglf_to_cgyro(CGYRO, TGLF, inputgacode):
    _commit_cgyro_conversion(CGYRO, TGLF, inputgacode, _build_convert_tglf_to_cgyro)


def convert_outtglf_to_cgyro(CGYRO, TGLF, inputgacode):
    _commit_cgyro_conversion(CGYRO, TGLF, inputgacode, _build_convert_outtglf_to_cgyro)


def bound_deriv(f,r,n):
    df = np.zeros(n)
    for i in range(n):
        if i == 0:
            ra = r[0]
            r1 = r[0]
            r2 = r[1]
            r3 = r[2]
            f1 = f[0]
            f2 = f[1]
            f3 = f[2]
        elif i == n-1:
            ra = r[-1]
            r1 = r[-3]
            r2 = r[-2]
            r3 = r[-1]
            f1 = f[-3]
            f2 = f[-2]
            f3 = f[-1]
        else:
            ra = r[i]
            r1 = r[i-1]
            r2 = r[i]
            r3 = r[i+1]
            f1 = f[i-1]
            f2 = f[i]
            f3 = f[i+1]
        df[i] = ((ra-r1)+(ra-r2))/(r3-r1)/(r3-r2)*f3 + ((ra-r1)+(ra-r3))/(r2-r1)/(r2-r3)*f2 + ((ra-r2)+(ra-r3))/(r1-r2)/(r1-r3)*f1
    return df


def cub_spline1(x,y,n,xi):
   h = np.zeros(n-1)
   zl = np.zeros(n-1)
   zu = np.zeros(n-1)
   z = np.zeros(n)
   c = np.zeros(n)
   b = np.zeros(n-1)
   d = np.zeros(n-1)
   if xi > x[-1]:
      print ('ERROR: (cub_spline1) Data above upper bound')
      print ('xi(ni) > x(n)',xi,x[-1])
   elif xi < x[0]:
      print ('ERROR: (cub_spline1) Data below lower bound')
      print ('xi(1) < x(1)',xi,x[0])
   for i in range(n-1):
      h[i]  = x[i+1]-x[i]
      zl[i] = h[i]
      zu[i] = h[i]
   zl[-1] = 0
   zu[0]  = 0
   z[0] = 1
   c[0] = 0
   for i in range(1,n-1):
      z[i] = 2*(h[i-1]+h[i])
      c[i] = 3*((y[i+1]-y[i])/h[i]-(y[i]-y[i-1])/h[i-1])
   z[-1] = 1
   c[-1] = 0
   zl,z,zu,zu2,ipiv,info = scipy.linalg.lapack.dgttrf(zl,z,zu)
   c,info = scipy.linalg.lapack.dgttrs(zl,z,zu,zu2,ipiv,c)
   c[-1] = 0
   for i in range(n-1):
      b[i] = (y[i+1]-y[i])/h[i]-h[i]*(2*c[i]+c[i+1])/3
      d[i] = (c[i+1]-c[i])/(3*h[i])
   i  = 0
   ii = 1
   while ii <= 1:
      if xi <= x[i+1]:
         yi = y[i]+(xi-x[i])*(b[i]+(xi-x[i])*(c[i]+(xi-x[i])*d[i]))
         ii = ii+1
      else:
         i = i+1
   return yi

convert_to_tglf = root['SETTINGS']['PHYSICS']['Transfer to tglf']
convert_to_cgyro = root['SETTINGS']['PHYSICS']['Transfer to cgyro']
tglf_is_out_tglf_localdump = root['SETTINGS']['PHYSICS']['tglf_is_out_tglf_localdump']


if convert_to_tglf and convert_to_cgyro:
    raise ValueError('Select only one conversion direction')

if convert_to_tglf:
    convert_cgyro_to_tglf(CGYRO,TGLF)
elif convert_to_cgyro:
    if tglf_is_out_tglf_localdump:
        convert_outtglf_to_cgyro(CGYRO,TGLF,inputgacode)
    else:
        convert_tglf_to_cgyro(CGYRO,TGLF,inputgacode)
