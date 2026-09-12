# this script is used to read the fast ions from the input.gacode
# with the fast ions density and it's pressure, specifically,compared with the electron density and total pressure
inputpro=root['INPUTS']['input.gacode']
inputtgyro=root['INPUTS']['input.tgyro']
rho=inputpro['rho']
p_tgyro=len(inputtgyro['DIR'])
rho_sparse=linspace(inputtgyro['TGYRO_RMIN'],inputtgyro['TGYRO_RMAX'],p_tgyro)
n_ion=inputpro['N_ION']
n_exp=inputpro['N_EXP']
denpro=zeros([n_ion+1,n_exp])
tempro=zeros([n_ion+1,n_exp])
denpro[0]=inputpro['ne']
tempro[0]=inputpro['Te']
aLTe_sparse=zeros([p_tgyro])
aLne_sparse=zeros([p_tgyro])
aLTf_sparse=zeros([p_tgyro])
aLnf_sparse=zeros([p_tgyro])
aLpe_sparse=zeros([p_tgyro]) # electron pressure gradient,
aLpf_sparse=zeros([p_tgyro]) # fast pressure gradient
beta_e_sparse=zeros([p_tgyro])
beta_f_sparse=zeros([p_tgyro])
for k in arange(n_ion)+1:
    denpro[k]=inputpro['ni_'+str(k)]
    tempro[k]=inputpro['Ti_'+str(k)]
# tglfout=root['OUTPUTS']['TGYRO']['TGLF']
for k in range(1,p_tgyro+1):
    inputtglf_k=root['OUTPUTS']['Profiles_gen']['input.tglf_'+str(k)]
    aLTe_sparse[k-1]=inputtglf_k['RLTS_1']
    aLne_sparse[k-1]=inputtglf_k['RLNS_1']
    aLTf_sparse[k-1]=inputtglf_k['RLTS_'+str(n_ion+1)]
    aLnf_sparse[k-1]=inputtglf_k['RLNS_'+str(n_ion+1)]
    beta_e_sparse[k-1]=inputtglf_k['BETAE']
    beta_f_sparse[k-1]=beta_e_sparse[k-1]*inputtglf_k['AS_'+str(n_ion+1)]*inputtglf_k['TAUS_'+str(n_ion+1)]
    aLpe_sparse[k-1]=beta_e_sparse[k-1]*(inputtglf_k['RLNS_1']+inputtglf_k['RLTS_1'])
    aLpf_sparse[k - 1] = beta_f_sparse[k - 1] * (inputtglf_k['RLNS_'+str(n_ion+1)] + inputtglf_k['RLTS_'+str(n_ion+1)])
