OMFITx.TitleGUI('CGYRO scan')
OMFITx.Tab('Run and inspect')

def prepare_only():
    setup = root['SETTINGS']['SETUP']
    previous = setup['irun']
    try:
        setup['irun'] = 0
        root['SCRIPTS']['subscan_lin.py'].run(scan_dimensions=int(setup['idimrun']))
    finally:
        setup['irun'] = previous

OMFITx.Button('Prepare inputs only', prepare_only)
OMFITx.Button('Run configured scan', lambda: root['SCRIPTS']['runCGYRO.py'].run())
OMFITx.Button('Load current run results', lambda: root['SCRIPTS']['downsync.py'].run())
OMFITx.Button('Plot linear frequency and growth', lambda: root['PLOTS']['CGYROscan']['linCGYRO.py'].run())
OMFITx.Button('Plot quasilinear weights', lambda: root['PLOTS']['CGYROscan']['qlflux.py'].run())
