raise RuntimeError('Legacy GYRO submission is disabled: this package lacks a verified restart converter and GYRO run manifest. Use CGYRO or supply and validate a GYRO backend before enabling this path.')

import numpy as np
import sys
#sys.path.append('/home/users/xiangjian/mymodule/CGYRO_SCAN/PLOTS/CGYROscan/assist')
from cgyro_read_xj import *
print ("============== scan_gyro ===========")
caseRoot=root['Cases'] # the root of the tag, defines where to store the scanning data
physics=root['SETTINGS']['PHYSICS']
phy1d=physics['1d']
caseName=physics['case_tag'] # the name of the tag, which indicates the name of the scanning
if not caseName in caseRoot.keys():
    caseRoot[caseName]=OMFITtree()
#else:
#    for item in caseRoot[caseName].keys():     #cover the previous calculation
#        del caseRoot[caseName][item]
kyarr=physics['kyarr']
restart_mode=physics['restart_mode']
para_name=phy1d['Para']
para_rang=phy1d['Range']
setup=root['SETTINGS']['SETUP']
effnum=setup['effnum']
wkdir=setup['workDir']
inputs_node=root['INPUTS']
inputgyro=inputs_node['input.gyro']
if inputgyro['RADIAL_PROFILE_METHOD']==3: # wil need to get the kinetic profiles from input.gacode
    inputs_node_names={'input.gyro':OMFITgacode,'input.gacode':OMFITgacode}
else:
    inputs_node_names={'input.gyro':OMFITgacode}
# change the filename of root['INPUTS']['input.gyro'], which might be input.gyro_3 or out.gyro.localdump to be 'input.gyro'
#deploypath='/home/users/xiangjian/temp/'
#inputgyro.deploy(deploypath+'input.gyro')
#inputgyro=OMFITgacode(deploypath+'input.gyro')
# if inputgyro['PROFILE_MODEL']==2:
#     inputs_node_names={'input.gyro':OMFITgacode,'input.profiles':OMFITgacode,'input.profiles.geo':OMFITgacode}
inputs=[]
# OK , before doing the scan, we need to keep the original input.gyro
inputs_node['input.gyro_orig']=inputgyro.duplicate()
# Gamma_E need to be set to 0 in the linear run
inputgyro['GAMMA_E']=0
inputgyro['NONLINEAR_FLAG']=0
#inputgyro['BOX_MULTIPLIER']=-1
# if inputgyro['PROFILE_MODEL']==2:
#     inputgyro['GAMMA_E_SCALE']=0.
# for linear run, the following setting should be specified
#base_loadOutputs={'bin.gyro.aparb':OMFITgacode,'bin.gyro.phib':OMFITgacode,'bin.gyro.bparb':OMFITgacode,\
#                  'bin.gyro.geo':OMFITgacode,'bin.gyro.kxky_phi':OMFITgacode,'bin.gyro.ky_flux':OMFITgacode,'bin.gyro.restart':OMFITgacode,\
#                  'input.gyro':OMFITgacode,'input.gyro.gen':OMFITgacode,\
#                  'out.gyro.freq':OMFITgacode,'out.gyro.info':OMFITgacode,'out.gyro.time':OMFITgacode,'out.gyro.timing':OMFITgacode,\
#                  'out.gyro.egrid':OMFITgacode,'out.gyro.equilibrium':OMFITgacode,'out.gyro.grids':OMFITgacode,\
#                  'out.gyro.hosts':OMFITgacode,'out.gyro.memory':OMFITgacode,'out.gyro.mpi':OMFITgacode,\
#                  'out.gyro.prec':OMFITgacode,'out.gyro.version':OMFITgacode,\
#                  'out.gyro.tag':OMFITgacode,'run_log':OMFITgacode\
#                  }
loadOutputs={}
dir_list=[]
ncount=-1
# get the original delta_t and max_time
delta_t_orig=inputgyro['TIME_STEP']
max_time_orig=inputgyro['TIME_MAX']
# restart_mode requires the CaseRoot to be OMFITtree format instead of OMFITgyro format
if restart_mode==1:
    keys=caseRoot[caseName].keys()
    if isinstance(caseRoot[caseName][keys[0]],OMFITgyro):
        root['PLOTS']['gyroscan']['assist']['changeOMFITgyrogacode.py'].run()
for para_val in para_rang:
    ncount=ncount+1
    printi('running the calculation on '+para_name+ '='+num2str_xj(para_val,effnum))
    inputgyro[para_name]=para_val
    nPara=2
    while 'Para'+str(nPara) in phy1d.keys() and 'Range'+str(nPara) in phy1d.keys():
        inputgyro[phy1d['Para'+str(nPara)]]=phy1d['Range'+str(nPara)][ncount]
        nPara=nPara+1
    ncount2=0
    for ky in kyarr:
        new_dir=para_name+'~'+num2str_xj(para_val,effnum)+'~ky~'+num2str_xj(ky,effnum)
        dir_list.append(new_dir)
        inputgyro['L_Y']=ky
        if phy1d['gyroeigen']['ieigensolver']==2:
            inputgyro['FIELDEIGEN_WR']=phy1d['gyroeigen']['wr_guess'][ncount2]
            inputgyro['FIELDEIGEN_WI'] = phy1d['gyroeigen']['wi_guess'][ncount2]
        ncount2=ncount2+1
