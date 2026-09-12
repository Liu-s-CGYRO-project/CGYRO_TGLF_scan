# -*-Python-*-
# Created by meneghini at 2015/07/05 14:26

OMFITx.TitleGUI('TGLF stiffness GUI')

b = OMFITx.Button('Calculate stiffness', "root['SCRIPTS']['runTGLFstiffness']")
b.configure(width=30)

if 'STIFFNESS' in root:
    OMFITx.Separator()
    OMFITx.Button('Plot stiffness', "root['PLOTS']['plotStiffness']")
