"""Explicit metadata repair before saving an archive with oversized keys.

Run OMFIT['CGYRO_TGLF_scan']['SCRIPTS']['repair_cgyro_archive_paths'].run().
"""
from builtins import print
from OMFITlib_cgyro_archive import repair_archive_paths

report = repair_archive_paths(root['CGYRO_scan'])
print('CGYRO save paths repaired: {} branches, {} point indexes.'.format(
    report['renamed_branches'], report['updated_points']))
print('Result files and full parameter metadata are retained. Save the project now.')
