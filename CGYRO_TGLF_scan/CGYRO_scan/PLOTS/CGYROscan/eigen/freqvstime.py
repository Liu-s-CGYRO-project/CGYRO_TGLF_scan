# this script is used to compare the eigenfunctions of different paraval or ky
# plots=root['SETTINGS']['PLOTS']
# effnum=plots['effnum']
# Para=plots['Para']
# if isinstance(plots['para_eigen'],float) or isinstance(plots['para_eigen'],int):
#     para_eigen=array([plots['para_eigen']])
# else:
#     para_eigen=plots['para_eigen']
# if isinstance(plots['ky_eigen'],float) or isinstance(plots['ky_eigen'],int):
#     ky_eigen=array([plots['ky_eigen']])
# else:
#     ky_eigen=plots['ky_eigen']
# #if len(para_eigen)*len(ky_eigen)>1:
# #   print('please use the eigencmp.py to compare the eigenfunction!')
# #   os._exit()
import numpy as np
import sys
#sys.path.append('/home/users/xiangjian/mymodule/CGYRO_SCAN/PLOTS/CGYROscan/assist')
from cgyro_read_xj import *
from cgyro_ball import *
f = open(root['PLOTS']['CGYROscan']['assist']['getglobal.py'].filename, 'r')
for line in f:
    exec(line)
f.close()
#root['PLOTS']['CGYROscan']['assist']['getglobal.py'].run()
if setup['icgyro']==1:
    root['PLOTS']['CGYROscan']['assist']['collect.py'].run()
else:
    root['PLOTS']['CGYROscan']['assist']['collect_gyro.py'].run()

# plot
figure(figsize=[16,12])
rct1=[0.1,0.55,0.35,0.35]
rct2=[0.5,0.55,0.35,0.35]
rct3=[0.1,0.05,0.35,0.35]
rct4=[0.5,0.05,0.35,0.35]
# fs1=24
# fs2=20
# fs3=16
# lw=2
ax1=plt.axes(rct1)
ax2=plt.axes(rct2)
ax3=plt.axes(rct3)
ax4=plt.axes(rct4)
lab=['-b','-r','-k','-g','-m','--b','--r','--k','--g','--m']
ncount=0
#iabs=1
for dirname in root['SETTINGS']['PLOTS']['dirname']:
#        dirname='para_'+num2str_xj(paraval_item,effnum)+'~ky_'+num2str_xj(ky_item,effnum)
    dirtree=mounttree[dirname]
    subplot(221)
    plot(dirtree['t'],dirtree['freq']['omega'][0],lab[ncount],linewidth=lw,label=dirname)
    xticks(fontsize=fs2,family='serif')
    yticks(fontsize=fs2,family='serif')
    title('$frequency$',fontsize=fs2,family='serif')
    legend(loc=0).set_draggable(True)
    subplot(223)
    plot(dirtree['t'],dirtree['freq']['gamma'][0],lab[ncount],linewidth=lw,label=dirname)
    xticks(fontsize=fs2,family='serif')
    yticks(fontsize=fs2,family='serif')
    title('$growth rate$',fontsize=fs2,family='serif')
    xlabel('$t(a/c_s)$',fontsize=fs2,family='serif')
    subplot(222)
    semilogy(dirtree['t'],abs(dirtree['freq']['omega'][0]),lab[ncount],linewidth=lw,label=dirname)
    xticks(fontsize=fs2,family='serif')
    yticks(fontsize=fs2,family='serif')
    title('$abs(frequency)$',fontsize=fs2,family='serif')
    legend(loc=0).set_draggable(True)
    subplot(224)
    semilogy(dirtree['t'],dirtree['freq']['gamma'][0],lab[ncount],linewidth=lw,label=dirname)
    xticks(fontsize=fs2,family='serif')
    yticks(fontsize=fs2,family='serif')
    title('$abs(growth rate)$',fontsize=fs2,family='serif')
    ncount=ncount+1
# Plotting never deletes saved OUTPUTS.
