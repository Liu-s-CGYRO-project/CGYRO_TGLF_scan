from OMFITlib_plot_style import plot_context
from OMFITlib_gui_api import plot_view

def styled_plot(callback, **kwargs):
    with plot_context(root):
        script = getattr(callback, '__self__', None)
        if hasattr(script, '__run__') and callback.__name__ in ('plot', 'plotFigure', 'run', 'runNoGUI'):
            if callback.__name__ == 'plotFigure':
                kwargs.setdefault('fig', figure())
            return plot_view(script, **kwargs)
        return callback(**kwargs)

from OMFITlib_gui_api import adapt
OMFITx = adapt(OMFITx)
# -*-Python-*-
# Created by thomek at 27 Sep 2016  16:20

OMFITx.TitleGUI('TGYRO 结果绘图')

OMFITx.Tab('单次运行')
if 'output' in root['OUTPUTS']:
    OMFITx.Separator()
    OMFITx.CheckBox("scratch['plot_gb']", '绘制回旋玻姆归一化通量', default=True, refresh_tree=False)
    OMFITx.CheckBox("scratch['plot_loggb']", '回旋玻姆通量采用对称对数坐标', default=False, refresh_tree=False)
    OMFITx.Separator()
    OMFITx.Button('绘制剖面与梯度尺度长度', lambda: styled_plot(root['PLOTS']['plotTGYROprofiles2'].runNoGUI), refresh_tree=False)
    OMFITx.Button(
        '绘制通量匹配', lambda: styled_plot(root['PLOTS']['plotTGYROfluxes2'].runNoGUI, gb=scratch['plot_gb'], loggb=scratch['plot_loggb']),
        refresh_tree=False,
    )
    OMFITx.Button(
        '绘制通量收敛过程', lambda: styled_plot(root['PLOTS']['plotTGYROconvergence2'].runNoGUI, gb=scratch['plot_gb'], loggb=scratch['plot_loggb']),
        refresh_tree=False,
    )
    OMFITx.Button('绘制剖面演化', lambda: styled_plot(root['OUTPUTS']['output'].plot_profiles_evolution), refresh_tree=False)
    OMFITx.Button('绘制通量–梯度关系', lambda: styled_plot(root['PLOTS']['plotTGYROflux_gradient'].runNoGUI), refresh_tree=False)
    OMFITx.Button('绘制剖面与通量汇总', lambda: styled_plot(root['PLOTS']['plotTGYROsummary'].plotFigure), refresh_tree=False)
    OMFITx.Button('绘制剖面迭代汇总', lambda: styled_plot(root['OUTPUTS']['output'].plotFigure), refresh_tree=False)

OMFITx.Tab('运行对比')
if len(root['RUN_DB']) == 0:
    OMFITx.Label('尚无可比较的运行记录。')
else:
    OMFITx.Separator()
    OMFITx.ListEditor("scratch['plot_runids']", list(root['RUN_DB'].keys()), lbl='选择运行记录', default=[], unique=True, updateGUI=False, refresh_tree=False)
    OMFITx.Separator()
    OMFITx.CheckBox("scratch['plot_gb']", '绘制回旋玻姆归一化通量', default=True, refresh_tree=False)
    OMFITx.CheckBox("scratch['plot_loggb']", '回旋玻姆通量采用对称对数坐标', default=False, refresh_tree=False)
    OMFITx.Separator()
    OMFITx.Button('对比残差', lambda: styled_plot(root['PLOTS']['plotTGYROcomparison_residual'].runNoGUI), refresh_tree=False)
    OMFITx.Button('对比剖面', lambda: styled_plot(root['PLOTS']['plotTGYROcomparison_profiles'].runNoGUI), refresh_tree=False)
    OMFITx.Button(
        '对比通量', lambda: styled_plot(root['PLOTS']['plotTGYROcomparison_fluxes'].runNoGUI, gb=scratch['plot_gb'], loggb=scratch['plot_loggb']),
        refresh_tree=False,
    )
    OMFITx.Button(
        '对比通量收敛过程',
        lambda: styled_plot(root['PLOTS']['plotTGYROcomparison_fluxconvergence'].runNoGUI, gb=scratch['plot_gb'], loggb=scratch['plot_loggb']),
        refresh_tree=False,
    )
    OMFITx.Button(
        '对比与实验剖面的均方根误差、偏移及偏差',
        lambda: styled_plot(root['PLOTS']['plotDeviation'].runNoGUI),
        refresh_tree=False,
    )

    OMFITx.Separator('与实验剖面对比')
    OMFITx.CheckBox('scratch["outside_module"]', '载入其他工程的剖面模块', default=False, updateGUI=True, refresh_tree=False)

    root['SETTINGS']['DEPENDENCIES'].setdefault('profiles_module', '')
    if scratch["outside_module"]:

        def inspect_project(location=None):
            # Inspect the selected archive only on an explicit file/refresh action.
            path = scratch['profile_module_project']
            try:
                modules = OMFITproject.info(filename=path)['modules']
                choices = [name.strip() for name in modules if 'OMFITprofiles' in name or 'QUICKFIT' in name]
                scratch['profile_module_catalog'] = dict(path=path, choices=choices, error='')
            except Exception as exc:
                scratch['profile_module_catalog'] = dict(path=path, choices=[], error=str(exc))

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
            postcommand=inspect_project,
        )
        OMFITx.Button('读取 / 刷新模块列表', inspect_project, updateGUI=True,
                      refresh_scope='section', refresh_tree=False)
        catalog = scratch.get('profile_module_catalog', {})
        if catalog.get('path', '') == scratch['profile_module_project'] and catalog.get('choices', []):
            OMFITx.ComboBox(
                "scratch['module_load']",
                catalog['choices'],
                '模块列表',
                default='',
                postcommand=load_project,
                updateGUI=True,
                refresh_tree=True,
            )
        else:
            OMFITx.Label(catalog.get('error', '') or '选择工程后读取模块列表。')

    else:
        OMFITx.ModulePicker(
            "root['SETTINGS']['DEPENDENCIES']['profiles_module']",
            modules=['OMFITprofiles', 'QUICKFIT'],
            lbl='剖面模块',
            default='',
            updateGUI=True,
        )

    if ismodule(profiles_module, ['OMFITprofiles', 'QUICKFIT']):
        OMFITx.Button(
            '与实验数据对比',
            lambda: styled_plot(root['PLOTS']['plotEXPcomparison_profiles'].runNoGUI),
            help="Plotting settings can be change directly in the script root['PLOTS']['plotEXPcomparison_profiles']",
            refresh_tree=False,
        )
