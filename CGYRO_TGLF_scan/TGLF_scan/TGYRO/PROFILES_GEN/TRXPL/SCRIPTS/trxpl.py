# -*-Python-*-
# Created by grierson at 15 Aug 2015  11:41
#
# For debugging
# runid = '155196B06'
# time = 3.0
# avgtim = 0.1
# nzones = None

# Slow down per process_id when run in parallel to handle ssh connections
sleep(process_id)
shot = root['SETTINGS']['EXPERIMENT']['shot']
if TRANSP is not None:
    runid = str(TRANSP['SETTINGS']['PHYSICS']['TRANSPID'])
else:
    runid = str(shot) + str(root['SETTINGS']['EXPERIMENT']['runid'])

if 'None' in runid:
    raise OMFITexception('TRANSP runid cannot be None')

defaultVars(
    server=root['SETTINGS']['EXPERIMENT']['server'],
    tree=root['SETTINGS']['EXPERIMENT']['tree'],
    device=root['SETTINGS']['EXPERIMENT']['device'],
    time=root['SETTINGS']['EXPERIMENT']['time'],
    avgtim=root['SETTINGS']['EXPERIMENT']['avgtim'],
    nzones=root['SETTINGS']['EXPERIMENT']['nzones'],
    runid=runid,
)
time /= 1e3
avgtim /= 1e3

if server == None:
    if is_device(device, 'DIII-D'):
        server = 'atlas.gat.com'
    else:
        server = 'transpgrid.pppl.gov'
if (tree is None) and (server != 'CDF'):
    if server == 'atlas.gat.com':
        tree = 'transp'
    else:
        tree = 'transp_' + tokamak(device, 'TRANSP').lower()

# Form statefile name as state[runid]_[sec]x[ms].cdf
statefile = 'state{}_{}x{}'.format(runid, int(floor(time)), int(floor(time * 1e3 - floor(time) * 1e3)))

trxpl_in = []

if server != 'CDF':

    trxpl_in.append('M S %s' % server)  # Set the server
    trxpl_in.append('T %s ' % tree)  # Set the tree
    trxpl_in.append('D S %s ' % runid)  # Set the 'shot' as the runid, will convert A->01

    Bt_CW = '0'
    Ip_CW = '0'

else:

    RealNameFile = os.path.split(str(root['INPUTS'][runid]))[-1]

    if is_device(device, 'JET'):
        # special instructions for JET runs, which aren't stored in MDS+
        # https://github.com/PrincetonUniversity/TRANSPhub/issues/452#issuecomment-1846100668
        trxpl_in.append('Y')
        # get the year from the CDF
        yearstr = root['INPUTS'][runid]['_globals']['year']
        trxpl_in.append('JET/' + yearstr)
        trxpl_in.append('D')

    else:
        trxpl_in.append('P')  # provide full path

    trxpl_in.append('{}'.format(RealNameFile.split('.')[0]))

    Bt_CW = root['SETTINGS']['PHYSICS']['directionBT']
    Ip_CW = root['SETTINGS']['PHYSICS']['directionIp']

trxpl_in.append('A')  # accept
trxpl_in.append(str(time))  # Set time
trxpl_in.append(str(avgtim))  # Set avgerating time +/-
trxpl_in.append('151')  # Set number of theta points for 2D splines (equil)
trxpl_in.append('101')  # Set number of R points for cartesian grid (equil)
trxpl_in.append('101')  # Set number of Z points for cartesian grid (equil)
trxpl_in.append(str(Bt_CW))  # Set direction of torodial field CCW=1, CW = -1, READ = 0
trxpl_in.append(str(Ip_CW))  # Set direction of plasma current CCW=1, CW = -1, READ = 0
trxpl_in.append('Y')  # Accept these grid/field settings
trxpl_in.append('X')  # Extract plasma state
if nzones is not None:  # If re-zoning
    trxpl_in.append('N %d' % int(nzones))
trxpl_in.append('H')  # Exract "heavy" with equilibrium
trxpl_in.append('W')  # Write file
trxpl_in.append(statefile)  # Give filename
trxpl_in.append('Q')  # Exit from extraction
trxpl_in.append('Q')  # Exit run options
trxpl_in.append('Q')  # Exit trxpl

# Place the driver in the module inputs
root['INPUTS']['trxpl.in'] = OMFITascii('trxpl.in', fromString='\n'.join(trxpl_in))

# Inputs
if server != 'CDF':
    inputs = [root['INPUTS']['trxpl.in']]
else:
    inputs = [root['INPUTS']['trxpl.in'], (root['INPUTS'][runid], runid + '.CDF'), (root['INPUTS'][runid + 'TR'], runid + 'TR.DAT')]

# Outputs
outputs = ['{}.cdf'.format(statefile), '{}.geq'.format(statefile)]

# Set the executable
execstr = root['SETTINGS']['REMOTE_SETUP']['environment']
if is_device(device, 'JET'):
    dirstr = "JET/" + yearstr
    execstr = execstr + 'export ARCDIR=$(pwd)\nmkdir JET\nmkdir ' + dirstr + '\n'
    execstr = execstr + 'cp * ' + dirstr + '\n'

execstr = execstr + 'trxpl < trxpl.in'

print('Running TRXPL')

OMFITx.executable(root, inputs=inputs, outputs=outputs, executable=execstr)

# Place the statefile in the tree
root['OUTPUTS']['statefile'] = OMFITplasmastate('./{}.cdf'.format(statefile))
# Here we save the gEQDSK with forceFindSeparatrix=False because equilibria from TRXPL may have no proper X-point
# and this will make the fluxSurface separatrix routine to find the last flux surface that intersect with the wall

root['OUTPUTS']['gEQDSK'] = OMFITgeqdsk('./{}.geq'.format(statefile), forceFindSeparatrix=False)

try:
    if root['SETTINGS']['EXPERIMENT'].get('dWdt_correction', False) and server != 'CDF':
        statefile = root['OUTPUTS']['statefile']

        runid = int(statefile['RunID']['data'])
        pplasma = OMFITmdsValue(treename=tree, shot=runid, server=server, TDI='\\%s::TOP.OUTPUTS.TWO_D.PPLAS' % tree)
        rho = atleast_2d(pplasma.dim_of(0))[0]
        tvec = pplasma.dim_of(1)

        # total plasma pressure in Pa
        pplasma = pplasma.data()

        ind = (tvec > time - avgtim) & (tvec < time + avgtim)

        dp_dt = np.mean(np.diff(pplasma[ind], axis=0) / np.diff(tvec[ind])[:, None], 0)  # W/m^3

        rho_in = statefile['rho']['data']

        dp_dt = np.interp((rho_in[1:] + rho_in[:-1]) / 2, rho, dp_dt)
        dvol = np.diff(statefile['vol']['data'])

        # remove half of dp_dt from electrons and half from ions, assume that both represents half of the stored energy
        # the value is subsctracted from beam heating. If beam power is zero, it can results in negative values, but it will work fine.

        statefile['pbi']['data'] -= dvol * dp_dt / 2  # W
        statefile['pbe']['data'] -= dvol * dp_dt / 2  # W

        statefile['pe_trans']['data'] -= dvol * dp_dt / 2  # W
        statefile['pi_trans']['data'] -= dvol * dp_dt / 2  # W

        statefile.save()

except Exception as e:
    printe('dW/dt correction failed', e)
    raise
