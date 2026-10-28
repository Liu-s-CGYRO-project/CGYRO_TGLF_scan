from OMFITlib_gui_api import adapt
OMFITx = adapt(OMFITx)
from OMFITlib_gui_layout import finish_gui_layout
from OMFITlib_gui_deferred import TabPages

from OMFITlib_gui_deferred import deferred_section

def render_module():
    # -*-Python-*-
    # Created by sciortinof at 16 Jul 2019  14:46

    """
    This script sets up a GUI to run TGLF scans to probe the sensitivity of growth rates and D,V transport coefficients
    to input variables.

    """

    # Create database structure for all results

    layout_anchor = OMFITx.Label('', align='left')
    layout_anchor.master.pack_forget()

    root.setdefault('TGLF_SCAN_DB', OMFITtree())


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



    def render_page(page):
        if page == 'setup':
            OMFITx.CompoundGUI(root['TGYRO']['PROFILES_GEN']['GUIS']['standaloneGUI'])
        elif page == 'ions':
            OMFITx.Label('此处仅设置背景离子，暂不添加示踪杂质。', align='left')
            OMFITx.CompoundGUI(root['TGYRO']['PROFILES_GEN']['GUIS']['modifyIonsGUI'])
        elif page == 'parameters':
            OMFITx.CompoundGUI(
                root['TGLF']['GUIS']['TGLF_GUI'],
                inp_loc=treeLocation(root['TGYRO']['INPUTS']['input.tglf'])[-1],
                showLocalTab=False, showButtons=False, showNumSpecies=False)
        else:
            name = 'particleDandVgui' if page == 'transport' else 'DV_scans_subgui'
            OMFITx.CompoundGUI(root['GUIS'][name])


    if root['SETTINGS']['PHYSICS']['runs_label']:
        captions = {'setup': 'Setup'}
        if 'input.gacode' in root['TGYRO']['PROFILES_GEN']['OUTPUTS']:
            captions.update({'ions': '背景离子', 'parameters': 'TGLF 参数',
                             'transport': '粒子输运径向剖面', 'scans': '扫描与敏感性分析'})
        pages = TabPages(OMFITx, captions, root['SETTINGS'].setdefault('GUI', {}), 'dv_tab', render_page)
    else:
        OMFITx.Label('填写扫描名称后进行敏感性分析')

    finish_gui_layout(layout_anchor, OMFITx)


content = deferred_section(OMFITx, render_module, local=True, container=True, action=True)
if content is None:
    render_module()
else:
    content.show()
