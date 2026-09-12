import os
import tempfile
case_tag = root['SETTINGS']['PHYSICS']['case_tag']
cases = root['Cases'][case_tag]
if not cases:
    raise ValueError('No cases to convert')
converted = OMFITtree()
for name in list(cases.keys()):
    if '~ky~' not in name:
        converted[name] = cases[name]
        continue
    staging_parent = tempfile.mkdtemp(prefix='cgyro-convert-', dir=str(OMFITworkDir(root, '')))
    directory = os.path.join(staging_parent, 'case')
    cases[name].deploy(directory)
    if isinstance(cases[name], OMFITcgyro):
        node = OMFITtree()
        for filename in os.listdir(directory):
            full_path = os.path.join(directory, filename)
            if os.path.isfile(full_path):
                node[filename] = OMFITgacode(full_path) if filename.startswith('input.') else OMFITpath(full_path)
        if 'input.cgyro' not in node:
            raise ValueError('Conversion produced no input.cgyro: ' + name)
    else:
        node = OMFITcgyro(directory)
        node['n_time']
    converted[name] = node
root['Cases'][case_tag] = converted
