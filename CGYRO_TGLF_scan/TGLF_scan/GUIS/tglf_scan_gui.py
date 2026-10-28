from OMFITlib_gui_api import task_action
from OMFITlib_gui_api import plot_view
from OMFITlib_gui_api import adapt
from OMFITlib_gui_deferred import TabPages, deferred_section
from OMFITlib_gui_layout import finish_gui_layout

OMFITx = adapt(OMFITx)


def render_module():
    OMFITx.TitleGUI('TGLF 参数与径向扫描')
    layout_anchor = OMFITx.Label('', align='left')
    layout_anchor.master.pack_forget()
    for name in ('scanResults', 'scanResults2D', 'input.tglf', 'tgyro_output'):
        root.setdefault(name, OMFITtree())
    physics = root['SETTINGS']['PHYSICS']
    child_physics = root['TGLF']['SETTINGS']['PHYSICS']
    profiles = root['TGYRO']['PROFILES_GEN']
    has_profiles = 'input.gacode' in profiles['OUTPUTS'] or bool(profiles.get('MULTI', {}))
    has_inputs = bool(root['input.tglf'])
    OMFITx.CheckBox("root['SETTINGS']['PHYSICS']['tglf_input_load']",
        '载入 input.tglf（请先于 input.gacode 载入）', default=False, updateGUI=True, refresh_tree=False)
    OMFITx.CheckBox("root['SETTINGS']['PHYSICS']['tglf_settings_from_TGYRO']",
        '使用 TGYRO 中的 TGLF 参数设置页', default=False, updateGUI=True, refresh_tree=False)
    if physics['tglf_settings_from_TGYRO']:
        input_gui = root['TGLF']['GUIS']['TGLFfromTGYROgui']
        input_options = dict(guis_loc=root['TGYRO']['GUIS']['TGLFinputGUI'],
            settings_loc_str=treeLocation(root['TGYRO']['SETTINGS'])[-1],
            inp_loc_tgyro_str=treeLocation(root['TGYRO'])[-1])
        root['TGYRO']['SETTINGS']['PHYSICS']['Turb_Model'] = 'TGLF'
    else:
        input_gui = root['TGLF']['GUIS']['TGLF_GUI']
        input_options = {}
    if has_inputs:
        coordinate = 'rho' if root['TGYRO']['INPUTS']['input.tgyro']['TGYRO_USE_RHO'] else 'r/a'
        OMFITx.ComboBox("root['SETTINGS']['PHYSICS']['rho']", sorted(root['input.tglf']),
            '半径（%s）' % coordinate, default=0.5, updateGUI=True, state='readonly', refresh_tree=False)
        OMFITx.ComboBox("root['SETTINGS']['PHYSICS']['scanDimensions']",
            {'径向扫描': 0, '一维': 1, '二维': 2, '不确定度': 'UQ'}, '扫描维数',
            default=0, updateGUI=True, state='readonly', refresh_tree=False)

    def render_inputs():
        if not has_inputs:
            source = root['TGYRO']['INPUTS']['input.tglf']
            source['USE_TRANSPORT_MODEL'] = True
            OMFITx.CompoundGUI(input_gui, inp_loc=treeLocation(source)[-1],
                showLocalTab=False, showButtons=False, showNumSpecies=False, **input_options)
            script = 'setup_batch_tglf' if profiles['TRXPL']['SETTINGS']['EXPERIMENT']['multiwindow'] else 'setup_tglf'
            OMFITx.Button('生成 TGLF 输入', lambda: task_action(root['SCRIPTS'][script]))
            return
        OMFITx.Label('使用所选半径的输入。可在工程总控 → TGLF 中比较后将其用作单文件输入。')
        OMFITx.CheckBox("root['SETTINGS']['PHYSICS']['show_TGLF_details']", '显示 TGLF 详细设置',
                       default=False, updateGUI=True, refresh_tree=False)
        if physics['show_TGLF_details'] and physics['rho'] in root['input.tglf']:
            OMFITx.CompoundGUI(input_gui, inp_loc=treeLocation(root['input.tglf'][physics['rho']])[-1],
                showButtons=False, allowOptions=['TGLF', 'TGLF-NN'], title='', showLocalTab=False, **input_options)

    def render_profiles():
        # Preparation may be empty after changing its source. Keep retained results.
        if has_inputs:
            OMFITx.Button('重新开始', "root['TGYRO']['PROFILES_GEN']['SCRIPTS']['reset']")
        OMFITx.CompoundGUI(profiles['GUIS']['standaloneGUI'])
        if physics['tglf_input_load']:
            OMFITx.ObjectPicker("root['TGYRO']['INPUTS']['input.tglf']", lbl='input.tglf 输入文件', objectType=OMFITgacode)

    def render_scan():
        dimension, rho = physics['scanDimensions'], physics['rho']
        if dimension == 0:
            OMFITx.CompoundGUI(root['GUIS']['tglf_radial_gui'])
            return
        if rho not in root['input.tglf']:
            OMFITx.Label('请选择已有输入的半径。')
            return
        name = {1: 'scanGUI', 2: 'scan2DGUI', 'UQ': 'uqGUI'}[dimension]
        if dimension == 'UQ':
            child_physics['rho'] = rho
        OMFITx.CompoundGUI(root['TGLF']['GUIS'][name], showButtons=False, title='')
        OMFITx.Button('运行 TGLF 扫描', lambda: task_action(root['SCRIPTS']['runScanAtRho'], copy_inputTGLF_rho=False))
        if dimension == 'UQ':
            group = '_'.join(child_physics['scanParameters'])
            if group in root.get('UQResults', {}).get(rho, {}):
                showUQPlots()
        else:
            group = child_physics['scanParameter']
            branch = 'scanResults'
            if dimension == 2:
                group = child_physics['scanParameter2D'] + '+' + group
                branch = 'scanResults2D'
            if group in root[branch].get(rho, {}):
                showPlots()

    def showPlots():
        OMFITx.Separator()
        OMFITx.CheckBox("root['SETTINGS']['PHYSICS']['plot_mks']", '通量采用国际单位制', default=True, refresh_tree=False)
        OMFITx.CheckBox("root['TGLF']['SETTINGS']['PHYSICS']['combine_ions']", '绘图时合并离子', default=True, refresh_tree=False)
        OMFITx.CheckBox("root['SETTINGS']['PHYSICS']['tglf_sign_convention']", '采用 TGLF 动量目标的符号约定', default=True, refresh_tree=False)
        OMFITx.CheckBox("root['SETTINGS']['PLOTS']['Use_x_log']", 'X 轴采用对数坐标', default=True, refresh_tree=False)
        OMFITx.CheckBox("root['SETTINGS']['PLOTS']['Use_y_log']", 'Y 轴采用对数坐标', default=True, refresh_tree=False)
        OMFITx.CheckBox("root['SETTINGS']['PLOTS']['Divided ky']", '绘制数值除以 ky 后的数据', default=True, refresh_tree=False)
        OMFITx.Button('绘制 %d 维 TGLF 扫描' % root['SETTINGS']['PHYSICS']['scanDimensions'], lambda: plot_view(root['PLOTS']['plotScanAtRho']), refresh_tree=False)
        if root['SETTINGS']['PHYSICS']['scanDimensions'] == 1:
            OMFITx.Button('绘制一维 TGLF 扫描谱', lambda: plot_view(root['PLOTS']['plotScanSpecAtRho']), refresh_tree=False)
        OMFITx.Separator()
        OMFITx.Button(
            '导出 %d 维 TGLF 扫描数据' % root['SETTINGS']['PHYSICS']['scanDimensions'],
            lambda: plot_view(root['PLOTS']['plotScanAtRho'], doSave=True),
            refresh_tree=False,
        )

    def showUQPlots():
        OMFITx.Separator()
        OMFITx.CheckBox("root['SETTINGS']['PHYSICS']['plot_mks']", '通量采用国际单位制', default=True, refresh_tree=False)
        OMFITx.CheckBox("root['TGLF']['SETTINGS']['PHYSICS']['combine_ions']", '绘图时合并离子', default=True, refresh_tree=False)
        OMFITx.CheckBox("root['SETTINGS']['PHYSICS']['tglf_sign_convention']", '采用 TGLF 动量目标的符号约定', default=True, refresh_tree=False)
        OMFITx.CheckBox("root['SETTINGS']['PHYSICS']['exp_prob']", '绘制实验子时间窗概率', default=False, refresh_tree=False)
        OMFITx.Button(
            '绘制 %d 维 TGLF 扫描不确定度传播' % root['TGLF']['SETTINGS']['PHYSICS']['scanDimensions'], lambda: plot_view(root['PLOTS']['plot_UQ']),
            refresh_tree=False,
        )

    captions = {}
    if has_profiles or has_inputs:
        captions['inputs'] = '指定半径输入' if has_inputs else '准备 TGLF 输入文件'
    if has_inputs:
        captions['scan'] = '扫描设置'
    captions['profiles'] = '准备输入剖面'
    renderers = {'inputs': render_inputs, 'scan': render_scan, 'profiles': render_profiles}
    TabPages(OMFITx, captions, root['SETTINGS'].setdefault('GUI', {}), 'scan_tab',
             lambda page: renderers[page]())
    finish_gui_layout(layout_anchor, OMFITx)


content = deferred_section(OMFITx, render_module, local=True, container=True, action=True)
if content is None:
    render_module()
else:
    content.show()
