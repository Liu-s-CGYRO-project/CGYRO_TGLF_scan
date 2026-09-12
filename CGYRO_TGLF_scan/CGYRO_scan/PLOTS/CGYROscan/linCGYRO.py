# this script is used to plot the eigenfrequency and growth rate for all the scanning cases,
# the parameters and the value is specified in root['SETTINGS']['PLOTS']['Para'] and root['SETTINGS']['PLOTS']['Range']
# note the stability analyis should be performed by GYRO before running this plot scrip
# first we should define a function to read the date of out.gyro.freq, which contains the frequency and growth rate
import numpy as np
import sys
#sys.path.append('/gpfs/scratch/liujy/OMFIT/mymodule/CGYRO_SCAN/PLOTS/CGYROscan/assist')
from cgyro_read_xj import *
f = open(root['PLOTS']['CGYROscan']['assist']['getglobal.py'].filename, 'r')
for line in f:
    exec(line)
f.close()
# define the function for fit
if ifit_mthd==1:
    def f_1(x,A,C):
        return A*x+C
elif ifit_mthd==2:
    def f_1(x,A,C):
        return A*x*x+C
else:
    def f_1(x,A,B,C):
        return A*x*x+B*x+C
csda=plots['csda']
unit_flag=plots['unit_flag']
w_arr=zeros([nRange,num_ky])     # dominate mode frequency
err_w_arr=zeros([nRange,num_ky])     # error in dominate mode frequency
gamma_arr=zeros([nRange,num_ky]) # dominate mode growth rate
err_gamma_arr=zeros([nRange,num_ky]) # error in dominate mode growth rate
icgyro=setup['icgyro']
# idebug=0 # 0: output the meanless default when encouter error; 1: stop and raise the error up
if icgyro==1:
    inputcgyro=root['INPUTS']['input.cgyro']
else:
    inputcgyro=root['INPUTS']['input.gyro']
# paraval_orig=inputcgyro[plt1d['Para']]
if 'GAMMA_E' in inputcgyro.keys():
    gamma_e=abs(inputcgyro['GAMMA_E'])
#    print(gamma_e)
else:
    gamma_e=0
# para_name
if Para in Paraname_dic.keys():
    plots['Para_label']=Paraname_dic[Para]
else:
    plots['Para_label']=Para

for k in range(0,nRange):
    for p in range(num_ky):
        datanode=root['OUTPUTScan'][Para][num2str_xj(Range[k],effnum)]['lin'][num2str_xj(kyarr[p],effnum)]
        # try:
        filename=datanode
        flag_read=1
        w, err_w = readfreq(filename,flag_read)
        # except:
        #     w=array([0,0])
        #     err_w=array([1,1])
        # else:
        #     if not isinstance(datanode, OMFITcgyro):
        #         filename = datanode['out.cgyro.freq'].filename
        #         flag_read=0
        #     else:
        #         filename = datanode
        #         flag_read = 1
        #     w, err_w = readfreq(filename,flag_read)
        if unit_flag==1:    # do the normalization from cs/a to omega_a
            if setup['icgyro']==1:
                inputcgyrogen=datanode['input.cgyro.gen']
                betae=inputcgyrogen['BETAE_UNIT']
                q = inputcgyrogen['Q']
                Rmaj=inputcgyro['RMAJ']
                nimisum=sum([inputcgyrogen['MASS_'+str(p)]*inputcgyrogen['DENS_'+str(p)] for p in arange(1,inputcgyrogen['N_SPECIES'])])
            else:
                inputgyrogen = datanode['input.gyro.gen']
                betae = inputgyrogen['BETAE_UNIT']
                q = inputgyrogen['SAFETY_FACTOR']
                Rmaj = inputgyro['ASPECT_RATIO']
                n_ion=len(datanode['tagspec'])
                nimisum = inputgyrogen['NI_OVER_NE' + str(p)] / inputgyrogen['MU_' + str(p)] ** 2
                if n_ion>1:
                    nimisum=nimisum+sum([inputgyrogen['NI_OVER_NE' + str(p)] / inputgyrogen['MU_' + str(p)] ** 2 for p in arange(2, n_ion+1)])
            omega_a_to_cs = sqrt(2 / betae / nimisum) / q / Rmaj
            print('omega_a/cs_a=%7.2f'%omega_a_to_cs)
            w=w/omega_a_to_cs
            ipltExB=0
        if not np.all(np.isfinite(w)):
            raise ValueError('Nonfinite frequency or growth rate at %s=%s, ky=%s' % (Para, Range[k], kyarr[p]))
        if ibelow0[0]==1:
            if w[1]<ibelow0[1]:
                w[1]=ibelow0[1]
        # if w<ibelow0, then change w to ibelow0, the ibelow 0 is -0.1
        if ilim_err[0]==1:
            if err_w[1]>ilim_err[1]:
                w[1]=ibelow0[1]
        w_arr[k][p]=w[0]
        gamma_arr[k][p]=w[1]
        err_w_arr[k][p]=err_w[0]
        err_gamma_arr[k][p]=err_w[1]
