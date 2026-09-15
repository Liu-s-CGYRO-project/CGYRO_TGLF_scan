# -*-Python-*-
# Created by smithsp at 02 Sep 2015  21:39

OMFITx.TitleGUI('TGLF 参数设置')

defaultVars(
    inp_loc="root['FILES']['input.tglf']",
    guis_loc=None,
    settings_loc_str=None,  # need this only for TGLF settings from TGYRO GUI
    inp_loc_tgyro_str=None,
    showButtons=True,
    allowOptions=['TGLF', 'TGLF-NN', 'wavefunction'],
    showLocalTab=True,
    showNumSpecies=True,
)
try:
    input_tglf = eval(inp_loc)
except Exception:
    OMFITx.ObjectPicker(inp_loc, lbl='input.tglf 输入文件', objectType=OMFITgacode)
    OMFITx.End()
if 'USE_TRANSPORT_MODEL' not in input_tglf:
    OMFITx.Label('此页面需要有效的 TGLF 输入文件，通常为 input.tglf。')
    OMFITx.End()

options = {
    'TGLF-NN': ('使用神经网络模型计算通量', [True, 1e6]),
    'TGLF': ('计算增长率谱与通量', [True, -1.0]),
    'wavefunction': ('计算指定 ky 的本征函数', [False, -1.0]),
}

OMFITx.ComboBox(
    [inp_loc + "['USE_TRANSPORT_MODEL']", inp_loc + "['NN_MAX_ERROR']"],
    {options[k][0]: options[k][1] for k in allowOptions},
    'TGLF 计算模式',
    updateGUI=True,
    default=[True, -1.0],
)

if eval(inp_loc + "['USE_TRANSPORT_MODEL']") and eval(inp_loc + "['NN_MAX_ERROR']") > 0:
    for item in root['TEMPLATES']['input.tglf.nn']:
        OMFITx.Lock(inp_loc + "['%s']" % str(item), root['TEMPLATES']['input.tglf.nn'][item])


# GEOMETRY_FLAG tglf_geometry_flag_in geometry type (0=-, 1=Miller, 2=Fourier, 3=ELITE) 1
OMFITx.Tab('物理参数')
if showNumSpecies:
    OMFITx.Entry(inp_loc + "['NS']", lbl='物种总数（电子与离子）', default=2, check=is_int, updateGUI=True)
OMFITx.CheckBox(inp_loc + "['USE_BPER']", lbl='包含横向磁扰动（A∥）', default=True)
OMFITx.CheckBox(inp_loc + "['USE_BPAR']", lbl='包含压缩磁扰动（B∥）', default=True)
OMFITx.CheckBox(inp_loc + "['USE_MHD_RULE']", lbl='忽略压强梯度对曲率漂移的贡献（Phi）', default=False)
OMFITx.CheckBox(inp_loc + "['ADIABATIC_ELEC']", lbl='采用绝热电子', default=False)
OMFITx.ComboBox(
    inp_loc + "['SAT_RULE']",
    {'0': 0, '1': 1, '2': 2},
    lbl='饱和规则',
    updateGUI=True,
    default=1,
    help='''SAT0 - Spectral shift [Staebler 2013] and quasilinear weights from GYRO [Staebler 2007].
SAT1 - Spectral shift [Staebler 2013] and quasilinear weights from multiscale GYRO [Staebler 2017] or CGYRO [Staebler 2021].
SAT2 - Spectral shift [Staebler 2013] new collision model and quasilinear weights from CGYRO [Staebler 2021].''',
)
# These are deprecated parameters:
# OMFITx.Entry(inp_loc+"['XNU_MODEL']",
#  lbl="Collision model (2=new)",default=2,check=is_int)
# OMFITx.Entry(inp_loc+"['VPAR_MODEL']",
#  lbl="VPAR_MODEL (0=low-Mach-number limit)",default=0)
OMFITx.ComboBox(
    inp_loc + "['ALPHA_QUENCH']",
    {'采用湍流抑制规则': 1.0, '采用新的谱位移模型': 0.0},
    lbl='湍流抑制规则',
    default=0.0,
)
OMFITx.ComboBox(inp_loc + "['SIGN_BT']", [1, -1], lbl='Bt 符号（俯视逆时针为正）', default=1)
OMFITx.ComboBox(inp_loc + "['SIGN_IT']", [1, -1], lbl='It 符号（俯视逆时针为正）', default=1)

