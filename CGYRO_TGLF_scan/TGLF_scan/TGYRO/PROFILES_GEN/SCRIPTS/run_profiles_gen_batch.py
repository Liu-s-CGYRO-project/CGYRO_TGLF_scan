# -*-Python-*-
# Created by vaezip at 2018/04/11 12:59

times = root['SETTINGS']['EXPERIMENT']['times']
# Set up given TRXPL
if root['SETTINGS']['PHYSICS']['use_trxpl']:
    if 'MULTI' not in root['TRXPL'] or not len(root['TRXPL']['MULTI']):
        printe('Must create multi-time window run of TRXPL first')
        OMFITx.End()

    shot = root['TRXPL']['SETTINGS']['EXPERIMENT']['shot']
    runid = root['TRXPL']['SETTINGS']['EXPERIMENT']['runid']
    runIDs = [f'{shot}{runid}_{t}' for t in times]

    MULTI = root['TRXPL']['MULTI']
    gfiles = [MULTI['gEQDSK'][rid] for rid in runIDs]
    statefiles = [MULTI['statefile'][rid] for rid in runIDs]
else:
    if ONETWOtime is None or EFITtime is None:
        raise OMFITexception('Must define the ONETWOtime and EFITtime dependencies')
    if not len(EFITtime.get('OUTPUTS', {}).get('gEQDSK', {})):
        raise OMFITexception('No EFIT gfiles in EFITtime dependency')
    if not len(ONETWOtime.get('OUTPUTS', {}).get('statefiles', {})):
        raise OMFITexception('No ONETWO statefiles in ONETWOtime dependency')

    gfiles = [EFITtime['OUTPUTS']['gEQDSK'][t] for t in times]
    statefiles = [ONETWOtime['OUTPUTS']['statefiles'][t] for t in times]

    if len(gfiles) != len(statefiles):
        raise OMFITexception('Different number of gfiles and statefiles')

    if any([g is None for g in gfiles]) or any([s is None for s in statefiles]):
        raise OMFITexception('Some required statefiles of gfiles were not found')

    runIDs = times


server = root['SETTINGS']['REMOTE_SETUP']['serverPicker']
if is_server(server, 'engaging'):
    ntasks = 2
elif is_server(server, 'portal'):
    ntasks = 16
else:
    ntasks = 5

# Do prun

root['OUTPUTS'].clear()
results = root['SCRIPTS']['run_profiles_gen'].prun(
    len(runIDs),
    min(ntasks, len(runIDs)),
    'results',
    runIDs=runIDs,
    gEQDSK=gfiles,
    profpowbal=statefiles,
    postrun='results=root["OUTPUTS"]',
    result_type=OMFITcollection,
)

results.sorted = True
root['MULTI'] = results