# choose the time scheme
        time_scheme=physics['time_scheme']
        if time_scheme[0]==1:  # determine whether to use the time scheme
            if ky>1:
                inputgyro['TIME_STEP']=time_scheme[1]/ky
                inputgyro['TIME_MAX']=time_scheme[2]/ky
            else:
                inputgyro['TIME_STEP']=delta_t_orig
                inputgyro['TIME_MAX']=max_time_orig
        ## ----------------- ##
        if not new_dir in caseRoot[caseName].keys():
            caseRoot[caseName][new_dir]=OMFITtree()
        if os.path.isfile(new_dir+r'.zip'):
            os.remove(new_dir+r'.zip')
        tmp_zip=zipfile.ZipFile(new_dir+r'.zip', mode='w') # construct a new zip file, and waiting for files to be written in
        if restart_mode == 0:
            inputs_node_names_key=inputs_node_names.keys()
            inputs_node['input.gyro'].save()
            for item in inputs_node_names_key:
                caseRoot[caseName][new_dir][item]=copy.deepcopy(inputs_node[item])
        else:
            if 'zip' in caseRoot[caseName][new_dir].keys():
#                print(new_dir)
                del caseRoot[caseName][new_dir]['zip']
#            inputs_node_names_key=inputs_node_names.keys()+base_loadOutputs.keys()
            inputs_node_names_key=caseRoot[caseName][new_dir].keys()
            # we need to consider the condition that we may add new paramters regime to scan or there is no data in previous scan
            for item in inputs_node_names.keys():
                if not item in inputs_node_names_key:
                    inputs_node_names_key=append(inputs_node_names_key,item)
#                    inputs_node[item].save()
#                    caseRoot[caseName][new_dir][item]=copy.deepcopy(inputs_node[item])
#        caseRoot[caseName][new_dir]['input.gyro']=inputgyro.duplicate()  # update the input.gyro in CaseRoot by root['INPUTS']['input.gyro']
        for item in caseRoot[caseName][new_dir].keys():
#            print(item)
            tmp_zip.write(caseRoot[caseName][new_dir][item].filename, caseRoot[caseName][new_dir][item].filename.split(os.sep)[-1]) # os.sep is / for linux and \ for windows
        tmp_zip.close()
        caseRoot[caseName][new_dir]['zip']=OMFITpath(tmp_zip.filename) # the inputs are compressed as an zip file and loaded in the output directory
        inputs.append(caseRoot[caseName][new_dir]['zip'])              # then the zipfile are import as input
        # set OUTPUTS( a lot of dir ) for loadOutputs, all the parameters ranges are covered
#        for item in base_loadOutputs:
#            loadOutputs[new_dir+os.sep+item]=base_loadOutputs[item]
outputs=loadOutputs.keys()
# executable='mv input.gyro* input.gyro;\n '+setup['executable']
executable=setup['executable']

#set job scipts
pbs_file=setup['workDir']+os.sep+'scan.pbs'
username=root['SETTINGS']['REMOTE_SETUP']['server'].split('@')[0]
ps_name='gyro'
rmt_setup=root['SETTINGS']['REMOTE_SETUP']
## the bash_head below is used for runing on SHNEMA
if rmt_setup['serverPicker']=='shenma' or rmt_setup['serverPicker'][0:5]=='login':
    bash_head= \
    r'#!/bin/bash '+'\n'+ \
    r'#PBS -N '+ps_name +'\n'+ \
    r'#PBS -l nodes='+str(setup['num_nodes'])+':ppn='+str(setup['num_cores']) +'\n'+ \
    r'#PBS -j oe' +'\n'+ \
    r'#PBS -l walltime='+str(setup['wall_time']) +'\n'+ \
    r'#PBS -q '+setup['pbs_queue'] +'\n'+ \
    r'cd ${PBS_O_WORKDIR}' +'\n'+ \
    r'pwd'  +'\n'+ \
    r'NP=`cat ${PBS_NODEFILE}|wc -l`' +'\n'+ \
    '\n'+ \
    r'JOBID_FILE="JOBID_${PBS_JOBID}"' +'\n'+ \
    r'touch ${JOBID_FILE}' +'\n'
