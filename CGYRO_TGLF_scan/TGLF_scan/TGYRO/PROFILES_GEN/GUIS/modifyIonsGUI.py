# -*-Python-*-
# Created by grierson at 15 Aug 2017  05:30

"""
This script contains the GUI that drives the modify_ions script
that allows the user to add and remove ions from input.gacode

"""
defaultVars(add_ion=True)

OMFITx.TitleGUI('修改离子物种')

ions = []
for i in root['OUTPUTS']['input.gacode']['IONS']:
    if root['OUTPUTS']['input.gacode']['IONS'][i][3] == 'fast':
        ions.append('{}[{}]'.format(root['OUTPUTS']['input.gacode']['IONS'][i][0], root['OUTPUTS']['input.gacode']['IONS'][i][3]))
    else:
        ions.append(root['OUTPUTS']['input.gacode']['IONS'][i][0])
OMFITx.Label('Existing ions: {}'.format(ions))

opts = {'Add': True, 'Remove': False}
OMFITx.ComboBox("scratch['modify_ions_add']", opts, 'Action', default=add_ion, updateGUI=True)

if scratch['modify_ions_add']:
    OMFITx.Entry("scratch['add_ions_name']", 'Name', default='F')
    OMFITx.Entry("scratch['add_ions_Z']", 'Charge', default=9)
    OMFITx.Entry("scratch['add_ions_mass']", 'Mass', default=19.0)
    OMFITx.Entry("scratch['add_ions_concen']", 'Concentration', default=1e-6)
    OMFITx.Entry("scratch['add_ions_aoLn']", 'a/Ln', default=None)
    OMFITx.Entry("scratch['add_ions_num']", '列表序号', default=3)
    OMFITx.Button(
        '运行离子修改',
        lambda: root['SCRIPTS']['modify_ions'].run(
            name=scratch['add_ions_name'],
            Z=scratch['add_ions_Z'],
            mass=scratch['add_ions_mass'],
            concen=scratch['add_ions_concen'],
            aoLn=scratch['add_ions_aoLn'],
            ion_num=scratch['add_ions_num'],
            thermal=True,
            add=True,
        ),
    )
else:
    OMFITx.ComboBox("scratch['remove_ions_name']", ions, 'Name', default=ions[-1], updateGUI=True)
    # EYES for next few lines
    OMFITx.Button(
        '运行离子修改',
        lambda: root['SCRIPTS']['modify_ions'].run(
            name=scratch['remove_ions_name'].replace('[fast]', ''), thermal=not 'fast' in scratch.pop('remove_ions_name'), add=False
        ),
    )  # EYES
    # OMFITx.CheckBox("scratch['remove_ions_thermal']",'Thermal',default=False)
    # OMFITx.Button('Run MODIFY_IONS', lambda: root['SCRIPTS']['modify_ions'].run(name=scratch['remove_ions_name'], thermal=scratch['remove_ions_thermal'], add=False))

OMFITx.Button('重置 input.gacode', lambda: root['SCRIPTS']['modify_ions'].run(reset=True))