########################################
# based on the profiles we get, then all the linear information can be plotted
figure('micro-turbulence linear stability property',figsize=[16,9])
if csda[0]==1:
    w_arr=w_arr*csda[1]
    gamma_arr=gamma_arr*csda[1]
gamma_max=amax(gamma_arr/kyarr**powky)
omega_dic={0:'$\omega$',1:'$\omega/ky$'}
gamma_dic={0:'$\gamma$',1:'$\gamma/ky$'}
freqarr=['w_arr','err_w_arr','gamma_arr','err_gamma_arr']
if icgyro==0:
    BunitOverBt=inputcgyro['KAPPA']*(1+inputcgyro['S_KAPPA']/2.-0.5*inputcgyro['SHIFT']*inputcgyro['RADIUS']/inputcgyro['ASPECT_RATIO'])
    v_dia=inputcgyro['DLNNDR_ELECTRON']+inputcgyro['DLNTDR_ELECTRON']
else:
    BunitOverBt = inputcgyro['KAPPA'] * (1 + inputcgyro['S_KAPPA'] / 2. - 0.5 * inputcgyro['SHIFT'] * inputcgyro['RMIN'] / inputcgyro['RMAJ'])
    ns=inputcgyro['N_SPECIES']
    v_dia=inputcgyro['DLNNDR_'+str(ns)]+inputcgyro['DLNTDR_'+str(ns)]
iplotw_dia=0  # plot the electron diamagnetic frequency
if idimplt==0:
    ax1=subplot(2,2,1)
    axp=ax1
    for p in arange(1,5):
        if p>1:
            axp=subplot(2,2,p,sharex=ax1)
        for k in range(0,nRange):
            cmd='axp.plot(kyarr,'+freqarr[p-1]+'[k]/kyarr**powky,lab[k],linewidth=lw+1,label=Para'+"+'='+"+'num2str_xj(Range[k],effnum))'
            #cmd='axp.plot(kyarr,'+freqarr[p-1]+'[k],lab[k],linewidth=lw+1,label=num2str_xj(Range[k],effnum))'
            exec(cmd)
            print(w_arr[k])

            # plot the diamgentic frequency
            if p==3 and iplotw_dia==1:
                plot(kyarr,kyarr*v_dia/kyarr**powky,'--k',linewidth=lw/2)
                plot(kyarr, BunitOverBt*kyarr * v_dia/kyarr**powky, '--k', linewidth=lw / 2)
        xlim([0.8*min(kyarr),1.2*max(kyarr)])

        plt.rc('font',family='Times New Roman')
        xticks(fontsize=fs2)
        yticks(fontsize=fs2)

        axp.set_xscale(scale_dic[ilogx])
        axp.set_yscale(scale_dic[ilogy])

        axp.spines['bottom'].set_linewidth(bwith)
        axp.spines['left'].set_linewidth(bwith)
        axp.spines['top'].set_linewidth(bwith)
        axp.spines['right'].set_linewidth(bwith)

        if unit_flag==1:
            title(freqarr[p-1]+'$(\omega_A)$',fontsize=fs1)
        else:
            if p==2 or p==4:
                title(freqarr[p-1]+'$(c_s/a)$'+'(relative)' , fontsize=fs1)
            else:
                title(freqarr[p-1]+'$(c_s/a)$' , fontsize=fs1)
        if p==1:
            axp.set_ylabel(omega_dic[powky],fontdict={'family' : 'Times New Roman', 'size':fs1},labelpad=5)
        if p==3:
            legend(loc='best',fontsize=fs2).set_draggable(True)
#            plot(array([min(kyarr),max(kyarr)]),array([0,0]),'--r',linewidth=lw)
            axp.set_ylabel(gamma_dic[powky],fontdict={'family' : 'Times New Roman', 'size':fs1},labelpad=5)
            if ipltExB == 1:
                # print(gamma_e)
                plot(kyarr,gamma_e*ones(len(kyarr))/kyarr**powky,'--r',linewidth=lw)
                text(kyarr[int(len(kyarr)/2.)],gamma_e*1.1/kyarr[int(len(kyarr)/2.)],'$\gamma_E$',fontsize=fs1,color='r')
        if p==3 or p==4:
            axp.set_xlabel('$k_y$*$\\rho_s$',fontdict={'family' : 'Times New Roman', 'size':fs1},labelpad=5)
        if p==2 or p==4:
            axp.set_yscale('log')
