# -*-Python-*-
# Created by grierson at 15 Aug 2015  13:26

OMFITx.TitleGUI('TRXPL：提取 TRANSP 等离子体状态')

if TRANSP is None:
    server = root['SETTINGS']['EXPERIMENT']['server']
    device = evalExpr(root['SETTINGS']['EXPERIMENT']['device'])
    if device is None:
        OMFITx.ShotTimeDevice()
        OMFITx.End()
    if server == None:
        if is_device(device, 'DIII-D'):
            server = 'atlas.gat.com'
        else:
            server = 'transpgrid.pppl.gov'
    tree = root['SETTINGS']['EXPERIMENT']['tree']
    if tree == None:
        if server in ['atlas.gat.com', 'alcdata-transp.psfc.mit.edu']:
            tree = 'transp'
        else:
            tree = 'transp_' + tokamak(device, 'TRANSP').lower()

    OMFITx.ComboBox(
        "root['SETTINGS']['EXPERIMENT']['server']",
        {
            'Auto (%s)' % server: None,
            'atlas.gat.com': 'atlas.gat.com',
            'transpgrid.pppl.gov': 'transpgrid.pppl.gov',
            'alcdata-transp.psfc.mit.edu': 'alcdata-transp.psfc.mit.edu',
            'CDF': 'CDF',
        },
        'Server',
        updateGUI=True,
        default=None,
        state='normal',
    )
    server = root['SETTINGS']['EXPERIMENT']['server']
    if server != 'CDF':
        OMFITx.ComboBox(
            "root['SETTINGS']['EXPERIMENT']['tree']",
            {'Auto (%s)' % tree: None, tree: tree},
            'Tree',
            updateGUI=True,
            default=None,
            state='normal',
        )
        OMFITx.Separator()
    else:
        root['SETTINGS']['EXPERIMENT']['tree'] = None

    OMFITx.ShotTimeDevice()
    if not is_device(device, 'CMOD'):
        _help = "TRANSP runID as either 'Z01' or '2601'"
        OMFITx.Entry("root['SETTINGS']['EXPERIMENT']['runid']", 'TRANSP 运行名称', default='Z01', updateGUI=True, help=_help)
        if not root['SETTINGS']['EXPERIMENT']['runid']:
            OMFITx.End()
    else:
        root['SETTINGS']['EXPERIMENT']['runid'] = ''

    OMFITx.Separator()
    if server == 'CDF':
        if TRANSP is not None:
            r = str(TRANSP['SETTINGS']['PHYSICS']['TRANSPID'])
        else:
            r = str(root['SETTINGS']['EXPERIMENT']['shot']) + str(root['SETTINGS']['EXPERIMENT']['runid'])
        OMFITx.ObjectPicker("root['INPUTS']['%s']" % r, '%s NetCDF file' % r, OMFITnc)
        OMFITx.ObjectPicker("root['INPUTS']['%sTR']" % r, '%s Namelist file' % r, OMFITnamelist)
        OMFITx.ComboBox(
            "root['SETTINGS']['PHYSICS']['directionBT']",
            {'Clockwise': -1, 'Counter-clockwise': 1},
            '环向磁场方向',
            default=-1,
            updateGUI=False,
        )
        OMFITx.ComboBox(
            "root['SETTINGS']['PHYSICS']['directionIp']",
            {'Clockwise': -1, 'Counter-clockwise': 1},
            '等离子体电流方向',
            default=1,
            updateGUI=False,
        )
else:
    OMFITx.Label('RunID: ' + TRANSP['SETTINGS']['PHYSICS']['TRANSPID'] + ' set by TRANSP dependency')
    OMFITx.ShotTimeDevice(showDevice=False, showShot=False, showTime=True)
OMFITx.Entry("root['SETTINGS']['EXPERIMENT']['avgtim']", '[+/-] avg [ms]', default=20, updateGUI=True)

with OMFITx.same_row():
    OMFITx.CheckBox("root['SETTINGS']['EXPERIMENT']['multiwindow']", '提取多个时间窗剖面', default=False, updateGUI=True)
    server = root['SETTINGS']['EXPERIMENT']['server']
    if server != 'CDF':
        OMFITx.CheckBox(
            "root['SETTINGS']['EXPERIMENT']['dWdt_correction']",
            '按 dW/dt 修正输入功率',
            default=False,
            updateGUI=False,
            help='Substract time derivative of pressure (dp/dt) from heating profile.\n Time evolution of pressure must be smooth',
        )


if root['SETTINGS']['EXPERIMENT']['multiwindow']:

    OMFITx.ShotTimeDevice(showShot=False, showDevice=False, multiTimes=True)
OMFITx.ComboBox(
    "root['SETTINGS']['EXPERIMENT']['nzones']", {'from TRANSP run': None}, '径向区域数', default=None, state='normal'
)

OMFITx.Separator()
if root['SETTINGS']['EXPERIMENT']['multiwindow']:
    OMFITx.Button('提取多个时间窗的等离子体状态', "root['SCRIPTS']['batch_trxpl']")
else:
    OMFITx.Button('提取等离子体状态', "root['SCRIPTS']['trxpl']")
