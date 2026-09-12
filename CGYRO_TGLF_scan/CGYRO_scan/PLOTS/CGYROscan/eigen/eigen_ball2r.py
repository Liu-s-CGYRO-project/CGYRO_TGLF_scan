# define a function convert the eigenfunction from ballooning space to r space
import numpy as np
import sys
#sys.path.append('/home/users/xiangjian/mymodule/CGYRO_SCAN/PLOTS/CGYROscan/assist')
from cgyro_read_xj import *
# from cgyro_ball import *
from cgyro_ball_class import OMFITcgyro_eigen
f = open(root['PLOTS']['CGYROscan']['assist']['getglobal.py'].filename, 'r')
for line in f:
    exec(line)
f.close()
if setup['icgyro']==1:
    root['PLOTS']['CGYROscan']['assist']['collect.py'].run()
else:
    root['PLOTS']['CGYROscan']['assist']['collect_gyro.py'].run()

# plot
figure(figsize=[8,10])
rct1=[0.1,0.55,0.35,0.35]
rct2=[0.5,0.55,0.35,0.35]
rct3=[0.1,0.05,0.35,0.35]
rct4=[0.5,0.05,0.35,0.35]
ax1=plt.axes(rct1)
ax2=plt.axes(rct2)
ax3=plt.axes(rct3)
ax4=plt.axes(rct4)
#Field_name=['phi_r_arr','phi_r_arr/phi_0','apar_r_arr','apar_r_arr/apar_0','jpar_r_arr','jpar_r_arr/jpar_0']
# Field_name=['phi_r_arr','apar_r_arr','jpar_r_arr']
Field_name=['apar_r_arr/apar_0',\
            'jpar_r_arr/jpar_0',\
            'phi_r_arr/phi_0']
ncount = 0
for dirname in root['SETTINGS']['PLOTS']['dirname']:
#        dirname='para_'+num2str_xj(paraval_item,effnum)+'~ky_'+num2str_xj(ky_item,effnum)
    case=mounttree[dirname]
    case.turn_ball2r()
    # f2_apar = interpolate.interp1d(self.theta_b, self.apar_b, kind='cubic')
    # apar_new=f2_apar(theta_new)
    ff_phi=interpolate.interp1d(case.r_arr, case.phi_r_arr, kind='cubic')
    phi_0 = ff_phi(0)
    ff_apar = interpolate.interp1d(case.r_arr, case.apar_r_arr, kind='cubic')
    apar_0 = ff_apar(0)
    ff_jpar = interpolate.interp1d(case.r_arr, case.jpar_r_arr, kind='cubic')
    jpar_0 = ff_jpar(0)
    if setup['icgyro']==1:
        delta_r=1./case['kyrhos']/case['input.cgyro.gen']['S']
    else:
        delta_r=1./case['kyrhos']/case['input.gyro.gen']['SHEAR']
    for k in range(1, 4):
        axk = subplot(3, 1, k)
        cmd='plot(case.r_arr,abs(case.'+Field_name[k-1]+'),lab[ncount],linewidth=lw,label=dirname)'
        exec(cmd)
        ylabel(Field_name[k - 1], fontsize=fs1, family='serif')
        xticks(fontsize=fs2, family='serif')
        yticks(fontsize=fs2, family='serif')
        xlim([-4*delta_r,4*delta_r])
    ncount = ncount + 1
xlabel('r($\\rho_s$)',fontsize=fs1)
legend(loc=0, fontsize=fs3).set_draggable(True)
# Temporary plot cache may be reused; saved OUTPUTS are untouched.
