"""One isolated unittest process with explicit, logged environment adapters.

The reader stand-ins are the same doubles already used by storage tests. They
must not leak between suites. Offline startup changes only fixture discovery;
explicit manager actions retain their production handlers. Native GUI callback
bodies, when requested, come from the supplied OMFIT checkout, not a copy here.
"""
import argparse
from contextlib import ExitStack
import importlib
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch


FAKE_NATIVE = {'test_cgyro', 'test_compare', 'test_native_mapping', 'test_project',
               'test_project_runtime', 'test_tglf_multi', 'test_tglf_parameters', 'test_transfer_schemes',
               'test_gui_tab_pages', 'test_gui_open_native'}
NATIVE_SOURCE = {'test_gui_refresh', 'test_gui_refresh_controls', 'test_gui_refresh_native', 'test_cgyro_callback_imports',
                 'test_cgyro_remote_environment', 'test_cgyro_archive_reference',
                 'test_cgyro_file_dedup', 'test_cgyro_browser_update', 'test_cgyro_scan_refresh', 'test_gui_tab_pages', 'test_runtime_persistence',
                 'test_workbench_navigation', 'test_refresh_boundaries', 'test_runtime_boundaries',
                 'test_transfer_refresh_native', 'test_gui_open_native'}
TK_SUITES = {'test_tk_callbacks', 'test_gui_refresh_native', 'test_gui_font_performance', 'test_plot_window', 'test_cgyro_task_manager', 'test_manager_startup',
             'test_cgyro_scan_refresh', 'test_gui_tab_pages', 'test_cgyro_read_boundaries',
             'test_workbench_navigation', 'test_refresh_boundaries', 'test_runtime_boundaries',
             'test_transfer_refresh_native', 'test_font_ui_boundaries', 'test_gui_open_native'}
BASH_PATH_SUITES = {'test_cgyro_collection', 'test_cgyro_job_recovery'}
BASH_NATIVE_SUITES = {'test_cgyro_collection', 'test_cgyro_launch'}
EXTERNAL_DEPENDENCIES = {'omfit_classes', 'numpy', 'matplotlib', 'scipy', 'tkinter', 'PIL'}
ENVIRONMENT_EXIT = 3


def check_shell(command):
    """Probe exactly the shell used by a suite, without solver/scheduler work."""
    try:
        process = subprocess.run(command + ['-c', 'exit 0'], stdin=subprocess.DEVNULL,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError('Required shell is unavailable: {} ({})'.format(' '.join(command), error)) from None
    if process.returncode:
        raise ValueError('Required shell failed: {} (exit {})'.format(' '.join(command), process.returncode))


def check_environment(path, omfit_source, adapters=False):
    manager_ui = path.parent.parent.name == 'OMFITtemplates' and path.stem == 'test_ui'
    if path.stem in NATIVE_SOURCE:
        if omfit_source is None or not all((omfit_source / name).is_file()
                                          for name in ('omfit_classes/OMFITx.py', 'utils_tk.py')):
            raise ValueError('Native callback tests require --omfit-source /path/to/omfit; no tests were run')
    if path.stem in FAKE_NATIVE and not adapters and importlib.util.find_spec('omfit_classes') is None:
        raise ValueError('This suite needs omfit_classes or the explicit --adapters fixtures; --omfit-source supplies callback source only')
    if path.stem in BASH_PATH_SUITES:
        check_shell(['bash'])
    if path.stem in BASH_NATIVE_SUITES:
        check_shell(['wsl.exe', '-d', 'Ubuntu', '--', '/bin/bash'] if os.name == 'nt' else ['/bin/bash'])
    if manager_ui or path.stem in TK_SUITES:
        if sys.platform.startswith('linux') and not os.environ.get('DISPLAY'):
            raise ValueError('Tk tests require DISPLAY (desktop or Xvfb); no tests were run')
        import tkinter as tk
        root = tk.Tk()
        try:
            root.withdraw()
        finally:
            root.destroy()
    if manager_ui and not Path(os.environ.get('OMFIT_REGRESSION_FONT_FILE', '')).is_file():
        raise ValueError('Offline manager tests require tools/run_regressions.py --font-file; no tests were run')


def environment_error(message):
    print('ENVIRONMENT ERROR: ' + str(message), flush=True)
    return ENVIRONMENT_EXIT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('suite', type=Path)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--omfit-source', type=Path)
    parser.add_argument('--adapters', action='store_true')
    args = parser.parse_args()
    path, repo = args.suite.resolve(), args.repo.resolve()
    if not path.is_file():
        parser.error('Suite file does not exist: ' + str(path))
    source = args.omfit_source.resolve() if args.omfit_source else None
    try:
        check_environment(path, source, args.adapters)
    except Exception as error:
        return environment_error(error)
    libraries = [repo / 'CGYRO_TGLF_scan/LIB', repo / 'OMFITtemplates/LIB']
    libraries.extend(sorted((repo / 'CGYRO_TGLF_scan').rglob('LIB')))
    sys.path[:0] = [str(path.parent)] + [str(folder) for folder in libraries if folder.is_dir()]
    try:
        return run(path, source, args.adapters)
    except ModuleNotFoundError as error:
        # Missing local modules remain code failures, not environment excuses.
        if (error.name or '').split('.')[0] in EXTERNAL_DEPENDENCIES:
            return environment_error('Missing dependency {}: {}; no tests were run'.format(error.name, error))
        raise


def run(path, source, adapters):
    with ExitStack() as scope:
        if adapters and path.stem in FAKE_NATIVE:
            importlib.import_module('test_cgyro_storage')
            print('ADAPTER: existing test_cgyro_storage native reader stand-ins', flush=True)
        if adapters and path.parent.parent.name == 'OMFITtemplates' and path.stem == 'test_ui':
            module = importlib.import_module('OMFITlib_template_ui')
            def local_startup(self):
                self._refresh_after = None
                if self.alive and not self.close_requested:
                    self.view_source.set('本地模板库')
                    self.refresh()
            scope.enter_context(patch.object(module.TemplateManager, '_startup', local_startup))
            print('ADAPTER: local fixture startup; automatic network discovery/check omitted; explicit actions unchanged', flush=True)
        if path.stem in NATIVE_SOURCE:
            if path.stem in ('test_gui_refresh_native', 'test_cgyro_callback_imports', 'test_cgyro_remote_environment', 'test_cgyro_archive_reference',
                             'test_cgyro_file_dedup', 'test_cgyro_scan_refresh', 'test_gui_tab_pages', 'test_runtime_persistence',
                             'test_workbench_navigation', 'test_refresh_boundaries', 'test_runtime_boundaries',
                             'test_transfer_refresh_native', 'test_gui_open_native'):
                importlib.import_module(path.stem).SOURCE = source
            else:
                importlib.import_module('test_gui_refresh').CORE = source / 'omfit_classes/OMFITx.py'
            print('NATIVE SOURCE: ' + str(source), flush=True)
        # Import explicitly so an absent external dependency is diagnosed once,
        # before unittest wraps it in an opaque _FailedTest traceback.
        module = importlib.import_module(path.stem)
        suite = unittest.defaultTestLoader.loadTestsFromModule(module)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        if not result.testsRun:
            print('RUNNER ERROR: no tests executed; this is not a passing suite', flush=True)
            return 2
        if len(result.skipped) == result.testsRun:
            reasons = '; '.join(sorted({reason for _, reason in result.skipped}))
            return environment_error('All tests skipped; suite was not validated: ' + reasons)
        return int(not result.wasSuccessful())


if __name__ == '__main__':
    raise SystemExit(main())
