# -*-Python-*-
# Created by avdeevag at 01 Mar 2023  07:13

"""
This script <fill in purpose>

defaultVars parameters
----------------------
:param kw1: kw1 can be passed to this script as <path to script>.run(kw1='hello')
"""
OMFITx.TitleGUI('TGLF')

defaultVars(
    inp_loc="root['INPUTS']['input.tglf']",  # need to pass this parameter through the TGLF_scan_gui
    inp_loc_tgyro_str="root['INPUTS']['input.tgyro']",  # probably do not need to pass this parameter through the TGLF_scan_gui
    settings_loc_str="root['SETTINGS']",
)
inp_loc_tree = eval(inp_loc)

inp_loc_tgyro = eval(inp_loc_tgyro_str)

settings_loc = eval(settings_loc_str)

OMFITx.Tab('TGLF')
# TGLF model

OMFITx.CheckBox(
    settings_loc_str + "['PHYSICS']['Customized_TGLF_input']",
    '自定义 TGLF 设置',
    default=False,
    updateGUI=True,
    help=''' The optimal default settings are summarized in TGLF scenarious.
            It is not recommended to deviate from the default settings without consulting Gary Staebler''',
)

if settings_loc['PHYSICS']['Customized_TGLF_input']:
    OMFITx.Label(
        'TGLF 参数方案提供推荐默认值。\n如需调整这些默认设置，建议咨询 Gary Staebler。',
        foreground='red',
    )

tglf_options = SortedDict()
tglf_options['Quench rule (SAT_RULE=0)'] = [1.0, 0, 0.0, 12, 1, 4, 4, 'GYRO', 2, 0.0, False]
tglf_options['Conventional (SAT_RULE=0)'] = [0.0, 0, 0.0, 12, 1, 4, 4, 'GYRO', 2, 0.0, False]
tglf_options['Conventional (SAT_RULE=1)'] = [0.0, 1, 1.0, 12, 1, 4, 4, 'GYRO', 2, 0.0, False]
tglf_options['Conventional(SAT_RULE=2)'] = [0.0, 2, 1.0, 12, 4, 6, 4, 'CGYRO', 3, 1.0, True]
tglf_options['JET (SAT_RULE=2)'] = [0.0, 2, 1.0, 17, 4, 6, 5, 'CGYRO', 3, 1.0, True]
tglf_options['ST (ETG resolution for low B, high Beta)'] = [0.0, 1, 1.0, 12, 4, 4, 4, 'GYRO', 2, 0.0, False]
tglf_options['ITER (ETG resolution for ITER)'] = [0.0, 1, 1.0, 20, 4, 4, 4, 'GYRO', 2, 0.0, False]

# some settings will be locked depending on the scenario, revision or SAT_RUL
state_revision = 'enabled'
state_quench = 'enabled'
state_xnu_model = 'enabled'
state = 'enabled'
state_quench = 'disabled'
state_em = 'enabled'

if settings_loc['PHYSICS']['Customized_TGLF_input'] == False:

    OMFITx.ComboBox(
        [
            inp_loc + "['%s']" % k
            for k in [
                'ALPHA_QUENCH',
                'SAT_RULE',
                'ALPHA_ZF',
                'NKY',
                'KYGRID_MODEL',
                'NBASIS_MAX',
                'NMODES',
                'UNITS',
                'XNU_MODEL',
                'WDIA_TRAPPED',
                'USE_AVE_ION_GRID',
            ]
        ],
        tglf_options,
        lbl='TGLF 参数方案',
        default=tglf_options['Conventional (SAT_RULE=1)'],
        updateGUI=True,
        help='TGLF scenarios adjust the wavenumber spectrum',
    )

    inp_loc_tgyro['TGYRO_TGLF_REVISION'] = 0
    state_revision = 'disabled'
    state_quench = 'disabled'
    state_xnu_model = 'disabled'
    state = 'disabled'

    OMFITx.Separator('以下设置由 TGLF 参数方案预先定义。', foreground='black')

else:
    if inp_loc_tree['SAT_RULE'] == 0:
        inp_loc_tree['ALPHA_ZF'] = 0
    else:
        inp_loc_tree['ALPHA_ZF'] = 1

    OMFITx.Separator('自定义设置', foreground='black')

OMFITx.ComboBox(
    inp_loc_tgyro_str + "['TGYRO_TGLF_REVISION']",
    {
        '0 - Customize settings': 0,
        '2 - Quench rule (2009)': 2,
        '3 - Spectral shift ExB shear model': 3,
        '4 - Momentum transport without EM terms': 4,
    },
    'TGLF 修订版本',
    default=3,
    help='''The Waltz quench rule has only been calibrated to GYRO for SAT_RULE=0 and the linear growth rates output to the file out.tglf.eigenvalue spectrum will be the net growth rate after the quench rule is applied, not the actual growth rates. ''',
    updateGUI=True,
    state=state_revision,
)

if inp_loc_tgyro['TGYRO_TGLF_REVISION'] == 2:
    inp_loc_tree['ALPHA_QUENCH'] = 1.0

