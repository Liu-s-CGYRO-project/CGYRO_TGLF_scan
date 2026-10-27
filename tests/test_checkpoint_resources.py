"""Exercise changed MPI/OMP resources through real v3 staging and ZIP paths."""
import hashlib
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zipfile

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(path) for path in (REPO / 'CGYRO_TGLF_scan').rglob('LIB')]
import test_cgyro_storage  # Native-file adapters, confined to temporary fixtures.
from OMFITlib_cgyro_checkpoint import MAGIC, OFFSET, directory_checkpoint
from OMFITlib_cgyro_continue import continuation_plan, prepare_point
from OMFITlib_cgyro_launch import validate_checkpoint_runtime


class Input(dict):
    def __init__(self, filename=None, values=None):
        self.filename = str(filename or '')
        if values is None:
            values = {key.strip(): float(value) for key, value in
                      (line.split('=', 1) for line in Path(filename).read_text().splitlines())}
        super().__init__(values)

    def duplicate(self):
        return Input(values=dict(self))

    def deploy(self, filename):
        Path(filename).write_text(''.join('{}={:g}\n'.format(key, value) for key, value in self.items()))
        self.filename = str(filename)


class ResourceContinuationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.original = self.base / 'original'
        self.original.mkdir()
        values = dict(N_THETA=2, N_RADIAL=2, N_SPECIES=2, N_XI=4, N_ENERGY=8,
                      N_TOROIDAL=1, VELOCITY_ORDER=1, DELTA_T=0.1, PRINT_STEP=1, MAX_TIME=20, KY=0.1)
        Input(values=values).deploy(self.original / 'input.cgyro')
        # Genuine v3 disk structure: 64 velocity cells on 16 old ranks.
        words = [MAGIC, 3, 2, 2, 2, 4, 8, 1, 1, 1, 4, 4, 1, 16, 1, 1, 0, 1, 1, 1, 1, 2, 64, 4, MAGIC]
        header = struct.pack('<25i', *words)
        payload = b''.join(struct.pack('<dd', float(index), -float(index)) for index in range(256))
        (self.original / 'bin.cgyro.restart').write_bytes(header + bytes(OFFSET - len(header)) + payload)
        for name, value in {'out.cgyro.tag': '3\n0.3\n0.1\n',
                            'out.cgyro.time': '0.1 1\n0.2 1\n0.3 1\n',
                            'out.cgyro.freq': '1 2\n1 2\n1 2\n', 'out.cgyro.prec': 'saved precision\n',
                            'out.cgyro.timing': '1 2 3\n1 2 3\n1 2 3\n',
                            'bin.cgyro.ky_flux': 'flux bytes', 'bin.cgyro.kxky_phi': 'field bytes'}.items():
            (self.original / name).write_text(value)
        self.before = {path.name: path.read_bytes() for path in self.original.iterdir()}
        self.previous = dict(executable='cgyro -e . -n 16 -nomp 1', environment='same solver setup')
        self.current = dict(executable='cgyro -e . -n 32 -nomp 1', environment='same solver setup', mpi_ranks=32)
        self.plan = dict(source_token='old_run', additional_time=1., runtime=self.previous,
                         rows={'p000001': dict(values={'N_ENERGY': 8., 'KY': 0.1})},
                         sources={'p000001': dict(mode='checkpoint', directory=str(self.original))})

    def prepare(self, **changes):
        runtime = dict(self.current, **changes)
        return prepare_point({}, self.plan, 'p000001', str(self.base / 'stage'), Input, runtime=runtime)

    def unchanged(self):
        self.assertEqual({path.name: path.read_bytes() for path in self.original.iterdir()}, self.before)

    def test_checkpoint_reports_original_disk_layout(self):
        _, report = directory_checkpoint(str(self.original))
        self.assertTrue(report['resume_ready'])
        layout = report['candidates']['bin.cgyro.restart']
        self.assertEqual((layout['format'], layout['mpi_ranks'], layout['nt_loc'], layout['nv_loc']), (3, 16, 1, 4))

    def test_retained_checkpoint_stages_without_ancestor_or_old_temporary_directory(self):
        row = dict(self.plan['rows']['p000001'], result_path=['N_ENERGY', '8', 'lin', '0.1'])
        manifest = dict(run_token='child', runid='Jet', case_id='nr=1__rho=0.33__ion=T',
            nr=1, mass='T', rho=.33, workDir='/gone/remote', local_workDir='/gone/tmp',
            runtime=self.previous, status='cancelled', collection_status='partial',
            points=['p000001'], partial_points=['p000001'], loaded_points=[],
            point_table={'p000001': row}, continuation=dict(source_token='missing-parent',
                source_points=['p000001', 'p000002']))
        root = dict(RUN_MANIFEST=manifest, RUN_DB={'__RUNS__': {'child': dict(manifest=manifest,
            cases={'p000001': test_cgyro_storage.OMFITcgyro(str(self.original))})}})
        self.plan = continuation_plan(root, 'child', ['p000001'], 1.)
        current, metadata, names = self.prepare()
        self.assertEqual(self.plan['source_points'], ['p000001', 'p000002'])
        self.assertEqual(metadata['continuation']['checkpoint']['time'], .3)
        self.assertEqual(current['MAX_TIME'], 1.)
        for name in self.before:
            if name != 'input.cgyro':
                self.assertIn(name, names)
                self.assertEqual((self.base / 'stage' / name).read_bytes(), self.before[name])
        self.unchanged()

    def test_16_to_32_mpi_keeps_checkpoint_time_and_all_original_files(self):
        current, row, names = self.prepare()
        self.assertEqual(current['MAX_TIME'], 1.)
        self.assertEqual(current['N_ENERGY'], 8.)
        self.assertEqual(row['continuation']['checkpoint']['time'], 0.3)
        self.assertEqual(row['continuation']['checkpoint_layout']['mpi_ranks'], 16)
        for name in self.before:
            if name != 'input.cgyro':
                self.assertEqual((self.base / 'stage' / name).read_bytes(), self.before[name])
                self.assertIn(name, names)
        self.unchanged()

    def test_checkpoint_zip_also_allows_16_to_32_without_changing_original_archive(self):
        packed = self.base / 'p000001.zip'
        with zipfile.ZipFile(packed, 'w') as archive:
            for name, value in self.before.items():
                archive.writestr(name, value)
        original_digest = hashlib.sha256(packed.read_bytes()).hexdigest()
        self.plan['sources']['p000001'] = dict(mode='checkpoint_zip', zip=str(packed),
            sha256={name: hashlib.sha256(value).hexdigest() for name, value in self.before.items()})
        _, row, _ = self.prepare()
        self.assertEqual(row['continuation']['checkpoint_layout']['format'], 3)
        self.assertEqual(hashlib.sha256(packed.read_bytes()).hexdigest(), original_digest)
        self.unchanged()

    def test_openmp_can_increase_while_mpi_stays_16(self):
        self.prepare(executable='cgyro -e . -n 16 -nomp 2', mpi_ranks=16)
        self.unchanged()

    def test_unknown_format_does_not_silently_restart_or_change_old_results(self):
        path = self.original / 'bin.cgyro.restart'
        value = bytearray(path.read_bytes())
        struct.pack_into('<i', value, 4, 2)
        path.write_bytes(value)
        self.before[path.name] = path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'verified current'):
            self.prepare()
        self.unchanged()

    def test_damaged_payload_cannot_gain_resource_change_permission(self):
        path = self.original / 'bin.cgyro.restart'
        value = bytearray(path.read_bytes())
        struct.pack_into('<d', value, OFFSET, float('nan'))
        path.write_bytes(value)
        self.before[path.name] = path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'verified current'):
            self.prepare()
        self.unchanged()

    def test_environment_change_is_rejected_even_with_valid_v3_checkpoint(self):
        with self.assertRaisesRegex(ValueError, 'environment'):
            self.prepare(environment='different solver setup')
        self.unchanged()

    def test_incompatible_rank_count_does_not_modify_the_physical_grid(self):
        with self.assertRaisesRegex(ValueError, 'does not divide'):
            self.prepare(executable='cgyro -e . -n 24 -nomp 1', mpi_ranks=24)
        self.unchanged()

    def test_runtime_flag_alone_cannot_bypass_checkpoint_validation(self):
        for checkpoint in (None, {'format': 3}, {'format': 3, 'status': 'invalid'},
                           {'format': 2, 'status': 'valid'}):
            with self.subTest(checkpoint=checkpoint), self.assertRaisesRegex(ValueError, 'verified CGYRO v3'):
                validate_checkpoint_runtime(self.previous, self.current, checkpoint=checkpoint)


if __name__ == '__main__':
    unittest.main()
