"""Exercise unchanged OMFIT _save with synthetic indexed archive branches.

The supplied checkout provides SortedDict and the complete _save method body.
The minimal host substitutes unrelated optional object types and the outer
session. No user project, reader arrays, scheduler or real result is opened.
"""
import argparse
import ast
import builtins
from datetime import datetime
import errno
import hashlib
import json
import os
from pathlib import Path
import pickle
import re
import shutil
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
import warnings
import zipfile

import numpy as np
from validate_project_mapping import load_native_mapping

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / 'tests'), str(REPO / 'CGYRO_TGLF_scan/LIB'), str(REPO / 'OMFITtemplates/LIB')]
import test_cgyro_storage  # Explicit opaque-reader adapters; no scientific arrays.
import OMFITlib_cgyro_archive as archive_api
from OMFITlib_template_archive import parse_tree


def verify(source):
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', SyntaxWarning)  # Unchanged upstream source.
        factory, registry, mapping_evidence = load_native_mapping(source / 'omfit_classes/sortedDict.py')
    class OMFITtree(factory):
        filename = None
        modifyOriginal = readOnly = False
    class Dummy:
        pass
    raw = (source / 'omfit_classes/omfit_base.py').read_text(encoding='utf-8')
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', SyntaxWarning)  # Unchanged upstream source.
        tree = ast.parse(raw)
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'OMFITtree')
    method = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == '_save')
    assert not method.decorator_list
    with patch.dict(sys.modules, {'omfit_classes.utils_base': registry}), \
            tempfile.TemporaryDirectory(prefix='omfit-save-paths-') as directory:
        work = Path(directory).resolve()
        namespace = dict(os=os, re=re, np=np, shutil=shutil, zipfile=zipfile,
            SortedDict=factory, OMFITtree=OMFITtree, OMFITtypes=[], OMFITtypesStr=[],
            xarray=SimpleNamespace(Dataset=Dummy), pandas=SimpleNamespace(DataFrame=Dummy),
            pickle=SimpleNamespace(dumps=pickle.dumps, OMFIT_PROTOCOL=4),
            omfit_hash=lambda value, size: hashlib.sha256(value.encode()).hexdigest()[:size],
            utils_base=SimpleNamespace(now=lambda pattern: datetime.now().strftime(pattern)),
            OMFITexpressionsReturnNone=False, OMFITcwd=str(work), errno=errno, printe=print)
        for name in ('_OMFITnoSave', 'OMFITstorage', 'OMFITlist', 'OMFITcollection', 'OMFITexpression',
                     'OMFITobjectError', 'OMFITlazyLoad', '_OMFITpython', 'OMFITascii', 'OMFITmds',
                     'OMFITmdsValue', 'OMFITtoksearch', 'OMFITwebLink', 'OMFITdir',
                     'OMFITsettings', 'OMFITmainSettings', 'OMFITnamelist'):
            namespace[name] = builtins.type(name, (Dummy,), {})
        exec(compile(ast.Module(body=[method], type_ignores=[]), str(source / 'omfit_classes/omfit_base.py'), 'exec'), namespace)
        OMFITtree._save = namespace['_save']
        root, module, db, case, tasks = [OMFITtree() for _ in range(5)]
        root['CGYRO_scan'] = module
        module['RUN_DB'] = db
        db['Jet'] = OMFITtree()
        db['Jet']['nr=1__rho=0.33__ion=T'] = case
        info = dict(runid='Jet', case_id='nr=1__rho=0.33__ion=T', dimensions=1,
                    scan_axes=[dict(name='N_ENERGY', values=[16])])
        case['__INFO__'], case['__TASKS__'] = info, tasks
        node = case
        coordinate = ['N_ENERGY', '16', 'lin', '0.1']
        requested_coordinate = ['N_ENERGY', '16.0', 'lin', '0.10']
        for part in coordinate:
            node[part] = OMFITtree()
            node = node[part]
        values = {'DEFAULT_' + str(index): index / 7 for index in range(247)}
        values.update(KY=.1, N_ENERGY=16.)
        old = ', '.join('{}={:.17g}'.format(name, value) for name, value in sorted(values.items()))
        node[old] = OMFITtree({'__RESULT_REF__': 'a' * 64})
        tasks['p000001'] = dict(values={'KY': .1, 'N_ENERGY': 16.}, input_parameters=values,
            result_path=coordinate + [old], coordinate_path=requested_coordinate)
        failed = False
        try:
            root._save(str(work / 'before'), quiet=True)
        except OSError as error:
            save_error = dict(errno=error.errno, winerror=getattr(error, 'winerror', None),
                              component_bytes=len(old.encode('utf-8')))
            if not (error.errno == errno.ENAMETOOLONG or save_error['winerror'] == 206 or
                    os.name == 'nt' and save_error['winerror'] in (3, 123) and save_error['component_bytes'] > 255):
                raise AssertionError(save_error) from None
            failed = True
        assert failed, 'The former oversized native tree key did not reproduce a save failure'
        repair = archive_api.repair_archive_paths(module)
        assert repair == dict(renamed_branches=1, updated_points=1), repair
        saved = work / 'after'
        root._save(str(saved), quiet=True)
        records = parse_tree((saved / 'OMFITsave.txt').read_bytes())
        restored = OMFITtree()
        for record in records:
            parent = restored
            for key in record.keys[:-1]:
                parent = parent[key]
            key = record.keys[-1]
            if record.kind == 'OMFITtree':
                parent[key] = OMFITtree()
            else:
                assert record.kind in ('pickle', 'OMFITpickle'), record.kind
                path = (saved / record.ref).resolve()
                assert path.is_relative_to(saved)
                with path.open('rb') as stream:
                    parent[key] = pickle.load(stream)  # Only the fixture just saved above.
        reopened = restored['CGYRO_scan']['RUN_DB']['Jet']['nr=1__rho=0.33__ion=T']
        row = reopened['__TASKS__']['p000001']
        result = archive_api._at(reopened, row['result_path'])
        assert result['__RESULT_REF__'] == 'a' * 64
        assert row['input_parameters'] == values and row['coordinate_path'] == requested_coordinate
        assert row['result_path'][:-1] == coordinate
        assert len(row['result_path'][-1].encode('utf-8')) <= archive_api.MAX_ARCHIVE_KEY_BYTES
        return dict(native_save_error_reproduced=True, repaired=repair, save_and_index_reload=True,
            equivalent_numeric_spelling=True,
            former_save_error=save_error,
            full_parameters_retained=len(values), result_reference_retained=True,
            native_save_sha256=hashlib.sha256(ast.get_source_segment(raw, method).encode()).hexdigest(),
            mapping=mapping_evidence, full_omfit_session=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = verify(args.source.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report))
