# this script is used to plot the eigenfrequency and growth rate for all the scanning cases,
import sys
from OMFITlib_cgyro_read import *
with open(root['PLOTS']['CGYROscan']['assist']['getglobal.py'].filename, 'r') as _helper_source:
    exec(compile(_helper_source.read(), _helper_source.name, 'exec'), globals())

# then read all the data
outmsg_arr=zeros([nRange_x,nRange_y,num_ky])
for k in range(nRange_x):
    for p in range(nRange_y):
        for q in range(num_ky):
            # try:
            datanode=root['OUTPUTScan'][Para_x][num2str_xj(Range_x[k],effnum)][Para_y][num2str_xj(Range_y[p],effnum)]['lin'][num2str_xj(kyarr[q],effnum)]
            filename=datanode['out.cgyro.info'].filename
            outmsg=getoutmsg(filename)
            # except:
            #     outmsg=4
            outmsg_arr[k][p][q]=outmsg
########################################
# based on the profiles we get, then all the linear information can be plotted
Para_x_dic={0:Para_x, 1: Para_y}
Para_y_dic={0:Para_y, 1: Para_x}
bdry_dic={1:0, 2:0, 3:1.e-4, 4:1.e-4}
texts='0:converged;/n 1: terminate at t_max;/n 2: integration error;/n 3: unfinished;/n 4: no out.cgyro.info '
rct=[0.2,0.2,0.6,0.6]
for k in range(num_ky):
    fig=figure(str(kyarr[k]),figsize=[12,12])
    axp=plt.axes(rct)
    if idimplt==0:
        for m in range(0,nRange_y):
            plot(Range_x,outmsg_arr.T[k][m],lab[m],label=num2str_xj(Range_y[m],effnum),linewidth=lw)
        text(0.0*max(Range_x),5,'\\'+texts)
    else:
        for m in range(0,nRange_x):
            plot(Range_y,outmsg_arr.T[k].T[m],lab[m],label=num2str_xj(Range_x[m], effnum), linewidth=lw)
        text(0.0*max(Range_y),5,'\\'+texts)
    legend(loc=0,fontsize=fs2).set_draggable(True)
    axp.set_xscale(scale_dic[ilogx])
    axp.set_yscale(scale_dic[ilogy])
    xticks(fontsize=fs2,family='serif')
    yticks(linspace(0,4,5),fontsize=fs2,family='serif')
    ylim([0,4])
    title(num2str_xj(kyarr[k],effnum),fontsize=fs1,family='serif')
