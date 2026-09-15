# -*-Python-*-
# Created by sciortinof at 16 Jul 2019  14:46

"""
This script sets up a GUI to run TGLF scans to probe the sensitivity of growth rates and D,V transport coefficients
to input variables.

"""

# Create database structure for all results
root.setdefault('TGLF_SCAN_DB', OMFITtree())


def no_spaces(x):
    if re.findall(r'[\s,/,\\]', x):
        return False
    return True


# get available database elements, excluding the 'scans' tree that comes from frequency scans:
available_trees = {x: root['TGLF_SCAN_DB'][x] for x in root['TGLF_SCAN_DB'] if x not in ['scans']}
OMFITx.ComboBox(
    "root['SETTINGS']['PHYSICS']['runs_label']",
    list(available_trees.keys()),
    '扫描名称',
    postcommand=lambda location=None: root['SCRIPTS']['reloadDVscan'].runNoGUI(),
    updateGUI=True,
    state='normal',
    check=no_spaces,
    default='',
)

if len(root['SETTINGS']['PHYSICS']['runs_label']):

    OMFITx.Tab("Setup")
    OMFITx.CompoundGUI(root['TGYRO']['PROFILES_GEN']['GUIS']['standaloneGUI'])

    if 'input.gacode' in root['TGYRO']['PROFILES_GEN']['OUTPUTS']:
        OMFITx.Tab('背景离子')
        # ==============================
        # Modify ions:
        OMFITx.Label('')
        OMFITx.Label('此处仅设置背景离子，暂不添加示踪杂质。', align='left')
        OMFITx.Label('')
        OMFITx.CompoundGUI(root['TGYRO']['PROFILES_GEN']['GUIS']['modifyIonsGUI'])

        OMFITx.Tab('TGLF 参数')
        OMFITx.CompoundGUI(
            root['TGLF']['GUIS']['TGLF_GUI'],
            inp_loc=treeLocation(root['TGYRO']['INPUTS']['input.tglf'])[-1],
            showLocalTab=False,
            showButtons=False,
            showNumSpecies=False,
        )

        # ===============================
        OMFITx.Tab('粒子输运径向剖面')
        OMFITx.CompoundGUI(root['GUIS']['particleDandVgui'])

        # ===============================
        OMFITx.Tab('扫描与敏感性分析')
        OMFITx.CompoundGUI(root['GUIS']['DV_scans_subgui'])

else:
    OMFITx.Label('')
    OMFITx.Label('填写扫描名称后进行敏感性分析')
