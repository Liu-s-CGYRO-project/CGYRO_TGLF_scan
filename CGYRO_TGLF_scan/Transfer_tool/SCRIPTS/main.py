# manage the whole workflow
# you have two options to run
#1. load the gfile, trpltout.nc and statefile.nc before running this script (recommendated)
#2. load the input.profiles and input.profiles.geo
if 'statefile' in root['INPUTS'] or 'statefile.nc' in root['INPUTS'] or 'pfile' in root['INPUTS'].keys() or 'input.profiles' in root['INPUTS'].keys():
    # step 1, run the profiles_gen.py to generate the input.profiles
    print('Running Profiles_gen....')
    root['SCRIPTS']['profiles_gen.py'].run()
    print('Finished Profiles_gen!')
    # step 2, take the output of profiles_gen to be the input of TGYRO
    root['INPUTS']['input.gacode']=root['OUTPUTS']['Profiles_gen']['input.gacode'].duplicate()
#    root['INPUTS']['input.profiles.geo']=root['OUTPUTS']['Profiles_gen']['input.profiles.geo'].duplicate()
# step 3, run tgyro to generate the target flux
print('Running TGYRO for generating target flux')
root['SCRIPTS']['tgyro_tglf.py'].run()
# step 4, run profiles_gen to to get the input.tglf, input.cgyro and input.gyro
print('Running profiles_gen for input.***')
root['SCRIPTS']['profiles_gen4input.py'].run()
#print('Transforming the input.cgyro to input.gyro')
#root['SCRIPTS']['inputcgyro2gyro.py'].run()
