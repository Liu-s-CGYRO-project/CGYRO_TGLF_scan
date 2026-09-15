# -*-Python-*-
# Created by snoepg at 20 Jul 2017  10:54

OMFITx.TitleGUI('TGYRO 粒子扩散与内箍分析')

OMFITx.Label('D / V 系数需要基于已收敛的运行结果计算。')
if input_gacode is None:
    OMFITx.End()

OMFITx.Separator()

max_nions = 0
species_choices = SortedDict()
# species_choices['Electrons']=1
if input_gacode is not None and 'N_ION' in input_gacode:
    max_nions = input_gacode['N_ION']
for i in range(max_nions):
    ion_name = input_gacode['IONS'][i + 1][0]
    ion_type = input_gacode['IONS'][i + 1][3]
    if ion_type == 'therm':
        species_choices["{} ({}) Ions".format(ion_name, ion_type)] = i + 1

new_trace = scratch.setdefault('add_trace_impurity', False)

if not new_trace:
    OMFITx.ComboBox(
        "root['SETTINGS']['PHYSICS']['ZERO_DENS_GRAD_FLAG']",
        species_choices,
        '选择需要计算 D / V 剖面的物种',
        state='normal',
        default=1,
    )
else:
    # the trace impurity density will be subtracted from the first ion
    root['SETTINGS']['PHYSICS']['ZERO_DENS_GRAD_FLAG'] = 1

OMFITx.CheckBox(
    "scratch['add_trace_impurity']",
    '添加示踪杂质',
    default=False,
    updateGUI=True,
    help='Add trace impurity which is not included in input.gacode',
)

if new_trace:
    OMFITx.Separator('示踪杂质')
    OMFITx.Entry("root['SETTINGS']['PHYSICS']['trace_imp_name']", 'Name', default='C')
    OMFITx.Entry("root['SETTINGS']['PHYSICS']['trace_imp_Z']", 'Charge', default=6)
    OMFITx.Entry("root['SETTINGS']['PHYSICS']['trace_imp_M']", 'Mass', default=12)
else:
    if 'trace_imp_name' in root['SETTINGS']['PHYSICS']:
        root['SETTINGS']['PHYSICS'].pop('trace_imp_name')

OMFITx.CheckBox("root['SETTINGS']['PHYSICS']['extendedProfiles']", '以更高分辨率计算 D 和 V', default=False)
OMFITx.CheckBox(
    "root['SETTINGS']['PHYSICS']['robustDVprofiles']",
    '稳健计算（较慢）',
    default=False,
    help="""Calculate flux for 5 values of impurity gradient. If
the gradient-flux relation is not a straight line, remove the worst point
and check again. If there are no 3 points
creating a straight line, ignore this radial location.""",
)


OMFITx.Separator()


OMFITx.Button('Compute D and v', "root['SCRIPTS']['D_and_v'].run")


if 'D_and_v' in root['OUTPUTS']:

    OMFITx.CheckBox(
        "root['SETTINGS']['PHYSICS']['STRAHL_like_DV']",
        '采用 STRAHL 对 D 和 V 的定义',
        default=False,
        help='STRAHL uses a different definition o a radial coordinate and\n'
        + 'density gradients are calculated with respect to a flux surface averadged density',
    )

    OMFITx.Button('Plot D and v profiles', "root['PLOTS']['plotDandV'].run")

if 'output' in root['OUTPUTS']:
    OMFITx.Button('绘制热扩散系数', "root['PLOTS']['plotChi'].run")
