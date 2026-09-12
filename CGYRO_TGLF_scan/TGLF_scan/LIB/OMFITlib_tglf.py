# -*-Python-*-
# Created by sciortinof at 18 Jul 2019  11:27

from scipy.constants import e, m_p
import numpy


def TGLF_var_group_scan(scan_vars, input_tglf=None):
    """
    Define groups of TGLF variables that should scanned together.
    The 'scan_vars' input is assumed to be a list of TGLF variables.

    Returns an ordered dictionary of {scan_var : [list of corresponding variables]}
    """

    if input_tglf is None:
        input_tglf = root['TGLF']['FILES'].get('input.tglf')
    if input_tglf is None:
        raise ValueError('Pass the actual local TGLF input to define species groups')
    ns = int(input_tglf['NS'])
    species = list(range(1, ns + 1))
    ions = [i for i in species if input_tglf['ZS_%d' % i] != -1]

    var_group_dict = OrderedDict()

    for variable in scan_vars:
        if variable == 'aLTe':
            var_group_dict[variable] = ['RLTS_1']
        elif variable == 'aLn':
            var_group_dict[variable] = [
                'RLNS_%d' % i for i in species
            ]  # can also change trace impurity aLnz -- it won't matter
        elif variable == 'aLTi':
            var_group_dict[variable] = ['RLTS_%d' % i for i in ions]  # don't include aLTe
        elif variable == 'XNUE':
            var_group_dict[variable] = ['XNUE']
        elif variable == 'Zeff':
            var_group_dict[variable] = ['ZEFF']
        elif variable == 'vtor':
            var_group_dict[variable] = ['VPAR_%d' % i for i in species]
        elif variable == 'vtor_shear':
            var_group_dict[variable] = ['VPAR_SHEAR_%d' % i for i in species]
        elif variable == 'taus':
            var_group_dict[variable] = ['TAUS_%d' % i for i in species]
        elif variable == 'alpha_p':
            var_group_dict[variable] = ['ALPHA_P']  # multiplies parallel vel shear for all species
        else:
            var_group_dict[variable] = [variable]

    return var_group_dict


def compute_STRAHL_correction(rho_list, Z, A, PROFILES_GEN):
    """
    Function to compute the quantities required to compare modelled impurity transport
    coefficients to the results of STRAHL inferences of D,V radial profiles.

    :param rho_list: list of values of rho (sqrt psi norm) for which the correction factors should be computed

    :param Z : Z (charge) of impurity of interest

    :param A : atomic mass units of impurity of interest (e.g. 12 for C)

    :param PROFILES_GEN : location in the OMFIT tree of the PROFILES_GEN module from which input.gacode will be obtained

    :returns: drV_drm, n_ratio, V_conv --> see Angioni NF 2014 for details on the meaning of these factors
    """
    input_gacode = PROFILES_GEN['OUTPUTS']['input.gacode']

    vol = PROFILES_GEN['OUTPUTS']['input.gacode']['vol']
    r_V = np.sqrt(vol / (2 * pi**2 * input_gacode['rmaj']))
    drV_drm = np.interp(rho_list, input_gacode['rho'], np.gradient(r_V, input_gacode['rmin']))
    rmin = input_gacode['rmin']
    a = rmin[-1]

    # calculate asymmetry correction factors
    ionM = 2.0  # deuterium atomic number (prevent integer division)
    R, z = input_gacode.rz_geometry(200)  # m
    Rlfs = R[0]
    omg = input_gacode['omega0']
    Ti = input_gacode['Ti_1'] * 1e3
    Te = input_gacode['Te'] * 1e3
    zeff = input_gacode['z_eff']

    # approximation for poloidal asymmetries
    lam = m_p * A * omg**2 / (2 * Ti * e) * (1 - Z * ionM / A * zeff * Te / (Ti + zeff * Te))

    # impurity density profile n_z/n_z_lfs
    prof = np.exp(lam * (R**2 - Rlfs[None] ** 2))

    # do flux surface averaging
    dV = 2 * np.pi * R * np.linalg.det(np.array((np.gradient(z), np.gradient(R))).T).T

    # n_ratio and V_conv are outputs from NEO which are not passed to TGYRO output
    n_ratio = safe_divide(np.sum(dV, 0), np.sum(prof * dV, 0), 1)
    V_conv = -np.gradient(n_ratio, input_gacode['rmin'] / a) / n_ratio
    if rmin[0] == 0:
        V_conv[0] = 0  # correct on-axis value

    n_ratio = np.interp(rho_list, input_gacode['rho'], n_ratio)
    V_conv = np.interp(rho_list, input_gacode['rho'], V_conv)

    return drV_drm, n_ratio, V_conv
