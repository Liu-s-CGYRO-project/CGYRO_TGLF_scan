"""Offline, code-only update followed by CGYRO archive maintenance.

Build with build_maintenance_commandbox.py; run the generated file inside the
OMFIT Command Box in an isolated namespace. The bundled code supplies its own
matching updater, including the manager's new result-reference reader. No
network, scheduler, solver, original ZIP overwrite or remote deletion occurs.
"""
from builtins import (RuntimeError, ValueError, any, dict, getattr, globals,
                      isinstance, len, print, set, str)
import base64
import hashlib
import json
from pathlib import Path
import tempfile
import zipfile

PACKAGE = None  # Filled by build_maintenance_commandbox.py.
PAYLOAD = None  # Filled by build_maintenance_commandbox.py.
RUN_MAINTENANCE = True  # Filled by build_maintenance_commandbox.py.


def verified_bytes():
    """Verify before loading any bundled Python into the native tree."""
    if PACKAGE is None or PAYLOAD is None:
        raise RuntimeError('Use the generated standalone maintenance script')
    data = base64.b85decode(PAYLOAD)
    if len(data) != PACKAGE['bytes'] or hashlib.sha256(data).hexdigest() != PACKAGE['sha256']:
        raise ValueError('Maintenance package integrity check failed; project unchanged')
    return data


def install(omfit, code, directory):
    from omfit_classes.omfit_base import OMFITtree
    from omfit_classes import OMFITx

    incoming = OMFITtree(str(code), quiet=True, developerMode=False)
    manager = incoming['OMFITtemplates']
    context = dict(root=manager)
    service = manager['LIB']['OMFITlib_template_service'].importCode(_relLoc=context)
    live = manager['LIB']['OMFITlib_template_live'].importCode(_relLoc=context)
    session_api = manager['LIB']['OMFITlib_template_session'].importCode(_relLoc=context)
    # This publishes into a temporary LOCAL template library, never GitHub.
    template = service.publish(str(code), str(directory / 'library'), dict(
        id='cgyro-tglf', name='CGYRO / TGLF', author='tdxy-liu',
        version=PACKAGE['version'], description='Offline archive maintenance'),
        ['CGYRO_TGLF_scan', 'OMFITtemplates'], include_examples=False)
    prepared = live.Prepared(str(template), data_policy='keep', settings_policy='keep')
    session = session_api.OMFITSession(omfit, tree_factory=OMFITtree, gui_api=OMFITx)
    plan = session.preview_live(prepared)
    # Retain extra local scripts; update BOTH modules so future migrations know
    # the new data expression. Calculation data/settings use keep policies.
    plan.operations = [op for op in plan.operations if op['data'] or op['new'] is not session_api.MISSING]
    print('Updating project ' + PACKAGE['version'] + ' and its matching manager ...')
    session.apply_live(plan)
    # Undoing only code after data-format migration would restore incompatible
    # readers. The existing saved project remains the recovery boundary.
    state = getattr(omfit, '_template_live_state', {})
    if state.get('undo', None) is plan:
        state['undo'] = None


def maintain(omfit):
    from omfit_classes.omfit_base import OMFITtree

    if not isinstance(omfit, dict) or not any(name in omfit for name in ('CGYRO_TGLF_scan', 'CGYRO_scan')):
        raise ValueError('Open the CGYRO project and run this script in its Command Box')
    data = verified_bytes()
    with tempfile.TemporaryDirectory(prefix='omfit-maintenance-') as temporary:
        directory = Path(temporary)
        code = directory / 'code.zip'
        code.write_bytes(data)
        # Hash binds this to the reviewed code-only build; CRC catches damaged
        # transport before any live tree operation. There is no pickle loading
        # of the user's attached ZIP in this installer.
        with zipfile.ZipFile(code) as archive:
            if archive.testzip() is not None:
                raise ValueError('Maintenance package CRC failed; project unchanged')
        install(omfit, code, directory)
    if not RUN_MAINTENANCE:
        print('Code update completed. Reopen the CGYRO workbench, then use Results / Recover by job ID.')
        print('Existing inputs, results and settings were kept. Save the project to retain this update.')
        return dict(installed=PACKAGE['version'], maintenance=False)
    node = omfit['CGYRO_TGLF_scan']['CGYRO_scan']
    api = node['LIB']['OMFITlib_cgyro_storage'].importCode(_relLoc=dict(root=node))
    print('Checking archive references, replacement coverage and checkpoints ...')
    report = api.consolidate_storage(node, OMFITtree)
    print('Maintenance completed: ' + json.dumps(report, sort_keys=True))
    print('Expand RUN_DB / run / radius / scan / ... / ky / data to inspect result details.')
    print('Use Save As for a NEW project ZIP, then close and reopen the settings windows.')
    return report


if 'OMFIT' in globals():
    _maintenance_report = maintain(globals()['OMFIT'])
elif __name__ == '__main__':
    raise RuntimeError('Execute this generated script in the OMFIT Command Box')
