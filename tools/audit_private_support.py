"""Compare the supplied private-support ZIP with support stored in this project.

Reads Python source without importing it. Records source hashes and symbol
coverage, so old helper versions cannot silently overwrite reviewed code.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import warnings
import zipfile

REPO = Path(__file__).resolve().parents[1]


def symbols(text):
    result = {}
    def visit(nodes, prefix=''):
        for node in nodes:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = prefix + node.name
                result[name] = ast.dump(node, include_attributes=False)
                if isinstance(node, ast.ClassDef):
                    visit(node.body, name + '.')
    visit(ast.parse(text).body)
    return result


def audit(archive):
    archive = Path(archive)
    records = []
    with zipfile.ZipFile(archive) as source, warnings.catch_warnings():
        warnings.simplefilter('ignore', (SyntaxWarning, DeprecationWarning))
        for item in source.infolist():
            if not item.filename.endswith('.py'):
                continue
            parts = item.filename.split('/')
            if len(parts) != 3 or parts[0] != 'GACODE_module' or parts[1] not in ('CGYROscan', 'CGYROalone'):
                raise ValueError('Unexpected support source: ' + item.filename)
            destination = REPO / 'CGYRO_TGLF_scan/CGYRO_scan/PLOTS' / parts[1] / 'assist' / parts[2]
            if parts[1:] == ['CGYROalone', 'collect.py']:
                destination = destination.with_name('collect_99949.py')
            if parts[2] == 'cgyro_read_xj.py':
                destination = REPO / 'CGYRO_TGLF_scan/CGYRO_scan/LIB/OMFITlib_cgyro_read.py'
            raw = source.read(item)
            old, new = symbols(raw.decode('utf-8-sig')), symbols(destination.read_text(encoding='utf-8-sig'))
            missing = sorted(set(old) - set(new))
            records.append(dict(source=item.filename, source_sha256=hashlib.sha256(raw).hexdigest(),
                                destination=destination.relative_to(REPO).as_posix(),
                                destination_sha256=hashlib.sha256(destination.read_bytes()).hexdigest(),
                                missing_symbols=missing, added_symbols=sorted(set(new) - set(old)),
                                changed_symbols=sorted(k for k in old.keys() & new.keys() if old[k] != new[k])))
    return dict(archive_name=archive.name, archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
                python_files=len(records), all_source_symbols_present=all(not r['missing_symbols'] for r in records),
                source_was_executed=False, records=records)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = audit(args.archive)
    content = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(content.encode())
    print(content)
    raise SystemExit(0 if result['all_source_symbols_present'] else 1)
