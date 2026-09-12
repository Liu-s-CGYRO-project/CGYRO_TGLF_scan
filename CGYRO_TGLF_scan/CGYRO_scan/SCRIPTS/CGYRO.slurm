#!/bin/bash
#SBATCH -J 99949_8
#SBATCH -p parallel31
#SBATCH --nodes=8 ### 等价于-N 2
#SBATCH --ntasks-per-node=64 ### 每个节点运行64个进程任务
#SBATCH --cpus-per-task=1 ### 每个任务使用1个CPU核心
#SBATCH -o %j.out
#SBATCH -e %j.err
module load GCCcore/10.2.0
module load zlib/1.2.11-GCCcore-10.2.0
module load binutils/2.35-GCCcore-10.2.0
module load iccifort/2020.4.304
module load numactl/2.0.13-GCCcore-10.2.0
module load UCX/1.9.0-GCCcore-10.2.0
module load impi/2019.9.304-iccifort-2020.4.304
module load iimpi/2020b
module load imkl/2020.4.304-iimpi-2020b
module load intel/2020b
module load Szip/2.1.1-GCCcore-10.2.0
module load HDF5/1.10.7-iimpi-2020b
module load cURL/7.72.0-GCCcore-10.2.0
module load netCDF/4.7.4-iimpi-2020b
module load netCDF-Fortran/4.5.3-iimpi-2020b
export GACODE_PLATFORM=SHENMANew_INTEL
export GACODE_ROOT=~/Gacode_250909/
source $GACODE_ROOT/shared/bin/gacode_setup

export I_MPI_FABRICS=shm:tcp
export I_MPI_OFI_PROVIDER=tcp
export UCX_TLS=none

cgyro -e . -n 512 -nomp 1 -mpinuma 16
