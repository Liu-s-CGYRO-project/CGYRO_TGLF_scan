# -*-Python-*-
# Created by meneghini at 21 Sep 2018  11:31

"""
This script removes deprecated parameters from the input.tgyro file
This is necessary as new versions of GACODE update the input variables to TGYRO
often breaking backwards compatibility
"""

OMFITx.executable(
    root,
    inputs=[],
    outputs=['tgyro_parse.py'],
    clean=False,
    executable='\n'.join(
        evalExpr(root['SETTINGS']['SETUP']['executable']).splitlines()[:-1] + ['cp $GACODE_ROOT/tgyro/bin/tgyro_parse.py ./']
    ),
)

with open('tgyro_parse.py') as f:
    tgyro_parse = f.read()

deprecated = []
valid = []
for l in tgyro_parse.splitlines():
    if 'x.dep' in l:
        deprecated.append(eval(l.split('(')[1].split(',')[0]))
    elif 'x.add' in l:
        valid.append(eval(l.split('(')[1].split(',')[0]))

for k in list(root['INPUTS']['input.tgyro'].keys()):
    if k in deprecated or k not in valid and k != 'DIR':
        printw('Automatically removing invalid parameter: %s' % k)
        del root['INPUTS']['input.tgyro'][k]

scratch['auto_remove_bogus_parameters'] = False
