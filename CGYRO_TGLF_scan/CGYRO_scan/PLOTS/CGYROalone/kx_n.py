# this script will be used to plot the potential amplitude averaged kx versus n
import sys
import numpy as np
#sys.path.append('/home/users/xiangjian/mymodule/CGYRO_SCAN/PLOTS/CGYROalone/assist')
f = open(root['PLOTS']['CGYROalone']['assist']['getglobal.py'].filename, 'r')
for line in f:
    exec(line)
f.close()
root['PLOTS']['CGYROalone']['assist']['collect.py'].run()
# check to see how many fields that all the cases have in common
n_field=3
for k_case in range(n_case):
    casek = outputs[case_plot[k_case]]
    n_field=min(len(casek['field_tags']),n_field)
# plot
figure('<kx>/ky',figsize=[8,12])
max_phi=0
kx_max=4
#i_n=3    # replaced with ky_want
ky_want=0.84 # the ky value what we want to specificially analyzed
for i_field in arange(n_field):
# plot the <kx> over ky
    ax=subplot(n_field,3,3*i_field+1)
    for k_case in range(n_case):
        casek=outputs[case_plot[k_case]]
        i_theta_plot = int(floor(1 / 2 * casek.n_theta_plot))
        print(i_theta_plot)
        casek.get_kx_ky(i_field=i_field,i_theta_plot=i_theta_plot)
        plot(casek.ky,np.divide(1., casek.kx_over_ky, out=np.full_like(casek.kx_over_ky, np.nan), where=casek.kx_over_ky_valid & (casek.kx_over_ky != 0)),labo[k_case],linewidth=lw,label=case_plot[k_case])
        legend(loc=0,fontsize=fs2).draggable(True)
        xticks(fontsize=fs2)
        yticks(fontsize=fs2)
        # xlabel('$k_y\\rho_s$',fontsize=fs1,family='serif')
        ax.set_xscale(tick_scale[root['SETTINGS']['PLOTS']['ilogx']])
        ax.set_yscale(tick_scale[root['SETTINGS']['PLOTS']['ilogy']])
        ylabel('$k_y/k_x$',fontsize=fs1,family='serif')
        if i_field==0:
            title('$\\theta=' + str(casek.ftheta_plot[i_theta_plot]) + '\pi$', fontsize=fs1, family='serif')
        if i_field == n_field-1:
            xlabel('$k_y\\rho_s$', fontsize=fs1, family='serif')
# phi over kx
    subplot(n_field,3,3*i_field+2)
    for k_case in range(n_case):
        theta=0
        casek=outputs[case_plot[k_case]]
        casek.get_phi_n(i_field=i_field,theta=theta)
        semilogy(casek.kx,abs(casek.phi_m_ave),labo[k_case],linewidth=lw,label=case_plot[k_case])
        # plot(casek.kx,casek.phi_m_ave,labo[k_case],linewidth=lw,label=case_plot[k_case])
        max_phi=max(max_phi,max(abs(casek.phi_m_ave)))
        kx_max = max(kx_max, max(abs(casek.kx)))
        # legend(loc=0,fontsize=fs2).draggable(True)
        # title('sum over ky, $\delta_{'+field_name[i_field]+'}/\\rho_s$',fontsize=fs1,family='serif')
        xticks(fontsize=fs2)
        yticks(fontsize=fs2)
        # xlabel('$k_x\\rho_s$',fontsize=fs1,family='serif')
        # ylim([0,ceil(max_phi)])
        xlim([-1*kx_max,kx_max])
        if i_field == 0:
            title('Sum Over ky', fontsize=fs1, family='serif')
        if i_field == n_field-1:
            xlabel('$k_x\\rho_s$', fontsize=fs1, family='serif')

    # # phi over kx for a given n
    # subplot(n_field,3,3*i_field+3)
    # for k_case in range(n_case):
    #     casek=outputs[case_plot[k_case]]
    #     i_n=np.where(abs(casek.ky-ky_want)==(min(abs(casek.ky-ky_want))))[0][0]
    #     casek.get_phi_n(i_field=i_field,theta=theta,i_n=i_n)
    #     semilogy(casek.kx,abs(casek.phi_n_overkx),labo[k_case],linewidth=lw,label=case_plot[k_case])
    #     max_phi=max(max_phi,max(abs(casek.phi_m_ave)))
    #     kx_max = max(kx_max, max(abs(casek.kx)))
    #     # legend(loc=0,fontsize=fs2).draggable(True)
    #     # title('$k_y\\rho_s='+str(casek.ky[i_n])+',\delta_{'+field_name[i_field]+'}/\\rho_s$',fontsize=fs1,family='serif')
    #     xticks(fontsize=fs2)
    #     yticks(fontsize=fs2)
    #     # ylim([0,ceil(max_phi)])
    #     xlim([-1*kx_max,kx_max])
    #     if i_field == 0:
    #         title('$k_y\\rho_s='+str(casek.ky[i_n])+'$', fontsize=fs1, family='serif')
    #     if i_field == n_field-1:
    #         xlabel('$k_x\\rho_s$', fontsize=fs1, family='serif')
    ax=subplot(n_field,3,3*i_field+3)
    for k_case in range(n_case):
        casek=outputs[case_plot[k_case]]
        i_theta_plot = int(floor(1 / 2 * casek.n_theta_plot))
        print(i_theta_plot)
        casek.get_kx_ky(i_field=i_field,i_theta_plot=i_theta_plot)
        plot(casek.ky,casek.kx0,labo[k_case],linewidth=lw,label=case_plot[k_case])
        legend(loc=0,fontsize=fs2).draggable(True)
        xticks(fontsize=fs2)
        yticks(fontsize=fs2)
        # xlabel('$k_y\\rho_s$',fontsize=fs1,family='serif')
        ax.set_xscale(tick_scale[root['SETTINGS']['PLOTS']['ilogx']])
        ax.set_yscale(tick_scale[root['SETTINGS']['PLOTS']['ilogy']])
        ylabel('$kx0$',fontsize=fs1,family='serif')
        if i_field==0:
            title('$\\theta=' + str(casek.ftheta_plot[i_theta_plot]) + '\pi$', fontsize=fs1, family='serif')
        if i_field == n_field-1:
            xlabel('$k_y\\rho_s$', fontsize=fs1, family='serif')
