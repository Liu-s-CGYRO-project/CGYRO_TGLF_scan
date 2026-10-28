from OMFITlib_gui_api import adapt
OMFITx = adapt(OMFITx)
from OMFITlib_gui_deferred import TabPages

from OMFITlib_gui_deferred import deferred_section

def render_module():
    # -*-Python-*-
    # Created by meneghini at 2013/05/06 11:49
    OMFITx.TitleGUI('TGYRO 总控')

    if not compoundGUI and input_gacode is None:
        OMFITx.CompoundGUI(PROFILES_GEN['GUIS']['standaloneGUI'])
        OMFITx.End()


    def no_spaces(x):
        if re.findall(r'[\s,/,\\,(,)]', x):
            return False
        return True


    OMFITx.ComboBox(
        "root['SETTINGS']['EXPERIMENT']['runid']",
        list(root['RUN_DB'].keys()),
        '计算运行名称',
        postcommand=lambda location=None: root['SCRIPTS']['reloadTGYRO'].runNoGUI(),
        updateGUI=True,
        state='normal',
        check=no_spaces,
        refresh_tree=True,
    )



    def render_page(page):
        if page == 'run':
            OMFITx.CompoundGUI(root['GUIS']['Rungui'], '')
        elif page == 'plot':
            OMFITx.CompoundGUI(root['GUIS']['Plotgui'], '')
        elif page == 'transport':
            OMFITx.CompoundGUI(root['GUIS']['D_and_v_gui'], '')
        else:
            render_export()


    def render_export():
        OMFITx.Separator()

        def ip_2_ods():
            root['OUTPUTS']['ods'] = root['OUTPUTS']['input.gacode'].to_omas()

        OMFITx.Button('从 input.gacode 生成 ODS', ip_2_ods)

        OMFITx.Separator('IMAS')
        OMFITx.ComboBox(
            "scratch['serverPicker']",
            {'ITER IMAS': 'iter_login', 'GATEWAY IMAS': 'itm_gateway'},
            'Server',
            default='iter_login',
            help='IMAS server',
            refresh_tree=False,
        )
        OMFITx.Entry("scratch['machine']", 'Machine', default=root['SETTINGS']['EXPERIMENT']['device'], help='IMAS machine', refresh_tree=False)
        OMFITx.Entry("scratch['pulse']", 'Pulse', check=is_int, default=root['SETTINGS']['EXPERIMENT']['shot'], help='IMAS pulse', refresh_tree=False)
        OMFITx.Entry("scratch['run']", '运行', check=is_int, default=root['SETTINGS']['EXPERIMENT']['time'], help='IMAS run', refresh_tree=False)

        def ip_2_ids():
            if 'ods' not in root['OUTPUTS']:
                root['OUTPUTS']['ods'] = root['OUTPUTS']['input.gacode'].to_omas()
            for item in root['OUTPUTS']['ods']:
                if 'time' not in root['OUTPUTS']['ods']:
                    root['OUTPUTS']['ods'][item]['time'] = [0.0]
            save_omas_imas_remote(
                scratch['serverPicker'],
                root['OUTPUTS']['ods'],
                pulse=scratch['pulse'],
                machine=scratch['machine'],
                run=scratch['run'],
                new=True,
            )

        e = OMFITx.Button('保存到 IMAS', ip_2_ids, help='Choose a shot/run/device to export data to a IMAS database.')


    captions = {'run': '运行 TGYRO'}
    if 'input.gacode' in root['OUTPUTS'] or 'output' in root['OUTPUTS']:
        captions.update({'plot': '绘制结果', 'transport': 'D&v profiles'})
    if 'input.gacode' in root['OUTPUTS']:
        captions['export'] = '导出'
    pages = TabPages(OMFITx, captions, root['SETTINGS'].setdefault('GUI', {}), 'main_tab', render_page)


content = deferred_section(OMFITx, render_module, local=True, container=True, action=True)
if content is None:
    render_module()
else:
    content.show()
