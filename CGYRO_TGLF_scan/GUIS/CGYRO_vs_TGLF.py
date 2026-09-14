"""Comparison entry with the project-level template manager."""
from OMFITlib_compare_ui import ComparisonUI

# Run the sibling module's GUI: OMFIT library imports are scoped to the current root.
open_templates = (lambda: OMFIT['OMFITtemplates']['GUIS']['main'].run()) if 'OMFITtemplates' in OMFIT else None
ComparisonUI(root, OMFITx).render(open_templates=open_templates)
