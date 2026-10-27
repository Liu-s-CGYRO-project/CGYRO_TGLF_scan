"""Durable, JSON-only submission identity for recovery after the GUI is lost.

The sidecar travels with the inputs, before sbatch. It contains no results and
does not authorize execution: recovery separately verifies Slurm ownership,
the receipt, script digest and input members. Never infer a lost scan from the
current GUI, whose radius, isotope and axes may already describe another run.
"""
from builtins import (ValueError, all, any, dict, enumerate, float, int, isinstance,
                      iter, len, list, set, str, tuple, zip)
from copy import deepcopy
import hashlib
import json
import math
import os
import posixpath
import re
import zipfile
from OMFITlib_cgyro_archive import full_point_coordinate

SIDECAR = '.cgyro_recovery.json'
SCHEMA = 1
MAX_MANIFEST_BYTES = 8 * 1024 * 1024
MAX_SCRIPT_BYTES = 1024 * 1024
POINT_PATTERN = r'p[0-9]{6,}'
SHA256_PATTERN = r'[a-f0-9]{64}'


def job_number(value):
    number = str(value).strip()
    if not re.fullmatch(r'[1-9][0-9]*', number):
        raise ValueError('请输入 Slurm 主作业号，例如 9817420，不含子任务后缀。')
    return number


def absolute_remote_path(value):
    path = str(value)
    if (not path.startswith('/') or path == '/' or posixpath.normpath(path) != path
            or any(char in path for char in ('\n', '\r', '\x00', '|'))):
        raise ValueError('Invalid absolute recovery path: ' + repr(path))
    return path


