# this script is used to plot the phi intensity over frequency via fft
import sys
#sys.path.append('/home/users/xiangjian/mymodule/CGYRO_SCAN/PLOTS/CGYROalone/assist')
from matplotlib import ticker, cm
f = open(root['PLOTS']['CGYROalone']['assist']['getglobal.py'].filename, 'r')
for line in f:
    exec(line)
f.close()

# note that it could be better if we split the time window in to several sub time windows
t_ave_orig=root['SETTINGS']['PLOTS']['nl']['t_ave']
t_end_orig=root['SETTINGS']['PLOTS']['nl']['t_end']
n_split=1
i_n = 6
i_field=0
icgyro=root['SETTINGS']['SETUP']['icgyro']
# root['PLOTS']['CGYROalone']['assist']['collect.py'].run()
for k_case in range(n_case):
    t_ave=t_ave_orig/n_split
    ncount=0
    for i_split in arange(n_split):
        t_end=t_end_orig-t_ave*i_split
        root['SETTINGS']['PLOTS']['nl']['t_ave']=t_ave
        root['SETTINGS']['PLOTS']['nl']['t_end'] = t_end
        print(t_ave)
        if icgyro==1:
            root['PLOTS']['CGYROalone']['assist']['collect.py'].run()
        else:
            root['PLOTS']['CGYROalone']['assist']['collect_gyro.py'].run()
        casename=case_plot[k_case]
        casek = outputs[casename]
        print(casename)
        # setup parameters for the plots
        i_r = casek.n_r // 2  #
        i_theta_plot = casek.n_theta_plot * 4 // 8  # outboard midplane
        casek.get_phi_freq(i_n=i_n,i_r=i_r,i_theta_plot=i_theta_plot,i_field=0)
        if icgyro==1:
            freqsign=sign(casek['freq']['omega'].isel(ky=-1,t=-1))
        else:
            freqsign=-1   # just a temporaly treatment
        if i_split==0:
            nss_ky=shape(casek.phi_ky_omega)
            phi_ky_omega_isplit0=casek.phi_ky_omega
            phi_ky_omega_kx0_isplit0=casek.phi_ky_omega_kx0
            phi_ithetaplot_omega_isplit0=casek.phi_ithetaplot_omega
            phi_ithetaplot_omega_kx0_isplit0=casek.phi_ithetaplot_omega_kx0
            ky_omega_grid_isplit0=casek.ky_omega_grid
            omega_ky_grid_isplit0=casek.omega_ky_grid
            omega_n_isplit0=casek.omega_n
            phi_kx_omega_isplit0=casek.phi_kx_omega
            phi_ky_omega_arr=zeros([n_split,nss_ky[0],nss_ky[1]],dtype='complex')
            phi_ky_omega_kx0_arr = zeros([n_split, nss_ky[0], nss_ky[1]], dtype='complex')
            if icgyro==1:
                casek.get_freq_n()
                freq_n_arr=zeros([n_split,len(casek.freq_n)])  # df/dt nonlin
            omega_n_arr = zeros([n_split, len(casek.omega_n)]) #weighted freq
            nss_ithetaplot=shape(casek.phi_ithetaplot_omega)
            phi_ithetaplot_omega_arr=zeros([n_split,nss_ithetaplot[0],nss_ithetaplot[1]],dtype='complex')
            phi_ithetaplot_omega_kx0_arr = zeros([n_split, nss_ithetaplot[0], nss_ithetaplot[1]], dtype='complex')
            nss_kx=shape(casek.phi_kx_omega)
            phi_kx_omega_arr=zeros([n_split,nss_kx[0],nss_kx[1]],dtype='complex')
        if icgyro==1:
            casek.get_freq_n()
        try:   # just in cass the len(ind_t_ave) is not exactly the same
            ncount=ncount+1
            phi_ky_omega_arr[i_split]=casek.phi_ky_omega
            phi_ky_omega_kx0_arr[i_split] = casek.phi_ky_omega_kx0
            phi_ithetaplot_omega_arr[i_split]=casek.phi_ithetaplot_omega
            phi_ithetaplot_omega_kx0_arr[i_split] = casek.phi_ithetaplot_omega_kx0
            omega_n_arr[i_split] = casek.omega_n
            phi_kx_omega_arr[i_split]=casek.phi_kx_omega
        except:
            phi_ky_omega_arr[i_split]=phi_ky_omega_isplit0
            phi_ky_omega_kx0_arr[i_split] = phi_ky_omega_kx0_isplit0
            phi_ithetaplot_omega_arr[i_split]=phi_ithetaplot_omega_isplit0
            phi_ithetaplot_omega_kx0_arr[i_split] = phi_ithetaplot_omega_kx0_isplit0
            omega_n_arr[i_split] = omega_n_isplit0
            phi_kx_omega_arr[i_split]=phi_kx_omega_isplit0
        if icgyro==1:
            freq_n_arr[i_split]=casek.freq_n
    print(n_split-ncount,'splits are not accounted in n_split of ',n_split )
