"""Run each unittest file in a separate process and retain reproducible logs.

No OMFIT session, scheduler or user's result ZIP is opened. Native stand-ins
are opt-in with --adapters. Real Tk suites require a usable display; the manager
suite also requires the repository's pinned CJK font through --font-file so
startup cannot wait for a network download. See MAINTAINER_GUIDE.md.
"""
import argparse
import ast
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import time


TOOLS = Path(__file__).resolve().parent
DEFAULT_REPO = TOOLS.parent


def write_json(path, value):
    path.write_bytes((json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))


def environment(repo, logs, font_file=None, font_sha256=None):
    """Supply implicit OMFIT LIB paths and an isolated, verified font cache."""
    env = dict(os.environ)
    libraries = [repo / 'CGYRO_TGLF_scan/LIB', repo / 'OMFITtemplates/LIB']
    libraries.extend(sorted((repo / 'CGYRO_TGLF_scan').rglob('LIB')))
    paths = list(dict.fromkeys(str(path) for path in libraries if path.is_dir()))
    if env.get('PYTHONPATH'):
        paths.append(env['PYTHONPATH'])
    env.update(PYTHONPATH=os.pathsep.join(paths), PYTHONDONTWRITEBYTECODE='1',
               PYTHONUTF8='1', MPLBACKEND='Agg', XDG_CACHE_HOME=str(logs / '.cache'))
    env.pop('OMFIT_REGRESSION_FONT_FILE', None)
    font_record = None
    if font_file is not None:
        constants = ast.parse((repo / 'CGYRO_TGLF_scan/LIB/OMFITlib_gui_font_data.py').read_text(encoding='utf-8'))
        identity = {node.targets[0].id: ast.literal_eval(node.value) for node in constants.body
                    if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
                    and node.targets[0].id in ('FONT_SHA256', 'FONT_FILENAME')}
        expected = font_sha256 or identity['FONT_SHA256']
        if not re.fullmatch('[a-f0-9]{64}', expected) or expected != identity['FONT_SHA256']:
            raise ValueError('--font-sha256 must match this checkout\'s pinned GUI font')
        data = font_file.read_bytes()
        actual = hashlib.sha256(data).hexdigest()
        if actual != expected:
            raise ValueError('GUI font SHA-256 mismatch: ' + str(font_file))
        target = logs / '.cache/omfit-cgyro/fonts' / (actual + Path(identity['FONT_FILENAME']).suffix)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != actual:
            target.write_bytes(data)
        env['OMFIT_REGRESSION_FONT_FILE'] = str(target)
        font_record = dict(source=str(font_file), sha256=actual, cached=str(target))
    return env, font_record


def suite_name(path):
    return ('manager_' if path.parent.parent.name == 'OMFITtemplates' else '') + path.stem


