# this script is used to plot the fluctuation intensity (kxky_phi spectrum) over different poloidal theta
# note the dky should be the same for those input cases
import sys
from matplotlib import ticker, cm
with open(root['PLOTS']['CGYROalone']['assist']['getglobal.py'].filename, 'r') as _helper_source:
    exec(compile(_helper_source.read(), _helper_source.name, 'exec'), globals())
root['PLOTS']['CGYROalone']['assist']['collect.py'].run()
# check to see how many fields that all the cases have in common
n_field=1
for k_case in range(n_case):
    casek = outputs[case_plot[k_case]]
    n_field=min(len(casek['field_tags']),n_field)
# plot
# figure(figsize=[15,12])
theta_p=linspace(-pi,pi,37)
i_thetap0=list(theta_p).index(0)  # geometry theta discretation
# for k_case in range(n_case):
#     print(case_plot[k_case])
#     casek = outputs[case_plot[k_case]]
#     casek.getbigfield()
#     casek.miller_wd_s(theta_p=theta_p)
# #   index specification
#     i_r=list(casek.kx).index(0)  # find the index of kx=0
#     i_n=0
#     i_theta0=list(casek.ftheta_plot).index(0)  # the i_theta for theta_plot=0
# ###
#     n_t_ft = len(casek.ind_t_ave)
# ## caution, don't write to be : phi_cmplx = casek.kxky_phi[0, :, :, :, case.t_ind_ave] + 1j * casek.kxky_phi[1, :, :, :, case.t_ind_ave]
#     phi_cmplx = casek.kxky_phi[0, :, :, :, :] + 1j * casek.kxky_phi[1, :, :, :,:] #phi_cmplx[i_r,i_theta_plot,i_n,self.ind_t_ave])
#     phi_cmplx=phi_cmplx[:,:,:,casek.ind_t_ave]/casek.dky
#     phi_abs=mean(abs(phi_cmplx),axis=-1) # phi2_abs[i_r,i_theta_plot,i_n]
#     subplot(231)
#     # phi over i_theta for a given i_n and i_r
#     plot(casek.ftheta_plot[0:-1]/pi,phi_abs[i_r,:,i_n]**2,lab3[k_case],linewidth=lw,label=case_plot[k_case])
#     xticks(fontsize=fs2)
#     yticks(fontsize=fs2)
#     # xlabel('$\\theta(\pi)$', fontsize=fs1, family='serif')
#     title('$\phi^2(k_y\\rho_s=%.2f,k_x\\rho_s=%.2f)$' % (casek.ky[i_n], casek.kx[i_r]),fontsize=fs1)
#     subplot(232)
#     # phi over i_theta for a given i_n summed over kx
#     plot(casek.ftheta_plot[0:-1]/pi,sum(phi_abs[:,:,i_n]*casek.dkx,axis=0)**2,lab3[k_case],linewidth=lw,label=case_plot[k_case])
#     xticks(fontsize=fs2)
#     yticks(fontsize=fs2)
#     # xlabel('$\\theta(\pi)$', fontsize=fs1, family='serif')
#     title('$\phi^2(k_y\\rho_s=%.2f)$' % casek.ky[i_n],fontsize=fs1)
#     subplot(233)
#     # phi over i_theta summed over i_n&i_r
#     plot(casek.ftheta_plot[0:-1]/pi,sum(phi_abs[:,:,:]*casek.dkx*casek.dky,axis=(0,2))**2,lab3[k_case],linewidth=lw,label=case_plot[k_case])
#     xticks(fontsize=fs2)
#     yticks(fontsize=fs2)
#     # xlabel('$\\theta(\pi)$', fontsize=fs1, family='serif')
#     title('$\phi^2$',fontsize=fs1)
#     # legend(loc=0, fontsize=fs2).draggable(True)
# #    normalized version, compared to the geometric parameters (Gary's suggestions)
#     subplot(234)
#     # phi over i_theta for a given i_n and i_r
#     plot(casek.ftheta_plot[0:-1]/pi,(phi_abs[i_r,:,i_n]/phi_abs[i_r,i_theta0,i_n])**2,lab3[k_case],linewidth=lw,label=case_plot[k_case])
#     if k_case==0:
#         plot(theta_p / pi, (casek.BoverBunit[i_thetap0]/casek.BoverBunit) ** 4, lab2[k_case],linewidth=lw,label='(B0/B)^4')
#         plot(theta_p / pi, (casek.Gq[i_thetap0] / casek.Gq) ** 4, lab[k_case], linewidth=lw,label='(G_q0/Gq)^4')
#     xticks(fontsize=fs2)
#     yticks(fontsize=fs2)
#     xlabel('$\\theta(\pi)$', fontsize=fs1, family='serif')
#     subplot(235)
#     # phi over i_theta for a given i_n summed over kx
#     plot(casek.ftheta_plot[0:-1]/pi,(sum(phi_abs[:,:,i_n]*casek.dkx,axis=0)/sum(phi_abs[:,i_theta0,i_n]*casek.dkx,axis=0))**2,lab3[k_case],linewidth=lw,label=case_plot[k_case])
#     if k_case == 0:
#         plot(theta_p / pi, (casek.BoverBunit[i_thetap0]/casek.BoverBunit) ** 4, lab2[k_case],linewidth=lw,label='(B0/B)^4')
#         plot(theta_p / pi, (casek.Gq[i_thetap0] / casek.Gq) ** 4, lab[k_case], linewidth=lw,label='(G_q0/Gq)^4')
#     xticks(fontsize=fs2)
#     yticks(fontsize=fs2)
#     xlabel('$\\theta(\pi)$', fontsize=fs1, family='serif')
#     # title('$\phi^2(k_y\\rho_s=%.2f)$' % casek.ky[i_n])
#     subplot(236)
#     # phi over i_theta summed over i_n&i_r
#     plot(casek.ftheta_plot[0:-1]/pi,(sum(phi_abs[:,:,:]*casek.dkx*casek.dky,axis=(0,2))/sum(phi_abs[:,i_theta0,:]*casek.dkx*casek.dky,axis=(0,-1)))**2,lab3[k_case],linewidth=lw,label=case_plot[k_case])
#     if k_case == 0:
#         plot(theta_p / pi, (casek.BoverBunit[i_thetap0]/casek.BoverBunit) ** 4, lab2[k_case],linewidth=lw,label='(B0/B)^4')
#         plot(theta_p / pi, (casek.Gq[i_thetap0] / casek.Gq) ** 4, lab[k_case], linewidth=lw,label='(G_q0/Gq)^4')
#     xticks(fontsize=fs2)
#     yticks(fontsize=fs2)
#     xlabel('$\\theta(\pi)$', fontsize=fs1, family='serif')
#     # title('$\phi^2$')
#     legend(loc=0, fontsize=fs2).draggable(True)

