# -*-Python-*-
# Created by smithsp at 2013/05/22 11:20

if input_gacode is None or not len(input_gacode):
    raise OMFITexception('Your input.gacode dependency is not satisfied. Did you run PROFILES_GEN ?')

ion_information = input_gacode['IONS']
if not len(ion_information):
    raise OMFITexception('You are missing the IONS information from your ' 'input.gacode file. TGYRO will not run without it.')

# set Z, A and calc flag for each of the ions
input_tgyro = root['INPUTS']['input.tgyro']
for i in ion_information:
    if i == 1:
        input_tgyro['LOC_Z'] = ion_information[i][1]
    else:
        input_tgyro['LOC_Z%d' % i] = ion_information[i][1]
    input_tgyro['LOC_MA%d' % i] = ion_information[i][2]

    if root['SETTINGS']['PHYSICS']['INCLUDE_IONS'] == 'thermal':
        input_tgyro['TGYRO_THERM_FLAG%d' % i] = int('fast' not in ion_information[i][3].lower())
        input_tgyro['TGYRO_CALC_FLAG%d' % i] = int('fast' not in ion_information[i][3].lower())
