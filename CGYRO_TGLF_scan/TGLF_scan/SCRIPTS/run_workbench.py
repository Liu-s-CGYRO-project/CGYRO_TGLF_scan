"""Run an explicit TGLF plan; archive every input and outcome in RUN_DB."""
from builtins import all, dict, enumerate, float, int, isinstance, len, list, range, str, zip
import copy
import itertools
import math
import uuid
import numpy as np
from datetime import datetime, timezone
from OMFITlib_tglf_workbench import clone, get, parameter_value

defaultVars(plan=None, project_root=None)
if not plan or not plan.get('sources', None):
    raise ValueError('TGLF scan plan is empty')

uq_combinations = None
if plan['mode'] == 'uq':
    import chaospy as cp
    distribution = cp.J(*(cp.Normal(item['mean'], item['std']) for item in plan['uq']))
    samples = np.asarray(distribution.sample(plan['samples'], plan['sampling'])).reshape(len(plan['uq']), -1)
    uq_combinations = [dict(zip([item['name'] for item in plan['uq']], values)) for values in samples.T]

# Resolve and validate every private input before any job can be submitted.
project = project_root
if project is None:
    raise ValueError('Project root is required')
prepared = []
for source in plan['sources']:
    original = get(project, source['path'])
    if original is None:
        raise ValueError('Input no longer exists: ' + source['label'])
    # Relative scans use each selected radius's own baseline, as in the native
    # OMFIT scan GUI. Absolute lists/ranges remain identical across inputs.
    axes = source.get('axes', plan['axes'])
    combinations = uq_combinations if plan['mode'] == 'uq' else [
        dict(zip([axis['name'] for axis in axes], values))
        for values in itertools.product(*(axis['values'] for axis in axes))]
    for scan_values in combinations:
        candidate = clone(original)
        candidate.pop('rho', None)
        candidate.update(source['parameters'])
        baseline = clone(candidate)
        for name, value in scan_values.items():
            candidate[name] = parameter_value(name, value, candidate[name])
            if (plan['single_Ti'] and name.startswith(('RLTS_', 'TAUS_'))
                    and candidate.get('ZS_' + name[5:], -1) > 0):
                for species in range(1, int(candidate['NS']) + 1):
                    field = name[:5] + str(species)
                    if (field not in scan_values and candidate.get('ZS_' + str(species), -1) > 0
                            and baseline.get(field, None) == baseline[name]):
                        candidate[field] = candidate[name]
        candidate['USE_TRANSPORT_MODEL'] = True
        if int(candidate['NS']) < 1 or float(candidate['NS']) != int(candidate['NS']):
            raise ValueError('NS must be a positive integer')
        prepared.append((source, dict(scan_values), candidate))

run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '_' + uuid.uuid4().hex[:8]
record = OMFITtree()
record.update(dict(id=run_id, created=datetime.now(timezone.utc).isoformat(), status='running',
                   mode=plan['mode'], plan=copy.deepcopy(plan), points=OMFITtree(),
                   runtime=copy.deepcopy(root['TGLF']['SETTINGS']['REMOTE_SETUP'])))
for index, (source, values, candidate) in enumerate(prepared, 1):
    point = OMFITtree()
    point.update(dict(label=source['label'], source=list(source['path']), parameters=values,
                      status='prepared', input=candidate))
    record['points']['p{:06d}'.format(index)] = point
root.setdefault('RUN_DB', OMFITtree())[run_id] = record
project['SETTINGS']['WORKBENCH']['tglf']['result_run'] = run_id
outputs = OMFITtree()
record['outputs'] = outputs
submission_error = None
try:
    root['TGLF']['SCRIPTS']['runTGLFbatch'].run(
        inputTGLF=[point['input'] for point in record['points'].values()],
        runIDs=list(record['points'].keys()), results=outputs,
        parallel=plan['parallel'], enforce_constraints=False, continue_on_error=True)
except BaseException as exc:
    submission_error = exc
    record['error'] = str(exc)
finally:
    failures = []
    for key, point in record['points'].items():
        result = outputs.get(key, None)
        if result is None or (hasattr(result, 'get') and result.get('_load_error', None)):
            message = result.get('_load_error', 'No result returned') if result is not None else str(submission_error or 'No result returned')
            point.update(dict(status='failed', error=message))
            if result is not None:
                point['diagnostics'] = result
            failures.append(key)
            continue
        point['result'] = result
        try:
            data = result['gbflux']['data']
            fluxes = []
            for species in data:
                values = [float(species[name]) for name in ('Gam/Gam_GB', 'Q/Q_GB', 'Pi/Pi_GB')]
                if not all(math.isfinite(value) for value in values):
                    raise ValueError('Non-finite TGLF flux')
                fluxes.append(dict(species=str(species[0]), particle=values[0], heat=values[1], momentum=values[2]))
            if not fluxes:
                raise ValueError('No TGLF flux rows')
            point.update(dict(status='complete', fluxes=fluxes))
        except Exception as exc:
            point.update(dict(status='failed', error=str(exc)))
            failures.append(key)
    final_status = 'complete' if not failures else ('failed' if len(failures) == len(prepared) else 'partial')
    if isinstance(submission_error, KeyboardInterrupt):
        final_status = 'cancelled'
    elif submission_error is not None and not failures:
        final_status = 'failed'
    record.update(dict(status=final_status, failed=failures,
                       finished=datetime.now(timezone.utc).isoformat()))
    record.pop('outputs', None)  # Each outcome is now owned by its corresponding point.
    if submission_error is not None:
        raise submission_error
    if failures:
        raise RuntimeError('TGLF: {} / {} points failed; see TGLF results in RUN_DB ({})\n{}: {}'.format(
            len(failures), len(prepared), run_id, failures[0], record['points'][failures[0]]['error']))
    print('TGLF: {} points saved to RUN_DB / {}'.format(len(prepared), run_id))
