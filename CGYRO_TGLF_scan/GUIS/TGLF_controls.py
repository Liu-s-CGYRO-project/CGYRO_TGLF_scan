"""Input, scan and run sub-tabs inside the native TGLF workbench."""
defaultVars(workbench=None)

if workbench is None:
    root['GUIS']['main'].run(workbench_page='tglf')
else:
    workbench.render_scan_tabs()
