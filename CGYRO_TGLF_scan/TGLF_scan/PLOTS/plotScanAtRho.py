# -*-Python-*-
# Created by lugaimin at 2014/06/12 15:14
from OMFITlib_gui_api import plot_view

defaultVars(doSave=False)

rho = root['SETTINGS']['PHYSICS']['rho']
if root['SETTINGS']['PHYSICS']['scanDimensions'] == 1:
    scanResults = 'scanResults'
else:
    scanResults = 'scanResults2D'

results = root[scanResults][rho]
inputTGLF = root['input.tglf'][rho]


# TGLF experimental values
expGm, expQe, expQi, expPi, gbGm, gbQ, gbPi = [nan] * 7
if 'tgyro_output' in root:
    output = root['tgyro_output']

    # -- Modification to be consistent with the x-axis used in the tgyro simulation (rho or r/a)

    if root['TGYRO']['INPUTS']['input.tgyro']['TGYRO_USE_RHO']:
        rho_ind = np.argmin(abs(rho - output['rho']))
    else:
        rho_ind = np.argmin(abs(rho - output['r/a']))
    # --------

    expGm = output['pflux_e_target'][0, rho_ind]
    expQe = output['eflux_e_target'][0, rho_ind]
    expQi = output['eflux_i_target'][0, rho_ind]
    expPi = output['mflux_target'][0, rho_ind]
    if root['SETTINGS']['PHYSICS']['tglf_sign_convention']:
        # Option to change sign of momentum flux for GACODE/TGYRO convention
        # Standard config. for DIII-D is SIGN_BT=-1, SIGN_IT=1
        # However this is opposite to GACODE standards (hence the negatives).
        # The following lines mirror the TGYRO source code.
        tglf_sign_it_in = (
            -1.0 * (-1.0 * inputTGLF['SIGN_BT']) * (-1.0 * inputTGLF['SIGN_IT'])
        )
        # Sign to be applied to Pi
        sign_tglf_Pi = -1.0 * tglf_sign_it_in
        expPi *= sign_tglf_Pi
    if root['SETTINGS']['PHYSICS']['plot_mks']:
        gbGm = output['Gamma_GB'][0, rho_ind]
        gbQ = output['Q_GB'][0, rho_ind]
        gbPi = output['Pi_GB'][0, rho_ind]


# plot the TGLF scan at the selected radius
if root['SETTINGS']['PHYSICS']['scanDimensions'] == 1:
    plot_view(root['TGLF']['PLOTS']['plotScan'], fig=figure(), results=results, inputTGLF=inputTGLF,
        expGm=expGm, expQe=expQe, expQi=expQi, expPi=expPi, gbGm=gbGm, gbQ=gbQ, gbPi=gbPi, doSave=doSave
    )

# 2D plot
else:
    plot_view(root['TGLF']['PLOTS']['plotScan2D'], fig=figure(), results=results, inputTGLF=inputTGLF,
        expGm=expGm, expQe=expQe, expQi=expQi, expPi=expPi, gbGm=gbGm, gbQ=gbQ, gbPi=gbPi, doSave=doSave
    )

if not doSave:
    cornernote('', 'rho=' + str(rho))
