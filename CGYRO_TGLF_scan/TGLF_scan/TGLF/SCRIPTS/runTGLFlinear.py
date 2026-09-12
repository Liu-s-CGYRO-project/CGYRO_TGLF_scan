# -*-Python-*-
# Created by smithsp at 01 Sep 2015  14:29

defaultVars(inputTGLF=root['FILES']['input.tglf'])

inputTGLF['USE_TRANSPORT_MODEL'] = False  # To get wavefunctions
inputTGLF['WRITE_WAVEFUNCTION_FLAG'] = 1
inputs = [(inputTGLF, 'input.tglf')]

outputs = ['./']

OMFITx.executable(root, inputs, outputs)

root['FILES'] = OMFITtglf(root['SETTINGS']['SETUP']['workDir'])
