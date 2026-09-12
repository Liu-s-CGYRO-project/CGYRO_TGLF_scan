# -*-Python-*-
# Created by smithsp at 2014/06/18 23:37

outlines = []
for r in root.setdefault('scanResults', OMFITtree()):
    outlines.extend(['--', 'rho=%g' % (r)])
    for param in root['scanResults'][r]:
        outlines.extend(['**Scan of %s**' % param])

        header = '%20s' % ('Value,')
        line = ''
        for ri, (val, res) in enumerate(root['scanResults'][r][param].items()):
            line += '%20g,' % val
            species = res['.']
            for si, s in enumerate(species):
                for t in ('Gam/Gam_GB', 'Q/Q_GB', 'Q_low/Q_GB', 'Pi/Pi_GB', 'S/S_GB'):
                    if ri == 0:
                        header += '%20s,' % (s + ':' + t)
                    line += '%20g,' % res[t][si]
            line += '\n'
        outlines.append(header)
        outlines.append(line)

if 'output_scan_fn' in scratch and scratch['output_scan_fn']:
    with open(scratch['output_scan_fn'], 'w') as f:
        f.write('\n'.join(outlines))
else:
    print('\n'.join(outlines))