OMFITx.Tab('数值参数')
OMFITx.CheckBox(inp_loc + "['USE_BISECTION']", lbl='用二分法寻找使增长率最大的模态宽度', default=True)
# Not relevant
# OMFITx.CheckBox(inp_loc+"['NEW_EIKONAL']",
#  lbl="Recompute the eikonal, (unclicking means to use the eikonal computed "
#  "on the last call to TGLF made with NEW_EIKONAL set)", default=True)
OMFITx.CheckBox(inp_loc + "['IFLUX']", lbl='计算准线性权重与模态幅度', default=True)


def check_nky(s):
    if not is_int(s):
        return False
    maxky0 = 480
    if s > maxky0:
        printe('For the user defined ky spectrum, the max number of NKY is ' + str(maxky0))
        return False
    else:
        return True


if not input_tglf['USE_TRANSPORT_MODEL']:
    OMFITx.Entry(inp_loc + "['KY']", 'TGLF 单模态计算的 k_y', default=0.3)
else:
    OMFITx.ComboBox(
        inp_loc + "['KYGRID_MODEL']",
        {'输运模型的标准 ky 谱': 1, '自定义等间距 ky 网格（NKY 个点，最大值 KY）': 0},
        lbl='ky 网格模型',
        default=1,
        updateGUI=True,
    )
    if input_tglf['KYGRID_MODEL'] == 0:
        OMFITx.Entry(inp_loc + "['KY']", lbl='自定义 ky 网格最大值', default=0.3)
        OMFITx.Entry(inp_loc + "['NKY']", lbl='自定义 ky 网格点数', default=12, check=check_nky)
    else:
        OMFITx.Entry(inp_loc + "['NKY']", lbl='TGLF_TM 高 k 谱的极向模态数', default=12, check=is_int)

    def set_nky(location=None):
        if location is None:
            return
        ibranch = eval(location)
        if ibranch in [-1]:
            input_tglf['NMODES'] = 2

    OMFITx.ComboBox(
        inp_loc + "['IBRANCH']",
        {
            "Find two most unstable modes; one for each sign of frequency": 0,
            # Remove these two options, because TGLF does not seem to do as directed
            # "Find most unstable positive frequency mode (electron drift direction)":1,
            # "Find most unstable negative frequency mode (ion drift direction)":2,
            "Sort the unstable modes by growthrate in rank order": -1,
        },
        lbl='模态选择',
        default=-1,
        updateGUI=True,
        postcommand=set_nky,
    )
    if input_tglf['IBRANCH'] == -1:
        OMFITx.Entry(inp_loc + "['NMODES']", lbl='保存的不稳定模态数', default=2, check=is_int)
# Note to self, add NMODES =2 for ibranch=0 for linear run, check for ibranch behavior

OMFITx.Entry(inp_loc + "['NBASIS_MIN']", lbl='平行基函数最小数量', default=2, check=is_int)
OMFITx.Entry(inp_loc + "['NBASIS_MAX']", lbl='平行基函数最大数量', default=4, check=is_int)
OMFITx.Entry(inp_loc + "['NXGRID']", lbl='Gauss–Hermite 求积节点数', default=16, check=is_int)

# Convert to on/off
OMFITx.Tab('物理模型开关')
OMFITx.CheckBox(inp_loc + "['ALPHA_P']", lbl='包含所有物种的平行速度剪切', default=1.0, mapFalseTrue=[0.0, 1.0])
OMFITx.CheckBox(inp_loc + "['ALPHA_E']", lbl='谱位移模型包含 E×B 速度剪切', default=1.0, mapFalseTrue=[0.0, 1.0])
OMFITx.CheckBox(
    inp_loc + "['XNU_FACTOR']",
    lbl='包含俘获 / 通行边界的电子–离子碰撞项',
    default=1.0,
    mapFalseTrue=[0.0, 1.0],
)
OMFITx.CheckBox(inp_loc + "['DEBYE_FACTOR']", lbl='包含德拜长度项', default=1.0, mapFalseTrue=[0.0, 1.0])

