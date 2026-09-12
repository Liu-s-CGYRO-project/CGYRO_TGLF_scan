# -*-Python-*-
# Created by smithsp at 2013/07/19 15:24
#
# This script creates input.neo with the species settings consistent with the input.gacode

root['INPUTS']['input.neo'] = input_neo = OMFITgacode('input.neo')

# parse the header of input.gacode
input_gacode = root['OUTPUTS']['input.gacode']
ion_names = [input_gacode['IONS'][k][0] for k in input_gacode['IONS']]
for k in input_gacode:
    if '__header' not in k:
        continue
    if 'IPCCW : ' in input_gacode[k]:
        input_neo['IPCCW'] = int(input_gacode[k].split(':')[1])
    if 'BTCCW : ' in input_gacode[k]:
        input_neo['BTCCW'] = int(input_gacode[k].split(':')[1])

# exclude last # of ions
n_ions = len(input_gacode['IONS']) - root['SETTINGS']['PHYSICS']['neglect_last_ions']

# Set total number of species in input.neo (nions+electrons)
input_neo['N_SPECIES'] = n_ions + 1

# Set property of each ion species (masses are relative to DEUTERIUM)
for k in input_gacode['IONS']:
    input_neo['Z_%d' % k] = input_gacode['IONS'][k][1]
    input_neo['MASS_%d' % k] = input_gacode['IONS'][k][2] / 2.0

# Set electrons property (always the last species) (also, mass relative to DEUTERIUM)
input_neo['Z_%d' % (n_ions + 1)] = -1
input_neo['MASS_%d' % (n_ions + 1)] = 0.0002724486

# (2=model shape, 3=general geometry)
input_neo['EQUILIBRIUM_MODEL'] = 3
input_neo['N_XI'] = root['SETTINGS']['PHYSICS']['vgen_N_XI']
input_neo['N_ENERGY'] = root['SETTINGS']['PHYSICS']['vgen_N_ENERGY']
