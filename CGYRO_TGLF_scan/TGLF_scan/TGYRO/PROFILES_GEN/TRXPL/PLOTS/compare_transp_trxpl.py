# -*-Python-*-
# Created by grierson at 16 Apr 2022  07:21

"""
This script compares a TRANSP run and TRXPL output state file

defaultVars parameters
----------------------
:param transp_output: Location of TRANSP output
:param statefile: Location of statefile
"""

defaultVars(transp_output=None, statefile=None, input_gacode=None, tgyro_output=None)
if statefile is None:
    statefile = root['OUTPUTS'].get('statefile', None)
if transp_output is None or statefile is None or input_gacode is None or tgyro_output is None:
    raise OMFITexception('Pass transp_output, statefile, input_gacode and tgyro_output from the runs to compare')
ig = input_gacode
out = tgyro_output

# ####
# Tokamak
# ####
tokamak = statefile['tokamak_id']['data']

# ####
# Shot number
# ####
shot = statefile['shot_number']['data']

# ####
# Run label (tok.TRANSP runid) and TRANSP shot number
# ####
label = statefile['Global_label']['data']
tr_shot = int(str(label).split()[1])

# ####
# Time range in state file
# ####

# Start time (s)
t0 = statefile['t0']['data']
# End time (s)
t1 = statefile['t1']['data']
# Center time
time = (t0 + t1) / 2.0
# Averaging time window +/-
avgtime = (t1 - t0) / 2.0


dm1_nrho = statefile['__dimensions__']['dm1_nrho']
dim_nrho = statefile['__dimensions__']['dim_nrho']

# rho on dim_nrho from [0.0, ..., 1.0]
rho = statefile['rho']['data']

# rho_eq on dim_nrho_eq from [0.0, ..., 1.0]
rho_eq = statefile['rho']['data']

# Create the rho axis to map to TRANSP grid centers "X"
drho1 = 1.0 / dm1_nrho
# rho on dm1_nrho from [drho1/2, ... 1-drho1/2]
rho1 = linspace(drho1 / 2.0, 1.0 - drho1 / 2.0, dm1_nrho)
rho1b = linspace(drho1, 1.0, dm1_nrho)

# Encosed volume [m**3] on rho_eq
vol = statefile['vol']['data']

# Differential volume [m**3] on rho1
dvol = np.diff(vol)

# Thermal species temperatures (dp1_nspec_th, dm1_nrho)
Ts = statefile['Ts']['data']

# Electron transport power times dV [W] (dm1_nrho)
pe_trans = statefile['pe_trans']['data']
# Volume integrated electron transport power
pe_trans_vint = np.cumsum(pe_trans)


# Ion transport power times dV [W] (dm1_nrho)
pi_trans = statefile['pi_trans']['data']
# Volume integrated ion transport power
pi_trans_vint = np.cumsum(pi_trans)


# particle transport   times dV [W] (dm1_nrho)
sn_trans = statefile['sn_trans']['data']
# Volume integrated particle transport
sn_trans_vint = np.cumsum(sn_trans, axis=1)

from scipy.constants import e

Z = statefile['q_SA']['data'] / e

# ####
# TRANSP Data
# ####

# Zone volume [cm**3] on X
tr_dvol = OMFITtranspData(transp_output, 'DVOL')
tr_dvol_tavg = tr_dvol.tavg(time=time, avgtime=avgtime)

# Enclosed volume [cm**3]
tr_evol = copy.deepcopy(tr_dvol)
tr_evol['DATA'] *= 0.0
tr_evol['DATA'] += 1.0
tr_evol = tr_evol.vint(dvol=tr_dvol)
tr_evol_tavg = tr_evol.tavg(time=time, avgtime=avgtime)

# Note: X is grid centers i.e. for nx points dx = 1/nx and X = [dx/2, ..., 1-dx/2]
# Note: XB is grid boundaries i.e. for nx points dx = 1/nx and X = [dx, ..., 1]

# Electron Temperature on X
tr_Te = OMFITtranspData(transp_output, 'TE')
tr_Te_tavg = tr_Te.tavg(time=time, avgtime=avgtime)

# Electron transport power EETR_OBS [W/cm3] on X
tr_eetr_obs = OMFITtranspData(transp_output, 'EETR_OBS')
tr_eetr_obs_tavg = tr_eetr_obs.tavg(time=time, avgtime=avgtime)

