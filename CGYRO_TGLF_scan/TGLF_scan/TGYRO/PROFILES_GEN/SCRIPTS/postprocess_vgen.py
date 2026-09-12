# -*-Python-*-
# Created by meneghini at 2013/09/16 18:04

# useful quantities
rho = root['OUTPUTS']['input.gacode']['rho']
q = root['OUTPUTS']['input.gacode']['q']
r = root['OUTPUTS']['input.gacode']['rmin']
w0 = root['OUTPUTS']['input.gacode']['omega0']
Bunit = root['OUTPUTS']['input.gacode']['bunit']
try:
    Bcentr = root['OUTPUTS']['input.gacode']['BT_EXP']
except KeyError:
    Bcentr = None
grad_r0 = root['OUTPUTS']['input.gacode']['grad_r0']

if gEQDSK is not None:
    # this Bcentr should be equal to the Bcentr in input.gacode
    Bcentr = gEQDSK.cocosify(2, calcAuxQuantities=True, calcFluxSurfaces=True, inplace=False)['BCENTR']

    # radial electric field [kV/m] (outer midplane)
    Er_midplane = w0 * (r * Bunit / q) * grad_r0
    root['OUTPUTS']['Er'] = SortedDict()
    root['OUTPUTS']['Er']['rho'] = rho
    root['OUTPUTS']['Er']['Er_midplane'] = Er_midplane / 1e3

    # midplane Er/R/Bp [rad/s] (at outer midplane)
    R = gEQDSK['fluxSurfaces']['midplane']['R']
    Br = gEQDSK['fluxSurfaces']['midplane']['Br']
    Bz = gEQDSK['fluxSurfaces']['midplane']['Bz']
    Bp = -sign(Bz) * sqrt(Br**2 + Bz**2)  # on midplane so in COCOS 1 (for CER file), sign(Bp) = -sign(Bz)
    RBpol = interp(rho, gEQDSK['fluxSurfaces']['geo']['rhon'], R * Bp)
    root['OUTPUTS']['Er']['Er_RBpol_midplane'] = root['OUTPUTS']['Er']['Er_midplane'] / RBpol * 1e3

    # CER file
    if root['SETTINGS']['EXPERIMENT']['shot'] != None and root['SETTINGS']['EXPERIMENT']['time'] != None:
        name = str(root['SETTINGS']['EXPERIMENT']['shot']) + "." + format(int(root['SETTINGS']['EXPERIMENT']['time']), "05d")
    else:
        name = '000000.00000'
    root['OUTPUTS']['CER'] = OMFITasciitable('cer' + name)
    tmp = []
    tmp.append(root['OUTPUTS']['Er']['rho'])
    tmp.append(root['OUTPUTS']['input.gacode']['Ti_1'])  # <-------should be more robust!
    tmp.append(root['OUTPUTS']['input.gacode']['ni_2'])  # <-------should be more robust!
    tmp.append(root['OUTPUTS']['input.gacode']['vpol_2'] / 1e3)  # <-------should be more robust!
    # Multiply toroidal rotation by negative 1 because of sign
    # convention difference between GACODE and CERFile
    tmp.append((root['OUTPUTS']['input.gacode']['vtor_2'] / 1e3) * (-1))  # <-------should be more robust!
    tmp.append(root['OUTPUTS']['Er']['Er_midplane'])
    tmp.append(root['OUTPUTS']['Er']['Er_RBpol_midplane'] / 1e3)
    root['OUTPUTS']['CER']['header'] = '         rho     Ti (keV)  nc(e19 m**3)  Vpol (km/s)  Vtor (km/s)    Er (kV/m)    Er_RBpol (krad/s)'
    root['OUTPUTS']['CER']['data'] = np.rec.array(
        tmp, dtype=[('rho', '<f8'), ('Ti', '<f8'), ('nc', '<f8'), ('Vpol', '<f8'), ('Vtor', '<f8'), ('Er', '<f8'), ('Er_RBpol', '<f8')]
    )
    root['OUTPUTS']['CER'].save()
    root['OUTPUTS']['CER'].load()

# bootstrap current
if 'out.vgen.jbs' in root['OUTPUTS'] and Bcentr is not None:
    root['OUTPUTS']['jboot'] = SortedDict()
    root['OUTPUTS']['jboot']['rho'] = root['OUTPUTS']['out.vgen.jbs']['data'][:, 0]
    root['OUTPUTS']['jboot']['B0'] = Bcentr
    root['OUTPUTS']['jboot']['JbootNEO'] = root['OUTPUTS']['out.vgen.jbs']['data'][:, 2] * Bunit / Bcentr * 1e6
    root['OUTPUTS']['jboot']['JbootSauter'] = root['OUTPUTS']['out.vgen.jbs']['data'][:, 3] * Bunit / Bcentr * 1e6
    try:
        root['OUTPUTS']['jboot']['JbootONETWO'] = profpowbal['curboot']['data'].copy()
    except Exception:
        pass
    try:
        root['OUTPUTS']['jboot']['JtorNEO'] = root['OUTPUTS']['out.vgen.jbs']['data'][:, 6] * 1e6
    except Exception:
        pass
    try:
        root['OUTPUTS']['jboot']['JtorSauter'] = root['OUTPUTS']['out.vgen.jbs']['data'][:, 7] * 1e6
    except Exception:
        pass
else:
    printw('Could not create jboot entry')
