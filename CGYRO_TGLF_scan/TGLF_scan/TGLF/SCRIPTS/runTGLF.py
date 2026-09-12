# -*-Python-*-
# Created by meneghini at 2013/03/08 15:34

inputTGLF = None
if 'input.tglf' in root['FILES']:
    inputTGLF = root['FILES']['input.tglf']

defaultVars(inputTGLF=inputTGLF)

if inputTGLF is None:
    raise OMFITexception('Need an input.tglf file to run TGLF')

constraints = root.get('constraint_vars', {})
if constraints:
    for k in inputTGLF:
        exec("%s = inputTGLF['%s']" % (k, k))
    for k, v in constraints.items():
        inputTGLF[k] = eval(v)
inputTGLF['USE_TRANSPORT_MODEL'] = True
inputs = [(inputTGLF, 'input.tglf')]

# OMFITtglf takes the whole running directory
outputs = ['./']

OMFITx.executable(root, inputs, outputs)

result = root['FILES'] = OMFITtglf(root['SETTINGS']['SETUP']['workDir'])
