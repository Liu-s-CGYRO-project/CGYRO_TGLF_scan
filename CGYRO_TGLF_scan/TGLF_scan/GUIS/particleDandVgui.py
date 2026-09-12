# -*-Python-*-
# Created by grierson at 27 Apr 2016  13:59
# modified by sciortino, 22 July 2019

OMFITx.TitleGUI('TGLF Impurity Particle Transport Coefficients')

root.setdefault('TGLF_SCAN_DB', OMFITtree())

if not compoundGUI:  # OMFIT GUIs have the compoundGUI variable in their namespace

    def no_spaces(x):
        if re.findall(r'[\s,/,\\]', x):
            return False
        return True

    # get available database elements, excluding the 'scans' tree that comes from frequency scans:
    available_trees = {x: root['TGLF_SCAN_DB'][x] for x in root['TGLF_SCAN_DB'] if x not in ['scans']}
    OMFITx.ComboBox(
        "root['SETTINGS']['PHYSICS']['runs_label']",
        list(available_trees.keys()),
        'Scan ID',
        postcommand=lambda location=None: root['SCRIPTS']['reloadDVscan'].runNoGUI(),
        updateGUI=True,
        state='normal',
        check=no_spaces,
        default='',
    )
else:
    # no need to select runs_label when this GUI is used within another GUI
    pass


if len(root['SETTINGS']['PHYSICS']['runs_label']):
    runs_label = root['SETTINGS']['PHYSICS']['runs_label']

    # create tree to store particle transport results
    root['TGLF_SCAN_DB'].setdefault(runs_label, OMFITtree())

    def get_ion_list_short():
        ions = root['TGYRO']['PROFILES_GEN']['OUTPUTS']['input.gacode']['IONS']
        ion_list = [ions[k][0] for k in ions.keys()]

        ion_list.insert(len(ion_list), root['TGLF_SCAN_DB'][runs_label]['impElement'])
        return ion_list

    def update_ion_list():
        if 'IONS' in root['TGLF_SCAN_DB'][runs_label]:
            del root['TGLF_SCAN_DB'][runs_label]['IONS']
        root['TGLF_SCAN_DB'][runs_label]['IONS'] = get_ion_list_short()

    # Select particle of interest
    if 'input.gacode' in root['TGYRO']['PROFILES_GEN']['OUTPUTS']:
        ions = root['TGYRO']['PROFILES_GEN']['OUTPUTS']['input.gacode']['IONS']
        ion_list = [ions[k][0] for k in ions.keys()]
        # root['TGLF_SCAN_DB'][runs_label]['IONS'] = ion_list
        OMFITx.Label('Original Ion List:{}'.format(ion_list))
    else:
        OMFITx.Label('**** No input.gacode! ****')

    OMFITx.Entry("root['TGLF_SCAN_DB']['%s']['impElement']" % runs_label, 'Impurity Element', default='Ca')
    OMFITx.Entry("root['TGLF_SCAN_DB']['%s']['impZ']" % runs_label, 'Impurity Charge (Z)', default=20)
    OMFITx.Entry("root['TGLF_SCAN_DB']['%s']['impM']" % runs_label, 'Impurity Mass (amu)', default=40)
    root['SETTINGS']['PHYSICS']['impElement'] = root['TGLF_SCAN_DB'][runs_label]['impElement']
    root['SETTINGS']['PHYSICS']['impZ'] = root['TGLF_SCAN_DB'][runs_label]['impZ']
    root['SETTINGS']['PHYSICS']['impM'] = root['TGLF_SCAN_DB'][runs_label]['impM']

    OMFITx.Label('')
    OMFITx.CheckBox(
        "root['SETTINGS']['PHYSICS']['transport_matrix_method']",
        'Use matrix inversion method to obtain transport coefficients ',
        default=True,
        updateGUI=True,
        help="If checked, transport coefficients are computed via a matrix inversion, "
        "using a single TGLF run with multiple impurities rather than multiple runs with different inputs.",
        postcommand=lambda location=None: update_ion_list(),
    )

    if root['SETTINGS']['PHYSICS']['transport_matrix_method']:
        OMFITx.CheckBox(
            "root['SETTINGS']['PHYSICS']['compute_thermodiffusion']",
            'Compute thermodiffusion',
            default=True,
            updateGUI=True,
            help="If checked, compute diffusion (D), thermodiffusion (vT) and the residual convection term (vp), rather than just D,v. ",
        )

        OMFITx.CheckBox(
            "root['SETTINGS']['PHYSICS']['compute_rotodiffusion']",
            'Compute rotodiffusion',
            default=True,
            updateGUI=True,
            help="If checked, compute rotodiffusion (vR) as well as thermodiffusion (vT).",
        )

    # display how many ions are expected to be included in TGLF runs, based on user choices above
    if 'input.gacode' in root['TGYRO']['PROFILES_GEN']['OUTPUTS']:
        OMFITx.Label('Ion List including new impurity:{}'.format(get_ion_list_short()))
    OMFITx.Label('')

    OMFITx.Entry("root['TGLF_SCAN_DB']['%s']['rhoList']" % runs_label, 'Radii (rho)', default=np.arange(0.35, 0.9, 0.1))
    root['SETTINGS']['PHYSICS']['rhoList'] = root['TGLF_SCAN_DB'][runs_label]['rhoList']

    OMFITx.Label('')
    OMFITx.Separator()
    OMFITx.Label('')
    # === Run ===
    if root['SETTINGS']['PHYSICS']['transport_matrix_method']:

        def get_transport_matrix():
            '''Form matrix of particle fluxes and solve for transport coefficients'''
            root['SCRIPTS']['resp_matrix'].run(
                runs_label=root['SETTINGS']['PHYSICS']['runs_label'], rhoList=root['TGLF_SCAN_DB'][runs_label]['rhoList']
            )
            # Obtain and store results using the plot_resp_matrix.py script (but don't plot now)
            root['PLOTS']['plot_resp_matrix'].run(runs_label=root['SETTINGS']['PHYSICS']['runs_label'], plot_results=False)

        OMFITx.Button('Compute particles transport coefficients', get_transport_matrix, updateGUI=True)

    else:

        def run_transport_scan():
            '''Scan grad(n_z) in separate TGLF runs and then do a linear fit to find transport coefficients'''
            root['SCRIPTS']['particleDandVscan'].run()  # run TGLF scans
            root['SCRIPTS']['particleDandVprofile'].run()  # linear fit step

        OMFITx.Button('Run TGLF scan', run_transport_scan, updateGUI=True)

    # === Plot ===
    if (
        root['SETTINGS']['PHYSICS']['runs_label'] in root['TGLF_SCAN_DB']
        and 'gamma_z' in root['TGLF_SCAN_DB'][root['SETTINGS']['PHYSICS']['runs_label']]
    ):

        OMFITx.Label('')
        OMFITx.CheckBox(
            "root['SETTINGS']['PHYSICS']['plot_STRAHL_corrections']",
            'Apply STRAHL-like corrections in plotting',
            default=True,
            updateGUI=False,
        )
        OMFITx.CheckBox(
            "root['SETTINGS']['PHYSICS']['plot_normalized_coeffs']",
            'Plot normalized transport coefficients',
            default=False,
            updateGUI=False,
        )

        if root['SETTINGS']['PHYSICS']['transport_matrix_method']:
            OMFITx.Button('Plot Scan and Profile', lambda: root['PLOTS']['plot_resp_matrix'].run(plot_results=True))
        else:
            OMFITx.Button('Plot Scan and Profile', "root['PLOTS']['plotDandV']")
