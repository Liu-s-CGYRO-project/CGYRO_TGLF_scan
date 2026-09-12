# -*-Python-*-
# Created by sciortinof at 12 Aug 2019  19:01

"""
This script allows computation of transport coefficients after the TGLF runs done in resp_matrix.py.
Corrections for radial coordinate definitions (as in STRAHL) and poloidal asymmetries can be easily
dealt with by the arguments.
"""
from copy import deepcopy
import OMFITlib_tglf

defaultVars(
    runs_label=root['SETTINGS']['PHYSICS']['runs_label'],
    thermodiffusion=root['SETTINGS']['PHYSICS']['compute_thermodiffusion'],
    rotodiffusion=root['SETTINGS']['PHYSICS']['compute_rotodiffusion'],
    plot_results=True,
)

run_root = root['TGLF_SCAN_DB'][runs_label]

# Fetch results
a = root['tgyro_output']['a'] * 1e-2
Rmaj = root['tgyro_output']['rmaj/a'][0, 0] * a  # use Rmaj on given on axis

# allocate space for matrix elements at each radius
num_runs_per_rad = 2
if root['SETTINGS']['PHYSICS']['compute_thermodiffusion']:
    num_runs_per_rad += 1
if root['SETTINGS']['PHYSICS']['compute_rotodiffusion']:
    num_runs_per_rad += 1

rhoList = run_root['rhoList']


# ***********************************
def get_transp_coeffs(run_root, apply_corrections=False):
    """Get particle and heat transport coefficients, given the gradients and fluxes from TGLF runs in the 'run_root' dictionary.
    The argument 'apply_corrections' allows the application of
    """
    out = {}

    # Collect results from TGLF runs
    gamma_over_n = run_root['gamma_z'] * run_root['gamma_GB'] / run_root['nz']
    Q_over_n = run_root['Q_z'] * run_root['Q_GB'] / run_root['nz']
    gradn_over_n = run_root['RLnz'] / Rmaj
    if thermodiffusion:
        gradT_over_T = run_root['RLTz'] / Rmaj
    if rotodiffusion:
        grad_vz = deepcopy(run_root['grad_vz'])
        vthz = deepcopy(run_root['vthz'])
        cs = deepcopy(run_root['cs'])

    out['chi_i'] = deepcopy(run_root['chi_i'])
    out['chi_e'] = deepcopy(run_root['chi_e'])
    out['chi_eff'] = deepcopy(run_root['chi_eff'])

    if apply_corrections:
        # Get STRAHL and pol asymmetry corrections (FSA)
        drV_drm, n_ratio, V_conv = OMFITlib_tglf.compute_STRAHL_correction(
            rhoList, run_root['PHYSICS_SETTINGS']['impZ'], run_root['PHYSICS_SETTINGS']['impM'], root['TGYRO']['PROFILES_GEN']
        )

        # Apply corrections to Gamma and density gradient -- allows one to consider corrections only once
        gamma_over_n *= n_ratio
        # Q_over_n *= n_ratio   # heat does not develop pol asymmetries!
        gradn_over_n -= V_conv / a

    # form gradients matrix
    if (not thermodiffusion) and (not rotodiffusion):
        M = np.asarray([gradn_over_n, np.ones((num_runs_per_rad, len(rhoList)))])
    elif thermodiffusion and (not rotodiffusion):
        M = np.asarray([gradn_over_n, gradT_over_T, np.ones((num_runs_per_rad, len(rhoList)))])
    elif (not thermodiffusion) and rotodiffusion:
        M = np.asarray([gradn_over_n, grad_vz / Rmaj, np.ones((num_runs_per_rad, len(rhoList)))])
    elif thermodiffusion and rotodiffusion:
        M = np.asarray([gradn_over_n, gradT_over_T, grad_vz / Rmaj, np.ones((num_runs_per_rad, len(rhoList)))])

    # Solve matrix equation for transport coefficients (heat coeffs not currently processed)
    particle_coeffs = np.asarray([np.linalg.solve(M[:, :, i].T, gamma_over_n[:, i]) for i in range(len(rhoList))])
    heat_coeffs = np.asarray([np.linalg.solve(M[:, :, i].T, Q_over_n[:, i]) for i in range(len(rhoList))])

    if (not thermodiffusion) and (not rotodiffusion):
        out['D'], out['v'] = particle_coeffs.T
    elif thermodiffusion and (not rotodiffusion):
        out['D'], out['vT'], out['v'] = particle_coeffs.T
    elif (not thermodiffusion) and rotodiffusion:
        out['D'], out['vR'], out['v'] = particle_coeffs.T
    elif thermodiffusion and rotodiffusion:
        out['D'], out['vT'], out['vR'], out['v'] = particle_coeffs.T

    # ===========
    out['v_D'] = out['v'] / out['D']
    out['vtot_D'] = deepcopy(out['v_D'])
    if thermodiffusion:
        out['vT_D'] = out['vT'] / out['D'] * np.max(gradT_over_T, axis=0)
        out['vtot_D'] += out['vT_D']
    if rotodiffusion:
        # Note use of cs/vthz normalization is to have the same rotodiffusion defn as Angioni NF 2014
        out['vR_D'] = out['vR'] / out['D'] * np.max(run_root['grad_vz'], axis=0)  # * Rmaj / a * cs / vthz,
        out['vtot_D'] += out['vR_D']

    if apply_corrections:
        # apply corrections to get STRAHL-like circular-equivalent geometry (in r_V coordinates)
        out['chi_i'] *= drV_drm
        out['chi_e'] *= drV_drm
        out['chi_eff'] *= drV_drm
        out['D'] *= drV_drm**2

        out['v_D'] /= drV_drm
        if thermodiffusion:
            out['vT_D'] /= drV_drm
        if rotodiffusion:
            out['vR_D'] /= drV_drm
        out['vtot_D'] /= drV_drm

    out['v'] = out['v_D'] * out['D']
    if thermodiffusion:
        out['vT'] = out['vT_D'] * out['D']
    if rotodiffusion:
        out['vR'] = out['vR_D'] * out['D']
    out['vtot'] = out['vtot_D'] * out['D']

    return out


