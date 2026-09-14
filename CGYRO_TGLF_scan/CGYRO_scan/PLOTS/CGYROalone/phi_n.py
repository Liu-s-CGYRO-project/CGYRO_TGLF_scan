# this script will be used to plot the fluctuation amplitute versus n
# plot flux(n) & flux(t)
import sys
with open(root['PLOTS']['CGYROalone']['assist']['getglobal.py'].filename, 'r') as _helper_source:
    exec(compile(_helper_source.read(), _helper_source.name, 'exec'), globals())
# check to see how many fields that all the cases have in common
icgyro=root['SETTINGS']['SETUP']['icgyro']
if icgyro==1:
    root['PLOTS']['CGYROalone']['assist']['collect.py'].run()
else:
    root['PLOTS']['CGYROalone']['assist']['collect_gyro.py'].run()
# check to see how many fields that all the cases have in common
n_field=3
for k_case in range(n_case):
    casek = outputs[case_plot[k_case]]
    if icgyro==1:
        n_field=min(len(casek['field_tags']),n_field)
    else:
        n_field=min(len(casek['tagfieldtext']),n_field)
# plot
figure('fluctuation amplitude',figsize=[8,12])
max_phi=0
kx_max=4
theta=0. #0 for outboard midplane and -1 for inboard plane
i_theta_plot=0 # 0 for outboard midplane
#i_n=3    # replaced with ky_want
ky_want=0.24 # the ky value what we want to specificially analyzed
ipltBr=0
for i_field in arange(n_field):
# plot the fluctuation amplitute
# phi over ky
    ax=subplot(n_field,3,3*i_field+1)
    for k_case in range(n_case):
        casek=outputs[case_plot[k_case]]
        if icgyro==1:
            casek.get_phi_n(i_field=i_field,theta=theta)
        else:
            casek.get_phi_n(i_field=i_field,i_theta_plot=i_theta_plot)
        #print(casek.get_phi_n(i_field=i_field,theta=theta))
        plot(casek.ky,abs(casek.phi_n_ave),labo[k_case],linewidth=lw,label=case_plot[k_case])
        #print(casek.phi_n_ave)
        max_phi=max(max_phi,max(abs(casek.phi_n_ave)))
        legend(loc=0,fontsize=fs2).draggable(True)
        xticks(fontsize=fs2)
        yticks(fontsize=fs2)
        # xlabel('$k_y\\rho_s$',fontsize=fs1,family='serif')
        ax.set_xscale(tick_scale[root['SETTINGS']['PLOTS']['ilogx']])
        ax.set_yscale(tick_scale[root['SETTINGS']['PLOTS']['ilogy']])
        ylabel('$\delta{'+field_name[i_field]+'}/\\rho_s$',fontsize=fs1,family='serif')
        if i_field==0:
            title('$\\theta=' + str(theta) + '\pi$', fontsize=fs1, family='serif')
        if i_field == n_field-1:
            xlabel('$k_y\\rho_s$', fontsize=fs1, family='serif')
# phi over kx
    subplot(n_field,3,3*i_field+2)
    for k_case in range(n_case):
        casek=outputs[case_plot[k_case]]
        if icgyro==1:
            casek.get_phi_n(i_field=i_field,theta=theta)
        else:
            casek.get_phi_n(i_field=i_field,i_theta_plot=i_theta_plot)
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

    # phi over kx for a given n
    subplot(n_field,3,3*i_field+3)
    for k_case in range(n_case):
        casek=outputs[case_plot[k_case]]
        i_n=np.where(abs(casek.ky-ky_want)==(min(abs(casek.ky-ky_want))))[0][0]
        if icgyro==1:
            casek.get_phi_n(i_field=i_field,theta=theta,i_n=i_n)
        else:
            casek.get_phi_n(i_field=i_field,i_theta_plot=i_theta_plot,i_n=i_n)
        semilogy(casek.kx,abs(casek.phi_n_overkx),labo[k_case],linewidth=lw,label=case_plot[k_case])
        max_phi=max(max_phi,max(abs(casek.phi_m_ave)))
        kx_max = max(kx_max, max(abs(casek.kx)))
        # legend(loc=0,fontsize=fs2).draggable(True)
        # title('$k_y\\rho_s='+str(casek.ky[i_n])+',\delta_{'+field_name[i_field]+'}/\\rho_s$',fontsize=fs1,family='serif')
        xticks(fontsize=fs2)
        yticks(fontsize=fs2)
        # ylim([0,ceil(max_phi)])
        xlim([-1*kx_max,kx_max])
        if i_field == 0:
            title('$k_y\\rho_s='+str(casek.ky[i_n])+'$', fontsize=fs1, family='serif')
        if i_field == n_field-1:
            xlabel('$k_x\\rho_s$', fontsize=fs1, family='serif')
# plot the Br
coe=8.
fpow_1=0.5
fpow_2=2.
if ipltBr==1:
    figure(figsize=[8,8])
    subplot(1,2,1)
    for k_case in range(n_case):
        casek=outputs[case_plot[k_case]]
        casek.get_phi_n(i_field=1,theta=theta)
        Br=casek.ky*casek.phi_n_ave
