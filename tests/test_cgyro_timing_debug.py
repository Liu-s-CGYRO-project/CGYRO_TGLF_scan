"""Compile the actual timer routines; standard restart history must not change."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'tools'))
from remove_cgyro_timing_debug import without_debug_writer, without_debug_name

FIXTURES = Path(__file__).parent / 'fixtures'
TIMERS = (FIXTURES / 'cgyro_write_timers.f90').read_bytes().replace(b'\r\n', b'\n')
DEBUG = (FIXTURES / 'cgyro_write_timers_debug.f90').read_bytes().replace(b'\r\n', b'\n')
SOURCE = TIMERS + b'\n' + DEBUG
DECLARATION = b"  character(len=22) :: runfile_timers_debug = 'out.cgyro.timing.debug'\n"
STUBS = '''module mpi
  implicit none
  integer, parameter :: MPI_DOUBLE_PRECISION=1, MPI_MIN=2, MPI_MAX=3, MPI_SUM=4
contains
  subroutine MPI_ALLREDUCE(src,dst,n,kind,op,comm,error)
    integer :: n,kind,op,comm,error
    real :: src(n),dst(n)
    dst=src
    error=0
  end subroutine
  subroutine MPI_barrier(comm,error)
    integer :: comm,error
    error=0
  end subroutine
end module
module cgyro_globals
  implicit none
  integer :: i_proc=0,n_proc=1,io=19,CGYRO_COMM_WORLD=0,i_err=0,i_time=100
  integer :: io_control=1,i_current=1
  real :: t_current=1.0,timer_cpu(32)=0.0
  character(len=4096) :: path
''' + DECLARATION.decode() + '''end module
module timer_lib
  implicit none
contains
  subroutine timer_lib_init(tag)
    character(len=*) :: tag
  end subroutine
  real function timer_lib_time(tag)
    character(len=*) :: tag
    timer_lib_time=1.25
  end function
end module
'''
DRIVER = '''program probe
  use cgyro_globals
  implicit none
  character(len=32) :: mode
  call get_command_argument(1,path)
  call get_command_argument(2,mode)
  if (trim(mode)=='restart') io_control=3
  call write_timers(trim(path)//'out.cgyro.timing')
  io_control=2
  call write_timers(trim(path)//'out.cgyro.timing')
  print *, 'STANDARD_TIMING_OK'
end program
'''


class SourceTests(unittest.TestCase):
    def test_only_diagnostic_routine_and_calls_removed(self):
        prefix, suffix = b'! physical output unchanged\n', b'! checkpoint unchanged\n'
        result = without_debug_writer(prefix + SOURCE + suffix)
        expected = b''.join(line for line in TIMERS.splitlines(keepends=True)
                            if b'call write_timers_debug' not in line)
        self.assertEqual(result, prefix + expected + b'\n' + suffix)
        self.assertEqual(without_debug_writer(result), result)

    def test_unknown_reference_refused(self):
        with self.assertRaisesRegex(ValueError, 'no change made'):
            without_debug_writer(SOURCE + b'call write_timers_debug(other,mode)\n')

    def test_incomplete_call_sites_refused(self):
        with self.assertRaisesRegex(ValueError, 'no change made'):
            without_debug_writer(SOURCE.replace(b'call write_timers_debug', b'call other', 1))

    def test_global_declaration_removal_is_narrow(self):
        source = b'module cgyro_globals\n' + DECLARATION + b'end module\n'
        self.assertEqual(without_debug_name(source), b'module cgyro_globals\nend module\n')
        self.assertEqual(without_debug_name(without_debug_name(source)), without_debug_name(source))
        with self.assertRaisesRegex(ValueError, 'no change made'):
            without_debug_name(source.replace(b'len=22', b'len=30'))
        with self.assertRaisesRegex(ValueError, 'no change made'):
            without_debug_name(source.replace(b'out.cgyro.timing.debug', b'outXcgyroXtimingXdebug'))

    def test_crlf_preserved(self):
        result = without_debug_writer(SOURCE.replace(b'\n', b'\r\n'))
        self.assertNotIn(b'\n', result.replace(b'\r\n', b''))


class CompiledTimerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which('gfortran')
        if compiler is None:
            raise unittest.SkipTest('gfortran required to execute the standard timer routine')
        cls.workspace = tempfile.TemporaryDirectory(dir=REPO / 'validation')
        cls.addClassCleanup(cls.workspace.cleanup)
        cls.build = Path(cls.workspace.name)
        cls.executables = {}
        for name, routine in [('old', SOURCE), ('fixed', without_debug_writer(SOURCE))]:
            source = cls.build / (name + '.f90')
            stubs = without_debug_name(STUBS.encode()).decode() if name == 'fixed' else STUBS
            source.write_text(stubs + routine.decode() + '\n' + DRIVER)
            target = cls.build / (name + '.exe')
            result = subprocess.run([compiler, '-ffree-line-length-none', '-fcheck=all',
                                     '-fdefault-real-8', '-fdefault-double-8',
                                     '-o', str(target), str(source)], cwd=cls.build,
                                    capture_output=True, text=True, timeout=30)
            if result.returncode:
                raise AssertionError(result.stdout + result.stderr)
            cls.executables[name] = target

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(dir=self.build)
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name)

    def run_writer(self, version='fixed', mode='fresh'):
        return subprocess.run([str(self.executables[version]), self.path.as_posix() + '/', mode],
                              capture_output=True, text=True, timeout=10)

    def test_standard_history_is_byte_identical_without_debug_output(self):
        old = self.run_writer('old')
        self.assertEqual(old.returncode, 0, old.stderr)
        timing = (self.path / 'out.cgyro.timing').read_bytes()
        (self.path / 'out.cgyro.timing.debug').unlink()
        result = self.run_writer()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.path / 'out.cgyro.timing').read_bytes(), timing)
        self.assertFalse((self.path / 'out.cgyro.timing.debug').exists())

    def test_restart_without_debug_preserves_standard_history_prefix(self):
        self.assertEqual(self.run_writer().returncode, 0)
        original = (self.path / 'out.cgyro.timing').read_bytes()
        result = self.run_writer(mode='restart')
        self.assertEqual(result.returncode, 0, result.stderr)
        updated = (self.path / 'out.cgyro.timing').read_bytes()
        self.assertTrue(updated.startswith(original))
        self.assertGreater(len(updated), len(original))
        self.assertFalse((self.path / 'out.cgyro.timing.debug').exists())

    def test_missing_standard_history_still_fails(self):
        self.assertNotEqual(self.run_writer(mode='restart').returncode, 0)

    def test_diagnostic_path_no_longer_accessed(self):
        (self.path / 'out.cgyro.timing.debug').mkdir()
        result = self.run_writer()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('STANDARD_TIMING_OK', result.stdout)


if __name__ == '__main__':
    unittest.main()
