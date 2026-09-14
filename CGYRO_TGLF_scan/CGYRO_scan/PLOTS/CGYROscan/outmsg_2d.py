# this script is used to plot the eigenfrequency and growth rate for all the scanning cases,
import sys
#import seaborn as sns
from OMFITlib_cgyro_read import *
with open(root['PLOTS']['CGYROscan']['assist']['getglobal.py'].filename, 'r') as _helper_source:
    exec(compile(_helper_source.read(), _helper_source.name, 'exec'), globals())

# then read all the data
outmsg_arr=zeros([nRange_x,nRange_y,num_ky])     # dominate mode frequency
for k in range(nRange_x):
    for p in range(nRange_y):
        for q in range(num_ky):
            try:
                datanode=root['OUTPUTScan'][Para_x][num2str_xj(Range_x[k],effnum)][Para_y][num2str_xj(Range_y[p],effnum)]['lin'][num2str_xj(kyarr[q],effnum)]
                filename=datanode['out.cgyro.info'].filename
                outmsg=getoutmsg(filename)
            except:
                outmsg=4
            outmsg_arr[k][p][q]=outmsg
########################################
# based on the profiles we get, then all the linear information can be plotted
Para_x_dic={0:Para_x, 1: Para_y}
Para_y_dic={0:Para_y, 1: Para_x}
bdry_dic=[0, 0, 1.e-4,1.e-4]
texts='0:converged;/n 1: terminate at t_max;/n 2: integration error;/n 3: unfinished;/n 4: no out.cgyro.info '
if idimplt==0:
    Range_x_grid,Range_y_grid=meshgrid(Range_x,Range_y)
else:
    Range_x_grid,Range_y_grid=meshgrid(Range_y,Range_x)
rct=[0.2,0.2,0.6,0.6]
for k in range(num_ky):
    fig=figure(kyarr[k],figsize=[12,12])
    axp=plt.axes(rct)
    if idimplt==0:
        contourf(Range_x,Range_y,outmsg_arr.T[k],cmap='seismic',levels=5)
#        sns.heatmap(Range_x,Range_y,outmsg_arr.T[k],cmap='seismic')
        text(Range_x[0],1.2*max(Range_y),texts,fontsize=fs3)
    else:
        contourf(Range_y, Range_x, outmsg_arr.T[k].T, cmap='seismic',levels=5)
#        sns.heatmap(Range_y,Range_x,outmsg_arr.T[k].T,cmap='seismic')
        text(Range_x[0],1.2*max(Range_x),texts,fontsize=fs3)
    text(0,5,texts,fontsize=fs3)
    colorbar(ticks=[0,1,2,3,4])
    axp.set_xscale(scale_dic[ilogx])
    axp.set_yscale(scale_dic[ilogy])
    xlabel(Para_x_dic[idimplt],fontsize=fs1,family='serif')
    ylabel(Para_y_dic[idimplt],fontsize=fs1,family='serif')
    xticks(fontsize=fs2,family='serif')
    yticks(fontsize=fs2,family='serif')
    title(num2str_xj(kyarr[k],effnum),fontsize=fs1,family='serif')
