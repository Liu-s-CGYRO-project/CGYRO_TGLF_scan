# -*-Python-*-
# Created by wgutten at 17 Oct 2017  12:32
# Updated by holland on 08 May 2019  10:41
"""
This script calculates various analytic driftwave thresholds.
USER WARNING:   The region of parameter space for which these
                expressions are applicable is typically very limited.
                YOU ARE RESPONSIBLE FOR THE INTERPRETATION OF THESE EXPRESSIONS.

defaultVars parameters
----------------------
x - x-axis for plots, which can be 'rho', 'r/a' or 'psin'

"""
defaultVars(x='rho')

#   Turn this into a loop over defined variables
rho = root['OUTPUTS']['input.gacode']['rho']
rmin = root['OUTPUTS']['input.gacode']['rmin']
rmaj = root['OUTPUTS']['input.gacode']['rmaj']
polflux = root['OUTPUTS']['input.gacode']['polflux']
bt_exp = root['OUTPUTS']['input.gacode']['BT_EXP']
q = root['OUTPUTS']['input.gacode']['q']
kappa = root['OUTPUTS']['input.gacode']['kappa']
z_eff = root['OUTPUTS']['input.gacode']['z_eff']
ne = root['OUTPUTS']['input.gacode']['ne']
Te = root['OUTPUTS']['input.gacode']['Te']
Ti_1 = root['OUTPUTS']['input.gacode']['Ti_1']
ra = rmin / rmin[-1]
Ra = rmaj / rmin[-1]
psin = polflux / polflux[-1]

s = root['OUTPUTS']['input.gacode']['s']
skappa = root['OUTPUTS']['input.gacode']['skappa']
dlnnedr = root['OUTPUTS']['input.gacode']['dlnnedr']
dlntedr = root['OUTPUTS']['input.gacode']['dlntedr']
dlntidr_1 = root['OUTPUTS']['input.gacode']['dlntidr_1']
dlnptotdr = -(1 / root['OUTPUTS']['input.gacode']['ptot']) * deriv(rmin, root['OUTPUTS']['input.gacode']['ptot'])
gamma_p = root['OUTPUTS']['input.gacode']['gamma_p']
cs = root['OUTPUTS']['input.gacode']['cs']
bunit = root['OUTPUTS']['input.gacode']['bunit']
# dlnxxdr has units of 1/m
rlne_exp = rmaj * dlnnedr
rlte_exp = rmaj * dlntedr
rlti1_exp = rmaj * dlntidr_1

if x == 'rho':
    xplot = rho
    xlab = '$\\rho$'
elif x == 'r/a':
    xplot = ra
    xlab = 'r/a'
elif x == 'psin':
    xplot = psin
    xlab = '$\\psi_N$'

# ------------------------------------
#   ETG threshold
#   See F. Jenko, W. Dorland, G.W. Hammett, Phys. Plasmas 8, 4096 (2001)
#   *** Should incorporate validity checks to
#   ensure parameters inside bounds of applicability.
#   E.g., does not work for small/negative shear, large beta/alpha,
#   should not use epsilon correction for STs, ...
#
#   Bounds of applicability:
#   0<Zeff*Te/Ti<5, 0.2<s<3, 0.5<a, 0<s/q<2, alpha<0.1, arbitrary R/Ln
# ------------------------------------
fn = FigureNotebook(0, 'Analytic mircoinstability thresholds')
fig, ax = fn.subplots(label='ETG')

rlte_jenko_rln = rmaj * 0.8 * dlnnedr
rlte_jenko_sq = (1 + z_eff * Te / Ti_1) * (1.33 + 1.91 * s / abs(q))
rlte_jenko_sq_eps = rlte_jenko_sq * (1 - 1.5 * ra / Ra)
rlte_jenko_sq_eps_kappa = rlte_jenko_sq_eps * (1 + 0.3 * skappa * kappa)

rlte_jenko = numpy.maximum(rlte_jenko_rln, rlte_jenko_sq_eps)

