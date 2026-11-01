"""Backport per-result HIPREC_FLAG decoding to the verified pygacode 1.0.1 reader.

Run with the OMFIT environment's Python. The default only reports the proposed
change; --apply atomically installs it after saving the original source. This
does not upgrade pygacode, alter its Fortran extension, or open result arrays.
Existing OMFIT processes need a normal restart to use the repaired dependency.
"""
import argparse
import difflib
import hashlib
import importlib.metadata
import os
from pathlib import Path
import tempfile


LEGACY_SHA256 = 'cf8dc0fb38826620d1138bc4f8f29e8bb8e2dfcf79d17d766f02fb132856651d'
MARKER = '# OMFIT HIPREC backport: keep the legacy real/imaginary array layout.'
PRECISION_METHOD = '''   def _output_dtype(self):
      # Generated input records the precision used to WRITE this result.
      # out.cgyro.prec is an integration diagnostic, not a binary dtype tag.
      filename = os.path.join(self.dir, 'input.cgyro.gen')
      if not os.path.isfile(filename):
         return 'float32'  # Pre-HIPREC results used single precision.
      flag = None
      with open(filename) as stream:
         for line in stream:
            parts = line.split('#', 1)[0].split()
            if 'HIPREC_FLAG' not in parts:
               continue
            if len(parts) != 2 or parts[1] != 'HIPREC_FLAG' or flag is not None:
               raise ValueError('Invalid or duplicate HIPREC_FLAG in ' + filename)
            flag = float(parts[0])
            if flag not in (0, 1):
               raise ValueError('HIPREC_FLAG must be 0 or 1 in ' + filename)
      return 'float64' if flag == 1 else 'float32'

'''
REPLACEMENTS = (
    ('      self.dir = sim_directory\n',
     '      self.dir = sim_directory\n      ' + MARKER + '\n      self.BYTE = self._output_dtype()\n'),
    ("dtype=BYTE)", "dtype=self.BYTE)"),
    ('   def extract(self,f):\n', PRECISION_METHOD + '   def extract(self,f):\n'),
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def patched_source(original):
    """Only the inspected upstream reader, or our exact patch, is accepted."""
    text = original.decode('utf-8')
    if MARKER in text:
        reverted = text
        for old, new in reversed(REPLACEMENTS):
            if reverted.count(new) != 1:
                raise ValueError('Modified HIPREC backport; refusing to overwrite it')
            reverted = reverted.replace(new, old, 1)
        if digest(reverted.encode('utf-8')) != LEGACY_SHA256:
            raise ValueError('Modified reader; refusing to overwrite it')
        return original
    if digest(original) != LEGACY_SHA256:
        raise ValueError('Unrecognized pygacode reader; no change made. Inspect this version before applying a patch.')
    for old, new in REPLACEMENTS:
        if text.count(old) != 1:
            raise ValueError('Legacy reader layout changed; no change made')
        text = text.replace(old, new, 1)
    compile(text, 'pygacode/cgyro/data.py', 'exec')
    return text.encode('utf-8')


def installed_source():
    """Find the dependency without importing its native extension."""
    package = importlib.metadata.distribution('pygacode')
    candidates = [package.locate_file(path) for path in (package.files or [])
                  if path.as_posix() == 'pygacode/cgyro/data.py']
    if len(candidates) != 1:
        raise ValueError('Cannot locate one installed pygacode/cgyro/data.py; supply --source explicitly')
    return Path(candidates[0])


def repair(source, apply=False):
    source = Path(source).resolve(strict=True)
    original = source.read_bytes()
    updated = patched_source(original)
    report = dict(source=str(source), before_sha256=digest(original), after_sha256=digest(updated),
                  status='already_patched' if original == updated else 'ready')
    if original == updated:
        return report
    if not apply:
        report['diff'] = ''.join(difflib.unified_diff(original.decode().splitlines(True),
                                updated.decode().splitlines(True), fromfile=str(source), tofile=str(source)))
        return report
    backup = source.with_name(source.name + '.before-hiprec-' + LEGACY_SHA256[:12])
    if backup.exists():
        if backup.read_bytes() != original:
            raise ValueError('Existing backup differs; no change made')
    else:
        with backup.open('xb') as stream:
            stream.write(original)
            stream.flush()
            os.fsync(stream.fileno())
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=source.parent, prefix='.hiprec-', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(updated)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, source.stat().st_mode)
        if source.read_bytes() != original:
            raise ValueError('Reader changed during preparation; no change made')
        os.replace(temporary, source)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    if source.read_bytes() != updated:
        raise RuntimeError('Installed reader verification failed; original backup: ' + str(backup))
    report.update(status='patched', backup=str(backup))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, help='Explicit installed pygacode/cgyro/data.py (default: this Python environment)')
    parser.add_argument('--apply', action='store_true', help='Back up and replace the verified source; otherwise show the diff only')
    args = parser.parse_args()
    try:
        report = repair(args.source if args.source is not None else installed_source(), args.apply)
    except (OSError, ValueError, importlib.metadata.PackageNotFoundError) as error:
        parser.exit(1, str(error) + '\n')
    for key, value in report.items():
        print(key + ': ' + value)
    if report['status'] == 'patched':
        print('Save your project and restart OMFIT normally, then collect the existing job again. No solver rerun is needed.')


if __name__ == '__main__':
    main()
