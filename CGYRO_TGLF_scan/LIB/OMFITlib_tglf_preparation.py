"""Resources and job-local MPI launch for TGLF input generation only."""
from builtins import any, bool, dict, int, isinstance, str
import re
import shlex


def preparation_resources(remote):
    selected = remote.get(str(remote.get('serverPicker', '')), {})
    values = {}
    for name, default in (('nodes', 1), ('ntasks_per_node', 16)):
        raw = selected.get(name, remote.get(name, default))
        if isinstance(raw, bool) or not re.fullmatch(r'[1-9][0-9]*', str(raw).strip()):
            raise ValueError('输入生成的节点数和每节点 CPU 数必须为正整数')
        values[name] = int(raw)
    values.update(dict(cpus_per_task=1, allocated_cpus=values['nodes'] * values['ntasks_per_node'],
                       mpi_ranks=99, oversubscribe=True))
    return values


def preparation_batch(resources, scheduler, partition, wall_time):
    # Keep scheduler directives on one line and separate from the shell body.
    if not re.fullmatch(r'[A-Za-z0-9_.,/-]+', partition) or not re.fullmatch(r'[0-9:-]+', wall_time):
        raise ValueError('输入生成的队列或时限格式无效')
    if scheduler == 'slurm':
        header = ('#SBATCH --partition={partition}\n#SBATCH --time={wall_time}\n'
                  '#SBATCH --nodes={nodes}\n#SBATCH --ntasks={allocated_cpus}\n'
                  '#SBATCH --ntasks-per-node={ntasks_per_node}\n#SBATCH --cpus-per-task=1\n'
                  '#SBATCH --mem-per-cpu=2GB\n#SBATCH --export=ALL\n#SBATCH --job-name=TGLFInputs\n'
                  '#SBATCH --output=input_generation.out\n#SBATCH --error=input_generation.err\n')
        directory = ''
    elif scheduler == 'pbs':
        header = ('#PBS -q {partition}\n#PBS -l walltime={wall_time}\n'
                  '#PBS -l nodes={nodes}:ppn={ntasks_per_node}\n#PBS -l mem=2GB\n'
                  '#PBS -N TGLFInputs\n#PBS -o input_generation.out\n#PBS -e input_generation.err\n')
        directory = 'cd "$PBS_O_WORKDIR"\n'
    else:
        raise ValueError('输入生成需要 Slurm 或 PBS 作业')
    return '#!/bin/bash\n' + header.format(partition=partition, wall_time=wall_time, **resources) + (
        '\nset -e\n' + directory + 'exec /bin/bash generate_inputs.sh\n')


def preparation_command(command):
    """The prepare command remains configurable, but must only generate inputs."""
    args = shlex.split(command)
    if (not args or '-t' not in args or '-n' not in args
            or any(item in args for item in ('-e', '-i', '-g', '-r', '-reset', '-s', '-p'))):
        raise ValueError('输入生成命令应为 tgyro -t . -n {n_radii}，不能使用计算模式')
    if args.count('-t') != 1 or args.count('-n') != 1:
        raise ValueError('TGYRO 生成命令重复指定了模式或进程数')
    if args[args.index('-t') + 1:args.index('-t') + 2] != ['.'] or args[args.index('-n') + 1:args.index('-n') + 2] != ['99']:
        raise ValueError('TGYRO 输入生成需要 -t . -n 99')
    return 'python prepare_tgyro_launcher.py ' + ' '.join(shlex.quote(item) for item in args)


# Use the installed TGYRO parser and its -t mode. Redirect only the platform exec
# hook in a private copy: site launchers can force ppr/binding options which
# override MPI environment variables and prevent oversubscription.
PREPARE_LAUNCHER = r'''import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

args = sys.argv[1:]
launcher = shutil.which(os.path.expandvars(args[0]))
if not launcher:
    raise RuntimeError('TGYRO launcher not found: ' + args[0])
source = Path(launcher).read_text()
hook = r'\$(?:GACODE_ROOT|\{GACODE_ROOT\})/platform/exec/exec\.\$(?:GACODE_PLATFORM|\{GACODE_PLATFORM\})'
source, count = re.subn(r'(?P<quote>["\']?)' + hook + r'(?P=quote)', '"${OMFIT_TGLF_PREPARE_EXEC}"', source)
if not count or 'gyrotest_flag' not in source:
    raise RuntimeError('Unsupported TGYRO launcher: cannot install the prepare-only MPI hook')
private = Path('prepare_tgyro.sh').resolve()
private.write_text(source)
os.environ['OMFIT_TGLF_PREPARE_EXEC'] = str(Path('prepare_mpi.sh').resolve())
os.environ['OMFIT_TGLF_PREPARE_MPI'] = shutil.which('mpirun') or ''
if not os.environ['OMFIT_TGLF_PREPARE_MPI']:
    raise RuntimeError('mpirun not found in the selected GACODE environment')
version = subprocess.check_output([os.environ['OMFIT_TGLF_PREPARE_MPI'], '--version'], text=True)
if 'Open MPI' not in version and 'OpenRTE' not in version:
    raise RuntimeError('Prepare-only oversubscription requires Open MPI; selected launcher: ' + version)
print('TGYRO launcher: ' + launcher, flush=True)
print('MPI launcher: ' + os.environ['OMFIT_TGLF_PREPARE_MPI'], flush=True)
print(version, flush=True)
subprocess.run(['/bin/bash', str(private)] + args[1:], check=True)
# Some GACODE launchers exit 0 even when their MPI child fails.
status = Path('input_generation.mpi_exit')
if not status.is_file() or status.read_text().strip() != '0':
    raise RuntimeError('TGYRO MPI preparation did not finish successfully; see input_generation.log')
'''

PREPARE_MPI = r'''#!/bin/bash
set -e
trap 'status=$?; printf "%s\n" "$status" > input_generation.mpi_exit' EXIT
[ "$#" -ge 3 ] || { echo "Missing TGYRO launch arguments"; exit 1; }
cd "$1"
[ "$2" = 99 ] || { echo "Expected 99 preparation ranks"; exit 1; }
[ "$(cat gyrotest_flag)" = 1 ] || { echo "Only TGYRO prepare mode may oversubscribe"; exit 1; }
[ "$3" -ef "$GACODE_ROOT/tgyro/src/tgyro_main" ] || { echo "Unexpected TGYRO executable"; exit 1; }
export OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OMP_DYNAMIC=false
export OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1
echo "Input generation MPI: -np 99 --oversubscribe --map-by slot --bind-to none"
"$OMFIT_TGLF_PREPARE_MPI" --oversubscribe --map-by slot --bind-to none --mca mpi_yield_when_idle 1 -np 99 "$3"
'''