def run_suite(path, repo, logs, env, timeout, adapters, omfit_source):
    start = time.perf_counter()
    name = suite_name(path)
    command = [sys.executable, '-B', '-X', 'utf8', str(TOOLS / 'run_isolated_suite.py'),
               str(path), '--repo', str(repo)]
    if adapters:
        command.append('--adapters')
    if omfit_source is not None:
        command.extend(['--omfit-source', str(omfit_source)])
    timed_out = False
    try:
        process = subprocess.run(command, cwd=repo, env=env, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, timeout=timeout)
        output, code = process.stdout.decode('utf-8', 'replace').replace('\r\n', '\n'), process.returncode
    except subprocess.TimeoutExpired as error:
        output = (error.stdout or b'').decode('utf-8', 'replace').replace('\r\n', '\n') + '\nTIMEOUT: suite did not complete\n'
        code, timed_out = 2, True
    except OSError as error:
        output, code = 'RUNNER ERROR: ' + str(error) + '\n', 2
    counts = re.findall(r'^Ran (\d+) tests?', output, flags=re.MULTILINE)
    tests = int(counts[-1]) if counts else 0
    if not code and not tests:
        code = 2
        output += '\nRUNNER ERROR: no tests executed; this is not a passing suite\n'
    (logs / (name + '.log')).write_bytes(output.encode('utf-8'))
    totals = re.findall(r'^(?:OK|FAILED)(?: \(([^\n]*)\))?$', output, flags=re.MULTILINE)
    details = dict(re.findall(r'(failures|errors|skipped|expected failures|unexpected successes)=(\d+)',
                              totals[-1] if totals else ''))
    return dict(suite=name, exit_code=code, tests=tests,
                failures=int(details.get('failures', 0)), errors=int(details.get('errors', 0)),
                skipped=int(details.get('skipped', 0)), timed_out=timed_out,
                seconds=round(time.perf_counter() - start, 3),
                failed_tests=re.findall(r'^(?:FAIL|ERROR): (.*)$', output, flags=re.MULTILINE),
                skip_reasons=[line for line in output.splitlines() if ' ... skipped ' in line],
                command=command, log=name + '.log')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=DEFAULT_REPO, help='Checkout to test; defaults to this tools directory\'s parent')
    parser.add_argument('--log-dir', type=Path, default=Path('dist/regressions'), help='Logs/cache directory, relative to the current directory')
    parser.add_argument('--omfit-source', type=Path, help='Native OMFIT omfit/ directory containing omfit_classes/OMFITx.py and utils_tk.py')
    parser.add_argument('--font-file', type=Path, help='Local pinned NotoSansCJKsc-Regular.otf; copied only to the test log cache')
    parser.add_argument('--font-sha256', help='Optional independently verified digest; default is this checkout\'s font identity')
    parser.add_argument('--workers', type=int, default=3)
    parser.add_argument('--timeout', type=float, default=300, help='Timeout per suite in seconds')
    parser.add_argument('--adapters', action='store_true', help='Enable documented fake-native readers and offline manager startup fixtures')
    parser.add_argument('--suite', action='append', default=[], help='Repeatable file stem or qualified name, e.g. test_build_project or manager_test_ui')
    args = parser.parse_args()
    if args.workers < 1 or not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error('--workers and --timeout must be positive; --timeout must be finite')
    if args.font_sha256 and args.font_file is None:
        parser.error('--font-sha256 requires --font-file')
    repo, logs = args.repo.resolve(), args.log_dir.resolve()
    omfit_source = args.omfit_source.resolve() if args.omfit_source is not None else None
    if omfit_source is not None and not all((omfit_source / name).is_file()
                                          for name in ('omfit_classes/OMFITx.py', 'utils_tk.py')):
        parser.error('--omfit-source must point to the native omfit/ source directory')
    suites = sorted((repo / 'tests').glob('test_*.py')) + sorted((repo / 'OMFITtemplates/tests').glob('test_*.py'))
    if args.suite:
        known = {name for path in suites for name in (path.stem, suite_name(path))}
        unknown = set(args.suite) - known
        if unknown:
            parser.error('Unknown suite(s): ' + ', '.join(sorted(unknown)))
        suites = [path for path in suites if path.stem in args.suite or suite_name(path) in args.suite]
    if not suites:
        parser.error('No test files found under ' + str(repo))
    logs.mkdir(parents=True, exist_ok=True)
    try:
        env, font = environment(repo, logs, args.font_file.resolve() if args.font_file else None, args.font_sha256)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    write_json(logs / 'environment.json', dict(
        python=sys.executable, version=sys.version, platform=platform.platform(), repo=str(repo),
        display=env.get('DISPLAY'), matplotlib_backend=env['MPLBACKEND'], pythonpath=env['PYTHONPATH'].split(os.pathsep),
        suites=len(suites), fixture_adapters=args.adapters, omfit_source=str(omfit_source) if omfit_source else None,
        font=font, font_cache=env['XDG_CACHE_HOME'], workers=args.workers, timeout=args.timeout))
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as workers:
        futures = [workers.submit(run_suite, path, repo, logs, env, args.timeout, args.adapters, omfit_source) for path in suites]
        for future in as_completed(futures):
            row = future.result()
            results.append(row)
            print(json.dumps(row, ensure_ascii=True), flush=True)
    results.sort(key=lambda row: row['suite'])
    write_json(logs / 'summary.json', results)
    total = dict(suites=len(results), tests=sum(row['tests'] for row in results),
                 failed_suites=sum(row['exit_code'] != 0 for row in results),
                 failures=sum(row['failures'] for row in results), errors=sum(row['errors'] for row in results),
                 skipped=sum(row['skipped'] for row in results), timeouts=sum(row['timed_out'] for row in results))
    write_json(logs / 'totals.json', total)
    print('TOTAL ' + json.dumps(total), flush=True)
    return int(bool(total['failed_suites']))


if __name__ == '__main__':
    raise SystemExit(main())
