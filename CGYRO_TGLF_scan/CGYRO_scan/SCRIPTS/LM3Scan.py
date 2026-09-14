# x: ky : y: para
# iegensolver=1: holland method on ky,    len(wr_guess)=len(Range)
# iegensolver=2: Holland method on para,  len(wr_guess)=len(ky)
# first we need to define a function to read the fieldeigen.out
# before using this method, some parameters should be set accordingly
import numpy as np
import sys
from OMFITlib_cgyro_read import *
effnum=root['SETTINGS']['SETUP']['effnum']
import copy
saved_physics = copy.deepcopy(root['SETTINGS']['PHYSICS'])
saved_input = root['INPUTS']['input.gyro'].duplicate()
try:
    inputgyro=root['INPUTS']['input.gyro']
    inputgyro['NONLINEAR_FLAG'] = 0
    inputgyro['BOX_MULTIPLIER'] = -1
    inputgyro['LINSOLVE_METHOD'] = 3
    # root['SCRIPTS']['set_resolution.py'].run()    # this step has been done
    inputgyro['ELECTRON_METHOD']=4
    physics=root['SETTINGS']['PHYSICS']
    case_tag=root['SETTINGS']['PHYSICS']['case_tag']
    kyarr=physics['kyarr']
    nky=len(kyarr)
    phy1d=physics['1d']
    para_name=phy1d['Para']
    para_rang=phy1d['Range']
    nrang=len(para_rang)
    wr_guess=phy1d['gyroeigen']['wr_guess']
    wi_guess=phy1d['gyroeigen']['wi_guess']
    ieigensolver=phy1d['gyroeigen']['ieigensolver']
    iholland=phy1d['gyroeigen']['iholland']
    # the length of wr_guess
    if len(wr_guess) != len(wi_guess):
        raise ValueError('wr_guess and wi_guess must have equal lengths')
    if ieigensolver==1:
        if not len(wr_guess)==nrang:
            print('len(wr_guess)=len(Range) is NOT satisfied')
            raise ValueError('Invalid LM3 initial guess configuration')
    elif ieigensolver==2:
        if not len(wr_guess)==nky:
            print('len(wr_guess)=len(kyarr) is NOT satisfied')
            raise ValueError('Invalid LM3 initial guess configuration')
    else:
        print('iegensolver must be equal to 1 or 2!')
        raise ValueError('Invalid LM3 initial guess configuration')
    # find the nPara, the parameter number to scan
    nPara=2
    while 'Para'+str(nPara) in phy1d.keys() and 'Range'+str(nPara) in phy1d.keys():
        nPara=nPara+1
    if ieigensolver==1:
        # prepare for the first run
        phy1d['Para'+str(nPara)]='FIELDEIGEN_WR'
        phy1d['Para'+str(nPara+1)]='FIELDEIGEN_WI'
        phy1d['Range'+str(nPara)]=wr_guess
        phy1d['Range'+str(nPara+1)]=wi_guess
        # start iteration
        wr_temp=np.array(wr_guess, copy=True)
        wi_temp=np.array(wi_guess, copy=True)
        for ky in kyarr:
            physics['kyarr']=array([ky])
            count=0
            root['SCRIPTS']['subscan_lin_gyro.py'].run()
            root['SCRIPTS']['downsync.py'].run()
            for count, para_val in enumerate(para_rang):
                new_dir = para_name + '~' + num2str_xj(para_val, effnum) + '~ky~' + num2str_xj(ky, effnum)
                casenode=root['Cases'][case_tag][new_dir]
                try:
                    omega,err_omega=readfreq(casenode)
                # there exist an error in the omfitcgyro, which get wrong the wr and wi, so here we will need to change accoridnlgy
                    wr_temp[count]=omega[1]
                    wi_temp[count]=omega[0]
                # if the omfitgyro bug is fixed, will need to do the following
                #     wr_temp[count]=omega[0]
                #     wi_temp[count]=omega[1]
                except Exception as exc:
                    raise RuntimeError('Failed reading eigensolver point ' + new_dir) from exc
            # prepare for the next iteration
            # there exist an error in the omfitcgyro, which get wrong the wr and wi, so here we will need to change accoridnlgy
            if iholland==1:
                phy1d['Range'+str(nPara)]=wr_temp
                phy1d['Range'+str(nPara+1)]=wi_temp
        # Cha pi gu
        del phy1d['Para' + str(nPara)]
        del phy1d['Range' + str(nPara)]
        del phy1d['Para' + str(nPara + 1)]
        del phy1d['Range' + str(nPara + 1)]
    elif ieigensolver==2:
        wr_temp=np.array(wr_guess, copy=True)
        wi_temp=np.array(wi_guess, copy=True)
        for para_val in para_rang:
            phy1d['Range']=array([para_val])
            count=0
            root['SCRIPTS']['subscan_lin_gyro.py'].run()
            root['SCRIPTS']['downsync.py'].run()
            for count, ky in enumerate(kyarr):
                new_dir = para_name + '~' + num2str_xj(para_val, effnum) + '~ky~' + num2str_xj(ky, effnum)
                casenode=root['Cases'][case_tag][new_dir]
                try:
                    omega,err_omega=readfreq(casenode)
                    wr_temp[count]=omega[1]
                    wi_temp[count]=omega[0]
                except Exception as exc:
                    raise RuntimeError('Failed reading eigensolver point ' + new_dir) from exc
            # prepare for the next iteration
            if iholland==1:
                phy1d['gyroeigen']['wr_guess']=wr_temp
                phy1d['gyroeigen']['wi_guess']=wi_temp
    # cha pi gu
    physics['kyarr']=kyarr
    phy1d['Range']=para_rang
    phy1d['gyroeigen']['wr_guess']=wr_guess
    phy1d['gyroeigen']['wi_guess']=wi_guess
    # # store the data
    # for item in root['Cases'][case_tag].keys():
    #     item_temp=item.split('~')
    #     if not item_temp[0] in root['OUTPUTScan'].keys():
    #         root['OUTPUTScan'][item_temp[0]]=OMFITtree()
    #     if not item_temp[1] in root['OUTPUTScan'][item_temp[0]].keys():
    #         root['OUTPUTScan'][item_temp[0]][item_temp[1]]=OMFITtree()
    #     if not 'lin' in root['OUTPUTScan'][item_temp[0]][item_temp[1]].keys():
    #         root['OUTPUTScan'][item_temp[0]][item_temp[1]]['lin']=OMFITtree()
    #     root['OUTPUTScan'][item_temp[0]][item_temp[1]]['lin'][item_temp[3]]=OMFITtree()
    #     for files in root['Cases'][case_tag][item]:
    #         root['OUTPUTScan'][item_temp[0]][item_temp[1]]['lin'][item_temp[3]][files]=root['Cases'][case_tag][item][files]
    #
finally:
    root['SETTINGS']['PHYSICS'] = saved_physics
    root['INPUTS']['input.gyro'] = saved_input