else:
    ax1=subplot(2,2,1)
    for k in range(0,num_ky):
        ax1.plot(Range,w_arr.T[k]/kyarr[k]**powky,lab[k],linewidth=lw+1,label=num2str_xj(kyarr[k],effnum))
    ax1.set_xscale(scale_dic[ilogx])
    plot(array([min(Range),max(Range)]),array([0,0]),'--r',linewidth=lw)
    plt.axvline(x=inputcgyro[Para],color='r', linestyle='--')
    legend(loc=1,fontsize=fs2).set_draggable(True)
    xlim([0.8*min(Range),1.2*max(Range)])
    xticks(fontsize=fs2)
    yticks(fontsize=fs2)
#    ylabel('$\omega/ky**$'+str(powky),fontsize=fs1)
    ylabel(omega_dic[powky],fontsize=fs1)
    if unit_flag == 1:
        title('$\omega(omega_A)$',fontdict={'family' : 'Times New Roman', 'size':fs1})
    else:
        title('$\omega(c_s/a)$',fontdict={'family' : 'Times New Roman', 'size':fs1})
    ax3=subplot(2,2,3,sharex=ax1)
    C_avg=0.
    for k in range(0,num_ky):
        ax3.plot(Range, gamma_arr.T[k] / kyarr[k] ** powky, lab[k], linewidth=lw + 1, label=num2str_xj(kyarr[k], effnum))
#     for p in ind_kyfit:
#         gamma_temp=gamma_arr.T[p]/kyarr[k]**powky
#         gamma_temp_rev=gamma_temp[::-1]
#         dg=diff(gamma_temp_rev)
#         if len(dg[dg>0])!=0:
#             # ind_begin=find(diff(gamma_temp_rev)>0)[0]+1
#             ind_begin=where(dg>0)[0][0]+1
#         else:
#             ind_begin=len(gamma_temp)
# #            print(ind_begin)
# #            A,B=optimize.curve_fit(f_1,gamma_arr.T[k][-1*ind_begin:],Range[-1*ind_begin:])[0]
# #            A,B,C=optimize.curve_fit(f_1,gamma_arr.T[k][-1*ind_begin:],Range[-1*ind_begin:])[0]
#         y1=linspace(0,gamma_arr.T[p][-1],36)
#         if ifit_mthd==1:
#             A,C=optimize.curve_fit(f_1,gamma_arr.T[p][-1*ind_begin:],Range[-1*ind_begin:])[0]
#             x1=A*y1+C
#         elif ifit_mthd==2:
#             A,C=optimize.curve_fit(f_1,gamma_arr.T[p][-1*ind_begin:],Range[-1*ind_begin:])[0]
#             x1=A*y1*y1+C
#         else:
#             A,B,C=optimize.curve_fit(f_1,gamma_arr.T[p][-1*ind_begin:],Range[-1*ind_begin:])[0]
#             x1=A*y1*y1+B*y1+C
#         C_avg=C_avg+C/kyarr[p]
#         ax3.plot(x1,y1,lab[k],linewidth=lw)
#     ax3.set_xscale(scale_dic[ilogx])
#     ax3.set_yscale(scale_dic[ilogy])
#     legend(loc=1,fontsize=fs2).set_draggable(True)
#     if len(ind_kyfit)!=0:
#         C_avg=C_avg/sum([1./kyarr[kk] for kk in ind_kyfit])  #the weight is inverse proportional to ky
# #        text(C_avg*1./2,gamma_max*3./4,'$val_{crit}$=%.2f'%C_avg,fontsize=fs2)
#         text(C_avg*1./2,gamma_max*1./4,plots['Para_label']+'$_{,Crit}$=%.2f'%C_avg,fontsize=fs2,color='b')
    plot(array([min(Range),max(Range)]),array([0,0]),'--r',linewidth=lw)
    plt.axvline(x=inputcgyro[Para],color='r', linestyle='--')
    # text(paraval_orig*3./4,gamma_max,plots['Para_label']+'$_{,Exp}$=%.2f'%paraval_orig,fontsize=fs2,color='b')
    # plot(array([paraval_orig,paraval_orig]),array([3./4*gamma_max,gamma_max]),'--b',linewidth=lw/2)
    plot(array([C_avg,C_avg]),array([0,1./5*gamma_max]),'--b',linewidth=lw/2)
    #legend(loc=1,fontsize=fs2).set_draggable(True)
    xticks(fontsize=fs2)
    yticks(fontsize=fs2)
    xlim([0.8*min(Range),1.2*max(Range)])
    ylim([1.e-3,4./3*gamma_max])
    xlabel(root['SETTINGS']['PLOTS']['Para_label'],fontdict={'family' : 'Times New Roman', 'size':fs1},labelpad=5)
    ylabel(gamma_dic[powky],fontdict={'family' : 'Times New Roman', 'size':fs1},labelpad=5)
    if unit_flag == 1:
        title('$\gamma(omega_A)$', fontsize=fs1)
    else:
        title('$\gamma(c_s/a)$', fontsize=fs1)
    #plot the error of w and gamma
    ax2=subplot(2,2,2,sharex=ax1)
    for k in range(0,num_ky):
        ax2.semilogy(Range,err_w_arr.T[k],lab[k],linewidth=lw+1)
    ax2.set_yscale('log')
    ax2.set_xscale(scale_dic[ilogx])
    plot(array([min(Range),max(Range)]),array([1.e-4,1.e-4]),'--r',linewidth=lw)
    #legend(loc=1,fontsize=fs2).set_draggable(True)
    xlim([0.8*min(Range),1.2*max(Range)])
    xticks(fontsize=fs2)
    yticks(fontsize=fs2)
    title('$\omega_{err}$', fontsize=fs1)
    ylabel('$\omega_{err}$',fontdict={'family' : 'Times New Roman', 'size':fs1},labelpad=5)
    ax4=subplot(2,2,4,sharex=ax1)
    for k in range(0,num_ky):
        semilogy(Range,err_gamma_arr.T[k],lab[k],linewidth=lw+1)
    ax4.set_yscale('log')
    ax4.set_xscale(scale_dic[ilogx])
    plot(array([min(Range),max(Range)]),array([1.e-4,1.e-4]),'--r',linewidth=lw)