elif inp_loc_tgyro['TGYRO_TGLF_REVISION'] in [3, 4]:
    inp_loc_tree['ALPHA_QUENCH'] = 0.0

if inp_loc_tgyro['TGYRO_TGLF_REVISION'] >= 3:
    inp_loc_tree['XNU_MODEL'] = 1
    state_xnu_model = 'disabled'

    OMFITx.Entry(
        inp_loc + "['ALPHA_E']",
        'ALPHA_E',
        default=1,
        state='disabled',
        help='''Multiplies ExB velocity shear for spectral shift model''',
    )
    OMFITx.Entry(
        inp_loc + "['ALPHA_P']",
        'ALPHA_P',
        default=1,
        state='disabled',
        help='''Multiplies parallel velocity shear for all species''',
    )

if inp_loc_tgyro['TGYRO_TGLF_REVISION'] == 4:
    state_em = 'disabled'
    inp_loc_tree['USE_BPER'] = False
    inp_loc_tree['USE_BPAR'] = False
    inp_loc_tree['USE_MHD_RULE'] = False

if settings_loc['PHYSICS']['Customized_TGLF_input'] and inp_loc_tgyro['TGYRO_TGLF_REVISION'] == 0:
    state_quench = 'enabled'

OMFITx.ComboBox(
    inp_loc + "['ALPHA_QUENCH']",
    {'0': 0.0, '1': 1.0},
    default=0.0,
    lbl="ALPHA_QUENCH",
    updateGUI=True,
    state=state_quench,
    help='''0 = New spectral shift model; 1= Quench rule (2009) that replaces growth rate by growth relative to ExB shear [Waltz 1997].  QL weights from GYRO [Staebler 2007]''',
)

OMFITx.ComboBox(
    inp_loc + "['SAT_RULE']",
    {'0': 0, '1': 1, '2': 2},
    lbl="SAT_RULE",
    updateGUI=True,
    default=1,
    state=state,
    help='''SAT0 - Spectral shift [Staebler 2013] and quasilinear weights from GYRO [Staebler 2007].
SAT1 - Spectral shift [Staebler 2013] and quasilinear weights from multiscale GYRO [Staebler 2017] or CGYRO [Staebler 2021].
SAT2 - Spectral shift [Staebler 2013] new collision model and quasilinear weights from CGYRO [Staebler 2021].''',
)

if inp_loc_tree['SAT_RULE'] != 0 and inp_loc_tree['ALPHA_QUENCH'] == 1.0:
    OMFITx.Label('Waltz 抑制规则（ALPHA_QUENCH=1）仅在 SAT_RULE=0 时\n经过 GYRO 标定。', foreground='red')

OMFITx.Entry(
    inp_loc + "['ALPHA_ZF']",
    lbl="ALPHA_ZF",
    default=1,
    state='disabled',
    help='Zonal flow, should be switched on (1) for SAT1 and SAT1.',
)

OMFITx.ComboBox(
    inp_loc + "['KYGRID_MODEL']",
    {'0': 0, '1': 1, '3': 3, '4': 4},
    default=1,
    lbl="KYGRID_MODEL",
    state=state,
    help=''' 0 = user defined with NKY modes up to KY equal spaced;
1 = standard ky spectrum for transport model;
3 and 4 = new options for ITER and ST scenarios''',
    updateGUI=True,
)


def check_nky(s):
    if not is_int(s):
        return False
    maxky0 = 480
    if s > maxky0:
        printe('For the user defined ky spectrum, the max number of NKY is ' + str(maxky0))
        return False
    else:
        return True


if inp_loc_tree['KYGRID_MODEL'] == 0:
    OMFITx.Entry(inp_loc + "['KY']", lbl='KY', help='自定义 ky 网格最大值', default=0.3)

    OMFITx.Entry(
        inp_loc + "['NKY']",
        default=12,
        lbl="NKY",
        state=state,
        help='''Number of poloidal modes in the high-k spectrum. You might choose to increase it if you're simulating a plasma with a lot of high-k transport.
For the user defined ky spectrum (['KYGRID_MODEL'] == 0), the max number of NKY is 480.''',
        check=check_nky,
        updateGUI=True,
    )
else:
    OMFITx.Entry(
        inp_loc + "['NKY']",
        default=12,
        lbl="NKY",
        state=state,
        help='''Number of poloidal modes in the high-k spectrum. You might choose to increase it if you're simulating a plasma with a lot of high-k transport.
For the user defined ky spectrum (['KYGRID_MODEL'] == 0), the max number of NKY is 480.''',
        check=is_int,
        updateGUI=True,
    )

GYRO_units = []
if inp_loc_tree['SAT_RULE'] == 0:
    inp_loc_tree['UNITS'] = 'GYRO'
    state_units = 'disabled'
elif inp_loc_tree['SAT_RULE'] == 1:
    GYRO_units = ['GYRO', 'CGYRO']
    state_units = state
