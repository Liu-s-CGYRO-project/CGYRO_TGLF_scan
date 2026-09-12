# this script is used to plot the status of the linear calculation
# linear converge: 0
# linear terminated at max time: 1
# integration exceed error: 2
# output nothing in out.cgyro.info: 3
# no out.cgyro.info: 4
# the parameters and the value is specified in root['SETTINGS']['PLOTS']['1d']['Para'] and root['SETTINGS']['PLOTS']['1d']['Range']
# note the stability analyis should be performed by GYRO before running this plot scrip

import numpy as np
import sys
sys.path.append('/home/users/xiangjian/mymodule/CGYRO_SCAN/PLOTS/CGYROscan/assist')
from cgyro_read_xj import *
f = open(root['PLOTS']['CGYROscan']['assist']['getglobal.py'].filename, 'r')
for line in f:
    exec(line)
f.close()
def getoutmsg(filename,icgyro):
    f=open(filename,'r')
    fread=f.readlines()
    lastline=fread[-1]
    if icgyro==1:
        if 'Linear converged' in lastline:
            outmsg=0
        elif 'Linear terminated at max time' in lastline:
            outmsg=1
        elif 'Integration error exceeded limit.' in lastline:
            outmsg=2
        else:
            outmsg=3
    else:
        if 'converged' in lastline:
            outmsg=0
        elif 'clean' in lastline:             #
            outmsg=1
        elif 'exceeded' in lastline:
            outmsg=2
        else:
            outmsg=3
    f.close()
    return outmsg

outmsg_arr=zeros([nRange,num_ky])     # dominate mode frequency
# para_name
if Para in Paraname_dic.keys():
    plots['Para_label']=Paraname_dic[Para]
else:
    plots['Para_label']=Para
# all the information about frequency and growth rate can be get
icgyro=setup['icgyro']
for k in range(0,nRange):
    for p in range(num_ky):
        datanode=root['OUTPUTScan'][Para][num2str_xj(Range[k],effnum)]['lin'][num2str_xj(kyarr[p],effnum)]
        if icgyro==1:
            try:
                filename=datanode['out.cgyro.info'].filename
                outmsg= getoutmsg(filename,icgyro)
            except:
                outmsg=4
        else:
            try:
                filename=datanode['out.gyro.run'].filename
                outmsg= getoutmsg(filename,icgyro)
            except:
                outmsg=4
        outmsg_arr[k][p]=outmsg
########################################
# based on the profiles we get, then all the linear information can be plotted
figure('outmsg',figsize=[12,10])
texts='0:converged;/n 1: terminate at t_max;/n 2: integration error;/n 3: unfinished;/n 4: no out.cgyro.info '
axp=plt.axes([0.2,0.2,0.6,0.6])
if idimplt==0:
    for k in range(0,nRange):
        plot(kyarr,outmsg_arr[k],lab[k],linewidth=lw+1,markersize=ms,label=num2str_xj(Range[k],effnum))
    xlim([0.8*min(kyarr),1.2*max(kyarr)])
    xlabel('$k_y$',fontsize=fs2,family='serif')
    text(0.8*kyarr[0],5,'\\'+texts)
else:
    for k in range(0,num_ky):
        plot(Range,outmsg_arr.T[k],lab[k],linewidth=lw+1,markersize=ms,label=num2str_xj(kyarr[k],effnum))
    axp.set_xscale(scale_dic[ilogx])
    xlim([0.8*min(Range),1.2*max(Range)])
    xlabel(Para,fontsize=fs2,family='serif')
    text(0.8*Range[0],5,'\\'+texts)
axp.set_xscale(scale_dic[ilogx])
axp.set_yscale(scale_dic[ilogy])
ylim([0,4])
legend(loc=1, fontsize=fs2).set_draggable(True)
xticks(fontsize=fs2)
yticks(linspace(0,4,5),fontsize=fs2)
