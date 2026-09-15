# -*-Python-*-
# Created by thomek at 27 Sep 2016  16:20

OMFITx.TitleGUI('TGYRO 结果绘图')

OMFITx.Tab('单次运行')
if 'output' in root['OUTPUTS']:
    OMFITx.Separator()
    OMFITx.CheckBox("scratch['plot_gb']", '绘制回旋玻姆归一化通量', default=True)
    OMFITx.CheckBox("scratch['plot_loggb']", '回旋玻姆通量采用对称对数坐标', default=False)
    OMFITx.Separator()
    OMFITx.Button('绘制剖面与梯度尺度长度', "root['PLOTS']['plotTGYROprofiles2'].runNoGUI")
    OMFITx.Button(
        '绘制通量匹配', lambda: root['PLOTS']['plotTGYROfluxes2'].runNoGUI(gb=scratch['plot_gb'], loggb=scratch['plot_loggb'])
    )
    OMFITx.Button(
        '绘制通量收敛过程', lambda: root['PLOTS']['plotTGYROconvergence2'].runNoGUI(gb=scratch['plot_gb'], loggb=scratch['plot_loggb'])
    )
    OMFITx.Button('绘制剖面演化', "root['OUTPUTS']['output'].plot_profiles_evolution")
    OMFITx.Button('绘制通量–梯度关系', lambda: root['PLOTS']['plotTGYROflux_gradient'].runNoGUI())
    OMFITx.Button('绘制剖面与通量汇总', "root['PLOTS']['plotTGYROsummary'].plotFigure")
    OMFITx.Button('绘制剖面迭代汇总', "root['OUTPUTS']['output'].plotFigure")

OMFITx.Tab('运行对比')
if len(root['RUN_DB']) == 0:
    OMFITx.Label('尚无可比较的运行记录。')
else:
    OMFITx.Separator()
    OMFITx.ListEditor("scratch['plot_runids']", list(root['RUN_DB'].keys()), lbl='Select runs', default=[], unique=True, updateGUI=False)
    OMFITx.Separator()
    OMFITx.CheckBox("scratch['plot_gb']", '绘制回旋玻姆归一化通量', default=True)
    OMFITx.CheckBox("scratch['plot_loggb']", '回旋玻姆通量采用对称对数坐标', default=False)
    OMFITx.Separator()
    OMFITx.Button('对比残差', "root['PLOTS']['plotTGYROcomparison_residual'].runNoGUI")
    OMFITx.Button('对比剖面', "root['PLOTS']['plotTGYROcomparison_profiles'].runNoGUI")
    OMFITx.Button(
        '对比通量', lambda: root['PLOTS']['plotTGYROcomparison_fluxes'].runNoGUI(gb=scratch['plot_gb'], loggb=scratch['plot_loggb'])
    )
    OMFITx.Button(
        '对比通量收敛过程',
        lambda: root['PLOTS']['plotTGYROcomparison_fluxconvergence'].runNoGUI(gb=scratch['plot_gb'], loggb=scratch['plot_loggb']),
    )
    OMFITx.Button(
        '对比与实验剖面的均方根误差、偏移及偏差',
        lambda: root['PLOTS']['plotDeviation'].runNoGUI(),
    )

    # function to load OMFITprofiles module from the existing project
    def load_project(location):
        print(location, scratch['kineticEFITtime_project'], scratch['module_load'])
        root['ExpProfiles'] = OMFITproject(
            filename=scratch['profile_data_project'],
            only=[scratch['module_load']],
        )

    OMFITx.Separator('与实验剖面对比')
    OMFITx.CheckBox('scratch["outside_module"]', '载入其他工程的剖面模块', default=False, updateGUI=True)

    root['SETTINGS']['DEPENDENCIES'].setdefault('profiles_module', '')
    if scratch["outside_module"]:

        # function to load OMFITprofiles module from the existing project
        def load_project(location):
            scratch['ExpProfiles'] = OMFITproject(
                filename=scratch['profile_module_project'],
                only=[scratch['module_load']],
            )
            root['SETTINGS']['DEPENDENCIES']['profiles_module'] = "scratch['ExpProfiles'][%r]" % scratch['module_load']

        OMFITx.Label('载入包含 OMFITprofiles 实验数据的工程')

        scratch['init_project_dir'] = str(MainSettings['SETUP']['projectsDir'])
        OMFITx.FilePicker(
            "scratch['profile_module_project']",
            lbl='已有 OMFIT 工程目录',
            init_directory_location="scratch['init_project_dir']",
            tree=False,
            default='',
            updateGUI=True,
        )
        try:
            modules = OMFITproject.info(filename=scratch['profile_module_project'])['modules']
        except Exception:
            OMFITx.Label('尚未选择工程')
        else:
            OMFITx.ComboBox(
                "scratch['module_load']",
                [x.strip() for x in modules if 'OMFITprofiles' in x or 'QUICKFIT' in x],
                '模块列表',
                default='',
                postcommand=load_project,
                updateGUI=True,
            )

    else:
        OMFITx.ModulePicker(
            "root['SETTINGS']['DEPENDENCIES']['profiles_module']",
            modules=['OMFITprofiles', 'QUICKFIT'],
            lbl='Profile modules',
            default='',
            updateGUI=True,
        )

    if ismodule(profiles_module, ['OMFITprofiles', 'QUICKFIT']):
        OMFITx.Button(
            '与实验数据对比',
            "root['PLOTS']['plotEXPcomparison_profiles'].runNoGUI",
            help="Plotting settings can be change directly in the script root['PLOTS']['plotEXPcomparison_profiles']",
        )
