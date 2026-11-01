"""Exercise the SHA-pinned old reader and OMFITcgyro.load on synthetic outputs.

Requires numpy/xarray and explicitly supplied source files. Only the upstream
reader class and native load body execute; standalone directory/input adapters
replace OMFIT's application lifecycle. This is not a running-GUI test. No user
result, scheduler, package installation or saved project is modified.
"""
import argparse
import ast
from contextlib import redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace

import numpy as np
import xarray as xr
from repair_pygacode_hiprec import LEGACY_SHA256, patched_source


def reader_class(source):
    tree = ast.parse(source)
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'cgyrodata')
    namespace = dict(os=os, np=np, time=time, BYTE='float32')
    exec(compile(ast.Module(body=[cls], type_ignores=[]), '<verified-pygacode>', 'exec'), namespace)
    return namespace['cgyrodata']


def generated_input(filename):
    values = {}
    for line in Path(filename).read_text().splitlines():
        value, key = line.split()
        values[key] = float(value)
    return values


def native_reader(source, legacy):
    tree = ast.parse(source)
    cls = next(node for node in ast.walk(tree) if isinstance(node, ast.ClassDef) and node.name == 'OMFITcgyro')
    load = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == 'load')
    load.decorator_list = []
    namespace = dict(os=os, np=np, xarray=xr, OMFITgacode=generated_input, OMFITascii=lambda path: path,
                     pygacode=SimpleNamespace(cgyro=SimpleNamespace(data=SimpleNamespace(cgyrodata=legacy))))
    exec(compile(ast.Module(body=[load], type_ignores=[]), '<native-OMFITcgyro.load>', 'exec'), namespace)
    class DirectoryReader(dict, legacy):
        def __init__(self, directory):
            dict.__init__(self)
            self.filename = self.originalFilename = str(directory)
            self.test_mode = False
    DirectoryReader.load = namespace['load']
    return DirectoryReader


def fixture(directory, dtype, nonlinear):
    directory.mkdir()
    nt, nr, nth, ns, nf = 4, 4, 4, 2, 3
    hiprec = int(dtype == 'float64')
    parameters = dict(NONLINEAR_FLAG=nonlinear, N_SPECIES=ns, N_FIELD=nf, N_TOROIDAL=1,
                      N_RADIAL=nr, N_THETA=nth, N_ENERGY=2, N_XI=2, HIPREC_FLAG=hiprec)
    (directory / 'input.cgyro.gen').write_text(''.join(str(value) + ' ' + key + '\n' for key, value in parameters.items()))
    grid = [1, ns, nf, nr, nth, 2, 2, 1, 16, 4, 1]
    grid += [-2, -1, 0, 1] + list(np.linspace(-3, 3, nth)) + [1, 2] + [-0.5, 0.5]
    grid += list(np.linspace(-12, 12, nth * nr)) + [0.5] + [0] + [0] * nr
    np.savetxt(directory / 'out.cgyro.grids', grid)
    equilibrium = np.ones(54 + 7 * ns + 2 * ns + 3)
    equilibrium[40] = 0  # gamma_e: ky_flux, not ky_cflux
    equilibrium[61] = -1  # electron charge
    equilibrium[-1] = hiprec
    np.savetxt(directory / 'out.cgyro.equilibrium', equilibrium)
    np.savetxt(directory / 'out.cgyro.time', np.column_stack((np.arange(1, nt + 1), np.zeros((nt, 2)), np.full(nt, 0.01))))
    freq = np.array([[[0.1, 0.2, 0.3, 0.4]], [[0.11, 0.12, 0.13, 0.14]]])
    np.savetxt(directory / 'out.cgyro.freq', freq.ravel(order='F'))
    flux = (np.arange(ns * 3 * nf * nt) / 7 - 4).astype(dtype).reshape((ns, 3, nf, 1, nt), order='F')
    flux.ravel(order='F').tofile(directory / 'bin.cgyro.ky_flux')
    fields = {}
    for offset, name in enumerate(('phib', 'aparb', 'bparb')):
        field = (np.linspace(-3, 5, 2 * nth * nr * nt) + offset).astype(dtype).reshape((2, nth * nr, nt), order='F')
        field.ravel(order='F').tofile(directory / ('bin.cgyro.' + name))
        fields[name] = field[0] + 1j * field[1]
    return flux, fields, freq


def verify(legacy_path, omfit_path):
    source = legacy_path.read_bytes()
    assert hashlib.sha256(source).hexdigest() == LEGACY_SHA256
    fixed = patched_source(source)
    native_source = omfit_path.read_bytes()
    old_class = native_reader(native_source, reader_class(source))
    fixed_class = native_reader(native_source, reader_class(fixed))
    checked = []
    with tempfile.TemporaryDirectory(prefix='hiprec-fixture-') as temporary:
        root = Path(temporary)
        for nonlinear in (0, 1):
            for dtype in ('float64', 'float32'):
                path = root / (str(nonlinear) + '-' + dtype)
                expected_flux, fields, freq = fixture(path, dtype, nonlinear)
                before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in path.iterdir()}
                if dtype == 'float64':
                    original = old_class(path)
                    with redirect_stdout(io.StringIO()):
                        try:
                            original.load()
                        except ValueError as error:
                            assert 'moment' in str(error) and 'length 6' in str(error) and 'length 3' in str(error), str(error)
                        else:
                            raise AssertionError('Unpatched reader did not reproduce the reported failure')
                    assert original.n_flux == 6
                result = fixed_class(path)
                with redirect_stdout(io.StringIO()):
                    result.load()
                assert result.n_flux == 3 and result.ky_flux.dtype == np.dtype(dtype)
                np.testing.assert_array_equal(result.ky_flux, expected_flux)
                np.testing.assert_allclose(result['freq']['omega'], freq[0])
                np.testing.assert_allclose(result['freq']['gamma'], freq[1])
                for channel, name in enumerate(('particle', 'energy', 'momentum')):
                    actual = result['flux_ky' if nonlinear else 'qlflux_ky'][name]
                    expected = expected_flux[:, channel] if nonlinear else expected_flux[:, channel].sum(axis=2)
                    np.testing.assert_array_equal(actual, expected)
                if not nonlinear:
                    for name, output in (('phib', 'phi'), ('aparb', 'apar'), ('bparb', 'bpar')):
                        np.testing.assert_array_equal(result['balloon']['balloon_' + output], fields[name])
                after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in path.iterdir()}
                assert before == after
                checked.append(dict(dtype=dtype, nonlinear=bool(nonlinear), moments=result.n_flux, values_match=True))
    return dict(legacy_sha256=LEGACY_SHA256, patched_sha256=hashlib.sha256(fixed).hexdigest(),
                omfit_source_sha256=hashlib.sha256(native_source).hexdigest(),
                reproduced_six_vs_three=True, cases=checked, synthetic_files_unchanged=True,
                live_omfit_test=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--legacy-reader', type=Path, required=True)
    parser.add_argument('--omfit-reader', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.legacy_reader, args.omfit_reader), indent=2))