# *******************************
# Get transport coefficients for LFS defn and for the STRAHL FSA defn
out_LFS = get_transp_coeffs(run_root, apply_corrections=False)
out_sFSA = get_transp_coeffs(run_root, apply_corrections=True)

# Store results in run_root
for q in out_LFS:
    run_root[q] = deepcopy(out_LFS[q])
    run_root[q + '_corr'] = deepcopy(out_sFSA[q])
# [run_root[q]=deepcopy(out_LFS[q]) for q in out_LFS]
# [run_root[q+'_corr']=deepcopy(out_sFSA[q]) for q in out_sFSA]


# ***************************************
# if requested, plot results

if plot_results:
    plot_STRAHL_corrections = root['SETTINGS']['PHYSICS']['plot_STRAHL_corrections']
    PNC = root['SETTINGS']['PHYSICS']['plot_normalized_coeffs']  # PNC: plot normalized coefficients
    out_plot = out_sFSA if plot_STRAHL_corrections else out_LFS

    fn = FigureNotebook(0, 'Particle Transport')
    fig, ax = fn.subplots(3, 1, label='Profiles', sharex=True)

    # Plot results that account for poloidal asymmetries due to centrifugal forces
    ax[0].plot(rhoList, out_plot['D'] / out_plot['chi_i'] if PNC else out_plot['D'], marker='o')
    ax[0].set_ylabel(r'$D/\chi_i$' if PNC else '$D$ $[m^2/s]$')
    if (not thermodiffusion) and (not rotodiffusion):
        # if only pure convection is plotted, set labels on the y axis
        ax[1].plot(rhoList, Rmaj * out_plot['v_D'] / out_plot['chi_i'] if PNC else out_plot['v'], marker='o')
        ax[1].set_ylabel(r'$R v_p/\chi_i$' if PNC else '$v_p$ $[m/s]$')
        ax[2].plot(rhoList, Rmaj * out_plot['v_D'] if PNC else out_plot['v_D'], marker='o')
        ax[2].set_ylabel('$R v_p/D$' if PNC else '$v_p/D$ $[1/m]$')
    else:
        # if other convection terms are plotted, use a legend
        ax[1].plot(
            rhoList,
            Rmaj * out_plot['v_D'] / out_plot['chi_i'] if PNC else out_plot['v'],
            marker='o',
            label=r'$R v_p/\chi_i$' if PNC else '$v_p$ $[m/s]$',
        )
        ax[2].plot(rhoList, Rmaj * out_plot['v_D'] if PNC else out_plot['v_D'], marker='o', label='$R v_p/D$' if PNC else '$v_p/D$ $[1/m]$')
        ax[1].set_ylabel(r'$R v/\chi_i$' if PNC else '$v$ $[m/s]$')
        ax[2].set_ylabel('$R v/D$' if PNC else '$v/D$ $[1/m]$')
    if thermodiffusion:
        ax[1].plot(
            rhoList,
            Rmaj * out_plot['vT'] / out_plot['chi_i'] if PNC else out_plot['vT'],
            marker='o',
            label=r'$R v_T/\chi_i$' if PNC else '$v_T$ $[m/s]$',
        )
        ax[2].plot(
            rhoList, Rmaj * out_plot['vT_D'] if PNC else out_plot['vT_D'], marker='o', label='$R v_T/D$' if PNC else '$v_T/D$ $[1/m]$'
        )
    if rotodiffusion:
        ax[1].plot(
            rhoList,
            Rmaj * out_plot['vR'] / out_plot['chi_i'] if PNC else out_plot['vR'],
            marker='o',
            label=r'$R v_R/\chi_i$' if PNC else '$v_R$ $[m/s]$',
        )
        ax[2].plot(
            rhoList, Rmaj * out_plot['vR_D'] if PNC else out_plot['vR_D'], marker='o', label='$R v_R/D$' if PNC else '$v_R/D$ $[1/m]$'
        )

    if thermodiffusion or rotodiffusion:
        # total (don't plot if only pure pinch was obtained)
        ax[1].plot(
            rhoList,
            Rmaj * out_plot['vtot'] / out_plot['chi_i'] if PNC else out_plot['vtot'],
            marker='o',
            label=r'$R v_{tot}/\chi_i$' if PNC else '$v_{tot}$ $[m/s]$',
        )
        ax[2].plot(
            rhoList,
            Rmaj * out_plot['vtot_D'] if PNC else out_plot['vtot_D'],
            marker='o',
            label='$R v_{tot}/D$' if PNC else '$v_{tot}/D$ $[1/m]$',
        )

    if thermodiffusion or rotodiffusion:
        ax[1].legend(loc='best').draggable()
        ax[2].legend(loc='best').draggable()

    ax[0].set_xlim([min(rhoList), max(rhoList)])
    ax[2].set_xlabel('$\\rho$')
