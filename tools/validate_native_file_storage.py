"""Round-trip a tiny file-deduplicated fixture through native OMFIT save/load.

Requires installed omfit_classes/pygacode. No user project, queue or solver is
opened. The standalone host supplies optional type names and LIB.importCode;
the native importCode callback is checked separately by validate_native_execution.
All files and native reader scratch paths belong to one disposable directory.
"""
import builtins
from collections import OrderedDict
import hashlib
import json
import os
from pathlib import Path
import pickle
import shutil
import sys
import tempfile
from types import SimpleNamespace
import zipfile


def verify():
    sys.modules['omas.omas_cython'] = None
    library = Path(__file__).resolve().parents[1] / 'CGYRO_TGLF_scan/LIB'
    sys.path.insert(0, str(library))
    with tempfile.TemporaryDirectory(prefix='omfit-native-files-') as directory:
        work = Path(directory)
        previous_cwd, previous_tmp = os.getcwd(), tempfile.tempdir
        os.chdir(work)
        tempfile.tempdir = str(work)
        try:
            import omfit_classes.omfit_base as native
            from omfit_classes.omfit_gacode import OMFITcgyro
            from omfit_classes.omfit_path import OMFITpath
            from OMFITlib_cgyro_reference import make_reference, validate_reference
            from OMFITlib_cgyro_storage import directory_inventory
            import OMFITlib_cgyro_payload as payload
            native.OMFITcwd = native.OMFITtmpDir = str(work)
            native.OMFITcgyro, native.OMFITpath = OMFITcgyro, OMFITpath

            def fixture_pickle(filename):
                path = Path(filename).resolve()
                assert str(path).startswith(str(work.resolve()) + os.sep)
                with path.open('rb') as stream:
                    return pickle.load(stream)  # Only our freshly saved fixture.

            native.OMFITpickle = fixture_pickle
            for name in ('OMFITmds', 'OMFITmdsValue', 'OMFITtoksearch', '_OMFITpython', 'OMFITdir'):
                if not hasattr(native, name):
                    setattr(native, name, builtins.type(name, (), {}))
            for cls in (OMFITcgyro, OMFITpath):
                if cls not in native.OMFITtypes:
                    native.OMFITtypes.append(cls)
                if cls.__name__ not in native.OMFITtypesStr:
                    native.OMFITtypesStr.append(cls.__name__)
            tree = native.OMFITtree()
            tree._OMFITkeyName = 'OMFIT'
            tree['MainSettings'] = native.OMFIT['MainSettings']
            tree['scratch'] = native.OMFITtree()
            tree['CGYRO_scan'] = module = native.OMFITmodule()
            module['RUN_DB'] = db = native.OMFITtree()
            db['__STORE__'] = pool = native.OMFITtree()
            db['Jet'] = public = native.OMFITtree()
            native.OMFIT = tree
            common = {'input.cgyro': b'KY=0.1\n', 'bin.cgyro.restart': b'synthetic checkpoint\n' * 128}
            keys, original_directories = [], []
            for number in (1, 2):
                path = work / ('original-' + str(number))
                path.mkdir()
                for name, data in dict(common, **{'out.cgyro.info': ('fixture ' + str(number)).encode()}).items():
                    (path / name).write_bytes(data)
                owner = OMFITcgyro(str(path), test_mode=True)
                owner.OMFITproperties['test_mode'] = True
                owner.modifyOriginal = False
                key = payload.content_key(directory_inventory(str(path)))
                keys.append(key)
                original_directories.append(path)
                pool[key] = owner
                public[str(number)] = make_reference(key, native.OMFITtree)
            assert payload.pack_results(module, directory_inventory, native.OMFITtree) == 2
            assert len(pool['__FILES__']) == 4
            # Standalone OMFIT defaults to links to original files; framework
            # file owners default to modifyOriginal=False. Match the latter.
            for blob in pool['__FILES__'].values():
                blob.modifyOriginal = False
            saved = work / 'saved'
            tree._save(str(saved), only="['CGYRO_scan']", quiet=True)
            rows = [line.split(' <-:-:-> ') for line in (saved / 'OMFITsave.txt').read_text().splitlines()
                    if ' <-:-:-> ' in line]
            file_rows = [row for row in rows if row[1] == 'OMFITpath']
            expression_rows = [row for row in rows if row[1] == 'OMFITexpression' and "['data']" in row[0]]
            assert len(file_rows) == 4, file_rows
            assert len(expression_rows) == 2, expression_rows
            assert not any(row[1] == 'OMFITcgyro' for row in rows)
            checkpoint_digest = hashlib.sha256(common['bin.cgyro.restart']).hexdigest()
            copies = [path for path in saved.rglob('*') if path.is_file()
                      and hashlib.sha256(path.read_bytes()).hexdigest() == checkpoint_digest]
            assert len(copies) == 1, copies
            archive_path = work / 'fixture.zip'
            with zipfile.ZipFile(archive_path, 'w') as archive:
                for path in saved.rglob('*'):
                    if path.is_file():
                        archive.write(path, str(path.relative_to(saved)))
            reopened_directory = work / 'reopened'
            with zipfile.ZipFile(archive_path) as archive:
                assert archive.testzip() is None
                archive.extractall(reopened_directory)  # All members just generated above.
            for path in original_directories + [saved]:
                shutil.rmtree(path)
            payload.native_readers._cgyro_file_views = OrderedDict()
            reopened = native.OMFITtree(str(reopened_directory / 'OMFITsave.txt'), quiet=True)
            reopened._OMFITkeyName = 'OMFIT'
            reopened['MainSettings'] = tree['MainSettings']
            reopened['scratch'] = native.OMFITtree()
            native.OMFIT = reopened
            restored_module = reopened['CGYRO_scan']
            restored_module['LIB'] = {'OMFITlib_cgyro_payload': SimpleNamespace(importCode=lambda **kwargs: payload)}
            for number, key in enumerate(keys, 1):
                reference = restored_module['RUN_DB']['Jet'][str(number)]
                validate_reference(reference, key)
                expression = dict.__getitem__(reference, 'data')
                reader = expression._value_()
                assert isinstance(reader, OMFITcgyro)
                assert 'out.cgyro.info' in list(expression.keys())
                assert (Path(reader.filename) / 'bin.cgyro.restart').read_bytes() == common['bin.cgyro.restart']
                assert (Path(reader.filename) / 'out.cgyro.info').read_bytes() == ('fixture ' + str(number)).encode()
            report = dict(python=sys.version.split()[0], source=native.__file__, native_file_owners=len(file_rows),
                          native_expression_rows=len(expression_rows), saved_checkpoint_copies=len(copies),
                          reopened_browsable=True, original_paths_removed=True, user_project_untouched=True)
            print('NATIVE_FILE_STORAGE_PASS ' + json.dumps(report, sort_keys=True))
            return report
        finally:
            os.chdir(previous_cwd)
            tempfile.tempdir = previous_tmp


if __name__ == '__main__':
    verify()
