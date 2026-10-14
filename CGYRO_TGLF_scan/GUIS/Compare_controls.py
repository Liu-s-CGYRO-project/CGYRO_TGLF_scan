"""Native child Notebook for one comparison mode."""
defaultVars(comparison=None, mode='CGYRO_vs_TGLF', open_templates=None)

if comparison is None:
    root['GUIS']['CGYRO_vs_TGLF'].run()
else:
    comparison.render_controls(mode, open_templates=open_templates)