# one figure for one case
    figure(figsize=[15,8])
    subplot(121)
    # contourf(casek.ky_omega_grid, casek.omega_ky_grid, abs(casek.phi_ky_omega).T)# normalized, can be compared to linear frequency
    # contourf(casek.ky_omega_grid, casek.omega_ky_grid, abs(mean(phi_ky_omega_arr**2,axis=0)).T)# normalized, can be compared to linear frequency
    phi_ky_omega_arr_ave=abs(mean(phi_ky_omega_arr, axis=0)).T
    phi_ky_omega_arr_norm=phi_ky_omega_arr_ave/amax(phi_ky_omega_arr_ave,axis=0)
    #phi_ky_omega_arr_norm=phi_ky_omega_arr_ave/amax(phi_ky_omega_arr_ave)
#    contourf(casek.ky_omega_grid, casek.omega_ky_grid,phi_ky_omega_arr_norm ,\
    contourf(ky_omega_grid_isplit0, -omega_ky_grid_isplit0, phi_ky_omega_arr_norm ,\
            locator=ticker.LogLocator(),levels=logspace(-2,0,21))# normalized, can be compared to linear frequency
#              levels=linspace(0,1,21))# normalized, can be compared to linear frequency
    if icgyro==1:
        print(freqsign*casek.freq_n)
        plot(casek.ky,freqsign*casek.freq_n,'-k',linewidth=lw*2,label='mode averge(nonlin)')
    xlabel('$k_y\\rho_s$',fontsize=fs2,family='serif')
    ylabel('$\omega(c_s/a)$', fontsize=fs2, family='serif')
    if casek.n_theta_plot==1:
        ftheta_plot=0
    else:
        ftheta_plot=casek.ftheta_plot[i_theta_plot]/3.14
    title('$' + field_name[i_field] + '(\\theta=%.2f\pi)$' % ftheta_plot)
    xticks(fontsize=fs2)
    yticks(fontsize=fs2)
#    plot the linear frequency
    if casename in freq_lin.keys():
        casek_lin=case_plot[k_case]
        plot(freq_lin[casek_lin]['ky'],array(freqsign)*freq_lin[casek_lin]['omega'],'--k',linewidth=lw*1.5,label='lin')
            # freq_linn=interp(casek.ky[i_n],freq_lin[casek_lin]['ky'],freqsign*freq_lin[casek_lin]['omega'])
            # freq_linn_adia = interp(casek.ky[i_n],freq_lin['adiabatic']['ky'], freqsign * freq_lin['adiabatic']['omega'])
        # casek.get_freq_n()
        # plot(casek.ky, freqsign*casek.freq_n, '--r', linewidth=lw*1.5, label='nonlin(df/dt)')
        # plot(casek.ky, casek.omega_n, '--m', linewidth=lw * 1.5, label='$<\omega>_{\phi}$')
        # plot(casek.ky, freqsign*mean(freq_n_arr,axis=0), '--r', linewidth=lw*1.5, label='nonlin(df/dt)')
        # plot(casek.ky, mean(omega_n_arr,axis=0), '--m', linewidth=lw * 1.5, label='$<\omega>_{\phi}$')
        xlim([casek.ky[0],casek.ky[-1]])
        legend(loc=0,fontsize=fs2).draggable(True)
    subplot(122)
    phi_ky_omega_kx0_arr_ave=abs(mean(phi_ky_omega_kx0_arr, axis=0)).T
    phi_ky_omega_kx0_arr_norm=phi_ky_omega_kx0_arr_ave/amax(phi_ky_omega_kx0_arr_ave,axis=0)
    # contourf(casek.ky_omega_grid, casek.omega_ky_grid, abs(mean(phi_ky_omega_kx0_arr,axis=0)).T, \
#    contourf(casek.ky_omega_grid, casek.omega_ky_grid, phi_ky_omega_kx0_arr_norm,\
    contourf(ky_omega_grid_isplit0, -omega_ky_grid_isplit0, phi_ky_omega_kx0_arr_norm,\
             locator=ticker.LogLocator(), levels=logspace(-2, 0, 21))
    #if icgyro==1:
        #plot(casek.ky,freqsign*casek.freq_n,'-k',linewidth=lw*2,label='mode averge(nonlin)')
    xlabel('$k_y\\rho_s$',fontsize=fs2,family='serif')
    ylabel('$\omega(c_s/a)$', fontsize=fs2, family='serif')