# the last ions species is treated to be fast ions by default
ntpro=sum(denpro*tempro,0)  # the profile of n*T sumed over all species
ntfastpro=denpro[n_ion]*tempro[n_ion]
pres=inputpro['ptot']
pres_fast=pres*ntfastpro/ntpro
# start to plot
rho=inputpro['rho']
fs1=24
fs2=20
figure('fast ions info',figsize=[12,8])
subplot(2,4,1)
plot(rho,inputpro['ne'],'-b',linewidth=2,label='ne')
plot(rho,10*inputpro['ni_'+str(n_ion)],'-r',linewidth=2,label='10*$n_{fast}$')
plot(rho,-1*inputpro['q'],'-k',linewidth=2,label='$q$')
xticks(fontsize=fs2,family='serif')
yticks(fontsize=fs2,family='serif')
ylim(0,10)
# title('',fontsize=fs1,family='serif')
# title('$density(10^{19}m^{-3}$)',fontsize=fs2,family='serif')
# xlabel('$\\rho$',fontsize=fs2,family='serif')
legend(loc=0,fontsize=fs2).draggable(True)
subplot(2,4,5)
plot(rho_sparse,aLne_sparse,'-bo',linewidth=2,label='$a/L_{ne}$')
plot(rho_sparse,aLnf_sparse,'-ro',linewidth=2,label='$a/L_{nf}$')
xticks(fontsize=fs2,family='serif')
yticks(fontsize=fs2,family='serif')
xlim([0,1])
# title('density',fontsize=fs1,family='serif')
# ylabel('$10^19m^{-3}$',fontsize=fs2,family='serif')
xlabel('$\\rho$',fontsize=fs2,family='serif')
legend(loc=0,fontsize=fs2).draggable(True)
subplot(2,4,2)
plot(rho,inputpro['Te'],'-b',linewidth=2,label='$T_e$')
plot(rho,inputpro['Ti_'+str(n_ion)]/10,'-r',linewidth=2,label='$T_f/10$')
plot(rho,inputpro['Ti_1'],'-k',linewidth=2,label='$T_i$')
xticks(fontsize=fs2,family='serif')
yticks(fontsize=fs2,family='serif')
title('Temperature(keV)',fontsize=fs1,family='serif')
# ylabel('$10^19m^{-3}$',fontsize=fs2,family='serif')
# xlabel('$\\rho$',fontsize=fs2,family='serif')
legend(loc=0,fontsize=fs2).draggable(True)
subplot(2,4,6)
plot(rho_sparse,aLTe_sparse,'-bo',linewidth=2,label='$a/L_{Te}$')
plot(rho_sparse,aLTf_sparse,'-ro',linewidth=2,label='$a/L_{Tf}$')
xticks(fontsize=fs2,family='serif')
yticks(fontsize=fs2,family='serif')
xlim([0,1])
# title('density',fontsize=fs1,family='serif')
# ylabel('$10^19m^{-3}$',fontsize=fs2,family='serif')
xlabel('$\\rho$',fontsize=fs2,family='serif')
legend(loc=0,fontsize=fs2).draggable(True)
subplot(2,4,3)
plot(rho,inputpro['ptot']/1.e3,'-b',linewidth=2,label='$p_{tot}$')
plot(rho,pres_fast/1.e3,'-r',linewidth=2,label='$p_{fast}$')
xticks(fontsize=fs2,family='serif')
yticks(fontsize=fs2,family='serif')
title('pressure(kpa)',fontsize=fs1,family='serif')
# ylabel('kpa',fontsize=fs2,family='serif')
xlabel('$\\rho$',fontsize=fs2,family='serif')
legend(loc=0,fontsize=fs2).draggable(True)
subplot(2,4,7)
plot(rho_sparse,aLpe_sparse,'-bo',linewidth=2,label='$d{p_e}/dr$')
plot(rho_sparse,aLpf_sparse,'-ro',linewidth=2,label='$d{p_f}/dr$')
xticks(fontsize=fs2,family='serif')
yticks(fontsize=fs2,family='serif')
xlim([0,1])
# title('density',fontsize=fs1,family='serif')
# ylabel('$10^19m^{-3}$',fontsize=fs2,family='serif')
xlabel('$\\rho$',fontsize=fs2,family='serif')
legend(loc=0,fontsize=fs2).draggable(True)
subplot(2,4,4)
plot(rho_sparse,beta_e_sparse,'-bo',linewidth=2,label='$\\beta_e$')
plot(rho_sparse,beta_f_sparse,'-ro',linewidth=2,label='$\\beta_f$')
xticks(fontsize=fs2,family='serif')
yticks(fontsize=fs2,family='serif')
title('$\\beta_{unit}$',fontsize=fs1,family='serif')
xlabel('$\\rho$',fontsize=fs2,family='serif')
legend(loc=0,fontsize=fs2).draggable(True)
xlim([0,1])
subplot(2,4,8)
# dimension paramter calculation
Ti_sparse=1.e3*interp(rho_sparse,inputpro['rho'],inputpro['Ti_1'])
Tf_sparse=1.e3*interp(rho_sparse,inputpro['rho'],inputpro['Ti_'+str(n_ion)])
Rmaj_sparse=interp(rho_sparse,inputpro['rho'],inputpro['rmaj'])
q_sparse=abs(interp(rho_sparse,inputpro['rho'],inputpro['q']))
qe=1.6e-19;   # charge of a electron
mp=1.67e-27;  # mass of a proton
mu0=4*pi*1.e-7;
mass_ion=inputtglf_k['MASS_2']
fct=2*pi*1.e3*q_sparse*Rmaj_sparse
omega_ti=sqrt(Ti_sparse*qe/mp/mass_ion/2.)/fct  # transit frequency of thermal ion
omega_tf=sqrt(Tf_sparse*qe/mp/mass_ion/2.)/fct  # transit frequency of thermal ion
plot(rho_sparse,omega_ti,'-bo',linewidth=2,label='$\\omega_{Ti}$')
plot(rho_sparse,omega_tf,'-ro',linewidth=2,label='$\\omega_{Tf}$')
xticks(fontsize=fs2,family='serif')
yticks(fontsize=fs2,family='serif')
title('$transit frequency(kHz)$',fontsize=fs1,family='serif')
xlabel('$\\rho$',fontsize=fs2,family='serif')
legend(loc=0,fontsize=fs2).draggable(True)
xlim([0,1])
