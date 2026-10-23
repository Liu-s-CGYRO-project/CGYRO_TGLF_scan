"""Explicit Command Box/GUI task: compact the current archive, then Save As.

Run OMFIT['CGYRO_TGLF_scan']['SCRIPTS']['compact_cgyro_storage'].run().
Native execution supplies root and OMFITtree and preserves Abort semantics.
"""
from builtins import len, print
from OMFITlib_cgyro_storage import consolidate_storage

cg = root['CGYRO_scan']
report = consolidate_storage(cg, OMFITtree)
print('CGYRO archive compaction:', report)
print('Retired {} superseded runs; released {:.3f} GiB from the next saved project.'.format(
    len(report.get('retired_runs', [])),
    (report.get('released_result_bytes', 0) + report.get('released_input_bytes', 0)) / 1024 ** 3))
print('Expand the data child below each ky point to inspect its stored result.')
print('Use OMFIT Save As to save a NEW project ZIP.')
