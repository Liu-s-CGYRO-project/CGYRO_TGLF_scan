# -*-Python-*-
# Created by meneghini at 2015/03/28 14:31

defaultVars(showButtons=True)

param = root['SETTINGS']['PHYSICS']['scanParameter']
param2 = root['SETTINGS']['PHYSICS']['scanParameter2D']

OMFITx.TitleGUI('TGLF 二维扫描')

if 'input.tglf' in root['FILES']:
    OMFITx.Tab('Parameter 1')
    OMFITx.CompoundGUI(root['GUIS']['scanGUI'], showButtons=False, show_constraints=False)
    OMFITx.Tab('Parameter 2')
    OMFITx.CompoundGUI(root['GUIS']['scanGUI'], paramN='2D', showButtons=False, show_constraints=False)
    OMFITx.Tab('Constraints')
    OMFITx.CompoundGUI(root['GUIS']['constraints_GUI'], title='', input_tglf=root['FILES']['input.tglf'])
    OMFITx.Tab('')
    if showButtons:
        OMFITx.Button('运行 TGLF 二维扫描', "root['SCRIPTS']['runTGLFscan2D']")
        if 'scanResults2D' in root and len(root['scanResults2D']) and param2 + '+' + param in root['scanResults2D']:
            OMFITx.CheckBox("root['SETTINGS']['PHYSICS']['combine_ions']", '绘图时合并离子', default=True)
            OMFITx.Button('绘制 TGLF 二维扫描结果', "root['PLOTS']['plotScan2D'].plotFigure")
else:
    OMFITx.Label('请先在 FILES 中准备 input.tglf')
    OMFITx.ObjectPicker("root['FILES']['input.tglf']", "input.tglf", OMFITgacode)
