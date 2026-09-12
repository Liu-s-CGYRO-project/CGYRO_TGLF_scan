# -*-Python-*-
# Created by thomek at 27 Sep 2016  16:20

OMFITx.TitleGUI('TGYRO plot GUI')

OMFITx.Tab('Individual run')
if 'output' in root['OUTPUTS']:
    OMFITx.Separator()
    OMFITx.CheckBox("scratch['plot_gb']", 'Plot GyroBohm Normalized Fluxes', default=True)
    OMFITx.CheckBox("scratch['plot_loggb']", 'symlog-scale GyroBohm Normalized Fluxes', default=False)
    OMFITx.Separator()
    OMFITx.Button('Plot profiles and scale lengths', "root['PLOTS']['plotTGYROprofiles2'].runNoGUI")
    OMFITx.Button(
        'Plot flux matching', lambda: root['PLOTS']['plotTGYROfluxes2'].runNoGUI(gb=scratch['plot_gb'], loggb=scratch['plot_loggb'])
    )
    OMFITx.Button(
        'Plot flux convergence', lambda: root['PLOTS']['plotTGYROconvergence2'].runNoGUI(gb=scratch['plot_gb'], loggb=scratch['plot_loggb'])
    )
    OMFITx.Button('Plot profiles evolution', "root['OUTPUTS']['output'].plot_profiles_evolution")
    OMFITx.Button('Plot flux-gradient', lambda: root['PLOTS']['plotTGYROflux_gradient'].runNoGUI())
    OMFITx.Button('Plot profiles and fluxes summary', "root['PLOTS']['plotTGYROsummary'].plotFigure")
    OMFITx.Button('Plot profiles iteration summary', "root['OUTPUTS']['output'].plotFigure")

OMFITx.Tab('Compare runs')
if len(root['RUN_DB']) == 0:
    OMFITx.Label('No runs are present, so there is nothing to compare to')
else:
    OMFITx.Separator()
    OMFITx.ListEditor("scratch['plot_runids']", list(root['RUN_DB'].keys()), lbl='Select runs', default=[], unique=True, updateGUI=False)
    OMFITx.Separator()
    OMFITx.CheckBox("scratch['plot_gb']", 'Plot GyroBohm Normalized Fluxes', default=True)
    OMFITx.CheckBox("scratch['plot_loggb']", 'symlog-scale GyroBohm Normalized Fluxes', default=False)
    OMFITx.Separator()
    OMFITx.Button('Compare residuals', "root['PLOTS']['plotTGYROcomparison_residual'].runNoGUI")
    OMFITx.Button('Compare profiles', "root['PLOTS']['plotTGYROcomparison_profiles'].runNoGUI")
    OMFITx.Button(
        'Compare fluxes', lambda: root['PLOTS']['plotTGYROcomparison_fluxes'].runNoGUI(gb=scratch['plot_gb'], loggb=scratch['plot_loggb'])
    )
    OMFITx.Button(
        'Compare flux convergence',
        lambda: root['PLOTS']['plotTGYROcomparison_fluxconvergence'].runNoGUI(gb=scratch['plot_gb'], loggb=scratch['plot_loggb']),
    )
    OMFITx.Button(
        'Compare RMS, offset and deviations from experimental profiles',
        lambda: root['PLOTS']['plotDeviation'].runNoGUI(),
    )

    # function to load OMFITprofiles module from the existing project
    def load_project(location):
        print(location, scratch['kineticEFITtime_project'], scratch['module_load'])
        root['ExpProfiles'] = OMFITproject(
            filename=scratch['profile_data_project'],
            only=[scratch['module_load']],
        )

    OMFITx.Separator('Compare with experimental profiles')
    OMFITx.CheckBox('scratch["outside_module"]', 'Load profile module outside of this project', default=False, updateGUI=True)

    root['SETTINGS']['DEPENDENCIES'].setdefault('profiles_module', '')
    if scratch["outside_module"]:

        # function to load OMFITprofiles module from the existing project
        def load_project(location):
            scratch['ExpProfiles'] = OMFITproject(
                filename=scratch['profile_module_project'],
                only=[scratch['module_load']],
            )
            root['SETTINGS']['DEPENDENCIES']['profiles_module'] = "scratch['ExpProfiles'][%r]" % scratch['module_load']

        OMFITx.Label('Load project with experimental data inside the OMFITprofiles module')

        scratch['init_project_dir'] = str(MainSettings['SETUP']['projectsDir'])
        OMFITx.FilePicker(
            "scratch['profile_module_project']",
            lbl='Directory of existing OMFIT project',
            init_directory_location="scratch['init_project_dir']",
            tree=False,
            default='',
            updateGUI=True,
        )
        try:
            modules = OMFITproject.info(filename=scratch['profile_module_project'])['modules']
        except Exception:
            OMFITx.Label('No project selected')
        else:
            OMFITx.ComboBox(
                "scratch['module_load']",
                [x.strip() for x in modules if 'OMFITprofiles' in x or 'QUICKFIT' in x],
                'Modules list',
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
            'Compare with experimental data',
            "root['PLOTS']['plotEXPcomparison_profiles'].runNoGUI",
            help="Plotting settings can be change directly in the script root['PLOTS']['plotEXPcomparison_profiles']",
        )
