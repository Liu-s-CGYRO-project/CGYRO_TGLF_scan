"""Input, scan and run sub-tabs inside the native CGYRO workbench."""
defaultVars(workbench=None)

if workbench is None:
    root['GUIS']['main'].run(workbench_page='cgyro')
else:
    workbench.render_cgyro_scan_tabs()

