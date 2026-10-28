"""Comparison entry with the project-level template manager."""
from OMFITlib_gui_api import gui_view
from OMFITlib_gui_api import adapt
OMFITx = adapt(OMFITx)
from OMFITlib_compare_ui import ComparisonUI

# Run the sibling module's GUI: OMFIT library imports are scoped to the current root.
open_templates = (lambda: gui_view(OMFIT['OMFITtemplates']['GUIS']['main'])) if 'OMFITtemplates' in OMFIT else None
ComparisonUI(root, OMFITx).render(open_templates=open_templates)
