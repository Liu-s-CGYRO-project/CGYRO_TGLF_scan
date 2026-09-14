# plot the eigenfunction average parameters for 1d scan
from OMFITlib_cgyro_read import *
with open(root['PLOTS']['CGYROscan']['assist']['getglobal.py'].filename, 'r') as _helper_source:
    exec(compile(_helper_source.read(), _helper_source.name, 'exec'), globals())
if setup['icgyro']==1:
    root['PLOTS']['CGYROscan']['assist']['collect.py'].run()
else:
    root['PLOTS']['CGYROscan']['assist']['collect_gyro.py'].run()

nRange_eigen=len(para_eigen)
num_ky_eigen=len(ky_eigen)
flux_lin_arr=zeros([nRange_eigen,num_ky_eigen])
k_perp_squal_arr=zeros([nRange_eigen,num_ky_eigen])
gamma_arr=zeros([nRange_eigen,num_ky_eigen])
theta_width_arr=zeros([nRange_eigen,num_ky_eigen])

# para_name
if Para in Paraname_dic.keys():
    plots['Para_label']=Paraname_dic[Para]
else:
    plots['Para_label']=Para
#
for k in range(0,nRange_eigen):
    for p in range(num_ky_eigen):
        dirname = Para + '_' + num2str_xj(para_eigen[k], effnum) + '~ky_' + num2str_xj(ky_eigen[p], effnum)
        datanode = mounttree[dirname]
        datanode.get_flux_lin()
        flux_lin_arr[k][p]=datanode.flux_lin
        k_perp_squal_arr[k][p]=datanode.k_perp_squal_ave
        gamma_arr[k][p]=datanode.gamma
        theta_width_arr[k][p]=datanode.theta_width

########################################
# based on the profiles we get, then all the linear information can be plotted
figure('Flux Estimated From Linear Calculation',figsize=[16,9])
avearr=['flux_lin_arr','theta_width_arr','gamma_arr','k_perp_squal_arr']
unitarr=[' ','(rad)','(cs/a)','']
titlearr=['$Q=\\theta_{width}*\gamma/k_{perp}^2$','$\\theta_{width}$','$\gamma$','$k_{\perp}^2$']
if idimplt==0:
    for p in arange(1,5):
        axp=subplot(1,4,p)
        for k in range(0,nRange_eigen):
            cmd='plot(ky_eigen,'+avearr[p-1]+'[k],lab[k],linewidth=lw+1,label=num2str_xj(para_eigen[k],effnum))'
            exec(cmd)
        xlim([0.8 * min(ky_eigen), 1.2 * max(ky_eigen)])
        legend(loc=0,fontsize=fs2)
        xticks(fontsize=fs2)
        yticks(fontsize=fs2)
        axp.set_xscale(scale_dic[ilogx])
        axp.set_yscale(scale_dic[ilogy])
        title(titlearr[p-1]+unitarr[p-1],fontsize=fs1)
        xlabel('$k_y\\rho_s$',fontsize=fs2,family='serif')
else:
    for p in arange(1,5):
        axp = subplot(1, 4, p)
        for k in range(0,num_ky_eigen):
            cmd = 'plot(para_eigen,' + avearr[p - 1] + '.T[k],lab[k],linewidth=lw+1,label=num2str_xj(ky_eigen[k],effnum))'
            exec (cmd)
        legend(loc=0, fontsize=fs2)
        xlim([0.8 * min(para_eigen), 1.2 * max(para_eigen)])
        xticks(fontsize=fs2)
        yticks(fontsize=fs2)
        axp.set_xscale(scale_dic[ilogx])
        axp.set_yscale(scale_dic[ilogy])
        xlabel(Para, fontsize=fs2, family='serif')
        title(titlearr[p - 1] + unitarr[p - 1], fontsize=fs1)
