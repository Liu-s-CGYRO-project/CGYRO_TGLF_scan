# this plot is used for theoretical KBM/BAE analysis
# theorectal basis, please refer to the https://docs.google.com/presentation/d/14ykhD2Om51SeFJmj9b97Ot4DgL5nfWbd/edit?usp=sharing&ouid=115141443709435661951&rtpof=true&sd=true
# in unit of cs/a
if not 'input.gacode' in root['INPUTS'].keys():
    raise Exception('input.gacode must exist')
# plot the kinetic profiles and profile gradient
inputpro=root['INPUTS']['input.gacode']
inputtgyro=root['INPUTS']['input.tgyro']
rho=inputpro['rho']
p_tgyro=len(inputtgyro['DIR'])
rho_sparse=linspace(inputtgyro['TGYRO_RMIN'],inputtgyro['TGYRO_RMAX'],p_tgyro)
lw=2
aLTe_sparse=zeros([p_tgyro])
aLne_sparse=zeros([p_tgyro])
aLTi_sparse=zeros([p_tgyro])
q_sparse=zeros([p_tgyro])
rmin_sparse=zeros([p_tgyro])
Rmaj_sparse=zeros([p_tgyro])
kappa_sparse=zeros([p_tgyro])
s_kappa_sparse=zeros([p_tgyro])
shift_sparse=zeros([p_tgyro])
betae_sparse=zeros([p_tgyro])
nimisum_sparse=zeros([p_tgyro]) # sum of n_i*m_i, for calculation of alfven frequency
nu_sparse=zeros([p_tgyro])
zeff_sparse=zeros([p_tgyro])
TioverTe_sparse=zeros([p_tgyro])
TfoverTe_sparse=zeros([p_tgyro])  # T_fast/Te
niaLnaLTi_sparse=zeros([p_tgyro])  # ni*Ti*(aLTi+aLni)
niaLnaLTf_sparse=zeros([p_tgyro])  # fast ion
tglfout=root['OUTPUTS']['Profiles_gen_D']
for k in range(1,p_tgyro+1):
    inputtglf_k=tglfout['input.tglf_'+str(k)]
    ns=inputtglf_k['NS']
    aLTi_sparse[k - 1] = inputtglf_k['RLTS_2']
    aLTe_sparse[k-1]=inputtglf_k['RLTS_1']
    aLne_sparse[k-1]=inputtglf_k['RLNS_1']
    q_sparse[k-1]=inputtglf_k['Q_LOC']
    rmin_sparse[k-1]=inputtglf_k['RMIN_LOC']
    kappa_sparse[k-1]=inputtglf_k['KAPPA_LOC']
    s_kappa_sparse[k-1]=inputtglf_k['S_KAPPA_LOC']
    Rmaj_sparse[k-1]=inputtglf_k['RMAJ_LOC']
    shift_sparse[k - 1] = inputtglf_k['DRMAJDX_LOC']
    betae_sparse[k - 1] = inputtglf_k['BETAE']
    nimisum_sparse[k-1] = sum([inputtglf_k['MASS_'+str(p)]*inputtglf_k['AS_'+str(p)] for p in arange(1,inputtglf_k['NS']+1)])
    niaLnaLTi_sparse[k-1]=sum([inputtglf_k['AS_'+str(p)]*inputtglf_k['TAUS_'+str(p)]*(inputtglf_k['RLNS_'+str(p)]+inputtglf_k['RLTS_'+str(p)]) for p in arange(2,ns)])
    niaLnaLTf_sparse[k - 1] = inputtglf_k['AS_' + str(ns)] * inputtglf_k['TAUS_' + str(ns)] * (inputtglf_k['RLNS_' + str(ns)] + inputtglf_k['RLTS_' + str(ns)])
    nu_sparse[k-1]=inputtglf_k['XNUE']
    zeff_sparse[k - 1] = inputtglf_k['ZEFF']
    TioverTe_sparse[k - 1] = inputtglf_k['TAUS_2']
    TfoverTe_sparse[k - 1] = inputtglf_k['TAUS_'+str(inputtglf_k['NS'])]
