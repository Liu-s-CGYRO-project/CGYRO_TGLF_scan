"""Explicit Command Box/GUI task: compact the current archive, then Save As.

Run OMFIT['CGYRO_TGLF_scan']['SCRIPTS']['compact_cgyro_storage'].run().
Native execution supplies root and OMFITtree and preserves Abort semantics.
"""
from builtins import len, print, sum
from OMFITlib_cgyro_storage import consolidate_storage

cg = root['CGYRO_scan']
report = consolidate_storage(cg, OMFITtree)
print('CGYRO archive compaction: retired {} runs and {} points from mixed snapshots.'.format(
    len(report.get('retired_runs', [])),
    sum(len(points) for points in report.get('retired_points', {}).values())))
print('Released {:.3f} GiB of payload for the next saved project; shared files remain single-owned.'.format(
    report['released_archive_bytes'] / 1024 ** 3))
print('Retained {} historical runs whose remaining payloads are not proven superseded.'.format(
    len(report.get('retained_history', {}))))
print('Expand the data child below each ky point to inspect its stored result.')
print('Use OMFIT Save As to save a NEW project ZIP.')
