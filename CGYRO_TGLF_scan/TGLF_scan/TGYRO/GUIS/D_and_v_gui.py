# -*-Python-*-
# Created by snoepg at 20 Jul 2017  10:54

OMFITx.TitleGUI('TGYRO particle diffusion and pinch GUI')

OMFITx.Label('NOTE: D/v coefficients can be reliably obtained only starting from a converged run')
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
        'Species to compute D and v profiles for',
        state='normal',
        default=1,
    )
else:
    # the trace impurity density will be subtracted from the first ion
    root['SETTINGS']['PHYSICS']['ZERO_DENS_GRAD_FLAG'] = 1

OMFITx.CheckBox(
    "scratch['add_trace_impurity']",
    'Add another trace impurity',
    default=False,
    updateGUI=True,
    help='Add trace impurity which is not included in input.gacode',
)

if new_trace:
    OMFITx.Separator('Trace impurity')
    OMFITx.Entry("root['SETTINGS']['PHYSICS']['trace_imp_name']", 'Name', default='C')
    OMFITx.Entry("root['SETTINGS']['PHYSICS']['trace_imp_Z']", 'Charge', default=6)
    OMFITx.Entry("root['SETTINGS']['PHYSICS']['trace_imp_M']", 'Mass', default=12)
else:
    if 'trace_imp_name' in root['SETTINGS']['PHYSICS']:
        root['SETTINGS']['PHYSICS'].pop('trace_imp_name')

OMFITx.CheckBox("root['SETTINGS']['PHYSICS']['extendedProfiles']", 'Calculate D and V in a higher resolution', default=False)
OMFITx.CheckBox(
    "root['SETTINGS']['PHYSICS']['robustDVprofiles']",
    'Robust Calculation (slow!)',
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
        'Use STRAHL definition of D and V',
        default=False,
        help='STRAHL uses a different definition o a radial coordinate and\n'
        + 'density gradients are calculated with respect to a flux surface averadged density',
    )

    OMFITx.Button('Plot D and v profiles', "root['PLOTS']['plotDandV'].run")

if 'output' in root['OUTPUTS']:
    OMFITx.Button('Plot heat diffusion coefficients', "root['PLOTS']['plotChi'].run")
