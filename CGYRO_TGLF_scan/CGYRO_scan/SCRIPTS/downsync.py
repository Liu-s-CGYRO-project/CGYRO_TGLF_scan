# this script is used to downsync those results after the calculation running is finished.
# we will have two kinds of loading method, determined by iloadmthd
import os


def cfg_get(node, key, default=None):
    try:
        if key in node.keys():
            return node[key]
    except Exception:
        pass
    return default


def cfg_str(node, key, default=''):
    value = cfg_get(node, key, default)
    if value is None:
        return default
    return str(value)


def path_join(dirname, filename):
    dirname = str(dirname)
    if dirname.endswith('/') or dirname.endswith('\\'):
        return dirname + filename
    if dirname.startswith('/'):
        return dirname + '/' + filename
    return os.path.join(dirname, filename)


def runtime_abs_path(path):
    path = str(path)
    if path.startswith('/') or (len(path) > 2 and path[1] == ':' and path[2] in ['/', '\\']):
        return path
    return os.path.abspath(path)


def looks_like_result_dir(path):
    if not os.path.isdir(path):
        return False
    markers = [
        'input.cgyro',
        'out.cgyro.info',
        'out.cgyro.freq',
        'out.cgyro.time',
        'run_log',
    ]
    for marker in markers:
        if os.path.exists(path_join(path, marker)):
            return True
    return False


def discover_local_result_dirs(workdir):
    workdir = runtime_abs_path(workdir)
    if not os.path.isdir(workdir):
        return []
    result_dirs = []
    for name in sorted(os.listdir(workdir)):
        if name.startswith('.') or name == '__pycache__':
            continue
        full_path = path_join(workdir, name)
        if looks_like_result_dir(full_path):
            result_dirs.append(name)
    return result_dirs


setup=root['SETTINGS']['SETUP']
# iloadmthd=setup['iloadmthd'] # 0(default): OMFITcgyro, 1: OMFITgacode
# outputs={'bin.cgyro.aparb':OMFITgacode,'bin.cgyro.phib':OMFITgacode,'bin.cgyro.bparb':OMFITgacode,\
#                   'bin.cgyro.geo':OMFITgacode,'bin.cgyro.kxky_phi':OMFITgacode,'bin.cgyro.ky_flux':OMFITgacode,\
#                   'bin.cgyro.restart':OMFITgacode,'bin.cgyro.restart.old':OMFITgacode,\
#                   'input.cgyro':OMFITgacode,'input.cgyro.gen':OMFITgacode,\
#                   'out.cgyro.freq':OMFITgacode,'out.cgyro.info':OMFITgacode,'out.cgyro.time':OMFITgacode,'out.cgyro.timing':OMFITgacode,\
#                   'out.cgyro.egrid':OMFITgacode,'out.cgyro.equilibrium':OMFITgacode,'out.cgyro.grids':OMFITgacode,\
#                   'out.cgyro.hosts':OMFITgacode,'out.cgyro.memory':OMFITgacode,'out.cgyro.mpi':OMFITgacode,\
#                   'out.cgyro.prec':OMFITgacode,'out.cgyro.version':OMFITgacode,\
#                   'out.cgyro.tag':OMFITgacode,'run_log':OMFITgacode
#                  }
icgyro=setup['icgyro']
rmtsetup=root['SETTINGS']['REMOTE_SETUP']
manifest = root.get('RUN_MANIFEST')
if not manifest:
    raise ValueError('No run manifest. Prepare a run first; importing old result directories requires an explicit manifest.')
rmtserver = manifest['server']
rmtworkdir = manifest['workDir']
rmttunnel = manifest['tunnel']
failed_cases = []
local = rmtserver == 'localhost'
caseTag = manifest['case_tag']
caseRoot = root['Cases']
parentdir = list(manifest['points'])
loaded_cases = []
for itemdir in parentdir:
    print("Loading "+itemdir)
    result_dir = path_join(rmtworkdir, itemdir)
    if local and not os.path.isdir(result_dir):
        print("Missing local result directory: "+result_dir)
        failed_cases.append(itemdir)
        continue
    try:
        if icgyro==0:
            if local:
                candidate=OMFITgyro(result_dir,extra_files=['RESTART_0','RESTART_tag_0','RESTART_1','RESTART_tag_1','restart.dat'])
            else:
                candidate=OMFITgyro([rmtworkdir+'/'+itemdir,rmtserver,rmttunnel],extra_files=['RESTART_0','RESTART_tag_0','RESTART_1','RESTART_tag_1','restart.dat'])
        else:
            if local:
                candidate=OMFITcgyro(result_dir,extra_files=['bin.cgyro.restart','bin.cgyro.restart.old'])
            else:
                candidate=OMFITcgyro([rmtworkdir+'/'+itemdir,rmtserver,rmttunnel],extra_files=['bin.cgyro.restart','bin.cgyro.restart.old'])
        # Force lazy parsing before replacing a preserved node is considered successful.
        if candidate['n_time'] < 1:
            raise ValueError('Result contains no time samples')
        caseRoot[caseTag][itemdir] = candidate
        loaded_cases.append(itemdir)
    except Exception as exc:
        print('Failed to load ' + itemdir + ': ' + str(exc))
        failed_cases.append(itemdir)
root['RUN_MANIFEST']['loaded_points'] = loaded_cases
root['RUN_MANIFEST']['failed_points'] = failed_cases
if failed_cases:
    raise RuntimeError('Result loading failed for: ' + ', '.join(failed_cases) + '; previous archived results are preserved')
root['RUN_MANIFEST']['status'] = 'loaded'