ax.plot(xplot, rlte_exp, label='exp.', color='black')
ax.plot(xplot, rlte_jenko, label='Jenko', ls='dashed', color='black')
ax.plot(xplot, rlte_jenko_sq_eps, label='F($\\tau$,s/q,$\\epsilon$)', ls='dotted', color='blue')
ax.plot(xplot, rlte_jenko_rln, label='0.8$\\cdot$R/Ln', ls='dotted', color='red')
ax.set_ylabel('$R/L_{Te}$')
ax.set_xlabel(xlab)
ax.legend(loc='best').draggable()
ax.set_ylim(0, 20)


# ------------------------------------
#   ITG threshold
#   Add IFS-PPPL model(s) here, with input validity checks
#   See M. Kotchenreuther, W. Dorland, G.W. Hammett, M. Beer Phys. Plasmas 2, 2381 (1995)
#   Also see NTCC IFS-PPPL module
#
#   Bounds of applicability:
#   0.7<q<8, 0.5<s<2, 0<R/Ln<6, 0.5<Ti/Te<4, 1<Zeff<4, 0.5<nu<10, 0.1<r/R<0.3
# ------------------------------------
fig, ax = fn.subplots(label='ITG')
# From IFS-PPPl NTCC module and .tex file
# ne (10^19 m^-3)
# Te, Ti (keV)
# sigma_b = n_beam/n_e
# R (m)
# B (T)
# R/LTi, R/LTe, R/Lne
# eps = r/R
# s_hat = r/q*dq/dr
# q
# kappa = b/a - elongation
# wexb = ExB shear rate (1/s)

# chi_i, chi_e (m^2/s)
# gamma (1/s)
ee = scipy.constants.e
md = 2 * scipy.constants.m_p

################ need condition for fast ion species, for dilution
sigma_b = 0
################
vti = np.sqrt(ee * Ti_1 * 1e3 / md)
rho_i = np.sqrt(md * Ti_1 * 1e3 / ee) / bt_exp
chi_i_gb = rho_i**2 * vti / rmaj

tau = Ti_1 / Te
tau_b = tau / (1 - sigma_b)

# in nu_norm, ne(10^19 m^-3), T(keV)
nu_norm = 2.1 * rmaj * ne / (Te**1.5 * Ti_1**0.5)

#   Typo in 1995 Kotchenreuther paper, as noted in .tex file, 'max' should be 'min'
RLn_star = numpy.minimum(6 * np.ones(len(Te)), rlne_exp)

#   Threshold gradients
# #   Paper
# f = 1 - 0.2*Zeff.^0.5 ./ s_hat.^-0.7 .* (14.*eps.^1.3./nu_norm.^0.2-1)
# g = (0.7 + 0.6.*s_hat - 0.2.*RLn_star).^2 + 0.4 + 0.3.*RLn_star - 0.8.*s_hat + 0.2.*s_hat.^2
# h = 1.5*(1 + 2.8./q.^2).^0.26 .* Zeff.^0.7 .* tau_b.^0.5

eps = ra / Ra
#   .tex file
f = 1 - 0.942 * z_eff**0.516 / s**0.671 * (2.95 * eps**1.257 / nu_norm**0.235 - 0.2126)
g = (0.671 + 0.570 * s - 0.189 * RLn_star) ** 2 + 0.392 + 0.335 * RLn_star - 0.779 * s + 0.210 * s**2
h = 2.46 * (z_eff / 2.0) ** 0.7 * tau_b**0.52 * (1 + 2.8 / q**2) ** 0.26

rlti_d_crit = f * g * h
Drln = numpy.maximum(np.ones(len(Te)), 3 - 0.6667 * RLn_star)
Ezeff = 1 + 6 * numpy.maximum(0, 2.9 - z_eff)
rlti_c_crit = 0.75 * (1 + tau_b) * (1 + s) * Drln * Ezeff

