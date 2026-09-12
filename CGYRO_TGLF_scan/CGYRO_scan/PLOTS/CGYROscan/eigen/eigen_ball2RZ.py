# this is used to turn the eigenfunction from ballooning space to RZ plane
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


# for plot
ieikon=1 # determin whether you want to plot the eikon part or not
iabs=0   # 0: real part; 1: absolute value
# ncase=len(para_eigen)*len(ky_eigen)
ncase=len(root['SETTINGS']['PLOTS']['dirname'])
ncount=1
# RZ contour plot
figure(figsize=[10,10])
for dirname in root['SETTINGS']['PLOTS']['dirname']:
    case=root['OUTPUTS']['Linear'][dirname]
    case.turn_ball2RZ(rhos_over_a=1.e-3,n =2)
    ax=plt.subplot(3,ncase,ncount,projection='polar')
    if iabs==0:
    	ax.contourf(case.theta_grid_2d,case.r_grid_2d,real(case.phi_r_theta),160,cmap='seismic')
    else:
	    ax.contourf(case.theta_grid_2d,case.r_grid_2d,abs(case.phi_r_theta),160,cmap='seismic')
    # plt.show()
    ax.set_rlim([0,np.max(case.r_grid_2d)*1.1])
    ax.grid(False)
    title(dirname)
    plt.axis('off')
    if case.iapar==1:
        ax=plt.subplot(3,ncase,ncount+ncase,projection='polar')
        if iabs==0:
            ax.contourf(case.theta_grid_2d,case.r_grid_2d,real(case.apar_r_theta),160,cmap='seismic')
        else:
            ax.contourf(case.theta_grid_2d,case.r_grid_2d,abs(case.apar_r_theta),160,cmap='seismic')
        # plt.show()
        ax.set_rlim([0,np.max(case.r_grid_2d)*1.1])
        ax.grid(False)
        plt.axis('off')
    ax = plt.subplot(3, ncase, ncount+ncase*2, projection='polar')
    if iabs == 0:
        ax.contourf(case.theta_grid_2d, case.r_grid_2d, real(case.epar_r_theta), 160, cmap='seismic')
    else:
        ax.contourf(case.theta_grid_2d, case.r_grid_2d, abs(case.epar_r_theta), 160, cmap='seismic')
    # plt.show()
    ax.set_rlim([0, np.max(case.r_grid_2d) * 1.1])
    ax.grid(False)
    plt.axis('off')
    ncount=ncount+1


# for item in mounttree.keys():
#     del mounttree[item]