else:
    num_nodes=setup['num_nodes']
    num_cores=setup['num_cores']
    bash_head= \
    r'#!/bin/bash '+'\n' + \
    r'#SBATCH -p '+setup['pbs_queue'] +'\n' +\
    r'#SBATCH -J '+ps_name +'\n' +\
    r'#SBATCH -t '+str(setup['wall_time']) +'\n' +\
    r'#SBATCH -o %j.out'+'\n' +\
    r'#SBATCH -e %j.err'+'\n' +\
    r'#SBATCH --workdir=./'+'\n' +\
    r'#SBATCH --ntasks '+str(num_nodes*num_cores) +'\n'
    if setup['server']=='cori':
        bash_head=bash_head + r'#SBATCH -C knl,quad,cache' +'\n'
###########
bash_content= \
'dir_list=('+' '.join(dir_list)+')' +'\n'+ \
r'for i in ${dir_list[@]}; ' +'\n'+  \
'do '  +'\n'+  \
r'  while [[ $( ps -u '+username+r' |grep '+ps_name+r' | wc -l ) -gt '+str(setup['num_cores']-1)+' ]]; do ' +'\n' + \
r'    sleep 2s' +'\n' +\
r'  done ' +'\n'+ \
r'  if [ -d ${i} ]; then  ' +'\n'+\
r'    echo "${i} exist. Do not unzip this case"   ' +'\n'+\
r'  cd $i' +'\n'+\
r'  else'   +'\n'+\
r'    unzip ${i}.zip -d $i'+'\n'+\
r'    cd $i' +'\n'+\
r'    mv input.gyro* input.gyro;'+'\n'+\
r'  fi'+'\n'+\
executable+r' > run_log & ' +'\n'+ \
r"  cd .." +'\n'+ \
r'done' +'\n'

bash_tail= \
r'while [[ $( ps -u '+username+r' |grep '+ps_name+r' | wc -l ) -gt 0 ]]; do ' +'\n' + \
r'  sleep 5s' +'\n'+ \
r'done ' +'\n'+ \
r'rm ${JOBID_FILE}' +'\n'



##############################################
if not os.path.exists(str(setup['workDir'])):
    os.makedirs(str(setup['workDir']))
##############################################
with open(pbs_file,'w') as f1:
    f1.write(bash_head+'\n'+bash_content+'\n'+bash_tail)
caseRoot[caseName][pbs_file.split(os.sep)[-1]]=OMFITascii(pbs_file)

inputs.append(caseRoot[caseName][pbs_file.split(os.sep)[-1]])
if setup['irun']==1:
    # sub jobs
    # Submit through scheduler directly and let OMFIT wait for job completion.
    # We first capture submission output, parse jobID, then follow jobID-specific logs.
    if rmt_setup['serverPicker']=='shenma' or rmt_setup['serverPicker'][0:5]=='login':
        submit_cmd='qsub scan.pbs'
        submit_rule=r'([0-9]{3,}(?:\.[A-Za-z0-9._-]+)?)'
        is_slurm=False
    else:
        submit_cmd='sbatch scan.pbs'
        submit_rule=r'(?i)submitted\s+batch\s+job\s+([0-9]+)'
        is_slurm=True
    rmtserver=root['SETTINGS']['REMOTE_SETUP']['server']
    rmttunnel=root['SETTINGS']['REMOTE_SETUP']['tunnel']
    workdir=root['SETTINGS']['SETUP']['workDir']
    rmtworkdir=root['SETTINGS']['REMOTE_SETUP']['workDir']
    submit_out=[]
    submit_err=[]
    ret_code=OMFITx.executable(root, inputs=inputs, outputs=[],  \
                               server=rmtserver, \
                               tunnel=rmttunnel, \
                               workdir=workdir,\
                               remotedir=rmtworkdir,\
                               executable=submit_cmd,clean=True,std_out=submit_out,std_err=submit_err)
    job=OMFITx.manage_job(root, submit_out, server=rmtserver, tunnel=rmttunnel, remotedir=rmtworkdir, qsub_findID=submit_rule)
    if is_slurm:
        wait_cmd='hb=0; while squeue -h -j '+job.jobID+' | grep -q .; do sleep 30; hb=$((hb+30)); if [ \"$hb\" -ge 600 ]; then echo \"[heartbeat] job '+job.jobID+' still in queue/running at $(date)\"; hb=0; fi; done; echo \"[heartbeat] job '+job.jobID+' finished at $(date)\"'
    else:
        wait_cmd='hb=0; while qstat '+job.jobID+' >/dev/null 2>&1; do sleep 30; hb=$((hb+30)); if [ \"$hb\" -ge 600 ]; then echo \"[heartbeat] job '+job.jobID+' still in queue/running at $(date)\"; hb=0; fi; done; echo \"[heartbeat] job '+job.jobID+' finished at $(date)\"'
    OMFITx.remote_execute(
        rmtserver,
        wait_cmd,
        rmtworkdir,
        rmttunnel,
        quiet=False,
        ignoreReturnCode=True,
        use_bang_command=False
    )
