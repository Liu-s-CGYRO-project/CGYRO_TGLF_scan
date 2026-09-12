# -*-Python-*-
# Created by prattq at 07 Aug 2023  13:56

"""
This script creates the TGLF analog to the plot "compareGYROfreq.py" in the GYRO_scan module.
The purpose is to show the (linear) eigenvalue spectrum for a TGLF run compared with
typical drift frequencies (diamagnetic and magnetic).

The formulas for the drift frequencies can be found in the GYRO_GACODE OMFIT module's OMFITlib_general.
Specifically the functions: get_diamag_freq() and get_drift_freq()

I have implemented the formulas here although I leave some questions in the comments...

defaultVars parameters
----------------------
:param rho: (float) radial location where TGLF_scan has been run.
:param mode_nums: (list) [1, 2, ... N_MODES]
:param ax: matplotlib axes object.
:param colors: (list) colors for each mode_num
:param dw_color: color str. for the drift-wave frequency annotations.
:param annotate: (bool) option to add a lot of annotations to the plot...
"""

from itertools import cycle

defaultVars(rho=root['SETTINGS']['PHYSICS'].get('rho', 0.5), mode_nums=[1], ax=None, colors=['b'], dw_color='k', annotate=True, ion_index=2)
fs = 16  # fontsize
if rho not in root['Experimental_spectra']:
    printe(f"ERROR: (plot_frequency_vs_ky) rho={rho} not found in Experimental_spectra")
    OMFITx.End()

eig_spect = root["Experimental_spectra"][rho]['eigenvalue_spectrum']
input_tglf = root["Experimental_spectra"][rho]['input.tglf']

# The linear eigenvalue spectrum from TGLF (real frequency)
ky = eig_spect["ky"].data
omega = eig_spect["freq"]

# 1. Diamagnetic frequencies,
# The textbook formula (for species 's') is,
# 	w_*s = k*|grad(Ps)|/(Zs*B*ns)
# 		 = k*|Ts*grad(ns) + ns*grad(Ts)|/(Zs*B*ns)
# 		 = k*|a*grad(ns)/ns + a*grad(Ts)/Ts|*Ts/(Zs*B*a)
# 		 = k*|RLNS + RLTS|*(Ts/mD)*mD/(Zs*B*a)
# NOTE: the TGLF RL?S_? variables are normalized by 'a' not 'R'.
# for electrons, when Ts = Te, we have a factor of cs^2 = Te/mD.
# 		 = k*|RLNS + RLTS|*cs^2/(a*|WcD|)
# 		 = k*rhos*|RLNS + RLTS| * cs/a
# If we work in units of [cs/a] then the formula for the electron diamagnetic freq.
# can be written simply as,
#  w_*,e = ky*|RLNS + RLTS| # assuming ky = k*rhos

Ti_Te = input_tglf[f"TAUS_{ion_index}"]
Zi = input_tglf[f"ZS_{ion_index}"]
we = ky * (input_tglf["RLNS_1"] + input_tglf["RLTS_1"])  # units of cs/a
wi = -1 * ky * Ti_Te / Zi * (input_tglf[f"RLNS_{ion_index}"] + input_tglf[f"RLTS_{ion_index}"])  # units of cs/a

# 2. Magnetic drift frequencies,
# The textbook formula for the *combined* grad-B and curv. drift frequency is,
# 	w_Ds = k*(v_par^2 + 0.5*v_perp^2)/(Wcs*R) ... cf. eq. 2.6.9 in Wesson
# if we assume (for some reason?) cs^2 = v_par^2 + 0.5*v_perp^2 then,
# 		 = k*cs^2/(Wcs*R)
# 		 = k*cs^2/(Wcs*(R/a)*a)
# 		 = k*cs/(Wcs*RMAJ_LOC) * cs/a
# For the ions, where Wcs = WcD, we have a factor of rhos = cs/WcD
# 	w_Di = k*cs/(Wcs*RMAJ_LOC) * cs/a
# 	 	 = k*rhos/RMAJ_LOC * cs/a
# If we work in units of [cs/a] then the formula for the ion 'magnetic drift' freq.
# can be written simply as,
# 	w_Di = ky/RMAJ_LOC # assuming ky = k*rhos

wDe = ky / input_tglf["RMAJ_LOC"]
wDi = -1 * wDe * Ti_Te / Zi

# WARNING...
# The TGLF 'ky' does not correspond to a real physical inverse-length, be careful
# interpreting the w_*,e/ky as a real drift *velocity*
ve, vi = we / 2 / ky, wi / 2 / ky
vDe, vDi = wDe / ky, wDi / ky

# Plotting,
if ax is None:
    fig, ax = plt.subplots(1, 1, num="TGLF_scan: plot_frequency_vs_ky")

if not colors:
    raise ValueError('Provide at least one mode color')
for m, c in zip(mode_nums, cycle(colors)):
    ax.plot(ky, omega.sel(mode_num=m).data, '-o', color=c, lw=2, label=f"mode_num={m}")

ax.axhline(0, ls='--', color='grey')

ax.plot(ky, we / 2, '--', color=dw_color, label=r'$\omega^*_s/2$')
ax.plot(
    ky,
    wi / 2,
    '--',
    color=dw_color,
)

ax.plot(ky, wDe, ':', lw=2, color=dw_color, label=r'$\omega_{D,s}$')
ax.plot(ky, wDi, ':', lw=2, color=dw_color)

ax.set_ylabel(r"$\omega$ [$c_s/a$]")
ax.set_xlabel(r"$k_y$")
ylm = np.array(ax.get_ylim())
ax.set_ylim(-1 * max(abs(ylm)), max(abs(ylm)))  # make symmetric
ax.legend(loc="lower center")

if annotate:
    annotate_kwargs = dict(xycoords="axes fraction", ha="left", va="top", fontsize=fs)
    # Ions are < 0, Elec. are > 0
    ax.annotate(fr"ion", xy=(0.1, 0.1), color="k", **annotate_kwargs).draggable()
    ax.annotate(fr"elec.", xy=(0.1, 0.9), color="k", **annotate_kwargs).draggable()

    # Not sure if I should include these "velocities" because the ky values used to
    # calculate them do not correspond to real inverse-lengths to they can be off by
    # a factor of 0.5 - 2 possibly.
    ax.annotate(fr"$0.5\omega^*_e/k_y = $ {ve[0]:.3f}", xy=(0.75, 0.9), color=dw_color, **annotate_kwargs).draggable()
    ax.annotate(fr"$\omega_{{De}}/k_y = $ {vDe[0]:.3f}", xy=(0.75, 0.55), color=dw_color, **annotate_kwargs).draggable()
    ax.annotate(fr"$\omega_{{Di}}/k_y = $ {vDi[0]:.3f}", xy=(0.75, 0.45), color=dw_color, **annotate_kwargs).draggable()
    ax.annotate(fr"$0.5\omega^*_i/k_y = $ {vi[0]:.3f}", xy=(0.75, 0.1), color=dw_color, **annotate_kwargs).draggable()
