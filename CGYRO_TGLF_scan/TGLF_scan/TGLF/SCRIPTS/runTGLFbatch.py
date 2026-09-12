# -*-Python-*-
# Created by fascianam at 14 Sep 2018  14:36

"""
This script runs TGLF via batch submission

defaultVars parameters
----------------------
:param inputTGLF: This is a list of TGLF input files
:param results: Dictionary like object in which to put the outputs. If no results variable given put results in root['batch'].
:param runIDs: Is a list of keys used for the results. If no runIDs given use the index number
:param enforce_constraints: Whether to enforce the constraints in root['constraint_vars']
"""

defaultVars(inputTGLF=None, runIDs=None, results=None, enforce_constraints=False)

if inputTGLF is None:
    raise OMFITexception('No inputs given.')

if results is None:
    results = root['batch'] = OMFITcollection()

if runIDs is None:
    runIDs = range(len(inputTGLF))

batch_lines = []

inputs = []

constraints = root.get('constraint_vars', {})

for i, input in enumerate(inputTGLF):
    if constraints and enforce_constraints:
        for k in input:
            exec("%s = input['%s']" % (k, k))
        for k, v in constraints.items():
            input[k] = eval(v)
    inputs.append((input, 'input_%d.tglf' % i))
    batch_lines.append(f'mkdir {i}; mv input_{i}.tglf {i}/input.tglf; tglf -e {i}')

outputs = ['./']

server = SERVER[root['SETTINGS']['REMOTE_SETUP']['serverPicker']]['server']
if is_server(server, 'iris'):
    partition = 'short,medium,long'
elif is_server(server, 'portal'):
    partition = 'general'
elif is_server(server, 'saturn'):
    partition = 'batch'
elif is_server(server, ['engaging', 'eofe7']):
    partition = 'sched_mit_psfc,sched_mit_psfc_serial'
elif is_server(server, 'localhost'):
    partition = SERVER[root['SETTINGS']['REMOTE_SETUP']['serverPicker']].get('partition', None) or None
else:
    partition = None

OMFITx.job_array(
    root,
    inputs=inputs,
    outputs=outputs,
    batch_lines=batch_lines,
    environment='\n'.join(str(root['SETTINGS']['SETUP']['executable']).splitlines()[:-1]),
    partition=partition,
    job_time='10',
)

for i, r in enumerate(runIDs):
    ascii_progress_bar(i, 0, len(runIDs) - 1, newline=False, mess='Loading TGLF outputs')
    results[r] = OMFITtglf(root['SETTINGS']['SETUP']['workDir'] + str(i))
