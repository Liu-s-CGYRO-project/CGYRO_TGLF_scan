# -*-Python-*-
# Created by vaezip at Apr 17 2018 88:28

"""
This script is used to extract multiple state/g-files
"""

defaultVars(
    shot=root['SETTINGS']['EXPERIMENT']['shot'],
    runid=root['SETTINGS']['EXPERIMENT']['runid'],
    avgtim=root['SETTINGS']['EXPERIMENT']['avgtim'],
    trange=root['SETTINGS']['EXPERIMENT']['times'],
    calculate_mean=True,
    skip_loaded=False,
)

# Error check trange
if trange is None:
    printe("Must pass `trange` or set root['SETTINGS']['EXPERIMENT']['times']")
    OMFITx.End()
trange = atleast_1d(trange)
if 0 in trange.shape:
    printe('Must give multiple values for the trange parameter')
    OMFITx.End()

# create subtree if not there
root.setdefault('MULTI', OMFITcollection(sorted=True))
if not skip_loaded:
    root['MULTI'].clear()
else:
    # calculated statefiles only for missing timepoints
    trange = [t for t in trange if f'{shot}{runid}_{t}' not in root['MULTI']]
    if len(trange) == 0:
        OMFITx.End()

root["OUTPUTS"].clear()

nrun = len(trange)

# parallel run of various cases
results = root['SCRIPTS']['trxpl'].prun(
    len(trange),
    min([5, nrun]),
    'results',
    time=trange,
    postrun='results=root["OUTPUTS"]',
    runIDs=list(map(str, trange)),
    runid='%s%s' % (shot, runid),
    avgtim=avgtim,
)
for k, v in results.items():
    simID = '%d%s_%s' % (shot, runid, k)
    if not isinstance(v, OMFITtree) or not len(v):  # make sure all cases have data
        printe(f'TRXPL case {k} failed')
        continue
    root['MULTI'][simID] = v


if calculate_mean:
    nrun += 1
    # last case with mean of all sub-windows
    root['SETTINGS']['EXPERIMENT']['time'] = (max(trange) + min(trange)) / 2
    root['SETTINGS']['EXPERIMENT']['avgtim'] = (max(trange) - min(trange)) / 2
    root['SCRIPTS']['trxpl'].run(runid='%s%s' % (shot, runid))
    simID = str(shot) + str(runid) + 'mean'
    root['MULTI'][simID] = copy.deepcopy(root['OUTPUTS'])

root['MULTI'].sort()


# make sure all cases ran properly
if len(root['MULTI']) != nrun:
    raise OMFITexception('Not all TRXPL cases requested ran successfully')
