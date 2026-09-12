# -*-Python-*-
# Created by smithsp at 2013/11/06 14:32

TGYRO = root['TGYRO']
rho = root['SETTINGS']['PHYSICS']['rho']
radial_grid = list(arange(1, 100) / 100.0)
if rho not in radial_grid:
    rho_near = radial_grid[argmin(abs(radial_grid - rho))]
    printi('%s not in default radial grid for running TGYRO' % rho)
    printi('Adjusting rho to nearest rho: %s' % rho_near)
    rho = root['SETTINGS']['PHYSICS']['rho'] = rho_near

# TGYRO should not run profiles_gen (the user should take care of this)
TGYRO['SETTINGS']['PHYSICS']['runPROFILES_GEN'] = False

# TGYRO needs at least 2 radial locations to run
TGYRO['SETTINGS']['PHYSICS']['n_rad'] = len(radial_grid)
TGYRO['INPUTS']['input.tgyro']['TGYRO_RMIN'] = min(radial_grid)
TGYRO['INPUTS']['input.tgyro']['TGYRO_RMAX'] = max(radial_grid)
# do -1 iterations (i.e. no evolution, since OMFIT will run TGYRO in test mode)
TGYRO['INPUTS']['input.tgyro']['TGYRO_RELAX_ITERATIONS'] = -1
TGYRO['INPUTS']['input.tgyro']['TGYRO_ITERATION_METHOD'] = 1
TGYRO['SETTINGS']['SETUP']['n_cpu_rad'] = 1
# use original profiles
TGYRO['INPUTS']['input.tgyro']['LOC_LOCK_PROFILE_FLAG'] = 1
# dump TGLF input file (this is what we are after)
TGYRO['INPUTS']['input.tgyro']['TGYRO_TGLF_DUMP_FLAG'] = 1
TGYRO['INPUTS']['input.tgyro']['TGYRO_TGLF_REVISION'] = 0
# need to evolve something even if only 0 steps are taken # This also fills in non-primary ion temperature
TGYRO['INPUTS']['input.tgyro']['LOC_TE_FEEDBACK_FLAG'] = 1
TGYRO['INPUTS']['input.tgyro']['LOC_TI_FEEDBACK_FLAG'] = 1
TGYRO['INPUTS']['input.tgyro']['TGYRO_DEN_METHOD0'] = 1
TGYRO['INPUTS']['input.tgyro']['LOC_ER_FEEDBACK_FLAG'] = 0
# set number of ions to 10, and TGYRO['SCRIPTS']['update_ion_data'] will correct it
TGYRO['SETTINGS']['PHYSICS']['LOC_N_ION_USER'] = 10

# Reuse local dumps only when both the upstream profiles and generating program
# have provenance. A cached rho alone says nothing about its input profiles.
cache = root['TGLF']['LIB']['OMFITlib_tglf_cache'].runNoGUI()
def local_input_provenance():
    return cache['provenance'](TGYRO, {
        'profiles': TGYRO['PROFILES_GEN']['OUTPUTS']['input.gacode'],
        'inputs': TGYRO['INPUTS'],
    }, 'localdump', {'radial_grid': radial_grid})
current = local_input_provenance()
if rho in root.get('input.tglf', {}) and cache['matches'](root.get('_input_cache_provenance'), current):
    root['TGLF']['FILES']['input.tglf'] = copy.deepcopy(root['input.tglf'][rho])
    OMFITx.End()
for key in ('input.tglf', 'tgyro_output', 'scanResults', 'scanResults_spectra',
            'scanResults2D', 'scanResults2D_spectra', 'UQResults', 'UQResults_spectra',
            'Experimental_fluxes', 'Experimental_spectra', '_scan_cache_provenance',
            '_radial_cache_provenance', '_input_cache_provenance'):
    root.pop(key, None)

# run TGYRO
TGYRO['SCRIPTS']['runTGYRO'].run()

# make sure destination directories are there
root.setdefault('scanResults', OMFITtree())
root.setdefault('input.tglf', OMFITtree())
root.setdefault('tgyro_output', OMFITtree())

# get the input.tglf file
for ri, rho_ in enumerate(radial_grid):
    root['input.tglf'][float(str(rho_))] = OMFITgacode(
        str(TGYRO['SETTINGS']['SETUP']['workDir']) + '/' + list(TGYRO['INPUTS']['input.tgyro']['DIR'].keys())[ri] + '/out.tglf.localdump'
    )
    root['input.tglf'][float(str(rho_))]['USE_TRANSPORT_MODEL'] = True

# get the tgyro results (only used for plotting purposes)
root['tgyro_output'] = copy.deepcopy(root['TGYRO']['OUTPUTS']['output'])

# get ready for a new tglf scan
root['TGLF']['FILES']['input.tglf'] = copy.deepcopy(root['input.tglf'][rho])

root['_input_cache_provenance'] = local_input_provenance()