#        print(Br)
        plot(casek.ky,abs(Br),labo[k_case],linewidth=lw,label=case_plot[k_case])
        legend(loc=0,fontsize=fs2).draggable(True)
        xticks(fontsize=fs2)
        yticks(fontsize=fs2)
        ylabel('$B_r/B_{unit}/\\rho_s$',fontsize=fs1,family='serif')
        xlabel('$k_y\\rho_s$', fontsize=fs1, family='serif')
    subplot(1,2,2)
    for k_case in range(n_case):
        casek=outputs[case_plot[k_case]]
        casek.get_phi_n(i_field=1,theta=theta)
        Br=casek.ky*casek.phi_n_ave
#        print(Br)
        fitforflux=coe*(Br/casek.ky**fpow_1)**fpow_2
        plot(casek.ky,abs(fitforflux),labo[k_case],linewidth=lw,label=case_plot[k_case])
        print(sum(fitforflux[1:]))
        legend(loc=0,fontsize=fs2).draggable(True)
        xticks(fontsize=fs2)
        yticks(fontsize=fs2)
        title(str(coe)+'*(Br/ky**'+str(fpow_1)+')**'+str(fpow_2),fontsize=fs1,family='serif')
        ylim([0,6])
        xlabel('$k_y\\rho_s$', fontsize=fs1, family='serif')

# # seperate the calculation from plotting to avid duplicated calculation, which is time-consuming
# for k_case in range(n_case):
#     casek = outputs[case_plot[k_case]]
#     i_n = np.where(abs(casek.ky - ky_want) == (min(abs(casek.ky - ky_want))))[0][0]
#     print(case_plot[k_case])
#     for i_field in arange(n_field):
#         print(i_field)
#         casek.get_phi_n(i_field=i_field, theta=theta,i_n=i_n)
# # phi over ky
#         if k_case==0:
#             subplot(3,n_field,3*i_field+1)
#         plot(casek.ky,casek.phi_n_ave,labo[k_case],linewidth=lw,label=case_plot[k_case])
#         # print(casek.phi_n_ave)
#         # max_phi=max(max_phi,max(casek.phi_n_ave))
#         legend(loc=0,fontsize=fs2).draggable(True)
#         title('$|\\'+field_name[i_field]+'|(a.u.)-theta='+str(theta)+'\pi$',fontsize=fs1,family='serif')
#         xticks(fontsize=fs2)
#         yticks(fontsize=fs2)
#         xlabel('$k_y\\rho_s$',fontsize=fs1,family='serif')
#         # ylim([0,ceil(max_phi)])
# # # phi over kx
# #     subplot(3,n_field,3*i_field+2)
# #     for k_case in range(n_case):
# #         casek=outputs[case_plot[k_case]]
# #         # casek.getbigfield()
# #         # itheta=0
# #         # moment='phi'
# #         # fk,ftk = casek.kxky_select(int(itheta),i_field,moment,0) #
# #         # pk=sum(abs(fk[:,:,:]),axis=0)/casek.rho
# #         # kyrhos=abs(casek['kyrhos'])
# #         # plot(kyrhos,abs(mean(pk.T[t_ind[k_case]:-1],0)),lab[k],linewidth=lw,label=case_plot[k])
# #         casek.get_phi_n(i_field=i_field,theta=theta)
# #         semilogy(casek.kx,casek.phi_m_ave,labo[k_case],linewidth=lw,label=case_plot[k_case])
# #         max_phi=max(max_phi,max(casek.phi_m_ave))
# #         kx_max = max(kx_max, max(casek.kx))
# #         # legend(loc=0,fontsize=fs2).draggable(True)
# #         title('sum over ky:|'+field_name[i_field]+'|(a.u.)',fontsize=fs1,family='serif')
# #         xticks(fontsize=fs2)
# #         yticks(fontsize=fs2)
# #         xlabel('$k_x\\rho_s$',fontsize=fs1,family='serif')
# #         # ylim([0,ceil(max_phi)])
# #         xlim([-1*kx_max,kx_max])
# # # phi over kx for a given n
# #     subplot(3,n_field,3*i_field+3)
# #     for k_case in range(n_case):
# #         casek=outputs[case_plot[k_case]]
# #         # casek.getbigfield()
# #         # itheta=0
# #         # moment='phi'
# #         # fk,ftk = casek.kxky_select(int(itheta),i_field,moment,0) #
# #         # pk=sum(abs(fk[:,:,:]),axis=0)/casek.rho
# #         # kyrhos=abs(casek['kyrhos'])
# #         # plot(kyrhos,abs(mean(pk.T[t_ind[k_case]:-1],0)),lab[k],linewidth=lw,label=case_plot[k])
# #         i_n=np.where(abs(casek.ky-ky_want)==(min(abs(casek.ky-ky_want))))[0][0]
# #         casek.get_phi_n(i_field=i_field,theta=theta,i_n=i_n)
# #         semilogy(casek.kx,casek.phi_n_overkx,labo[k_case],linewidth=lw,label=case_plot[k_case])
# #         max_phi=max(max_phi,max(casek.phi_m_ave))
# #         kx_max = max(kx_max, max(casek.kx))
# #         # legend(loc=0,fontsize=fs2).draggable(True)
# #         title('ky='+str(casek.ky[i_n])+'|'+field_name[i_field]+'|(a.u.)',fontsize=fs1,family='serif')
# #         xticks(fontsize=fs2)
# #         yticks(fontsize=fs2)
# #         xlabel('$k_x\\rho_s$',fontsize=fs1,family='serif')
# #         # ylim([0,ceil(max_phi)])
# #         xlim([-1*kx_max,kx_max])
