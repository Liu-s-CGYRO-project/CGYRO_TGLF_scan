# -*-Python-*-
# Created by smithsp at 2013/11/07 15:41

OMFITx.TitleGUI('TGLF 参数与径向扫描')

root.setdefault('scanResults', OMFITtree())
root.setdefault('scanResults2D', OMFITtree())
root.setdefault('input.tglf', OMFITtree())
root.setdefault('tgyro_output', OMFITtree())

param = root['TGLF']['SETTINGS']['PHYSICS']['scanParameter']
param2 = root['TGLF']['SETTINGS']['PHYSICS']['scanParameter2D']


OMFITx.CheckBox(
    "root['SETTINGS']['PHYSICS']['tglf_input_load']",
    '载入 input.tglf（请先于 input.gacode 载入）',
    default=False,
    updateGUI=True,
    help='展开 input.tglf 文件选择界面，可载入新的输入文件。',
)

OMFITx.CheckBox(
    "root['SETTINGS']['PHYSICS']['tglf_settings_from_TGYRO']",
    '使用 TGYRO 中的 TGLF 参数设置页',
    default=False,
    updateGUI=True,
    help='勾选后使用 TGYRO 模块中的 TGLF 参数设置页。',
)

if not root['SETTINGS']['PHYSICS']['tglf_settings_from_TGYRO']:
    tglf_input_gui = root['TGLF']['GUIS']['TGLF_GUI']
    guis_loc = None  # this variable is not used in TGLF_GUI
    settings_loc_str = None
    inp_loc_tgyro_str = None
else:

    tglf_input_gui = root['TGLF']['GUIS']['TGLFfromTGYROgui']
    guis_loc = root['TGYRO']['GUIS']['TGLFinputGUI']
    settings_loc_str = treeLocation(root['TGYRO']['SETTINGS'])[-1]
    inp_loc_tgyro_str = treeLocation(root['TGYRO'])[-1]
    root['TGYRO']['SETTINGS']['PHYSICS']['Turb_Model'] = 'TGLF'