if showLocalTab:
    OMFITx.Tab('局部参数')
    OMFITx.Entry(
        inp_loc + "['VEXB_SHEAR']",
        lbl='所有物种共用的归一化环向 E×B 多普勒频移梯度（大 E×B 速度排序）',
        default=0.0,
    )
    OMFITx.Entry(inp_loc + "['BETAE']", lbl='以 B_unit 定义的电子 β', default=0.0)
    OMFITx.Entry(inp_loc + "['XNUE']", lbl='电子–离子碰撞频率 / (c_s/a)', default=0.0)
    OMFITx.Entry(inp_loc + "['ZEFF']", lbl='有效离子电荷数 Zeff', default=1.0)
    OMFITx.Entry(inp_loc + "['DEBYE']", lbl='德拜长度 / 回旋半径', default=0.0)
    OMFITx.ComboBox(
        "scratch['tglf_species_num']", list(range(1, input_tglf['NS'] + 1)) + ['all'], lbl='显示物种', default=1, updateGUI=True
    )
    if scratch['tglf_species_num'] == 'all':
        spec_nums = list(range(1, input_tglf['NS'] + 1))

    else:
        spec_nums = [scratch['tglf_species_num']]
    for spec_num in spec_nums:
        OMFITx.Entry(inp_loc + "['ZS_%s']" % spec_num, lbl="Species #%s Charge number (Z)" % spec_num, default=1)
        OMFITx.Entry(inp_loc + "['MASS_%s']" % spec_num, lbl="Species #%s Mass / Deuterium Mass" % spec_num, default=1)
        OMFITx.Entry(inp_loc + "['RLNS_%s']" % spec_num, lbl="Species #%s Normalized density gradient -(a/n)(dn/dr)" % spec_num, default=1)
        OMFITx.Entry(
            inp_loc + "['RLTS_%s']" % spec_num, lbl="Species #%s Normalized temperature gradient -(a/n)(dT/dr)" % spec_num, default=3
        )
        OMFITx.Entry(inp_loc + "['TAUS_%s']" % spec_num, lbl="Species #%s Temperature / Te" % spec_num, default=1)
        OMFITx.Entry(inp_loc + "['AS_%s']" % spec_num, lbl="Species #%s Density / ne" % spec_num, default=1)
        OMFITx.Entry(
            inp_loc + "['VPAR_%s']" % spec_num, lbl="Species #%s Parallel velocity sign(It)(R_maj V_tor/R)(a/c_s)" % spec_num, default=0
        )
        OMFITx.Entry(
            inp_loc + "['VPAR_SHEAR_%s']" % spec_num,
            lbl="Species #%s Parallel velocity shear -sign(It)R_maj(d/dr(V_tor/R))(a/c_s)" % spec_num,
            default=0,
        )

# Provide means of scaling one variable with another
OMFITx.Tab("Constraints")
OMFITx.CompoundGUI(root['GUIS']['constraints_GUI'], input_tglf=input_tglf, title='')

if showButtons:
    # Run
    OMFITx.Tab("")
    OMFITx.Separator()
    if input_tglf['USE_TRANSPORT_MODEL']:
        OMFITx.Button('运行 TGLF 计算通量', "root['SCRIPTS']['runTGLF']")
        if 'eigenvalue_spectrum' in root['FILES']:
            OMFITx.Button('绘制本征值谱', "root['FILES']['eigenvalue_spectrum'].plotFigure")
            OMFITx.Button('绘制离散谱', "root['PLOTS']['plotSpectrumDiscrete']")
    else:
        OMFITx.Button('运行 TGLF 计算本征函数', "root['SCRIPTS']['runTGLFlinear']")
        if 'wavefunction' in root['FILES']:
            OMFITx.Button('绘制本征函数', "root['FILES']['wavefunction'].plot")