# dimension paramter calculation, in unit of cs/a
omega_ti=1./q_sparse/Rmaj_sparse*sqrt(2*TioverTe_sparse)
omega_tf=1./q_sparse/Rmaj_sparse*sqrt(2*TfoverTe_sparse)
kyrhos_test=0.27
kyrhos_exp=0.27
omega_star_ni=kyrhos_test*aLne_sparse
#omega_star_pi=kyrhos_test*(aLne_sparse+aLTi_sparse)
omega_star_pi=kyrhos_test*niaLnaLTi_sparse
omega_star_pf=kyrhos_test*niaLnaLTf_sparse
omega_GAM=q_sparse*(sqrt(7./4+1./TioverTe_sparse))*sqrt((1+1./2/q_sparse**2)*(2./(kappa_sparse**2+1)))*omega_ti  # omeg
omega_pi_BAE=omega_star_pi*omega_GAM/omega_ti/omega_ti  # this should be compared to 1, if >1, should be unstable
#kyrhos_maxdrive=omega_GAM/(aLne_sparse+aLTi_sparse)     # the kyrhos_max should be most unstable since under such a kyrhos, the BAE and KBM are most efficiently coupled
kyrhos_maxdrive=omega_GAM/niaLnaLTi_sparse     # the kyrhos_max should be most unstable since under such a kyrhos, the BAE and KBM are most efficiently coupled
omega_star_pi_maxdrive=kyrhos_maxdrive*(aLne_sparse+aLTi_sparse)/omega_ti/omega_ti
# get max drive n
rhosunit_over_a=interp(rho_sparse,rho,inputpro['rhos'])/inputpro['rmin'][-1]
n_maxdrive=kyrhos_maxdrive/rhosunit_over_a*rmin_sparse/q_sparse  #n value for a given kyrhos
figure(figsize=[18,12])
print(omega_GAM)
lab=['-bo','-ro','-ko','-mo']
fs1=24
fs2=20
fs3=16
rct1=[0.1,0.1,0.2,0.35]
rct2=[0.4,0.1,0.2,0.35]
rct3=[0.7,0.1,0.2,0.35]
rct4=[0.1,0.6,0.2,0.35]
rct5=[0.4,0.6,0.2,0.35]
rct6=[0.7,0.6,0.2,0.35]
ax1=plt.axes(rct1)
plot(rho_sparse,omega_ti,'-ko',linewidth=lw,label='$\\omega_{ti}(c_s/a)$')
plot(rho_sparse,1*q_sparse/rmin_sparse*rhosunit_over_a*niaLnaLTi_sparse,'-bo',linewidth=lw,label='$\\omega_{*pi}(n=1)$')
legend(loc=0,fontsize=fs2).draggable(True)
xlabel('$\\rho$',fontsize=fs1,family='serif')
title('resonance condition',fontsize=fs1,family='serif')
xticks(fontsize=fs1,family='serif')
#xticks(linspace(0.2,0.8,4),fontsize=fs1,family='serif')
yticks(fontsize=fs1,family='serif')
#subplot(132)
ax2=plt.axes(rct2)
plot(rho_sparse, omega_GAM, '-go', linewidth=lw ,label='$\omega_{GAM}$')
plot(rho_sparse, omega_star_pi, '-ko', linewidth=lw,label='$\omega_{*,pi}$')
#plot(rho_sparse, omega_star_pf, '-bo', linewidth=lw,label='$\omega_{*,pf}$')
legend(loc=0,fontsize=fs3).draggable(True)
xlabel('$\\rho$',fontsize=fs1,family='serif')
ylabel('$\\omega(c_s/a)(k_y\\rho_s='+str(kyrhos_test)+')$',fontsize=fs1,family='serif')
xticks(fontsize=fs1,family='serif')
#xticks(linspace(0.2,0.8,4),fontsize=fs1,family='serif')
yticks(fontsize=fs1,family='serif')
ax3=plt.axes(rct3)
ax3.plot(rho_sparse,kyrhos_maxdrive,'-ko',linewidth=lw)
print(kyrhos_maxdrive)

ax3.plot(rho_sparse,kyrhos_test*ones(len(rho_sparse)),'--g',linewidth=lw/2)
ax3.plot(rho_sparse,kyrhos_exp*ones(len(rho_sparse)),'--g',linewidth=lw/2)
legend(loc=0,fontsize=fs3).draggable(True)
ax3.set_ylabel('$k_y\\rho_s$',fontsize=fs1,family='serif')
xticks(fontsize=fs1,family='serif')
yticks(fontsize=fs1,family='serif')
ax32=ax3.twinx()
ax32.plot(rho_sparse,n_maxdrive,'-rd',linewidth=lw)
ax32.set_ylabel('$n$',fontsize=fs1,family='serif',color='r')
title('Most Unstable',fontsize=fs1)
xticks(fontsize=fs1,family='serif')
yticks(fontsize=fs1,family='serif',color='r')

ax5=plt.axes(rct5)
plot(rho_sparse,omega_pi_BAE,'-ko',linewidth=lw)
plot(rho_sparse,ones(len(rho_sparse)),'--k',linewidth=lw/2)
legend(loc=0,fontsize=fs3).draggable(True)
# xlabel('$\\rho$',fontsize=fs1,family='serif')
title('$\\Omega_{*,pi}*\Omega_{BAE} (k_y\\rho_s='+str(kyrhos_test)+')$')
xticks(fontsize=fs1,family='serif')
yticks(fontsize=fs1,family='serif')
ax6=plt.axes(rct6)
plot(rho_sparse,omega_star_pi_maxdrive,'-ko',linewidth=lw)
plot(rho_sparse,ones(len(rho_sparse)),'--k',linewidth=lw/2)
legend(loc=0,fontsize=fs3).draggable(True)
title('$\\Omega_{*,pi}*\\Omega_{BAE} (max drive)$')
xticks(fontsize=fs1,family='serif')
yticks(fontsize=fs1,family='serif')
