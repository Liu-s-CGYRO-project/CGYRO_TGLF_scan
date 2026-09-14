import numpy as np
import sys
from OMFITlib_cgyro_read import *
with open(root['PLOTS']['CGYROscan']['assist']['getglobal.py'].filename, 'r') as _helper_source:
    exec(compile(_helper_source.read(), _helper_source.name, 'exec'), globals())
if setup['icgyro']==1:
    root['PLOTS']['CGYROscan']['assist']['collect.py'].run()
else:
    root['PLOTS']['CGYROscan']['assist']['collect_gyro.py'].run()
# plot
figure(figsize=[12,8])
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

lab=['-b','-r','-k','-g','-m','--b','--r','--k','--g','--m']
ncount=0
iabs=0
for dirname in root['SETTINGS']['PLOTS']['dirname']:
    case=mounttree[dirname]
    balloon=case['balloon']
    # if case['n_r']==1:
    #     thetaname='theta_over_pi'
    # else:
    #     thetaname='theta_b_over_pi'
    subplot(221)
    if iabs==0:
        plot(case.theta_b/np.pi,case.phi_b,lab[ncount],linewidth=lw,label=dirname)
    else:
        plot(case.theta_b/np.pi,abs(case.phi_b),lab[ncount],linewidth=lw,label=dirname)
#        ax1.plot(balloon[thetaname],balloon['balloon_phi'].T[-1],lab[ncount],linewidth=lw)
    xticks(fontsize=fs2,family='serif')
    yticks(fontsize=fs2,family='serif')
    title('$\phi$',fontsize=fs2,family='serif')
    legend(loc=0).set_draggable(True)
# in addition, the normalized eigenfunction will also be plotted
#     phi_0=interp(0,balloon[thetaname],balloon['balloon_phi'].T[-1])# used for normalization
#     subplot(222)
#     if iabs==0:
#         plot(balloon[thetaname],balloon['balloon_phi'].T[-1]/phi_0,lab[ncount],linewidth=lw)
#     else:
#         plot(balloon[thetaname],abs(balloon['balloon_phi'].T[-1]/phi_0),lab[ncount],linewidth=lw)
# #        ax2.plot(balloon[thetaname],balloon['balloon_phi'].T[-1]/phi_0,lab[ncount],linewidth=lw)
# # for writting out
# #    theta_b=balloon[thetaname]
# #    phi_norm=balloon['balloon_phi'].T[-1].data/phi_0
# #    eigenout='/home/jianx/highgradient/eigen_ball'+dirname+'.txt'
# #    fid=open(eigenout,'w')
# #    for kk in arange(len(theta_b)):
# #        theta_item=theta_b[kk]
# #        phi_item=phi_norm[kk]
# #        line=str(theta_item)+'    '+str(real(phi_item))+'    '+str(imag(phi_item))
# #        fid.write(line)
# #        fid.write('\n')
# #    fid.close()
    subplot(222)
    if iabs==0:
        plot(case.theta_b/np.pi,case.epar_b,lab[ncount],linewidth=lw)
    else:
        plot(case.theta_b/np.pi,abs(case.epar_b),lab[ncount],linewidth=lw)
    xticks(fontsize=fs2,family='serif')
    yticks(fontsize=fs2,family='serif')
    # title('$\phi_{norm}$',fontsize=fs2,family='serif')
    title('$E_{||}$',fontsize=fs2,family='serif')
    if 'balloon_apar' in balloon.keys():
        subplot(223)
        if iabs==0:
            # plot(balloon[thetaname],balloon['balloon_apar'].T[-1],lab[ncount],linewidth=lw,label=dirname)
            plot(case.theta_b/np.pi,case.apar_b,lab[ncount],linewidth=lw,label=dirname)
        else:
            # plot(balloon[thetaname],abs(balloon['balloon_apar'].T[-1]),lab[ncount],linewidth=lw,label=dirname)
            plot(case.theta_b/np.pi , abs(case.apar_b), lab[ncount], linewidth=lw, label=dirname)
        xlabel('$\\theta(\pi)$',fontsize=fs1,family='serif')
        xticks(fontsize=fs2,family='serif')
        yticks(fontsize=fs2,family='serif')
        title('$A_{||}$',fontsize=fs2,family='serif')
    if case.ibpar !=0:
        subplot(224)
        #ax4=plt.axes(rct4)
        if iabs == 0:
            plot(case.theta_b/np.pi, case.bpar_b, lab[ncount], linewidth=lw, label=dirname)
        else:
            plot(case.theta_b/np.pi, abs(case.bpar_b), lab[ncount], linewidth=lw, label=dirname)
        #            ax3.plot(balloon[thetaname],balloon['balloon_apar'].T[-1],lab[ncount],linewidth=lw,label=dirname)
        xlabel('$\\theta(\pi)$', fontsize=fs1, family='serif')
        xticks(fontsize=fs2, family='serif')
        yticks(fontsize=fs2, family='serif')
        title('$B_{||}$', fontsize=fs2, family='serif')
        # title('$A_{||}$', fontsize=fs2, family='serif')
#         apar_0=interp(0,balloon[thetaname],balloon['balloon_apar'].T[-1])# used for normalization
        # subplot(224)
        # if iabs==0:
        #      plot(balloon[thetaname],balloon['balloon_apar'].T[-1]/apar_0,lab[ncount],linewidth=lw,label=dirname)
        # else:
        #      plot(balloon[thetaname],abs(balloon['balloon_apar'].T[-1]/apar_0),lab[ncount],linewidth=lw,label=dirname)
        # xlabel('$\\theta(\pi)$',fontsize=fs1,family='serif')
        # xticks(fontsize=fs2,family='serif')
        # yticks(fontsize=fs2,family='serif')
        # title('$A_{||,norm}$',fontsize=fs2,family='serif')
    ncount=ncount+1
# for item in mounttree.keys():
#    del mounttree[item]

    ax1.spines['bottom'].set_linewidth(bwith)
    ax1.spines['left'].set_linewidth(bwith)
    ax1.spines['top'].set_linewidth(bwith)
    ax1.spines['right'].set_linewidth(bwith)
    ax2.spines['bottom'].set_linewidth(bwith)
    ax2.spines['left'].set_linewidth(bwith)
    ax2.spines['top'].set_linewidth(bwith)
    ax2.spines['right'].set_linewidth(bwith)
    ax3.spines['bottom'].set_linewidth(bwith)
    ax3.spines['left'].set_linewidth(bwith)
    ax3.spines['top'].set_linewidth(bwith)
    ax3.spines['right'].set_linewidth(bwith)