start_over = False
if 'input.gacode' in root['TGYRO']['PROFILES_GEN']['OUTPUTS'] or (
    'MULTI' in root['TGYRO']['PROFILES_GEN'] and len(root['TGYRO']['PROFILES_GEN']['MULTI'])
):

    def show_reset():
        OMFITx.Tab('准备输入剖面')
        if start_over:
            OMFITx.Button('重新开始', "root['TGYRO']['PROFILES_GEN']['SCRIPTS']['reset']")
        else:
            OMFITx.CompoundGUI(root['TGYRO']['PROFILES_GEN']['GUIS']['standaloneGUI'])

    # setup
    if not len(root['input.tglf']):
        root['TGYRO']['INPUTS']['input.tglf']['USE_TRANSPORT_MODEL'] = True
        OMFITx.Tab('准备 TGLF 输入文件')
        OMFITx.CompoundGUI(
            tglf_input_gui,
            inp_loc=treeLocation(root['TGYRO']['INPUTS']['input.tglf'])[-1],
            settings_loc_str=settings_loc_str,
            inp_loc_tgyro_str=inp_loc_tgyro_str,
            guis_loc=guis_loc,
            showLocalTab=False,
            showButtons=False,
            showNumSpecies=False,
        )
        if root['TGYRO']['PROFILES_GEN']['TRXPL']['SETTINGS']['EXPERIMENT']['multiwindow']:
            OMFITx.Button('生成 TGLF 输入', "root['SCRIPTS']['setup_batch_tglf']")
        else:
            OMFITx.Button('生成 TGLF 输入', "root['SCRIPTS']['setup_tglf']")
        show_reset()
        OMFITx.End()

    # -------------------------
    OMFITx.Tab('指定半径运行 TGLF')
    rho = root['SETTINGS']['PHYSICS']['rho']

    def show_single_rho():
        # Selecting a radius never overwrites the user's single-file input.
        rad_lab = 'rho' if root['TGYRO']['INPUTS']['input.tgyro']['TGYRO_USE_RHO'] else 'r/a'
        OMFITx.ComboBox(
            "root['SETTINGS']['PHYSICS']['rho']",
            sorted(root['input.tglf'].keys()),
            '半径（%s）' % rad_lab,
            default=0.5,
            updateGUI=True,
            state='normal',
        )
        OMFITx.Label('使用所选半径的输入。可在工程总控 → TGLF 中比较后将其用作单文件输入。')

    def show_tglf_detail():
        OMFITx.CheckBox("root['SETTINGS']['PHYSICS']['show_TGLF_details']", lbl='显示 TGLF 详细设置', default=False, updateGUI=True)
        if root['SETTINGS']['PHYSICS']['show_TGLF_details']:
            OMFITx.CompoundGUI(
                tglf_input_gui,
                inp_loc=treeLocation(root['input.tglf'][rho])[-1],
                guis_loc=guis_loc,
                showButtons=False,
                allowOptions=['TGLF', 'TGLF-NN'],
                title='',
                showLocalTab=False,
            )

    # -------------------------

    if rho in root['input.tglf']:
        OMFITx.ComboBox(
            "root['SETTINGS']['PHYSICS']['scanDimensions']",
            {'径向扫描': 0, '一维': 1, '二维': 2, '不确定度': 'UQ'},
            '扫描维数',
            default=0,
            updateGUI=True,
            state='readonly',
        )

    def showPlots():
        OMFITx.Separator()
        OMFITx.CheckBox("root['SETTINGS']['PHYSICS']['plot_mks']", '通量采用国际单位制', default=True)
        OMFITx.CheckBox("root['TGLF']['SETTINGS']['PHYSICS']['combine_ions']", '绘图时合并离子', default=True)
        OMFITx.CheckBox("root['SETTINGS']['PHYSICS']['tglf_sign_convention']", '采用 TGLF 动量目标的符号约定', default=True)
        OMFITx.CheckBox("root['SETTINGS']['PLOTS']['Use_x_log']", 'X 轴采用对数坐标', default=True)
        OMFITx.CheckBox("root['SETTINGS']['PLOTS']['Use_y_log']", 'Y 轴采用对数坐标', default=True)
        OMFITx.CheckBox("root['SETTINGS']['PLOTS']['Divided ky']", '绘制数值除以 ky 后的数据', default=True)
        OMFITx.Button('绘制 %d 维 TGLF 扫描' % root['SETTINGS']['PHYSICS']['scanDimensions'], "root['PLOTS']['plotScanAtRho'].runNoGUI")
        if root['SETTINGS']['PHYSICS']['scanDimensions'] == 1:
            OMFITx.Button('绘制一维 TGLF 扫描谱', "root['PLOTS']['plotScanSpecAtRho'].runNoGUI")
        OMFITx.Separator()
        OMFITx.Button(
            '导出 %d 维 TGLF 扫描数据' % root['SETTINGS']['PHYSICS']['scanDimensions'],
            lambda: root['PLOTS']['plotScanAtRho'].runNoGUI(doSave=True),
        )

    def showUQPlots():
        OMFITx.Separator()
        OMFITx.CheckBox("root['SETTINGS']['PHYSICS']['plot_mks']", '通量采用国际单位制', default=True)
        OMFITx.CheckBox("root['TGLF']['SETTINGS']['PHYSICS']['combine_ions']", '绘图时合并离子', default=True)
        OMFITx.CheckBox("root['SETTINGS']['PHYSICS']['tglf_sign_convention']", '采用 TGLF 动量目标的符号约定', default=True)
        OMFITx.CheckBox("root['SETTINGS']['PHYSICS']['exp_prob']", '绘制实验子时间窗概率', default=False)
        OMFITx.Button(
            '绘制 %d 维 TGLF 扫描不确定度传播' % root['TGLF']['SETTINGS']['PHYSICS']['scanDimensions'], "root['PLOTS']['plot_UQ'].runNoGUI"
        )

    # 1D scan
    if root['SETTINGS']['PHYSICS']['scanDimensions'] == 1 and rho in root['input.tglf']:
        start_over = True
        OMFITx.Tab('指定半径运行 TGLF')
        show_single_rho()
        show_tglf_detail()
        OMFITx.Tab('扫描设置')
        OMFITx.CompoundGUI(root['TGLF']['GUIS']['scanGUI'], showButtons=False, title='')
        OMFITx.Button('运行一维 TGLF 扫描', lambda: root['SCRIPTS']['runScanAtRho'].run(copy_inputTGLF_rho=False))

        if 'scanResults' in root and rho in root['scanResults'] and param in root['scanResults'][rho]:
            showPlots()

    # 2D scan
    elif root['SETTINGS']['PHYSICS']['scanDimensions'] == 2 and rho in root['input.tglf']:
        start_over = True
        OMFITx.Tab('指定半径运行 TGLF')
        show_single_rho()
        show_tglf_detail()
        OMFITx.Tab('扫描设置')
        OMFITx.CompoundGUI(root['TGLF']['GUIS']['scan2DGUI'], showButtons=False, title='')
        OMFITx.Button('运行二维 TGLF 扫描，半径：' + str(rho), lambda: root['SCRIPTS']['runScanAtRho'].run(copy_inputTGLF_rho=False))
        if 'scanResults2D' in root and rho in root['scanResults2D'] and param2 + '+' + param in root['scanResults2D'][rho]:
            showPlots()

    # UQ scan
    elif root['SETTINGS']['PHYSICS']['scanDimensions'] == 'UQ' and rho in root['input.tglf']:
        start_over = True
        OMFITx.Tab('指定半径运行 TGLF')
        show_single_rho()
        show_tglf_detail()
        OMFITx.Tab('不确定度扫描')
        # Move rho information to TGLF submodule
        root['TGLF']['SETTINGS']['PHYSICS']['rho'] = root['SETTINGS']['PHYSICS']['rho']
        OMFITx.CompoundGUI(root['TGLF']['GUIS']['uqGUI'], showButtons=False, title='')
        uqparam = root['TGLF']['SETTINGS']['PHYSICS']['scanParameters']  # Gets set in uqGUI
        OMFITx.Button('运行 TGLF 不确定度扫描', lambda: root['SCRIPTS']['runScanAtRho'].run(copy_inputTGLF_rho=False))
        if 'UQResults' in root and rho in root['UQResults'] and '_'.join(uqparam) in root['UQResults'][rho]:
            showUQPlots()

    elif root['SETTINGS']['PHYSICS']['scanDimensions'] == 0:
        OMFITx.CompoundGUI(root['GUIS']['tglf_radial_gui'])

    show_reset()
else:
    # this ensures a reset of the scans if the inputs of PROFILES_GEN have changed
    # (PROFILES_GEN will clear the outputs if its inputs change)
    root['SCRIPTS']['reset'].runNoGUI()

    OMFITx.Tab('准备输入剖面')
    OMFITx.CompoundGUI(root['TGYRO']['PROFILES_GEN']['GUIS']['standaloneGUI'])

    if root['SETTINGS']['PHYSICS']['tglf_input_load']:
        inp_loc = "root['TGYRO']['INPUTS']['input.tglf']"

        OMFITx.ObjectPicker(inp_loc, lbl='input.tglf 输入文件', objectType=OMFITgacode)
