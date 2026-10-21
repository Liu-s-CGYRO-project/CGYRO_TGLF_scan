"""Explicit Command Box/GUI task: compact the current archive, then Save As.

Run OMFIT['CGYRO_TGLF_scan']['SCRIPTS']['compact_cgyro_storage'].run().
Native execution supplies root and OMFITtree and preserves Abort semantics.
"""
from builtins import print
from OMFITlib_cgyro_storage import consolidate_storage

cg = root['CGYRO_scan']
report = consolidate_storage(cg, OMFITtree)
print('CGYRO archive compaction:', report)
print('Use OMFIT Save As to save a NEW project ZIP.')