def write_sidecar(directory, manifest):
    """Atomic local write; an interrupted upload cannot reach gated submission."""
    frozen = deepcopy(dict(manifest))
    # Retry ancestry is already represented by attempts and point_workdirs.
    # A recursively copied live view makes repeated attempts unnecessarily big.
    frozen.pop('submission_parent', None)
    content = json.dumps(dict(schema=SCHEMA, manifest=frozen), ensure_ascii=False,
                         allow_nan=False, separators=(',', ':')).encode('utf-8')
    if len(content) > MAX_MANIFEST_BYTES:
        raise ValueError('CGYRO recovery manifest exceeds the supported size.')
    path = os.path.join(directory, SIDECAR)
    temporary = path + '.tmp'
    try:
        with open(temporary, 'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.isfile(temporary):
            os.remove(temporary)
    return path


def read_manifest(content):
    if len(content.encode('utf-8')) > MAX_MANIFEST_BYTES:
        raise ValueError('Recovery manifest is too large.')
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate recovery field: ' + key)
            result[key] = value
        return result
    value = json.loads(content, object_pairs_hook=unique_object)
    if not isinstance(value, dict):
        raise ValueError('A recovery manifest must be a JSON object.')
    if 'schema' in value:
        if value['schema'] != SCHEMA or not isinstance(value.get('manifest', None), dict):
            raise ValueError('Unsupported CGYRO recovery manifest schema.')
        value = value['manifest']
    return value


def _point_index(manifest):
    points, table = manifest.get('points', []), manifest.get('point_table', {})
    if (not isinstance(points, list) or not points or len(set(points)) != len(points)
            or any(not isinstance(point, str) or not re.fullmatch(POINT_PATTERN, point) for point in points)):
        raise ValueError('Missing or invalid frozen CGYRO point list.')
    if not isinstance(table, dict) or set(table) != set(points):
        raise ValueError('The recovery point table does not match the prepared point list.')
    active = manifest.get('active_points', points)
    if not isinstance(active, list) or not active or len(set(active)) != len(active) or not set(active) <= set(points):
        raise ValueError('Invalid active point list in recovered attempt.')
    dimensions = manifest.get('dimensions', None)
    axes = manifest.get('scan_axes', [])
    if dimensions not in (1, 2, 3) or not isinstance(axes, list) or len(axes) != dimensions:
        raise ValueError('Missing frozen scan axes; current GUI parameters cannot reconstruct this run.')
    names = [axis.get('name', '') for axis in axes]
    if len(set(names)) != len(names) or any(not re.fullmatch(r'[A-Z][A-Z0-9_]*', name) for name in names):
        raise ValueError('Invalid frozen scan axis names.')
    coordinates = set()
    for point in points:
        row = table[point]
        values, physical = row.get('values', {}), row.get('result_path', [])
        path = row.get('coordinate_path', physical)
        if (not isinstance(path, list) or len(path) != 2 * dimensions + 2 or path[-2] != 'lin'
                or path[:-2:2] != names or any(not isinstance(key, str) or '/' in key or '\\' in key for key in path)):
            raise ValueError('Invalid archived result path for ' + point)
        if (physical != path and (not isinstance(physical, list) or len(physical) != len(path) + 1
                or physical[:-1] != path or not isinstance(physical[-1], str) or not physical[-1]
                or '/' in physical[-1] or '\\' in physical[-1])):
            raise ValueError('Invalid physical result location for ' + point)
        try:
            numeric = tuple(float(values[name]) for name in names + ['KY'])
            indexed = tuple(float(value) for value in path[1:-2:2] + [path[-1]])
            # effnum is user-configurable. Recover the precision from each
            # written key, never round all old scans using today's GUI value.
            keys = path[1:-2:2] + [path[-1]]
            matches = all(re.fullmatch(r'-?[0-9]+\.[0-9]+', key) and
                          format(value, '.' + str(len(key.split('.')[1])) + 'f') == key
                          for value, key in zip(numeric, keys))
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise ValueError('Missing numeric coordinates for ' + point) from exc
        if not all(math.isfinite(value) for value in numeric + indexed) or not matches or numeric[-1] == 0:
            raise ValueError('Frozen coordinates disagree with result path for ' + point)
        identity = full_point_coordinate(manifest, row)
        if identity in coordinates:
            raise ValueError('Duplicate frozen result coordinates: ' + point)
        coordinates.add(identity)
    return points


def validate_manifest(manifest, workdir, script):
    """Validate provenance without evaluating scripts or deserializing objects."""
    workdir = absolute_remote_path(workdir)
    token = str(manifest.get('run_token', ''))
    if not re.fullmatch(r'[a-f0-9]{32}', token) or manifest.get('workDir', '') != workdir:
        raise ValueError('The frozen run identity does not match the Slurm working directory.')
    base = absolute_remote_path(manifest.get('source_workDir', workdir))
    if posixpath.basename(base) != token or not (workdir == base or workdir.startswith(base + '/retry_')):
        raise ValueError('Recovery directory is not part of the frozen run.')
    if manifest.get('scheduler', '') != 'slurm':
        raise ValueError('Job-number recovery currently supports Slurm CGYRO scans.')
    for field in ('runid', 'case_id', 'case_tag', 'mass'):
        value = manifest.get(field, '')
        if not isinstance(value, str) or not value or value.startswith('__') or '/' in value or '\\' in value:
            raise ValueError('Missing or invalid original ' + field)
    if 'nr' not in manifest or 'rho' not in manifest:
        raise ValueError('The original radius identity is missing.')
    points = _point_index(manifest)
    if len(script.encode('utf-8')) > MAX_SCRIPT_BYTES:
        raise ValueError('Submission script is too large.')
    expected = manifest.get('retry_script_sha256', manifest.get('submit_script_sha256', ''))
    if not re.fullmatch(SHA256_PATTERN, str(expected)) or hashlib.sha256(script.encode('utf-8')).hexdigest() != expected:
        raise ValueError('The submission script changed; the original scan cannot be verified.')
    rows = re.findall(r'^dir_list=\(([^\n]*)\)\s*$', script, re.MULTILINE)
    if len(rows) != 1 or rows[0].split() != points:
        raise ValueError('Submission task order disagrees with the frozen point list.')
    for point, directory in manifest.get('point_workdirs', {}).items():
        if point not in points or not (absolute_remote_path(directory) == base or directory.startswith(base + '/retry_')):
            raise ValueError('A point refers outside its original run directory.')
    hashes = manifest.get('input_sha256', {})
    if set(hashes) != set(points):
        raise ValueError('Original input checksums are incomplete.')
    for point, members in hashes.items():
        if not isinstance(members, dict) or 'input.cgyro' not in members:
            raise ValueError('Missing original input.cgyro checksum: ' + point)
        for name, digest in members.items():
            if (not name or name in ('.', '..') or '/' in name or '\\' in name
                    or not re.fullmatch(SHA256_PATTERN, str(digest))):
                raise ValueError('Invalid frozen input member: ' + point)
    return deepcopy(manifest)


def verify_input_zip(path, expected, row=None):
    """Stream hashes; checkpoint ZIPs can be large and must never be extracted."""
    with zipfile.ZipFile(path) as archive:
        if len(archive.namelist()) != len(expected) or set(archive.namelist()) != set(expected):
            raise ValueError('Recovered input member list changed: ' + path)
        for name, digest in expected.items():
            hashed = hashlib.sha256()
            with archive.open(name) as member:
                for block in iter(lambda: member.read(1024 * 1024), b''):
                    hashed.update(block)
            if hashed.hexdigest() != digest:
                raise ValueError('Recovered input checksum mismatch: ' + name)
        if row is not None:
            _verify_coordinates(archive, row)


def _verify_coordinates(archive, row):
    """Check scalar coordinates against input text, without running a parser."""
    if archive.getinfo('input.cgyro').file_size > MAX_SCRIPT_BYTES:
        raise ValueError('Recovered input.cgyro is too large.')
    content = archive.read('input.cgyro').decode('utf-8')
    assignments = dict(re.findall(r'^\s*([A-Za-z][A-Za-z0-9_]*)\s*=\s*([^#!\n]*)', content, re.MULTILINE))
    for name, value in row['values'].items():
        expected = row.get('effective_time', {}).get(name, value)
        try:
            actual = float(assignments[name].strip().replace('D', 'E').replace('d', 'e'))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError('Recovered input has no numeric coordinate: ' + name) from exc
        if not math.isclose(actual, float(expected), rel_tol=1e-9, abs_tol=1e-12):
            raise ValueError('Recovered input disagrees with frozen coordinate: ' + name)
