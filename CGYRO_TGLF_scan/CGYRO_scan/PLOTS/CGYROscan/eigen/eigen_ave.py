# calculate the wd for a given case
import numpy as np
import sys
from OMFITlib_cgyro_read import *
with open(root['PLOTS']['CGYROscan']['assist']['getglobal.py'].filename, 'r') as _helper_source:
    exec(compile(_helper_source.read(), _helper_source.name, 'exec'), globals())

if setup['icgyro']==1:
    root['PLOTS']['CGYROscan']['assist']['collect.py'].run()
else:
    root['PLOTS']['CGYROscan']['assist']['collect_gyro.py'].run()
nRange_eigen=len(para_eigen)
num_ky_eigen=len(ky_eigen)
q_loc_ave=zeros([nRange_eigen,num_ky_eigen])     # eigenfunction averaged q
s_loc_ave=zeros([nRange_eigen,num_ky_eigen])
wd1_ave=zeros([nRange_eigen,num_ky_eigen])
k_par_ave=zeros([nRange_eigen,num_ky_eigen])
k_perp_ave=zeros([nRange_eigen,num_ky_eigen])
epar_ave=zeros([nRange_eigen,num_ky_eigen])
apar_ave=zeros([nRange_eigen,num_ky_eigen])
theta_width=zeros([nRange_eigen,num_ky_eigen])
epar_esratio_ave=zeros([nRange_eigen,num_ky_eigen])
kparvtioveromega_ave=zeros([nRange_eigen,num_ky_eigen])

# para_name
if Para in Paraname_dic.keys():
    plots['Para_label']=Paraname_dic[Para]
else:
    plots['Para_label']=Para
#
for k in range(0,nRange_eigen):
    for p in range(num_ky_eigen):
#        datanode=root['OUTPUTScan'][Para][num2str_xj(para_eigen[k],effnum)]['lin'][num2str_xj(ky_eigen[p],effnum)]
        datanode=mounttree[Para+'_'+num2str_xj(para_eigen[k],effnum)+'~ky_'+num2str_xj(ky_eigen[p],effnum)]
#        if setup['icgyro']==1:
#            datanode=OMFITcgyro_eigen(datanode.filename)
#        else:
#            datanode = OMFITgyro_eigen(datanode.filename)
        datanode.eigen_ave()
        q_loc_ave[k][p]=datanode.q_loc_ave
        s_loc_ave[k][p] = datanode.s_loc_ave
        wd1_ave[k][p] = datanode.wd1_ave
        k_par_ave[k][p] = datanode.k_par_ave
        k_perp_ave[k][p] = datanode.k_perp_ave
        epar_ave[k][p] = datanode.epar_ave
        apar_ave[k][p] = datanode.apar_ave
#        print('theta_width=',datanode.theta_width)
        theta_width[k][p] = datanode.theta_width
        epar_esratio_ave[k][p] = datanode.epar_esratio_ave
        kparvtioveromega_ave[k][p] = datanode.kparvtioveromega_ave

########################################
# based on the profiles we get, then all the linear information can be plotted
figure('Eigenfunction averged property',figsize=[16,9])
# avearr=['q_loc_ave','s_loc_ave','epar_ave','epar_esratio_ave','wd1_ave','k_par_ave','k_perp_ave']
# unitarr=['','','','','(cs/a)','(a^{-1})','*rhos']
avearr=['q_loc_ave','s_loc_ave','epar_ave','apar_ave','k_par_ave','k_perp_ave','wd1_ave','theta_width','epar_esratio_ave','kparvtioveromega_ave']
unitarr=['','','','(tearing)','(a^{-1})','*rhos','(cs/a)','(pi)','','']
if idimplt==0:
    for p in arange(1,11):
        axp=subplot(2,5,p)
        for k in range(0,nRange_eigen):
            cmd='plot(ky_eigen,'+avearr[p-1]+'[k],lab[k],linewidth=lw+1,label=num2str_xj(para_eigen[k],effnum))'
            exec(cmd)
        xlim([0.8 * min(ky_eigen), 1.2 * max(ky_eigen)])
        legend(loc=0,fontsize=fs2)
        xticks(fontsize=fs2)
        yticks(fontsize=fs2)
        axp.set_xscale(scale_dic[ilogx])
        axp.set_yscale(scale_dic[ilogy])
        title(avearr[p-1]+unitarr[p-1],fontsize=fs1)
        xlabel('$k_y\\rho_s$', fontsize=fs2, family='serif')
else:
    for p in arange(1,11):
        axp = subplot(2, 5, p)
        for k in range(0,num_ky_eigen):
            cmd = 'plot(para_eigen,' + avearr[p - 1] + '.T[k],lab[k],linewidth=lw+1,label=num2str_xj(ky_eigen[k],effnum))'
            exec (cmd)
        legend(loc=0, fontsize=fs2)
        xlim([0.8 * min(para_eigen), 1.2 * max(para_eigen)])
        xticks(fontsize=fs2)
        yticks(fontsize=fs2)
        axp.set_xscale(scale_dic[ilogx])
        axp.set_yscale(scale_dic[ilogy])
        if p>4:
            xlabel(Para, fontsize=fs2, family='serif')
        title(avearr[p - 1]+unitarr[p-1], fontsize=fs1)
