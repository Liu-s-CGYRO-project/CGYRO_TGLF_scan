OMFITx.TitleGUI('CGYRO 扫描')
OMFITx.Tab('运行与检查')

def prepare_only():
    setup = root['SETTINGS']['SETUP']
    previous = setup['irun']
    try:
        setup['irun'] = 0
        root['SCRIPTS']['subscan_lin.py'].run(scan_dimensions=int(setup['idimrun']))
    finally:
        setup['irun'] = previous

OMFITx.Button('仅生成输入', prepare_only)
OMFITx.Button('运行已配置扫描', lambda: root['SCRIPTS']['runCGYRO.py'].run())
OMFITx.Button('读取当前运行结果', lambda: root['SCRIPTS']['downsync.py'].run())
OMFITx.Button('绘制线性频率与增长率', lambda: root['PLOTS']['CGYROscan']['linCGYRO.py'].run())
OMFITx.Button('绘制准线性权重', lambda: root['PLOTS']['CGYROscan']['qlflux.py'].run())
