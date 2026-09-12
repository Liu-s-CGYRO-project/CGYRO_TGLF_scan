# -*-Python-*-
# Created by grierson at 25 Apr 2016  14:38

# Compute particle transport coefficeints radial diffusion and pinch velocity.
# The equation is as follows:
#   Gamma = -D grad(n) + V n
# Where
#  Gamma - particle flux
#  n - particle density
#  D - diffusion
#  V - convection
#
# We re-arrange to form
#  Gamma/n = -D grad(n)/n + V
# and perform a TGLF scan of grad(n) and fit to a line
# to get both D and V.
#
# The steps to perform this are as follows:
# Get input.gacode from steatefile.
# Add trace impurity with T(imp) = T(main ion) and debit main-ion density by Z*nZ.
# Run TGYRO without iterating to get the mapping from input.gacode to TGLF.
# Run a TGLF 3-point scan for +/- 10% on RLNS_[?] to define a line
#   In the compainion script particleDandVprofile.py we do the next step
# Fit the slope and y-intercept of the flux for D and V

root.setdefault('D_and_v', OMFITtree())

####
# Workflow inputs
####
# Impurity element
impElement = root['SETTINGS']['PHYSICS']['impElement']  # root['D_and_v']['impElement']
# Impurity charge
impZ = root['SETTINGS']['PHYSICS']['impZ']  # root['D_and_v']['impZ']
# Impurity mass
impM = root['SETTINGS']['PHYSICS']['impM']  # root['D_and_v']['impM']
# Impurity type
impType = 'therm'
# Impurity locaton in the list (D, C, [imp], D_fast, ...)
impLoc = root['D_and_v']['impLoc'] = 2  # fixed
# Impurity concentration (~trace)
impC = root['D_and_v']['impC'] = 1e-6  # fixed
# TGLF maximum number of ion species
# Keep this simple: if user wants to ignore species, they can eliminate them from input.gacode
nIonsTGLF = root['D_and_v']['nIonsTGLF'] = 7  # fixed max number

# List of rho values for D and V profile
rhoList = root['D_and_v']['rhoList'] = root['SETTINGS']['PHYSICS']['rhoList']

####
# Store inputs
####
rho = np.array(rhoList)
input_rho = root['TGYRO']['PROFILES_GEN']['OUTPUTS']['input.gacode']['rho']
input_polflux = root['TGYRO']['PROFILES_GEN']['OUTPUTS']['input.gacode']['polflux']
input_psiN = (input_polflux - input_polflux[0]) / (input_polflux[-1] - input_polflux[0])
psiN = (interpolate.interp1d(input_rho, input_psiN))(rho)
root['D_and_v']['rho'] = rho
root['D_and_v']['psin'] = psiN

####
# Copy original input.gacode and create input.gacode_mod for our ion
####
root['D_and_v']['input.gacode_orig'] = copy.deepcopy(root['TGYRO']['PROFILES_GEN']['OUTPUTS']['input.gacode'])
root['D_and_v']['input.gacode_mod'] = copy.deepcopy(root['TGYRO']['PROFILES_GEN']['OUTPUTS']['input.gacode'])

# Set our ion in the IONS list by first moving ions beyond our ion location down
# For all ions beyond our desired location move down one, i.e if we want our ion inserted into
# position 4 and have 6 ions, then move ion 6->7 and 5->6 then insert 4.
for i in list(reversed(list(range(impLoc, root['D_and_v']['input.gacode_mod']['N_ION'] + 1)))):
    print('Moving ion {}'.format(i))
    root['D_and_v']['input.gacode_mod']['IONS'][i + 1] = copy.deepcopy(root['D_and_v']['input.gacode_mod']['IONS'][i])
    root['D_and_v']['input.gacode_mod']['ni_{}'.format(i + 1)] = root['D_and_v']['input.gacode_mod']['ni_{}'.format(i)]
    root['D_and_v']['input.gacode_mod']['Ti_{}'.format(i + 1)] = root['D_and_v']['input.gacode_mod']['Ti_{}'.format(i)]
    root['D_and_v']['input.gacode_mod']['vtor_{}'.format(i + 1)] = root['D_and_v']['input.gacode_mod']['vtor_{}'.format(i)]
    root['D_and_v']['input.gacode_mod']['vpol_{}'.format(i + 1)] = root['D_and_v']['input.gacode_mod']['vpol_{}'.format(i)]

# Set our ion identification
root['D_and_v']['input.gacode_mod']['IONS'][impLoc] = [impElement, impZ, impM, impType]
# Increment ion counter
root['D_and_v']['input.gacode_mod']['N_ION'] = root['D_and_v']['input.gacode_mod']['N_ION'] + 1
# Set ion density (10**19 m**-3)
nZ = root['D_and_v']['input.gacode_mod']['ne'] * impC
root['D_and_v']['input.gacode_mod']['ni_{}'.format(impLoc)] = nZ
# Remove impurity charge density from main-ion
root['D_and_v']['input.gacode_mod']['ni_1'] = root['D_and_v']['input.gacode_mod']['ni_1'] - (nZ * impZ)
# Set ion temperature by copying the first ion
root['D_and_v']['input.gacode_mod']['Ti_{}'.format(impLoc)] = copy.deepcopy(root['D_and_v']['input.gacode_mod']['Ti_1'])

root['SETTINGS']['PHYSICS']['scanDimensions'] = 1

# Set our input.gacode_mod in the PROFILES_GEN module
root['TGYRO']['PROFILES_GEN']['OUTPUTS']['input.gacode'] = copy.deepcopy(root['D_and_v']['input.gacode_mod'])

# Set the number of ions for TGYRO
root['TGYRO']['INPUTS']['input.tgyro']['LOC_N_ION'] = nIonsTGLF
root['TGYRO']['SETTINGS']['PHYSICS']['LOC_N_ION_USER'] = nIonsTGLF

# Setup the inputs for TGLF
root['SCRIPTS']['setup_tglf'].run()

# Reset the input.gacode file without the trace impurity
root['TGYRO']['PROFILES_GEN']['OUTPUTS']['input.gacode'] = copy.deepcopy(root['D_and_v']['input.gacode_orig'])

for rho in rhoList:
    ####
    # Set radius for D and V
    ####
    root['SETTINGS']['PHYSICS']['rho'] = rho

    ####
    # Run TGLF scan for RLNS_[impurity] varied by +/- 10% in three steps
    # Note RLTS_[impurity] is one higher number than TGYRO numbering because of electrons
    ####
    root['TGLF']['SETTINGS']['PHYSICS']['scanParameter'] = 'RLNS_{}'.format(impLoc + 1)
    root['TGLF']['SETTINGS']['PHYSICS']['scanParameterMin'] = 0.9
    root['TGLF']['SETTINGS']['PHYSICS']['scanParameterMax'] = 1.1
    root['TGLF']['SETTINGS']['PHYSICS']['scanParameterSteps'] = 3
    root['SCRIPTS']['runScanAtRho'].run()