# plot the kxky_spectrum
figure(figsize=[15,8])
for k_case in range(n_case):
    print(case_plot[k_case])
    casek = outputs[case_plot[k_case]]
    casek.getbigfield()
    casek.miller_wd_s(theta_p=theta_p)
#   index specification
    i_r=list(casek.kx).index(0)  # find the index of kx=0
    i_n=0
    # i_theta0=list(casek.ftheta_plot).index(0)  # the i_theta for theta_plot=0
    i_theta0=int(8./16*casek.theta_plot)
###
    n_t_ft = len(casek.ind_t_ave)
    phi_cmplx = casek.kxky_phi[0, :, :, :, :] + 1j * casek.kxky_phi[1, :, :, :,:] #phi_cmplx[i_r,i_theta_plot,i_n,self.ind_t_ave])
    phi_cmplx=phi_cmplx/casek.dkx/casek.dky
    phi_cmplx=phi_cmplx[:,:,:,casek.ind_t_ave]
    phi_abs=mean(abs(phi_cmplx),axis=-1) # phi2_abs[i_r,i_theta_plot,i_n]
    axk=subplot(1,n_case,k_case+1)
    kx_grid,ky_grid=meshgrid(casek.kx,casek.ky)
    levels=np.logspace(-2,2,5)
    try:
        contourf(kx_grid,ky_grid,phi_abs[:,i_theta0,:].T,locator=ticker.LogLocator(),levels=levels)
    except:
        print('dimension does not really match!!')
        contourf(kx_grid,ky_grid,phi_abs[1:,i_theta0,:].T,locator=ticker.LogLocator(),levels=levels) # in the case that the dimension does not match
    colorbar()
    xlabel('$k_x\\rho_s$',fontsize=fs2,family='serif')
    if k_case==0:
        ylabel('$k_y\\rho_s$', fontsize=fs2, family='serif')
    title(case_plot[k_case]+'|$\\theta_{plot}$=%.2f'%casek.ftheta_plot[i_theta0])
