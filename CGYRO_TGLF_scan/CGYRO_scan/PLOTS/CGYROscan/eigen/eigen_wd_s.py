
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
mounttree=root['OUTPUTS']['Linear']
if setup['icgyro']==1:
    root['PLOTS']['CGYROscan']['assist']['collect.py'].run()
else:
    root['PLOTS']['CGYROscan']['assist']['collect_gyro.py'].run()


# plot the drift frequency for different cases
# mostly we will focus on wd1
figure(figsize=[20,10])
ncount=0
inorm=2 # 0: no normalization; 1: normalized by the averaged value; 2: normalized by the value at theta=0
fieldname='apar'

for dirname in root['SETTINGS']['PLOTS']['dirname']:
    case=mounttree[dirname]
    subplot(251)
    plot(case.theta_b/pi,case.phi_b,lab[ncount],linewidth=lw,label=dirname)
    xlabel('$\\theta_b(\pi)$',fontsize=fs2,family='serif')
    if case.n_r==1:
        xlim([-1,1])
    else:
        xlim([1-case.n_r,case.n_r-1])
    xticks(fontsize=fs2,family='serif')
    yticks(fontsize=fs2,family='serif')
    title('$\\phi$',fontsize=fs2,family='serif')
#    legend(loc=0).set_draggable(True)
    subplot(256)
    # theta,phi_theta,apar_theta=turn_ball2theta(case)
    case.turn_ball2theta()
    phi_p0=interp(0,case.theta_p,case.phi_p)
    if inorm==1:
        phi_p=case.phi_p/mean(abs(case.phi_p))
    elif inorm==2:
        phi_p=case.phi_p/phi_p0
    plot(case.theta_p/pi,abs(phi_p),lab[ncount],linewidth=lw,label=dirname)
    xlabel('$\\theta_p(\pi)$',fontsize=fs2,family='serif')
    xticks(fontsize=fs2,family='serif')
    yticks(fontsize=fs2,family='serif')
    # title('$\phi$',fontsize=fs2,family='serif')
#    legend(loc=0).set_draggable(True)
    subplot(252)
    if case.iapar==1:
        plot(case.theta_b/pi,case.apar_b,lab[ncount],linewidth=lw,label=dirname)
    xlabel('$\\theta_b(\pi)$',fontsize=fs2,family='serif')
    if case.n_r==1:
        xlim([-1,1])
    else:
        xlim([1-case.n_r,case.n_r-1])
    xticks(fontsize=fs2,family='serif')
    yticks(fontsize=fs2,family='serif')
    title('$A_{||}$',fontsize=fs2,family='serif')
#    legend(loc=0).set_draggable(True)
    subplot(257)
#        theta,phi_theta,apar_theta=turn_ball2theta(case)
    if case.iapar==1:
        if inorm == 1:
            apar_p = case.apar_p / mean(abs(case.apar_p))
        plot(case.theta_p/pi,abs(case.apar_p),lab[ncount],linewidth=lw,label=dirname)
    xlabel('$\\theta_p(\pi)$',fontsize=fs2,family='serif')
    xticks(fontsize=fs2,family='serif')
    yticks(fontsize=fs2,family='serif')
    # title('$\phi$',fontsize=fs2,family='serif')
    legend(loc=0).set_draggable(True)
    subplot(253)
    # theta, wd1,wd2,wd3,k_perp=miller_dftfreq(inputcgyro)
    case.miller_wd_s()
    plot(case.theta_p/pi,case.wd1,lab[ncount],linewidth=lw,label=dirname)
    plot([-1,1],[0,0],'--r',linewidth=lw/2.)
#        xlabel('$\\theta_p(\pi)$',fontsize=fs2,family='serif')
    xticks(fontsize=fs2,family='serif')
    yticks(fontsize=fs2,family='serif')
    text(-0.9,0.2,'Destabilizing',fontsize=fs3)
    text(-0.9,-0.5,'Stabilizing',fontsize=fs3)
    title('$w_{d1}$',fontsize=fs2,family='serif')
    subplot(258)
    # theta, q_loc, s_loc=local_s_q(inputcgyro)
    plot(case.theta_p/pi,case.s_loc,lab[ncount],linewidth=lw,label=dirname)
    plot([-1, 1], [0, 0], '--r', linewidth=lw / 2.)
    xlabel('$\\theta_p(\pi)$',fontsize=fs2,family='serif')
    xticks(fontsize=fs2,family='serif')
    yticks(fontsize=fs2,family='serif')
    title('$s_{loc}$',fontsize=fs2,family='serif')
    subplot(254)
    plot(case.theta_p / pi, case.q_loc*case.Rmaj, lab[ncount], linewidth=lw, label=dirname)
    plot([-1, 1], [0, 0], '--r', linewidth=lw / 2.)
    #        xlabel('$\\theta_p(\pi)$',fontsize=fs2,family='serif')
    xticks(fontsize=fs2, family='serif')
    yticks(fontsize=fs2, family='serif')
    title('$q_{loc}*R_{maj,loc}$', fontsize=fs2, family='serif')
    subplot(259)
#    plot(theta / pi, abs(s_loc), lab[ncount], linewidth=lw, label=dirname)
    plot(case.theta_p / pi, case.k_perp, lab[ncount], linewidth=lw, label=dirname)
    plot([-1, 1], [0, 0], '--r', linewidth=lw / 2.)
    #        xlabel('$\\theta_p(\pi)$',fontsize=fs2,family='serif')
    xticks(fontsize=fs2, family='serif')
    yticks(fontsize=fs2, family='serif')
    xlabel('$\\theta_p(\pi)$',fontsize=fs2,family='serif')
#    title('$|s_{loc}|$', fontsize=fs2, family='serif')
    title('$k_{perp}$', fontsize=fs2, family='serif')
    subplot(255)
    jnorm=1 # whether normlized to the outboard midplane
    if jnorm==1:
        plot(case.theta_p / pi, case.BoverBunit/amin(case.BoverBunit), lab[ncount], linewidth=lw, label=dirname)
        ylim([1, 1.5])
        title('$B/B_{unit}-normalized to B(\\theta=0)$', fontsize=fs2, family='serif')
    else:
        plot(case.theta_p / pi, case.BoverBunit, lab[ncount], linewidth=lw, label=dirname)
        ylim([0.5,1])
        title('$B/B_{unit}$', fontsize=fs2, family='serif')
    xticks(fontsize=fs2, family='serif')
    yticks(fontsize=fs2, family='serif')
    #    title('$|s_{loc}|$', fontsize=fs2, family='serif')
    subplot(2,5,10)
    plot(case.theta_p / pi, case.q_loc, lab[ncount], linewidth=lw, label=dirname)
    plot(array([-1,1]),array([case.q,case.q]),'--k',linewidth=lw/2)
    plot([-1, 1], [0, 0], '--r', linewidth=lw / 2.)
    #        xlabel('$\\theta_p(\pi)$',fontsize=fs2,family='serif')
    xticks(fontsize=fs2, family='serif')
    yticks(fontsize=fs2, family='serif')
    xlabel('$\\theta_p(\pi)$', fontsize=fs2, family='serif')
    title('$q_{loc}$', fontsize=fs2, family='serif')


    ncount=ncount+1
# Temporary plot cache may be reused; saved OUTPUTS are untouched.