# Volume integrated electron transport power EETR_OBS [W] on XB
tr_eetr_obs_vint = tr_eetr_obs.vint(dvol=tr_dvol)
tr_eetr_obs_vint_tavg = tr_eetr_obs_vint.tavg(time=time, avgtime=avgtime)


# IonElectron transport power IETR_OBS [W/cm3] on X - 	 long name: Div(  energy flux) (observed)
tr_ietr_obs = OMFITtranspData(transp_output, 'IETR_OBS')
tr_ietr_obs_tavg = tr_ietr_obs.tavg(time=time, avgtime=avgtime)

# Volume integrated ion transport power IETR_OBS [W] on XB
tr_ietr_obs_vint = tr_ietr_obs.vint(dvol=tr_dvol)
tr_ietr_obs_vint_tavg = tr_ietr_obs_vint.tavg(time=time, avgtime=avgtime)


tr_iptr_obs = OMFITtranspData(transp_output, 'IPTR_OBS')
tr_iptr_obs_tavg = tr_iptr_obs.tavg(time=time, avgtime=avgtime)
tr_iptr_obs_vint = tr_iptr_obs.vint(dvol=tr_dvol)
tr_iptr_obs_vint_tavg = tr_iptr_obs_vint.tavg(time=time, avgtime=avgtime)


tr_eptr_obs = OMFITtranspData(transp_output, 'EPTR_OBS')
tr_eptr_obs_tavg = tr_eptr_obs.tavg(time=time, avgtime=avgtime)
tr_eptr_obs_vint = tr_eptr_obs.vint(dvol=tr_dvol)
tr_eptr_obs_vint_tavg = tr_eptr_obs_vint.tavg(time=time, avgtime=avgtime)

# ####
# Plotting
# ####
fn = FigureNotebook(0)


f = fn.add_figure(label='VOL')
ax = f.use_subplot(111)
uband(tr_evol['DIM_OF'][0][0, :], tr_evol_tavg * 1e-6, ax=ax, label='TRANSP')
ax.plot(rho_eq, vol, '--', label='STATEFILE')
ax.plot(out['rho'][0], out['volume'][0], '-o', label='TGYRO')

ax.set_title('Enclosed volume (m**3)')
ax.legend(loc='best')

f = fn.add_figure(label='TE')
ax = f.use_subplot(111)
uband(tr_Te['DIM_OF'][0][0, :], tr_Te_tavg * 1e-3, ax=ax)
ax.plot(rho1, Ts[0, :], '--')
ax.plot(out['rho'][0], out['te'][0], '-o')

ax.set_title('Te (keV)')

f = fn.add_figure(label='EETR')
ax = f.use_subplot(111)
uband(tr_eetr_obs_vint['DIM_OF'][0][0, :], tr_eetr_obs_vint_tavg, ax=ax)
ax.plot(rho1b, pe_trans_vint, '--')
ax.set_title('Electron power flow (W)')

r = ig['rmin']
vol = ig.volume()
surf = gradient(vol, r)

surf = interp(out['rmin'][0] / 100, r, surf)


ax.plot(out['rho'][0], (out['eflux_e_target'] * out['Q_GB'])[0] * 1e6 * surf, '-o')


f = fn.add_figure(label='IETR')
ax = f.use_subplot(111)
uband(tr_ietr_obs_vint['DIM_OF'][0][0, :], tr_ietr_obs_vint_tavg, ax=ax)
ax.plot(rho1b, pi_trans_vint, '--')
ax.set_title('Ion power flow (W)')
ax.plot(out['rho'][0], (out['eflux_i_target'] * out['Q_GB'])[0] * 1e6 * surf, '-o')


# ax.plot(ig['rho'], (ig['pow_i']-ig['pow_ei'])*1e6,'o')

f = fn.add_figure(label='IPTR')
ax = f.use_subplot(111)
uband(tr_iptr_obs_vint['DIM_OF'][0][0, :], tr_iptr_obs_vint_tavg, ax=ax)
ax.plot(rho1b, np.sum(sn_trans_vint[1:], 0), '--')
ax.set_title('Ion particle flow (#/s)')


f = fn.add_figure(label='EPTR')
ax = f.use_subplot(111)
uband(tr_eptr_obs_vint['DIM_OF'][0][0, :], tr_eptr_obs_vint_tavg, ax=ax)
ax.plot(rho1b, sn_trans_vint[0], '--')
ax.set_title('Electron particle flow (#/s)')

ax.plot(out['rho'][0], (out['pflux_e_target'] * out['Gamma_GB'])[0] * 1e19 * surf, '-o')
