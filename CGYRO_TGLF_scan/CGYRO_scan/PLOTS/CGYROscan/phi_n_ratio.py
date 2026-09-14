# this script is used to plot the ratio of fluctuating phi to density fluctuation
# the parameters and the value is specified in root['SETTINGS']['PLOTS']['Para'] and root['SETTINGS']['PLOTS']['Range']
import numpy as np
import sys
from OMFITlib_cgyro_read import *
with open(root['PLOTS']['CGYROscan']['assist']['getglobal.py'].filename, 'r') as _helper_source:
    exec(compile(_helper_source.read(), _helper_source.name, 'exec'), globals())
if setup['icgyro']==1:
    root['PLOTS']['CGYROscan']['assist']['collect.py'].run()
else:
    root['PLOTS']['CGYROscan']['assist']['collect_gyro.py'].run()

ratio_phi_n=zeros([nRange,num_ky])     # ratio of phi to n, applicable to BES
ratio_phi_e=zeros([nRange,num_ky])     # ratio of phi to e, potential applicable to ECEI
icgyro=setup['icgyro']
if icgyro==1:
    inputcgyro=root['INPUTS']['input.cgyro']
else:
    inputcgyro=root['INPUTS']['input.gyro']
# paraval_orig=inputcgyro[plt1d['Para']]
# para_name
if Para in Paraname_dic.keys():
    plots['Para_label']=Paraname_dic[Para]
else:
    plots['Para_label']=Para

for k in range(0,nRange):
    for p in range(num_ky):
        # datanode=root['OUTPUTScan'][Para][num2str_xj(Range[k],effnum)]['lin'][num2str_xj(kyarr[p],effnum)]
        datanode = mounttree[Para + '_' + num2str_xj(Range[k], effnum) + '~ky_' + num2str_xj(kyarr[p], effnum)]
        # try:
        datanode.get_phi_n_ratio(theta=0, i_field=0,i_species=-1,moment='n')
        ratio_phi_n_temp=datanode.phi_n_ratio
        datanode.get_phi_n_ratio(theta=0, i_field=0,i_species=-1,moment='e')
        ratio_phi_e_temp=datanode.phi_n_ratio
        # except:
        #     ratio_phi_n_temp=0
        #     ratio_phi_e_temp = 0
        ratio_phi_n[k][p]=ratio_phi_n_temp
        ratio_phi_e[k][p] = ratio_phi_e_temp
########################################
# based on the profiles we get, then all the linear information can be plotted
figure('phi_n_ratio',figsize=[16,9])
phinratio={'phi_n_ratio','phi_e_ratio'}
if idimplt==0:
    ax1=subplot(1, 1, 1)
    for k in range(0,nRange):
        plot(kyarr,ratio_phi_n[k],lab[k],linewidth=lw+1,label=num2str_xj(Range[k],effnum))
    legend(loc=0).set_draggable(True)
    xlim([0.8*min(kyarr),1.2*max(kyarr)])
    ax1.set_xscale(scale_dic[ilogx])
    ax1.set_yscale(scale_dic[ilogy])
    xticks(fontsize=fs2)
    yticks(fontsize=fs2)
    xlabel('$k_y$*$\\rho_s$',fontsize=fs1)
    title('$phi_n_ratio$', fontsize=fs1)
    # subplot(1, 2, 2)
    # for k in range(0,nRange):
    #     plot(kyarr,ratio_phi_e[k],lab[k],linewidth=lw+1,label=num2str_xj(Range[k],effnum))
    # xlim([0.8*min(kyarr),1.2*max(kyarr)])
    # xticks(fontsize=fs2)
    # yticks(fontsize=fs2)
    # xlabel('$k_y$*$\\rho_s$',fontsize=fs1)
    # title('$phi_e_ratio$', fontsize=fs1)
else:
    # subplot(1,2,1)
    for k in range(0,num_ky):
        plot(Range,ratio_phi_n.T[k],lab[k],linewidth=lw+1,label=num2str_xj(kyarr[k],effnum))
    plot(array([min(Range),max(Range)]),array([0,0]),'--r',linewidth=lw)
    legend(loc=0,fontsize=fs2).set_draggable(True)
    xlim([0.8*min(Range),1.2*max(Range)])
    xticks(fontsize=fs2)
    yticks(fontsize=fs2)
    title('$phi_n_ratio$', fontsize=fs1)
    # subplot(1,2,2)
    # for k in range(0,num_ky):
    #     plot(Range, ratio_phi_e.T[k], lab[k], linewidth=lw + 1, label=num2str_xj(kyarr[k], effnum))
    # xlim([0.8*min(Range),1.2*max(Range)])
    # xticks(fontsize=fs2)
    # yticks(fontsize=fs2)
    # title('$phi_e_ratio$',fontsize=fs1)
