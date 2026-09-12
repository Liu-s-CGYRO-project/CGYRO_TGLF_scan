# -*-Python-*-
# Created by thomek at 05 Jul 2016  16:48

OMFITx.TitleGUI('TGLF Experimental Radial Scan Gui')

root.setdefault('Experimental_spectra', OMFITcollection())
xp_flx = root.setdefault('Experimental_fluxes', OMFITcollection())


def clean_rho(location):
    rad = tolist(root['SETTINGS']['PHYSICS']['rho_scan'])
    rad_good = sorted(root['input.tglf'].keys())
    rad_new = []
    for r in rad:
        rad_new.append(rad_good[closestIndex(rad_good, r)])
    rad_new = unique(rad_new)
    root['SETTINGS']['PHYSICS']['rho_scan'] = rad_new


OMFITx.Entry("root['SETTINGS']['PHYSICS']['rho_scan']", 'rho', default=[0.2, 0.25, 0.5, 0.75, 0.9], updateGUI=True, postcommand=clean_rho)
OMFITx.CheckBox("root['SETTINGS']['PHYSICS']['recalculate']", 'Recalculate previously calculated radii', default=False)
OMFITx.Button('Run TGLF at experimental values', "root['SCRIPTS']['Radial_scan']")
if len(xp_flx):
    #    OMFITx.Button('Plot shears',"root['PLOTS']['plotGammaMaxvsExB'].runNoGUI",help='At experimental parameters, plot max shear at ky<1 and ExB experimental shear vs radii')
    OMFITx.Button(
        'Plot fluxes',
        "root['PLOTS']['plotFluxesvsRho'].runNoGUI",
        help='At experimental parameters, plot particle, heat and momentum fluxes vs radii',
    )
    OMFITx.Button(
        "Plot growth rate/freq vs ky and radius",
        "root['PLOTS']['plot_gamma_vs_k_and_r']",
        help=("Make a plot of growth rate and frequency" "vs ky and radius for each mode"),
    )
