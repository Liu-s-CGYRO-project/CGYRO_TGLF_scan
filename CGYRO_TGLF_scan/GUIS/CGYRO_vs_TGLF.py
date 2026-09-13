"""Comparison entry with the project-level template manager."""
from OMFITlib_compare_ui import ComparisonUI

if not globals().get('compoundGUI', False) and 'main' in root.get('GUIS', {}):
    OMFITx.Button('Project 总控', lambda: root['GUIS']['main'].run())

# Run the sibling module's GUI: OMFIT library imports are scoped to the current root.
open_templates = (lambda: OMFIT['OMFITtemplates']['GUIS']['main'].run()) if 'OMFITtemplates' in OMFIT else None
ComparisonUI(root, OMFITx).render(open_templates=open_templates)
