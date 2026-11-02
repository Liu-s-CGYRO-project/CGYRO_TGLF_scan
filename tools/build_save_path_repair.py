"""Extract the current metadata-only save-path repair for an open old project."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'OMFITtemplates/LIB'))
from OMFITlib_template_service import new_file

ARCHIVE_SOURCE = ROOT / 'CGYRO_TGLF_scan/LIB/OMFITlib_cgyro_archive.py'
FUNCTIONS = ('_same_coordinate_path', 'archive_variant_key', '_restore_variant', 'repair_archive_paths')
HEADER = '''"""Repair oversized CGYRO archive keys in the current OMFIT session.

Only indexed public branch names and result_path values change. Full numeric
coordinates and all result file owners remain intact. Repeated calls are safe.
Run in OMFIT Command Box; this script does not update the installed code.
"""
from builtins import BaseException, RuntimeError, TypeError, ValueError, all, dict, enumerate, float, getattr, globals, id, len, list, print, reversed, set, sorted, str, zip
import hashlib
import json

'''
FOOTER = '''


def repair(omfit):
    cg = omfit['CGYRO_TGLF_scan']['CGYRO_scan']
    api = cg['LIB']['OMFITlib_cgyro_archive'].importCode(_relLoc=dict(root=cg))
    db = cg['LIB']['OMFITlib_cgyro_db'].importCode(_relLoc=dict(root=cg))
    for name in ('case_sources', 'case_scans', 'coordinate_path', 'point_values', 'metadata_value', '_at'):
        globals()[name] = getattr(api, name)
    globals()['rollback_actions'] = db.rollback_actions
    report = repair_archive_paths(cg)
    print('CGYRO save-path repair: {} branch names; {} indexed points.'.format(
        report['renamed_branches'], report['updated_points']))
    print('Full parameters and result file owners retained. Save the project now.')
    return report


if 'OMFIT' in globals():
    _save_path_report = repair(globals()['OMFIT'])
elif __name__ == '__main__':
    raise RuntimeError('Run this file in the open OMFIT project Command Box')
'''


def build(output):
    raw = ARCHIVE_SOURCE.read_text(encoding='utf-8')
    tree = ast.parse(raw, feature_version=(3, 9))
    nodes = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    limit = next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
                 and any(isinstance(target, ast.Name) and target.id == 'MAX_ARCHIVE_KEY_BYTES'
                         for target in node.targets))
    functions = {name: ast.get_source_segment(raw, nodes[name]) for name in FUNCTIONS}
    script = HEADER + 'MAX_ARCHIVE_KEY_BYTES = ' + repr(limit) + '\n\n' + '\n\n'.join(functions.values()) + FOOTER
    ast.parse(script, feature_version=(3, 9))
    output = Path(output)
    with new_file(output) as temporary:
        temporary.write_bytes(script.encode('utf-8'))
    return dict(output=str(output), bytes=output.stat().st_size,
                sha256=hashlib.sha256(script.encode('utf-8')).hexdigest(),
                functions={name: hashlib.sha256(code.encode('utf-8')).hexdigest() for name, code in functions.items()})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.output), indent=2))
