# -*-Python-*-
# Created by meneghini at 02 May 2017  12:26

"""
This script is used to extract multiple state/g-files
"""

defaultVars(sims=None, discard_first_dtime=200, discard_last_dtime=0)


if TRANSP is not None:
    default_runid = str(TRANSP['SETTINGS']['PHYSICS']['TRANSPID'])
else:
    default_runid = str(root['SETTINGS']['EXPERIMENT']['shot']) + str(root['SETTINGS']['EXPERIMENT']['runid'])

if sims is None:
    raise OMFITexception(
        '''
Specify data to extract with the `sim` dictionary using the format:

sims={}
sims[0]={'runid':'1633030104',
         'time':5000,
         'avgtim':25
         }
sims[1]={'runid':'1633030104',
         'time':None}

possible keywords:
    device, server, tree, time, avgtim, nzones, runid

If time==None, then time-slices separated by 2*avgtim will be extracted

'''
    )

root.setdefault('MULTI', OMFITtree())

run_sim = OrderedDict()

for sim in sims.values():

    device = sim.get('device', root['SETTINGS']['EXPERIMENT']['device'])
    server = sim.get('server', root['SETTINGS']['EXPERIMENT']['server'])
    tree = sim.get('tree', root['SETTINGS']['EXPERIMENT']['tree'])
    times = sim.get('time', root['SETTINGS']['EXPERIMENT']['time'])
    avgtim = sim.get('avgtim', root['SETTINGS']['EXPERIMENT']['avgtim'])
    nzones = sim.get('nzones', root['SETTINGS']['EXPERIMENT']['nzones'])
    runid = sim.get('runid', default_runid)

    if evalExpr(server) is None:
        if is_device(device, 'DIII-D'):
            server = 'atlas.gat.com'
        else:
            server = 'transpgrid.pppl.gov'
    if evalExpr(tree) is None:
        if server == 'atlas.gat.com':
            tree = 'transp'
        else:
            tree = 'transp_' + tokamak(device, 'TRANSP').lower()

    if times is None:
        times = (
            OMFITmdsValue(treename=tree, TDI='\\%s::TOP.OUTPUTS.ONE_D.LI_3' % tree, shot=runid, quiet=False, server=server).dim_of(0) * 1000
        )
        times = flipud(arange(max(times) - discard_last_dtime, min(times) + discard_first_dtime, -avgtim))
    print('*' * 10)
    print('%s %s' % (device, runid))
    print('*' * 10)

    times = tolist(times)
    for time in times:
        time = int(time)
        print('@ %s' % time)

        identifier = '%s_%s_%d' % (tokamak(device, 'TRANSP'), runid, time)

        if identifier in root['MULTI']:
            print('%s already present' % identifier)
            continue

        run_sim[identifier] = dict(device=device, server=server, tree=tree, time=time, avgtim=avgtim, nzones=nzones, runid=runid)


def dict_array(d):
    da = d.__class__()
    for k in list(d.values())[0].keys():
        da[k] = []
    for k in da:
        for item in d.values():
            da[k].append(evalExpr(item[k]))
    for k in da:
        da[k] = array(da[k])
    return da


if len(run_sim):
    results = root['SCRIPTS']['trxpl'].prun(
        len(run_sim), 10, 'results', postrun="results=root['OUTPUTS']", runIDs=list(run_sim.keys()), **dict_array(run_sim)
    )

    root['MULTI'].update(results)

root['MULTI'].sort()