#    legend(loc=1,fontsize=fs2).set_draggable(True)
    xticks(fontsize=fs2)
    yticks(fontsize=fs2)
    xlim([0.8*min(Range),1.2*max(Range)])
    xlabel(root['SETTINGS']['PLOTS']['Para_label'],fontdict={'family' : 'Times New Roman', 'size':fs1},labelpad=5)
    title('$\gamma_{err}$', fontsize=fs1)
    ylabel('$\gamma_{err}$',fontdict={'family' : 'Times New Roman', 'size':fs1},labelpad=5)

    plt.rc('font',family='Times New Roman')
    xticks(fontsize=fs2)
    yticks(fontsize=fs2)

    ax1.set_xscale(scale_dic[ilogx])
    ax1.set_yscale(scale_dic[ilogy])

    ax1.spines['bottom'].set_linewidth(bwith)
    ax1.spines['left'].set_linewidth(bwith)
    ax1.spines['top'].set_linewidth(bwith)
    ax1.spines['right'].set_linewidth(bwith)

    ax2.set_xscale(scale_dic[ilogx])
    ax2.set_yscale(scale_dic[ilogy])

    ax2.spines['bottom'].set_linewidth(bwith)
    ax2.spines['left'].set_linewidth(bwith)
    ax2.spines['top'].set_linewidth(bwith)
    ax2.spines['right'].set_linewidth(bwith)

    ax3.set_xscale(scale_dic[ilogx])
    ax3.set_yscale(scale_dic[ilogy])

    ax3.spines['bottom'].set_linewidth(bwith)
    ax3.spines['left'].set_linewidth(bwith)
    ax3.spines['top'].set_linewidth(bwith)
    ax3.spines['right'].set_linewidth(bwith)

    ax4.set_xscale(scale_dic[ilogx])
    ax4.set_yscale(scale_dic[ilogy])

    ax4.spines['bottom'].set_linewidth(bwith)
    ax4.spines['left'].set_linewidth(bwith)
    ax4.spines['top'].set_linewidth(bwith)
    ax4.spines['right'].set_linewidth(bwith)




# # ===================================
iwritelin=root['SETTINGS']['PLOTS']['iwritelin']  # determine whether to write out to a file
num_ky=len(kyarr)
nmodes=1
if iwritelin==1 and 'linout' in root['SETTINGS']['DEPENDENCIES'].keys():
    eigenout=root['SETTINGS']['DEPENDENCIES']['linout']
    fid=open(eigenout,'w')
# first write the scanned parameter name into the file
    fid.write(Para)
    fid.write('\n')
# write the nRange and the para_val into the file
    fid.write(str(nRange))
    fid.write('\n')
    line=''
    for m in range(nRange):
        line=line+str(Range[m])+'    '
    fid.write(line)
    fid.write('\n')
# write nmodes into the file
    fid.write(str(nmodes)+'    '+str(num_ky))
    fid.write('\n')
    for k in range(num_ky):
        line=str(kyarr[k])
        for p in range(nRange):
#            line=line+'    '+str(w_arr[p][k])+'    '+str(gamma_arr[p][k])+'    '+str(err_w_arr[p][k])+'    '+str(err_gamma_arr[p][k])
            line=line+'    '+str(w_arr[p][k])+'    '+str(gamma_arr[p][k])
        fid.write(line)
        fid.write('\n')
    fid.close()