elif inp_loc_tree['SAT_RULE'] == 2:
    inp_loc_tree['UNITS'] = 'CGYRO'
    state_units = 'disabled'
elif inp_loc_tree['SAT_RULE'] == 3:
    inp_loc_tree['UNITS'] = 'CGYRO'
    state_units = 'disabled'


OMFITx.ComboBox(
    inp_loc + "['UNITS']",
    GYRO_units,
    default='GYRO',
    lbl="UNITS",
    state=state_units,
    updateGUI=True,
    help='''TGLF calibration is for the quasilinear weights from GYRO or CGYRO.
SAT0 - GYRO ;
SAT1 - GYRO or CGYRO;
SAT2 - CGYRO.
SAT3 - CGYRO.''',
)

if (
    settings_loc['PHYSICS']['Customized_TGLF_input']
    and inp_loc_tree['SAT_RULE'] == 1
    and inp_loc_tree['ALPHA_QUENCH'] == 0.0
    and inp_loc_tree['UNITS'] != 'CGYRO'
):
    OMFITx.Label('高 β 等离子体建议将 UNITS 设为 CGYRO。', foreground='black')


def sat_rule_restr(val):
    if inp_loc_tree['SAT_RULE'] == 0 and (val not in [2, 4]):
        printe('For SAT0 NMODES can only be either 2 or 4')
        return False
    elif not is_int(val):
        return False
    else:
        return True


OMFITx.Entry(
    inp_loc + "['NMODES']",
    default=4,
    lbl="NMODES",
    state=state,
    help='''Number of modes to compute. For SAT0 can only be either 2 or 4. For other saturation rules it can be arbitrary.''',
    check=sat_rule_restr,
)

OMFITx.Entry(
    inp_loc + "['NBASIS_MAX']",
    default=4,
    lbl="NBASIS_MAX",
    state=state,
    help='''Maximum number of parallel basis functions. Default - 4. ''',
    check=sat_rule_restr,
)

if inp_loc_tree['SAT_RULE'] != 2 and not settings_loc['PHYSICS']['Customized_TGLF_input']:

    inp_loc_tree['XNU_MODEL'] = 2
    inp_loc_tree['WDIA_TRAPPED'] = 0.0

elif inp_loc_tree['SAT_RULE'] == 2 and not settings_loc['PHYSICS']['Customized_TGLF_input']:
    inp_loc_tree['XNU_MODEL'] = 3
    inp_loc_tree['WDIA_TRAPPED'] = 1.0
    # NKY and NMODES are already set by the selected scenario above.
    inp_loc_tree['NBASIS_MAX'] = 6
    inp_loc_tree['KYGRID_MODEL'] = 4
    inp_loc_tree['USE_AVE_ION_GRID'] = True

OMFITx.ComboBox(
    inp_loc + "['XNU_MODEL']",
    {'2': 2, '3': 3},
    default=2,
    lbl="XNU_MODEL",
    state=state,
    help='''Collision model.
2 = default collision model,
3 = improved collision model and isotope for SAT2''',
)

OMFITx.ComboBox(
    inp_loc + "['WDIA_TRAPPED']",
    {'0.0': 0.0, '1.0': 1.0},
    default=0,
    lbl="WDIA_TRAPPED",
    state='disabled',
    help='''New model for the loss of bounce averaging due to the diamagnetic drift.
0 = default, 1 = for SAT2''',
)

OMFITx.Entry(
    inp_loc + "['USE_AVE_ION_GRID']",
    default=False,
    lbl="USE_AVE_ION_GRID",
    state=state,
    help='''This setting is used with SAT2 for DT plasma''',
    check=is_int,
)

OMFITx.Separator()

EMcontr = SortedDict()
EMcontr['Electrostatic (Phi)'] = [False, False]
EMcontr['Electromagnetic (Phi + BPAR (B||) + BPER (A||))'] = [True, True]
EMcontr['Electromagnetic (Phi + BPER (A||))'] = [True, False]

OMFITx.ComboBox(
    [inp_loc + "['%s']" % k for k in ['USE_BPER', 'USE_BPAR']],
    EMcontr,
    lbl='电磁贡献',
    default=[False, False],
    updateGUI=True,
    state=state_em,
    help='''MHD_RULE (Phi) - Ignore pressure gradient contribution to curvature drift (MHD rule)
BPER (A||) - Include transverse magnetic fluctuations (perpendicular B effects)
BPAR (B||) - Include compressional magnetic fluctuations (parallel B effects)
Note - for EM effects mach number effects are removed ALPHA_MACH=0.0 ''',
)

if inp_loc_tgyro['TGYRO_TGLF_REVISION'] == 4:
    inp_loc_tree['ALPHA_MACH'] = 1.0
    OMFITx.Entry(
        inp_loc + "['ALPHA_MACH']",
        'ALPHA_MACH',
        default=1,
        state='disabled',
        help='''Multiplies parallel velocity for all species.''',
    )
else:
    inp_loc_tree['ALPHA_MACH'] = 0.0
