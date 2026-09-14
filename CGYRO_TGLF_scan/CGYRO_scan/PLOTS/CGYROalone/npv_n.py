# this script will be used to plot the fluctuation amplitute of n&p&v versus n
import sys
with open(root['PLOTS']['CGYROalone']['assist']['getglobal.py'].filename, 'r') as _helper_source:
    exec(compile(_helper_source.read(), _helper_source.name, 'exec'), globals())
root['PLOTS']['CGYROalone']['assist']['collect.py'].run()
# check to see how many fields that all the cases have in common
n_moment=3
for k_case in range(n_case):
    casek = outputs[case_plot[k_case]]
    # n_moment=min(len(casek['field_tags']),n_moment)

# plot
figure('fluctuation npv amplitude',figsize=[8,12])
max_npv=0
kx_max=4
theta=0. #0 for outboard midplane and -1 for inboard plane
#i_n=3    # replaced with ky_want
ky_want=0.15 # the ky value what we want to specificially analyzed
i_species=-1  # electron case
for i_moment in arange(n_moment):
# plot the fluctuation amplitute
# npv over ky
    ax=subplot(n_moment,3,3*i_moment+1)
    for k_case in range(n_case):
        casek=outputs[case_plot[k_case]]
#        casek.get_npv_n(i_moment=i_moment,theta=theta)
#        case.get_npv_n(theta=0, i_n=1, i_species=-1, i_moment=0)
        casek.get_npv_n(theta=theta,  i_species=i_species, i_moment=i_moment)
        plot(casek.ky,casek.npv_n_ave,labo[k_case],linewidth=lw,label=case_plot[k_case])
#        print(casek.npv_n_ave)
        max_npv=max(max_npv,max(casek.npv_n_ave))
        legend(loc=0,fontsize=fs2).draggable(True)
        xticks(fontsize=fs2)
        yticks(fontsize=fs2)
        # xlabel('$k_y\\rho_s$',fontsize=fs1,family='serif')
        ax.set_xscale(tick_scale[root['SETTINGS']['PLOTS']['ilogx']])
        ax.set_yscale(tick_scale[root['SETTINGS']['PLOTS']['ilogy']])
        ylabel('$\delta{'+moment_name[i_moment]+'}/\\rho_s$',fontsize=fs1,family='serif')
        if i_moment==0:
            title('$\\theta=' + str(theta) + '\pi$', fontsize=fs1, family='serif')
        if i_moment == n_moment-1:
            xlabel('$k_y\\rho_s$', fontsize=fs1, family='serif')
# npv over kx
    subplot(n_moment,3,3*i_moment+2)
    for k_case in range(n_case):
        casek=outputs[case_plot[k_case]]
        casek.get_npv_n(theta=theta, i_species=i_species, i_moment=i_moment)
        semilogy(casek.kx,abs(casek.npv_m_ave),labo[k_case],linewidth=lw,label=case_plot[k_case])
        #plot(casek.kx,casek.npv_m_ave,labo[k_case],linewidth=lw,label=case_plot[k_case])
        max_npv=max(max_npv,max(casek.npv_m_ave))
        kx_max = max(kx_max, max(casek.kx))
        # legend(loc=0,fontsize=fs2).draggable(True)
        # title('sum over ky, $\delta_{'+field_name[i_moment]+'}/\\rho_s$',fontsize=fs1,family='serif')
        xticks(fontsize=fs2)
        yticks(fontsize=fs2)
        # xlabel('$k_x\\rho_s$',fontsize=fs1,family='serif')
        # ylim([0,ceil(max_npv)])
        xlim([-1*kx_max,kx_max])
        if i_moment == 0:
            title('Sum Over ky', fontsize=fs1, family='serif')
        if i_moment == n_moment-1:
            xlabel('$k_x\\rho_s$', fontsize=fs1, family='serif')

    # npv over kx for a given n
    subplot(n_moment,3,3*i_moment+3)
    for k_case in range(n_case):
        casek=outputs[case_plot[k_case]]
        i_n=np.where(abs(casek.ky-ky_want)==(min(abs(casek.ky-ky_want))))[0][0]
        casek.get_npv_n(theta=theta,i_n=i_n, i_species=i_species, i_moment=i_moment)
        semilogy(casek.kx,abs(casek.npv_n_overkx),labo[k_case],linewidth=lw,label=case_plot[k_case])
        #plot(casek.kx,casek.npv_n_overkx,labo[k_case],linewidth=lw,label=case_plot[k_case])

        max_npv=max(max_npv,max(casek.npv_m_ave))
        kx_max = max(kx_max, max(casek.kx))
        # legend(loc=0,fontsize=fs2).draggable(True)
        # title('$k_y\\rho_s='+str(casek.ky[i_n])+',\delta_{'+field_name[i_moment]+'}/\\rho_s$',fontsize=fs1,family='serif')
        xticks(fontsize=fs2)
        yticks(fontsize=fs2)
        # ylim([0,ceil(max_npv)])
        xlim([-1*kx_max,kx_max])
        if i_moment == 0:
            title('$k_y\\rho_s='+str(casek.ky[i_n])+'$', fontsize=fs1, family='serif')
        if i_moment == n_moment-1:
            xlabel('$k_x\\rho_s$', fontsize=fs1, family='serif')