#    ftheta_plot=casek.ftheta_plot[i_theta_plot]/3.14
    title('$'+field_name[i_field]+'(\\theta=%.2f\pi,k_x=0)$' % ftheta_plot)
    xticks(fontsize=fs2)
    yticks(fontsize=fs2)
    if icgyro==1:
        if casename in freq_lin.keys():
            casek_lin=case_plot[k_case]
            plot(freq_lin[casek_lin]['ky'],array(freqsign)*freq_lin[casek_lin]['omega'],'--k',linewidth=lw*1.5,label='lin')
            # plot(freq_lin['adiabatic']['ky'], freqsign * freq_lin['adiabatic']['omega'], '-k', linewidth=lw * 1.5, label='lin-adia')
            # freq_linn=interp(casek.ky[i_n],freq_lin[casek_lin]['ky'],freqsign*freq_lin[casek_lin]['omega'])
        # casek.get_freq_n()
        # plot(casek.ky, freqsign*casek.freq_n, '--r', linewidth=lw*1.5, label='nonlin(df/dt)')
        # plot(casek.ky, casek.omega_n, '--m', linewidth=lw * 1.5, label='$<\omega>_{\phi}$')
        # plot(casek.ky, freqsign*mean(freq_n_arr,axis=0), '--r', linewidth=lw*1.5, label='nonlin(df/dt)')
        # plot(casek.ky, mean(omega_n_arr,axis=0), '--m', linewidth=lw * 1.5, label='$<\omega>_{\phi}$')
    xlim([casek.ky[0],casek.ky[-1]])
    legend(loc=0,fontsize=fs2).draggable(True)
    # subplot(232)
    # # contourf(casek.ftheta_omega_grid/pi, casek.omega_ftheta_grid, abs(casek.phi_ithetaplot_omega).T)  # the phi_ithetaplot_omega will not be normalized to show the different intensity
    # contourf(casek.ftheta_omega_grid/pi, casek.omega_ftheta_grid, abs(mean(phi_ithetaplot_omega_arr,axis=0)).T)  # the phi_ithetaplot_omega will not be normalized to show the different intensity
    # # plot(array([-1,1]),freqsign*array([casek.freq_n[i_n].data,casek.freq_n[i_n].data]),'--r',linewidth=lw*1.5,label='nonlin(df/dt)')
    # # plot(array([-1, 1]), array([freq_linn_adia, freq_linn_adia]), '-k', linewidth=lw * 1.5, label='lin-adia')
    # if casename in freq_lin.keys():
    #     plot(array([-1, 1]), array([freq_linn,freq_linn]), '--k', linewidth=lw * 1.5,label='lin')
    # xlabel('$\\theta(\pi)$',fontsize=fs2,family='serif')
    # # ylabel('$\omega(c_s/a)$', fontsize=fs2, family='serif')
    # title('$\phi(k_y\\rho_s=%.2f)$' % casek.ky[i_n])
    # # print(casek.freq_n[i_n].data)
    # xticks(fontsize=fs2)
    # yticks(fontsize=fs2)
    # subplot(233)
    # # contourf(casek.kx_omega_grid, casek.omega_kx_grid, abs(casek.phi_kx_omega).T)
    # contourf(casek.kx_omega_grid, casek.omega_kx_grid, abs(mean(phi_kx_omega_arr,axis=0)).T,\
    #     locator = ticker.LogLocator(), levels = logspace(-3.5, -1.5, 11))
    # colorbar()
    # # plot(array([casek.kx[0], casek.kx[-1]]), array([freq_linn_adia, freq_linn_adia]), '-k', linewidth=lw * 1.5, label='lin-adia')
    # # plot(array([casek.kx[0], casek.kx[-1]]), array([freq_linn, freq_linn]), '--k', linewidth=lw * 1.5,label='lin-adia')
    # xlabel('$k_x\\rho_s$',fontsize=fs2,family='serif')
    # title('$\phi(k_y\\rho_s=%.2f,\\theta=%.2f\pi)$' % (casek.ky[i_n],ftheta_plot))
    # # print(casek.freq_n[i_n].data)
    # xticks(fontsize=fs2)
    # yticks(fontsize=fs2)
    # subplot(235)
    # contourf(casek.ftheta_omega_grid/pi, casek.omega_ftheta_grid, abs(mean(phi_ithetaplot_omega_kx0_arr,axis=0)).T,\
    #          locator=ticker.LogLocator(),levels=logspace(-3.5,-1.5,11))
    # colorbar()
    # # plot(array([-1,1]),freqsign*array([casek.freq_n[i_n].data,casek.freq_n[i_n].data]),'--r',linewidth=lw*1.5,label='nonlin(df/dt)')
    # # plot(array([-1, 1]), array([freq_linn_adia, freq_linn_adia]), '-k', linewidth=lw * 1.5, label='lin-adia')
    # if casename in freq_lin.keys():
    #     plot(array([-1, 1]), array([freq_linn,freq_linn]), '--k', linewidth=lw * 1.5,label='lin')
    # xlabel('$\\theta(\pi)$',fontsize=fs2,family='serif')
    # # ylabel('$\omega(c_s/a)$', fontsize=fs2, family='serif')
    # title('$\phi(k_y\\rho_s=%.2f,k_x=0)$' % casek.ky[i_n])
    # # print(casek.freq_n[i_n].data)
    # xticks(fontsize=fs2)
    # yticks(fontsize=fs2)


root['SETTINGS']['PLOTS']['nl']['t_ave']=t_ave_orig
root['SETTINGS']['PLOTS']['nl']['t_end']=t_end_orig
