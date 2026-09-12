# -*-Python-*-
# Created by meneghini at 2015/07/05 13:27

defaultVars(scale=0.5)

input_tglf = root['FILES']['input.tglf']

root['STIFFNESS'] = OMFITcollection()
vars = ['nominal']
exceptions = [
    'SIGN_BT',
    'SIGN_IT',
    'ZS_1',
    'ZS_2',
    'ZS_3',
    'ZS_4',
    'ZS_5',
    'MASS_1',
    'MASS_2',
    'MASS_3',
    'MASS_4',
    'MASS_5',
    'AS_1',
    'AS_2',
    'AS_3',
    'AS_4',
    'AS_5',
    'KY',
    'VExB',
    'ALPHA_QUENCH',
    'ALPHA_MACH',
    'ALPHA_E',
    'ALPHA_P',
    'ALPHA_ZF',
    'NN_MAX_ERROR',
    'RMIN_SA',
    'RMAJ_SA',
    'Q_SA',
    'SHAT_SA',
    'ALPHA_SA',
    'XWELL_SA',
    'THETA0_SA',
    'B_MODEL_SA',
    'FT_MODEL_SA',
]
root['STIFFNESS']['nominal'] = OMFITtree()
root['STIFFNESS']['nominal']['input.tglf'] = copy.deepcopy(input_tglf)
for var in input_tglf:
    if is_float(input_tglf[var]) and input_tglf[var] != 0.0 and var not in exceptions:
        vars.append(var)
        root['STIFFNESS'][var] = OMFITtree()
        root['STIFFNESS'][var]['input.tglf'] = copy.deepcopy(input_tglf)
        root['STIFFNESS'][var]['input.tglf'][var] *= scale

prerun = '''
root['FILES'].clear()
root['FILES']['input.tglf']=root['STIFFNESS'][var]['input.tglf']
'''
postrun = '''
results=root['FILES']['gbflux']
'''

results = root['SCRIPTS']['runTGLF'].prun(len(vars), 4, 'results', var=vars, prerun=prerun, postrun=postrun)

for k, var in enumerate(vars):
    root['STIFFNESS'][var]['gbflux'] = results[k]

root['FILES'] = root['STIFFNESS']['nominal']
del root['STIFFNESS']['nominal']
