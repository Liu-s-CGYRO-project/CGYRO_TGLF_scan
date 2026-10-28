from OMFITlib_gui_api import task_action
from OMFITlib_gui_api import plot_view
from OMFITlib_gui_api import adapt
OMFITx = adapt(OMFITx)
# -*-Python-*-
# Created by grierson at 27 Apr 2016  13:59
# modified by sciortino, 22 July 2019
from OMFITlib_gui_layout import finish_gui_layout

layout_anchor = OMFITx.Label('', align='left')
layout_anchor.master.pack_forget()

OMFITx.TitleGUI('TGLF 杂质粒子输运系数')

root.setdefault('TGLF_SCAN_DB', OMFITtree())

if not compoundGUI:  # OMFIT GUIs have the compoundGUI variable in their namespace

    def no_spaces(x):
        if re.findall(r'[\s,/,\\]', x):
            return False
        return True

    # get available database elements, excluding the 'scans' tree that comes from frequency scans:
    available_trees = [x for x in root['TGLF_SCAN_DB'] if x != 'scans']
    OMFITx.ComboBox(
        "root['SETTINGS']['PHYSICS']['runs_label']",
        available_trees,
        '扫描名称',
        postcommand=lambda location=None: root['SCRIPTS']['reloadDVscan'].runNoGUI(),
        updateGUI=True,
        state='normal',
        check=no_spaces,
        default='',
        refresh_tree=True,
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
        OMFITx.Label('尚未载入 input.gacode')

    OMFITx.Entry("root['TGLF_SCAN_DB']['%s']['impElement']" % runs_label, '杂质元素', default='Ca', refresh_tree=False)
    OMFITx.Entry("root['TGLF_SCAN_DB']['%s']['impZ']" % runs_label, '杂质电荷数 Z', default=20, refresh_tree=False)
    OMFITx.Entry("root['TGLF_SCAN_DB']['%s']['impM']" % runs_label, '杂质质量（amu）', default=40, refresh_tree=False)
    root['SETTINGS']['PHYSICS']['impElement'] = root['TGLF_SCAN_DB'][runs_label]['impElement']
    root['SETTINGS']['PHYSICS']['impZ'] = root['TGLF_SCAN_DB'][runs_label]['impZ']
    root['SETTINGS']['PHYSICS']['impM'] = root['TGLF_SCAN_DB'][runs_label]['impM']

    OMFITx.Label('')
    OMFITx.CheckBox(
        "root['SETTINGS']['PHYSICS']['transport_matrix_method']",
        '使用矩阵求逆计算输运系数',
        default=True,
        updateGUI=True,
        help="If checked, transport coefficients are computed via a matrix inversion, "
        "using a single TGLF run with multiple impurities rather than multiple runs with different inputs.",
        postcommand=lambda location=None: update_ion_list(),
        refresh_tree=False,
    )

    if root['SETTINGS']['PHYSICS']['transport_matrix_method']:
        OMFITx.CheckBox(
            "root['SETTINGS']['PHYSICS']['compute_thermodiffusion']",
            '计算热扩散',
            default=True,
            updateGUI=True,
            help="If checked, compute diffusion (D), thermodiffusion (vT) and the residual convection term (vp), rather than just D,v. ",
            refresh_tree=False,
        )

        OMFITx.CheckBox(
            "root['SETTINGS']['PHYSICS']['compute_rotodiffusion']",
            '计算旋转扩散',
            default=True,
            updateGUI=True,
            help="If checked, compute rotodiffusion (vR) as well as thermodiffusion (vT).",
            refresh_tree=False,
        )

    # display how many ions are expected to be included in TGLF runs, based on user choices above
    if 'input.gacode' in root['TGYRO']['PROFILES_GEN']['OUTPUTS']:
        OMFITx.Label('Ion List including new impurity:{}'.format(get_ion_list_short()))
    OMFITx.Label('')

    OMFITx.Entry("root['TGLF_SCAN_DB']['%s']['rhoList']" % runs_label, 'Radii (rho)', default=np.arange(0.35, 0.9, 0.1), refresh_tree=False)
    root['SETTINGS']['PHYSICS']['rhoList'] = root['TGLF_SCAN_DB'][runs_label]['rhoList']

    OMFITx.Label('')
    OMFITx.Separator()
    OMFITx.Label('')
    # === Run ===
    if root['SETTINGS']['PHYSICS']['transport_matrix_method']:

        def get_transport_matrix():
            '''Form matrix of particle fluxes and solve for transport coefficients'''
            task_action(root['SCRIPTS']['resp_matrix'],
                runs_label=root['SETTINGS']['PHYSICS']['runs_label'], rhoList=root['TGLF_SCAN_DB'][runs_label]['rhoList']
            )
            # Obtain and store results using the plot_resp_matrix.py script (but don't plot now)
            task_action(root['PLOTS']['plot_resp_matrix'], runs_label=root['SETTINGS']['PHYSICS']['runs_label'], plot_results=False)

        OMFITx.Button('计算粒子输运系数', get_transport_matrix, updateGUI=True)

    else:

        def run_transport_scan():
            '''Scan grad(n_z) in separate TGLF runs and then do a linear fit to find transport coefficients'''
            task_action(root['SCRIPTS']['particleDandVscan'])  # run TGLF scans
            task_action(root['SCRIPTS']['particleDandVprofile'])  # linear fit step

        OMFITx.Button('运行 TGLF 扫描', run_transport_scan, updateGUI=True)

    # === Plot ===
    if (
        root['SETTINGS']['PHYSICS']['runs_label'] in root['TGLF_SCAN_DB']
        and 'gamma_z' in root['TGLF_SCAN_DB'][root['SETTINGS']['PHYSICS']['runs_label']]
    ):

        OMFITx.Label('')
        OMFITx.CheckBox(
            "root['SETTINGS']['PHYSICS']['plot_STRAHL_corrections']",
            '绘图时采用 STRAHL 类修正',
            default=True,
            updateGUI=False,
            refresh_tree=False,
        )
        OMFITx.CheckBox(
            "root['SETTINGS']['PHYSICS']['plot_normalized_coeffs']",
            '绘制归一化输运系数',
            default=False,
            updateGUI=False,
            refresh_tree=False,
        )

        if root['SETTINGS']['PHYSICS']['transport_matrix_method']:
            OMFITx.Button('绘制扫描与剖面', lambda: plot_view(root['PLOTS']['plot_resp_matrix'], plot_results=True), refresh_tree=False)
        else:
            OMFITx.Button('绘制扫描与剖面', lambda: plot_view(root['PLOTS']['plotDandV']), refresh_tree=False)

finish_gui_layout(layout_anchor, OMFITx)
