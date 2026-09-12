# -*-Python-*-
# Created by smithsp at 2013/07/15 09:08

input_gacode = None
if 'input.gacode' in root['OUTPUTS']:
    input_gacode = root['OUTPUTS']['input.gacode']

defaultVars(doPlot=False, input_gacode=input_gacode)

if input_gacode is None:
    printe('Must specify input_gacode to run enforce_quasineutrality')
    OMFITx.End()

if len(input_gacode['IONS']) == 0:
    raise OMFITexception('IONS information missing from input.gacode file.  ' 'Can not enforce quasineutrality without it.')

input_gacode.enforce_quasineutrality(ion=1, balanced_DT=True)
