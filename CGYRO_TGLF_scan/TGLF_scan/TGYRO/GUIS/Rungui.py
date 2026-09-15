# -*-Python-*-
# Created by thomek at 27 Sep 2016  16:15

OMFITx.TitleGUI('TGYRO 运行设置')

from OMFITlib_general import fit_ne_EPED1

defaultVars(showRunLoadButtons=True)

if not showRunLoadButtons:
    OMFITx.CheckBox("root['SETTINGS']['PHYSICS']['reload']", '读取已有结果', updateGUI=True)

root.setdefault('RUN_DB', OMFITtree())

max_nions = 10
if input_gacode is not None:
    max_nions = len(input_gacode['IONS'])

if 'output' not in root['OUTPUTS']:
    OMFITx.Lock("root['INPUTS']['input.tgyro']['LOC_RESTART_FLAG']", 0)

if not root['SETTINGS']['PHYSICS']['reload']:

    OMFITx.Tab('输入剖面')
    if root['INPUTS']['input.tgyro']['LOC_RESTART_FLAG']:
        OMFITx.Lock("root['SETTINGS']['PHYSICS']['runPROFILES_GEN']", False)
        OMFITx.Label('续算：使用上次计算的剖面')
    else:
        txt = "Update input profiles"
        if input_gacode is None:
            OMFITx.Lock("root['SETTINGS']['PHYSICS']['runPROFILES_GEN']", True)
            txt = "Generate input profiles"
        OMFITx.CheckBox("root['SETTINGS']['PHYSICS']['runPROFILES_GEN']", txt, updateGUI=True)
        if root['SETTINGS']['PHYSICS']['runPROFILES_GEN']:
            OMFITx.CompoundGUI(PROFILES_GEN['GUIS']['vgenGUI'], allowEPED=True, showRunButton=True)

    # Geometry
    OMFITx.Tab('Geometry')

    from OMFITlib_general import radii, setup_radii

    root['INPUTS']['input.tgyro'].setdefault('TGYRO_USE_RHO', 0)
    if PROFILES_GEN and PROFILES_GEN['SETTINGS']['PHYSICS']['blendEPED']:
        if PROFILES_GEN['SETTINGS']['PHYSICS']['rho_nml'] > PROFILES_GEN['SETTINGS']['PHYSICS']['rho_core']:
            OMFITx.Lock("root['INPUTS']['input.tgyro']['TGYRO_RMIN']", PROFILES_GEN['SETTINGS']['PHYSICS']['rho_core'])
            OMFITx.Lock("root['INPUTS']['input.tgyro']['TGYRO_RMAX']", PROFILES_GEN['SETTINGS']['PHYSICS']['rho_nml'])
        OMFITx.Lock("root['INPUTS']['input.tgyro']['TGYRO_USE_RHO']", 1)

    r_str = ['r/a', 'rho'][root['INPUTS']['input.tgyro']['TGYRO_USE_RHO']]
    OMFITx.CheckBox("root['INPUTS']['input.tgyro']['TGYRO_USE_RHO']", '使用 rho 坐标', updateGUI=True, useInt=True)
    with OMFITx.same_row():
        OMFITx.ComboBox(
            "root['SETTINGS']['PHYSICS']['radial_distribution']",
            {'Uniform r': 'uniform_r', 'Uniform z': 'uniform_z', 'Variation z': 'variation_z', 'User': 'user'},
            '径向分布',
            postcommand=lambda location: setup_radii(),
            default='uniform_r',
            updateGUI=True,
        )
        OMFITx.Button('绘制径向分布', lambda: radii(doPlot=True))

    if root['SETTINGS']['PHYSICS']['radial_distribution'] == 'user':
        OMFITx.Entry("root['SETTINGS']['PHYSICS']['radii']", 'Radii', postcommand=lambda location: setup_radii(), updateGUI=True)
    else:
        OMFITx.Entry(
            "root['SETTINGS']['PHYSICS']['n_rad']",
            '半径数量',
            postcommand=lambda location: setup_radii(),
            default=8,
            updateGUI=True,
            check=is_int,
        )
        rho_min = {}
        if input_gacode is not None:
            tmp = input_gacode['rho'][where(abs(input_gacode['q']) <= 1.0)]
            if len(tmp):
                rho_min = {'at inversion radius (rho=%2.2f)' % max(tmp): eval('%2.2f' % max(tmp))}
        if len(rho_min):
            OMFITx.ComboBox(
                "root['INPUTS']['input.tgyro']['TGYRO_RMIN']",
                rho_min,
                'From %s' % r_str,
                updateGUI=True,
                state='nonrmal',
                postcommand=lambda location: setup_radii(),
            )
        else:
            OMFITx.Entry(
                "root['INPUTS']['input.tgyro']['TGYRO_RMIN']", 'From %s' % r_str, updateGUI=True, postcommand=lambda location: setup_radii()
            )
        OMFITx.Entry(
            "root['INPUTS']['input.tgyro']['TGYRO_RMAX']", 'To %s' % r_str, updateGUI=True, postcommand=lambda location: setup_radii()
        )

    # equilibrium
    n_rad = root['SETTINGS']['PHYSICS']['n_rad']
    rmin = eval("root['INPUTS']['input.tgyro']['TGYRO_RMIN']")
    rmax = eval("root['INPUTS']['input.tgyro']['TGYRO_RMAX']")
    r = linspace(rmax, rmin, n_rad)
    fix_r_choices = SortedDict()
    for ri, rad in enumerate(r):
        fix_r_choices.update({'%2.2f' % rad: ri})

    # this option is not supported in TGYRO any more
    # OMFITx.ComboBox("root['INPUTS']['input.tgyro']['LOC_BC_OFFSET']", fix_r_choices, lbl='Fixed Point', default=0)

    # Evolution
    OMFITx.Tab('演化设置')
    OMFITx.CheckBox("root['INPUTS']['input.tgyro']['LOC_EVOLVE_GRAD_ONLY_FLAG']", '仅修改梯度', useInt=True, default=0)
    OMFITx.Separator('Temperatures')
    OMFITx.CheckBox("root['INPUTS']['input.tgyro']['LOC_TE_FEEDBACK_FLAG']", '演化电子温度 Te', useInt=True)
    OMFITx.CheckBox("root['INPUTS']['input.tgyro']['LOC_TI_FEEDBACK_FLAG']", '演化离子温度 Ti', useInt=True)
    # Density evolution

    for i in range(max_nions):
        root['INPUTS']['input.tgyro'].setdefault('TGYRO_DEN_METHOD' + str(i + 1), 0)

    # This assumes standard TGYRO_SE_SCALEx, i.e. electrons 1 and ions all to 0
    def reset_density_evolve():
        root['INPUTS']['input.tgyro']['TGYRO_DEN_METHOD0'] = 1
        for i in range(max_nions):
            ion_z = input_gacode['IONS'][i + 1][1]
            ion_type = input_gacode['IONS'][i + 1][3]
            if ion_type == 'therm' and ion_z == 1:
                root['INPUTS']['input.tgyro']['TGYRO_DEN_METHOD' + str(i + 1)] = -1
            else:
                root['INPUTS']['input.tgyro']['TGYRO_DEN_METHOD' + str(i + 1)] = 0

    def save_density_evolve(location=None, was_denevo=False):

        if root['SETTINGS']['PHYSICS']['evolve_density'] and was_denevo:
            scratch['density_evolve'] = SortedDict()
            scratch['density_evolve']['e'] = root['INPUTS']['input.tgyro']['TGYRO_DEN_METHOD0']
            for i, ion_name in enumerate(input_gacode.ion_names(), 1):
                scratch['density_evolve'][ion_name] = root['INPUTS']['input.tgyro']['TGYRO_DEN_METHOD' + str(i)]

        elif root['SETTINGS']['PHYSICS']['evolve_density']:
            try:
                if 'density_evolve' in scratch:
                    root['INPUTS']['input.tgyro']['TGYRO_DEN_METHOD0'] = scratch['density_evolve']['e']
                    for i, ion_name in enumerate(input_gacode.ion_names(), 1):
                        root['INPUTS']['input.tgyro']['TGYRO_DEN_METHOD' + str(i)] = scratch['density_evolve'][ion_name]
                else:
                    reset_density_evolve()
            except Exception:
                if 'density_evolve' in scratch:
                    del scratch['density_evolve']
                reset_density_evolve()

    if root['SETTINGS']['PHYSICS']['evolve_density'] == -33:
        reset_density_evolve()

    if 'was_denevo' in scratch:
        save_density_evolve(was_denevo=scratch['was_denevo'])
    else:
        save_density_evolve(was_denevo=False)

    scratch['was_denevo'] = copy.deepcopy(root['SETTINGS']['PHYSICS']['evolve_density'])

    OMFITx.Separator('Density')

    OMFITx.CheckBox(
        "root['SETTINGS']['PHYSICS']['evolve_density']",
        '演化密度',
        updateGUI=True,
        default=True,
        help='The default is recommended; select d to use.',
    )

    if root['SETTINGS']['PHYSICS']['evolve_density']:
        den_options = SortedDict()
        den_options['-1: Species used to enforce quasineutrality'] = -1
        den_options[' -2: Species given same shape as electron density profile (with pivot density ratio)'] = -2
        den_options[' 0: Species locked'] = 0
        den_options[' 1: Species evolved to match target density flux'] = 1

        ion_names = input_gacode.ion_names()

        if 'DT' in ion_names or ('D' in ion_names and 'T' in ion_names):
            den_options[' 2: Species evolved with alpha particles from DT reaction as source'] = 2
        OMFITx.ComboBox("root['INPUTS']['input.tgyro']['TGYRO_DEN_METHOD0']", den_options, lbl='Electrons', updateGUI=True)
        numd_ion_names = input_gacode.ion_names()
        if any([True for k in tolist(numd_ion_names, [None]) if k]):
            for k in range(max_nions):
                OMFITx.ComboBox(
                    "root['INPUTS']['input.tgyro']['TGYRO_DEN_METHOD{}']".format(k + 1), den_options, lbl=numd_ion_names[k], updateGUI=True
                )
        else:
            OMFITx.Label('其他离子物种的密度演化请在 PROFILES_GEN 中设置。', align='left', foreground='red')
    else:
        for k in range(max_nions + 1):
            # Lock electrons (0) and every ion (1..max_nions).
            den_str = 'TGYRO_DEN_METHOD' + str(k)
            root['INPUTS']['input.tgyro'][den_str] = 0

    OMFITx.Separator('电场与旋转')
    OMFITx.CheckBox("root['INPUTS']['input.tgyro']['LOC_ER_FEEDBACK_FLAG']", '演化径向电场 Er', useInt=True, updateGUI=True, default=0)
    er_bc_choices = SortedDict()
    for k, v in [('Input omega0\'', 1), ('omega0\'=0', 2), ('omega0\'\'=0', 3)]:
        er_bc_choices[k] = v
    if eval("root['INPUTS']['input.tgyro']['LOC_ER_FEEDBACK_FLAG']") == 1:
        OMFITx.ComboBox("root['INPUTS']['input.tgyro']['TGYRO_ER_BC']", er_bc_choices, lbl='r=0 处电场边界条件')

    # pedestal
    if (
        is_device(root['SETTINGS']['EXPERIMENT']['device'], ['DIII-D', 'ITER', 'JET', 'KSTAR'])
        and 'IP_EXP' in input_gacode
        and 'RVBV' in input_gacode
    ):
        text_color = 'black'
    elif root['INPUTS']['input.tgyro']['TGYRO_PED_MODEL'] == 2:
        text_color = 'red'
    elif 'IP_EXP' in input_gacode and 'RVBV' in input_gacode:
        text_color = 'black'
    else:
        text_color = 'red'

    OMFITx.Separator('Pedestal')
    OMFITx.CheckBox(
        "root['INPUTS']['input.tgyro']['TGYRO_PED_MODEL']",
        '台基演化',
        mapFalseTrue=[1, 2],
        default=1,
        updateGUI=True,
        foreground=text_color,
        help=(
            "Use EPED1-NN model to perform dynamic pedestal calculation. \n"
            "This model has been calibrated to work for DIII-D and ITER, and to a lesser degree JET and KSTAR.\n"
            "Also to work the input.gacode file must have the IP_EXP and RVBV fields. \n"
            "If text red, EPED_NN is not compatible with device, uncheck ped evolution or run full EPED."
        ),
    )
    if eval("root['INPUTS']['input.tgyro']['TGYRO_PED_MODEL']") == 2:

        def fit_ped(location=None, updateGUI=True):
            try:
                data = fit_ne_EPED1(debug_plot=updateGUI)
            except Exception as _excp:
                if updateGUI is False:
                    fit_ne_EPED1(debug_plot=True)
                printe(repr(_excp))
                return
            if root['INPUTS']['input.tgyro']['TGYRO_NEPED'] == 0:
                root['INPUTS']['input.tgyro']['TGYRO_NEPED'] = data['ne_ped']
            if root['INPUTS']['input.tgyro']['TGYRO_ZEFFPED'] == 0:
                root['INPUTS']['input.tgyro']['TGYRO_ZEFFPED'] = data['zeff_ped']
            if updateGUI:
                OMFITx.UpdateGUI()

        if root['INPUTS']['input.tgyro']['TGYRO_ZEFFPED'] == 0 or root['INPUTS']['input.tgyro']['TGYRO_NEPED'] == 0:
            fit_ped(updateGUI=False)
        options = {'from input.gacode at rho=%3.3f' % -k: k for k in -linspace(0.91, 0.99, 17)}
        options['from EPED1 profiles fit of input.gacode'] = 0
        OMFITx.ComboBox(
            "root['INPUTS']['input.tgyro']['TGYRO_NEPED']",
            options,
            '台基密度（10¹⁹）',
            state='normal',
            default=-0.95,
            help='* negative values indicate radial location where to evaluate\n'
            '  the pedestal density based on the input profiles\n\n'
            '* positive values indicate actual density in 1E19 [m^-3]',
            postcommand=fit_ped,
        )
        OMFITx.ComboBox(
            "root['INPUTS']['input.tgyro']['TGYRO_ZEFFPED']",
            options,
            '台基 Zeff',
            state='normal',
            default=2.0,
            help='* negative values indicate radial location where to evaluate\n'
            '  the pedestal density based on the input profiles\n\n'
            '* positive values indicate actual Z_eff',
            postcommand=fit_ped,
        )

    # Solver controls
    OMFITx.Tab('求解器设置')
    if 'output' in root['OUTPUTS']:
        OMFITx.CheckBox("root['INPUTS']['input.tgyro']['LOC_RESTART_FLAG']", '重新启动计算', useInt=True, updateGUI=True)
        OMFITx.Separator()
    OMFITx.Entry("root['INPUTS']['input.tgyro']['TGYRO_RELAX_ITERATIONS']", '迭代次数', updateGUI=True)

    # Required because Serial Block only works with >0 iterations
    if root['INPUTS']['input.tgyro']['TGYRO_RELAX_ITERATIONS'] == 0:
        root['INPUTS']['input.tgyro']['TGYRO_ITERATION_METHOD'] = 1

    iteration_method_options = {'1: Standard Iteration': 1, '2: Diagonal': 2, '4: Serial Block': 4, '5: Parallel Block': 5, '6: Simple': 6}

    def set_residual(location):
        if eval(location) == 6:
            root['INPUTS']['input.tgyro']['LOC_RELAX'] = 0.1
        elif eval(location) == 2:
            root['INPUTS']['input.tgyro']['LOC_RELAX'] = 1.0
        else:
            root['INPUTS']['input.tgyro']['LOC_RELAX'] = 2.0

    OMFITx.ComboBox(
        "root['INPUTS']['input.tgyro']['TGYRO_ITERATION_METHOD']",
        iteration_method_options,
        lbl='迭代方法',
        postcommand=set_residual,
        updateGUI=True,
    )
    residual_method_options = {'|f-g|': 2, '(f-g)^2': 3, '(f-g)^2/MAX(1,(f^2+g^2))': 4}
    OMFITx.ComboBox("root['INPUTS']['input.tgyro']['LOC_RESIDUAL_METHOD']", residual_method_options, lbl='残差方法')
    OMFITx.Entry(
        "root['INPUTS']['input.tgyro']['TGYRO_RESIDUAL_TOL']",
        '残差容限',
        default=0.0,
        delete_if_default=True,
        help='Use the residual tolerance to set a residual threshold after which TGYRO can stop iterating and exit.\n'
        'The default value is 0 such that TGYRO performs the specied number of iterations.',
    )
    OMFITx.Entry("root['INPUTS']['input.tgyro']['LOC_DX']", '雅可比步长')
    OMFITx.Entry("root['INPUTS']['input.tgyro']['LOC_DX_MAX']", '最大步长')
    OMFITx.Entry("root['INPUTS']['input.tgyro']['LOC_RELAX']", '松弛参数')
    OMFITx.Entry("root['SETTINGS']['SETUP']['n_cpu_rad']", '每个输运模型实例的进程数', check=is_int)

    # Profiles
    if not eval("root['INPUTS']['input.tgyro']['LOC_RESTART_FLAG']"):
        OMFITx.Tab('参数缩放')
        for name, desc in [
            ('DEN', 'Density'),
            ('TE', 'Te'),
            ('TI', 'Ti'),
            ('W0', 'omega0'),
            ('PAUX', 'Auxiliary Power'),
            ('FUSION', 'Fusion Power'),
        ]:
            OMFITx.Entry("root['INPUTS']['input.tgyro']['TGYRO_INPUT_%s_SCALE']" % name, 'Scale %s' % desc, default=1.0)
        OMFITx.Entry("root['INPUTS']['input.tgyro']['LOC_BETAE_SCALE']", '缩放电子 β', default=1.0)
        OMFITx.Entry("root['INPUTS']['input.tgyro']['LOC_ME_MULTIPLIER']", '缩放电子质量', default=1.0)
        OMFITx.Entry("root['INPUTS']['input.tgyro']['LOC_NU_SCALE']", '缩放碰撞频率', default=1.0)
        if eval("root['INPUTS']['input.tgyro']['TGYRO_PED_MODEL']") == 2:
            OMFITx.Separator()
            OMFITx.Entry("root['INPUTS']['input.tgyro']['TGYRO_PED_SCALE']", '缩放台基压强', default=1.0)
        OMFITx.Separator()
        OMFITx.CheckBox(
            "root['INPUTS']['input.tgyro']['LOC_LOCK_PROFILE_FLAG']", '第 0 次迭代使用原始剖面', useInt=True, default=1
        )
        OMFITx.CheckBox(
            "root['INPUTS']['input.tgyro']['TGYRO_CONSISTENT_FLAG']", '积分梯度尺度长度以匹配剖面', useInt=True, default=1
        )

    # Models
    OMFITx.Tab('Models')
    model_choices = ['TGLF', 'MMM', 'OMFIT QLGYRO']  # ,'IFS','GLF23']
    OMFITx.ComboBox(
        "root['SETTINGS']['PHYSICS']['Turb_Model']",
        model_choices,
        lbl='湍流模型',
        default='TGLF',
        postcommand=lambda location: setup_radii(),
        updateGUI=True,
    )

    # NEO
    OMFITx.ComboBox(
        "root['INPUTS']['input.tgyro']['TGYRO_NEO_METHOD']",
        {'None': 0, 'Hinton-Hazeltine': 1, 'NEO': 2},
        lbl='新经典模型',
        default=2,
    )

    pflux_choices = SortedDict()
    for k, v in [('No particle sources', 1), ('Only beam particle sources', 2), ('Beam + Wall sources', 3)]:
        pflux_choices[k] = v
    OMFITx.ComboBox("root['INPUTS']['input.tgyro']['LOC_PFLUX_METHOD']", pflux_choices, lbl='粒子源', default=1)

    scenario_choices = SortedDict()
    for k, v in [
        ('Fixed integrated powers with static exchange', 1),
        ('Fixed integrated powers with dynamic exchange', 2),
        ('Thermonuclear source, radiation and exchange with auxiliary heating from data', 3),
    ]:
        scenario_choices[k] = v

    OMFITx.ComboBox("root['INPUTS']['input.tgyro']['LOC_SCENARIO']", scenario_choices, lbl='功率平衡方案')
    if root['INPUTS']['input.tgyro']['LOC_ER_FEEDBACK_FLAG']:
        OMFITx.Lock("root['INPUTS']['input.tgyro']['TGYRO_ROTATION_FLAG']", 1)
    OMFITx.CheckBox("root['INPUTS']['input.tgyro']['TGYRO_ROTATION_FLAG']", '启用全部旋转物理项', default=1, mapFalseTrue=[0, 1])

    if input_gacode is not None:
        OMFITx.ComboBox(
            "root['SETTINGS']['PHYSICS']['INCLUDE_IONS']",
            ['thermal', 'user'],
            '参与通量计算的离子',
            'IONS in simulation: ' + ', '.join(input_gacode.ion_names()),
            default='thermal',
            help='These ions are used in the flux calculation in NEO and TGLF',
            postcommand=root['SCRIPTS']['update_ion_data'].run,
        )
        for i in range(max_nions):
            ion_name = input_gacode['IONS'][i + 1][0]
            ion_type = input_gacode['IONS'][i + 1][3]
            if root['SETTINGS']['PHYSICS']['INCLUDE_IONS'] != 'thermal':
                with OMFITx.same_row():
                    OMFITx.CheckBox(
                        "root['INPUTS']['input.tgyro']['TGYRO_CALC_FLAG{}']".format(i + 1),
                        'Calculate fluxes of (Ion {}[{}])'.format(ion_name, ion_type),
                        mapFalseTrue=(0, 1),
                        default=[0, 1]['fast' not in ion_type],
                    )
                    OMFITx.CheckBox(
                        "root['INPUTS']['input.tgyro']['TGYRO_THERM_FLAG{}']".format(i + 1),
                        'Treat as thermal (Ion {}[{}])'.format(ion_name, ion_type),
                        mapFalseTrue=(0, 1),
                        default=[0, 1]['fast' not in ion_type],
                    )
    else:
        root['SETTINGS']['PHYSICS']['INCLUDE_IONS'] = 'thermal'

    # TGLF

    if root['SETTINGS']['PHYSICS']['Turb_Model'] == 'TGLF' or root['SETTINGS']['PHYSICS']['Turb_Model'] == 'OMFIT QLGYRO':
        OMFITx.Tab('TGLF')
        # TGLF model

        if root['SETTINGS']['PHYSICS']['Turb_Model'] == 'TGLF' and (
            is_device(root['SETTINGS']['EXPERIMENT']['device'], 'DIII-D')
            or is_device(root['SETTINGS']['EXPERIMENT']['device'], 'ITER')
            and root['SETTINGS']['SETUP']['branch'] == 'btf'
        ):

            def toggle_nn(location=None):
                if scratch['NN']:
                    root['INPUTS']['input.tgyro']['TGYRO_TGLF_NN_MAX_ERROR'] = 9999999
                    root['SETTINGS']['SETUP']['n_cpu_rad'] = 1  # avoid waste of computer resources when running with NNs
                elif 'TGYRO_TGLF_NN_MAX_ERROR' in root['INPUTS']['input.tgyro']:
                    del root['INPUTS']['input.tgyro']['TGYRO_TGLF_NN_MAX_ERROR']

            if 'TGYRO_TGLF_NN_MAX_ERROR' in root['INPUTS']['input.tgyro'] and root['INPUTS']['input.tgyro']['TGYRO_TGLF_NN_MAX_ERROR'] > 0:
                scratch['NN'] = 1
            OMFITx.CheckBox(
                "scratch['NN']",
                '使用神经网络加速',
                postcommand=toggle_nn,
                default=0,
                updateGUI=True,
                useInt=True,
                help='Use the TGLF-NN model.\nNOTE: this model has been calibrated only on DIII-D ion-stiffness experiments!\nTo get full advantage of NN speed, you will likely want to set Chang-Hinton as neoclassical model.',
            )
            root['INPUTS']['input.tgyro'].setdefault('TGYRO_TGLF_NN_MAX_ERROR', -1)
            toggle_nn()
        else:
            root['INPUTS']['input.tgyro'].setdefault('TGYRO_TGLF_NN_MAX_ERROR', -1)

        if root['INPUTS']['input.tgyro'].get('TGYRO_TGLF_NN_MAX_ERROR', -1) < 0:
            OMFITx.CompoundGUI(root['GUIS']['TGLFinputGUI'])
    elif root['SETTINGS']['PHYSICS']['Turb_Model'] == 'MMM':
        OMFITx.Tab('MMM')
        OMFITx.Entry("root['INPUTS']['input.mmm']['mmm_input']['cmodel'][0]", '启用 Weiland 分量（ITG/TEM）', default=1.0)
        OMFITx.Entry("root['INPUTS']['input.mmm']['mmm_input']['cmodel'][1]", '启用 DRIBM 分量', default=0.0)
        OMFITx.Entry("root['INPUTS']['input.mmm']['mmm_input']['cmodel'][2]", '启用 H-J ETG 分量', default=1.0)
        OMFITx.Entry("root['INPUTS']['input.mmm']['mmm_input']['cmodel'][3]", '启用 MTM 分量', default=1.0)
        OMFITx.Entry("root['INPUTS']['input.mmm']['mmm_input']['cmodel'][3]", '启用 mETG 分量（测试）', default=0.0)

OMFITx.Tab("")
if showRunLoadButtons:
    if not root['SETTINGS']['PHYSICS']['reload']:
        OMFITx.Button('提交 TGYRO 作业', lambda: root['SCRIPTS']['runTGYRO'].run(reload=False))
    OMFITx.Button('读取 TGYRO 作业', lambda: root['SCRIPTS']['runTGYRO'].run(reload=True))