ax.plot(xplot, rlti1_exp, label='exp.', color='black')
# ax.plot(xplot,rlti1_exp,label='exp.',color='red')
ax.plot(xplot, rlti_d_crit, label='IFS-PPPL D', ls='dashed', color='black')
ax.plot(xplot, rlti_c_crit, label='IFS-PPPL C', ls='dashed', color='red')
ax.set_ylabel('$R/L_{Ti}$')
ax.set_xlabel(xlab)
ax.legend(loc='best').draggable()
ax.set_ylim(0, 20)


# ------------------------------------
#   TEM threshold
#   From A.G. Peeters et al., Phys. Plasmas 12, 022505 (2005)
#   *** Strictly only applicable for electron-dominated
#   regimes,  Te/Ti~3, R/LTi~0<<R/LTe ***
# ------------------------------------
fig, ax = fn.subplots(label='TEM')

#   Eq. 1 ne(10^19 m^-3), Te(keV)
nu_eff = 0.1 * ne * z_eff / Te**2

#   Eq. 9, TEM threshold
rlte_peeters = (0.357 * np.sqrt(ra / Ra) + 0.271) / np.sqrt(ra / Ra) * (4.90 - 1.31 * rmaj * dlnnedr + 2.68 * s + log(1 + 20 * nu_eff))
#   Eq. 10, relative stiffness (~heat pulse thermal diffusivity)
lambda_star_peeters = 9 * ra / Ra * (1 - 0.39 * s - 0.1 * nu_eff)

# Rough criteria for applicability
# find(Ti_1 > 0.5*Te && R/LTi>0.5*R/LTe)

ax.plot(xplot, rlte_exp, label='exp.', color='black')
ax.plot(xplot, rlte_peeters, label='Peeters', ls='dashed', color='black')
ax.set_ylabel('$R/L_{Te}$')
ax.set_xlabel(xlab)
ax.legend(loc='best').draggable()
ax.set_ylim(0, 20)

# ------------------------------------
#   KBM, alpha and shear
# ------------------------------------
fig, ax = fn.subplots(label='KBM')

#   alpha = -q^2 * 2*mu0 * grad-P_tot / B^2
#   alpha_unit = q^2 * (R/a) * beta_e * sum[(n_s/n_e)(T_s/T_e)(a/Lns+a/Ts)]
#   Sum should be over all species
beta_e_unit = 2 * 4 * pi * 1e-7 * ne * 1.6 * Te * 1e3 / bunit**2
beta_e_btexp = 2 * 4 * pi * 1e-7 * ne * 1.6 * Te * 1e3 / bt_exp**2
alpha_unit_ptot = q**2 * rmaj * beta_e_unit * dlnptotdr
alpha_btexp_ptot = q**2 * rmaj * beta_e_btexp * dlnptotdr
## now do this by actually summing over all kinetic species, maybe w/ and w/o fast ions to see the difference

ax.plot(xplot, alpha_unit_ptot, label='$\\alpha_{unit}$', color='black')
ax.plot(xplot, alpha_btexp_ptot, label='$\\alpha_{bt,exp}$', ls='dashed', color='black')
ax.plot(xplot, s, label='s', color='red')
ax.plot([0, 1], [0, 0], ls='dotted', color='black')
ax.set_ylabel('')
ax.set_xlabel(xlab)
ax.legend(loc='best').draggable()
ax.set_ylim(-1, 5)

##   Future: calculate equivalent alphas e.g. like what GS2 or ELITE use
##   More future: calculate ideal MHD stability from balloo and overlay


# ------------------------------------
#   PVG, u' vs. R/Ln (k_|| assumptions)
# ------------------------------------
fig, ax = fn.subplots(label='PVG')

csa_ref = cs / rmin[-1]
uprime = rmaj * gamma_p / csa_ref

ax.plot(xplot, abs(uprime), label='|$u^\prime$|', color='black')
ax.set_ylabel('')
ax.set_xlabel(xlab)
ax.legend(loc='best').draggable()
ax.set_ylim(0, 5)
