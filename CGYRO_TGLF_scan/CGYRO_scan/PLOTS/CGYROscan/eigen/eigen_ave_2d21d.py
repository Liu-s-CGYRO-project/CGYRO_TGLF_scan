# calculate the wd for a given case
import numpy as np
import sys
#sys.path.append('/home/users/xiangjian/mymodule/CGYRO_SCAN/PLOTS/CGYROscan/assist')
from cgyro_read_xj import *
from cgyro_ball import *
from cgyro_ball_class import OMFITcgyro_eigen
f = open(root['PLOTS']['CGYROscan']['assist']['getglobal.py'].filename, 'r')
for line in f:
    exec(line)
f.close()

if setup['icgyro']==1:
    root['PLOTS']['CGYROscan']['assist']['collect.py'].run()
else:
    root['PLOTS']['CGYROscan']['assist']['collect_gyro.py'].run()

# then read all the data
nRange_x_eigen=len(para_x_eigen)
nRange_y_eigen=len(para_y_eigen)
num_ky_eigen=len(ky_eigen)
q_loc_ave=zeros([nRange_x_eigen,nRange_y_eigen,num_ky_eigen])
s_loc_ave=zeros([nRange_x_eigen,nRange_y_eigen,num_ky_eigen])
wd1_ave=zeros([nRange_x_eigen,nRange_y_eigen,num_ky_eigen])
k_par_ave=zeros([nRange_x_eigen,nRange_y_eigen,num_ky_eigen])
k_perp_ave=zeros([nRange_x_eigen,nRange_y_eigen,num_ky_eigen])
epar_ave=zeros([nRange_x_eigen,nRange_y_eigen,num_ky_eigen])
epar_esratio_ave=zeros([nRange_x_eigen,nRange_y_eigen,num_ky_eigen])
apar_ave=zeros([nRange_x_eigen,nRange_y_eigen,num_ky_eigen])
theta_width=zeros([nRange_x_eigen,nRange_y_eigen,num_ky_eigen])
kparvtioveromega_ave=zeros([nRange_x_eigen,nRange_y_eigen,num_ky_eigen])


for k in range(nRange_x_eigen):
    for p in range(nRange_y_eigen):
        for q in range(num_ky_eigen):
            dirname=Para_x+'_'+num2str_xj(para_x_eigen[k],effnum)+'~'+Para_y+'_'+num2str_xj(para_y_eigen[p],effnum)+'~ky_'+num2str_xj(ky_eigen[q],effnum)
            datanode=mounttree[dirname]
#            if setup['icgyro']==1:
#                datanode=OMFITcgyro_eigen(datanode.filename)
#            else:
#                datanode = OMFITcgyro_eigen(datanode.filename)
            datanode.eigen_ave()
            q_loc_ave[k][p][q]=datanode.q_loc_ave
            s_loc_ave[k][p][q] = datanode.s_loc_ave
            wd1_ave[k][p][q] = datanode.wd1_ave
            k_par_ave[k][p][q] = datanode.k_par_ave
            k_perp_ave[k][p][q] = datanode.k_perp_ave
            epar_ave[k][p][q] = datanode.epar_ave
            apar_ave[k][p][q] = datanode.apar_ave
#            epar_esratio_ave[k][p][q] = datanode.epar_esratio_ave
            theta_width[k][p][q] = datanode.theta_width
            epar_esratio_ave[k][p][q] = datanode.epar_esratio_ave
            kparvtioveromega_ave[k][p][q] = datanode.kparvtioveromega_ave

########################################
# based on the profiles we get, then all the linear information can be plotted
Para_x_dic={0:Para_x, 1: Para_y}
Para_y_dic={0:Para_y, 1: Para_x}
bdry_dic=[0, 0, 1.e-4,1.e-4,1,1]
avearr=['q_loc_ave','s_loc_ave','epar_ave','apar_ave','k_par_ave','k_perp_ave','wd1_ave','theta_width','kparvtioveromega_ave']
unitarr=['','','','(tearing)','(a^{-1})','*rhos','(cs/a)','(pi)','']

if idimplt==0:
    Range_x_grid,Range_y_grid=meshgrid(para_x_eigen,para_y_eigen)
else:
    Range_x_grid,Range_y_grid=meshgrid(para_y_eigen,para_x_eigen)
for k in range(num_ky_eigen):
    for p in range(1, len(avearr) + 1):
        fig=figure(ky_eigen[k],figsize=[10,10])
        ax = fig.gca()
        axp=subplot(2,5,p)
        if idimplt==0:
            cmd='plot(para_x_eigen,'+avearr[p-1]+'.T[k][m],lab[m],label=num2str_xj(para_y_eigen[m],effnum),linewidth=lw)'
            for m in range(0,nRange_y_eigen):
                exec(cmd)
        else:
            cmd='plot(para_y_eigen,'+avearr[p-1]+'.T[k].T[m],lab[m],label=num2str_xj(para_x_eigen[m],effnum),linewidth=lw)'
            for m in range(0,nRange_x_eigen):
                exec(cmd)
        if p>3 :
            xlabel(Para_x_dic[idimplt],fontsize=fs1,family='serif')
        axp.set_xscale(scale_dic[ilogx])
        axp.set_yscale(scale_dic[ilogy])
        xticks(fontsize=fs2,family='serif')
        yticks(fontsize=fs2,family='serif')
        legend(loc=0,fontsize=fs2).set_draggable(True)
        title(avearr[p-1]+unitarr[p-1],fontsize=fs1,family='serif')
