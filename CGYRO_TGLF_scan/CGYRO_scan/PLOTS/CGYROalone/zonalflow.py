# this script is used to plot the zonal flow shearing rate versus theta
import sys
with open(root['PLOTS']['CGYROalone']['assist']['getglobal.py'].filename, 'r') as _helper_source:
    exec(compile(_helper_source.read(), _helper_source.name, 'exec'), globals())
icgyro=root['SETTINGS']['SETUP']['icgyro']
if icgyro==1:
    root['PLOTS']['CGYROalone']['assist']['collect.py'].run()
else:
    root['PLOTS']['CGYROalone']['assist']['collect_gyro.py'].run()
# check to see how many fields that all the cases have in common
n_field=2
figure(figsize=[15,6])
for k_case in range(n_case):
    casename=case_plot[k_case]
    casek = outputs[casename]
#    freqsign=sign(casek['kyrhos'][-1])
#    print(casename)
    i_theta_plot=4*casek.n_theta_plot//8   # outboard midplane
    casek.get_zfshear(i_theta_plot=i_theta_plot)
    ftheta_plot = casek.ftheta_plot[i_theta_plot] / 3.14
# one figure for one case
    subplot(1,4,1)
    try:
        semilogy(casek.kx, abs(casek.zf_kx/casek.rho),lab[k_case],linewidth=lw,label=casename)
        #plot(casek.kx, casek.zf_kx/casek.rho,lab[k_case],linewidth=lw,label=casename)
    except:
        semilogy(casek.kx, casek.zf_kx[1:]/casek.rho,lab[k_case],linewidth=lw,label=casename)
    xlabel('$k_x\\rho_s$',fontsize=fs1,family='serif')
    title('$\phi_{ZF}/\\rho_s(\\theta=%.2f)$' % ftheta_plot,fontsize=fs1)
    plt.show()
    # print(casek.freq_n[i_n].data)
    xticks(fontsize=fs1)
    yticks(fontsize=fs1)
    subplot(1,4,2)
    plot(casek.kx, casek.gamma_zf,lab[k_case],linewidth=lw,label=casename)
    xlabel('$k_x\\rho_s$',fontsize=fs1,family='serif')
    # title('$\gamma_{ZF}(k_x^2*\phi_{ZF},cs/a)(\\theta=%.2f)$' % ftheta_plot,fontsize=fs1)
    title('$\gamma_{ZF}(c_s/a, \\theta=%.2f)$' % ftheta_plot,fontsize=fs1)
    xticks(fontsize=fs1)
    yticks(fontsize=fs1)
    subplot(1,4,3)
    plot(casek.ftheta_plot[0:casek.n_theta_plot]/np.pi,casek.zf_shear,lab[k_case],linewidth=lw,label=casename)
    print(casek.zf_shear)
    xlabel('$\\theta/pi$',fontsize=fs1,family='serif')
    title('$s_{ZF}(c_s/a)$', fontsize=fs1, family='serif')
    xticks(fontsize=fs2)
    yticks(fontsize=fs2)
    legend(loc=0,fontsize=fs2).draggable(True)
    subplot(1,4,4)
    casek.get_shear_stress(theta=ftheta_plot)   # should be careful that the theta should be in unit of rad
    plot(casek.ky,casek.S_stree,lab[k_case],linewidth=lw,label=casename)
    xlabel('$k_y\\rho_s$',fontsize=fs1,family='serif')
    title('$S_{stress}(c_s/a), \\theta=%.2f)$' % ftheta_plot,fontsize=fs1)
    xticks(fontsize=fs2)
    yticks(fontsize=fs2)
