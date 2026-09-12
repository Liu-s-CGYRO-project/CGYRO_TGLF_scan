# -*-Python-*-
# Created by meneghini at 06 May 2016  15:18

defaultVars(harvest_index=None)

if harvest_index is None:
    raise OMFITexception('Must define a index from the harvest database')

harvest = root['HARVEST'][harvest_index]

if 'gen' not in root['TEMPLATES']:
    root['FILES']['input.tglf'] = OMFITgacode('input.tglf', fromString='')
    root['SCRIPTS']['runTGLF'].run()
    root['TEMPLATES']['gen'] = root['FILES']['input.tglf']

tmp1 = root['TEMPLATES']['gen']
tmp = root['FILES']['input.tglf'] = OMFITgacode('input.tglf', fromString='')

# run TGLF
tmp['NN_MAX_ERROR'] = -1000000

for k in harvest:
    if k in tmp1:
        tmp[k] = harvest[k]
        if k in ['SIGN_IT', 'SIGN_BT'] and isinstance(tmp[k], bool):
            tmp[k] = int(tmp[k]) * 2 - 1
        elif not isinstance(tmp[k], bool) and tmp[k] == int(tmp[k]):
            tmp[k] = int(tmp[k])
