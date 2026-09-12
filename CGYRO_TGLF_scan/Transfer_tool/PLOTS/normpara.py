# get the normalization parameters, which is favorable for experimental validation
# rho_s/a, c_s, VA, n(kyrhos=0.1), Doppler shift (kyrhos=0.1)
if not 'input.gacode' in root['INPUTS'].keys():
    raise Exception('input.gacode must exist')
# plot the kinetic profiles and profile gradient
inputpro=root['INPUTS']['input.gacode']
inputtgyro=root['INPUTS']['input.tgyro']
rho=inputpro['rho']
p_tgyro=len(inputtgyro['DIR'])
rho_sparse=linspace(inputtgyro['TGYRO_RMIN'],inputtgyro['TGYRO_RMAX'],p_tgyro)
lw=2
q_sparse=zeros([p_tgyro])
rmin_sparse=zeros([p_tgyro])
Rmaj_sparse=zeros([p_tgyro])
kappa_sparse=zeros([p_tgyro])
s_kappa_sparse=zeros([p_tgyro])
shift_sparse=zeros([p_tgyro])
betae_sparse=zeros([p_tgyro])
nimisum_sparse=zeros([p_tgyro]) # sum of n_i*m_i, for calculation of alfven frequency
TioverTe=zeros([p_tgyro])
TfoverTe=zeros([p_tgyro])
aLTe_sparse=zeros([p_tgyro])
aLTi_sparse=zeros([p_tgyro])
# tglfout=root['OUTPUTS']['TGYRO']['TGLF']
for k in range(1,p_tgyro+1):
    # inputtglf_k=tglfout['out.tglf.localdump_'+str(k)]
    inputtglf_k=root['OUTPUTS']['Profiles_gen']['input.tglf_'+str(k)]
    q_sparse[k-1]=inputtglf_k['Q_LOC']
    rmin_sparse[k-1]=inputtglf_k['RMIN_LOC']
    kappa_sparse[k-1]=inputtglf_k['KAPPA_LOC']
    s_kappa_sparse[k-1]=inputtglf_k['S_KAPPA_LOC']
    Rmaj_sparse[k-1]=inputtglf_k['RMAJ_LOC']
    shift_sparse[k - 1] = inputtglf_k['DRMAJDX_LOC']
    betae_sparse[k - 1] = inputtglf_k['BETAE']
    TioverTe[k - 1] = inputtglf_k['TAUS_2']
    TfoverTe[k - 1] = inputtglf_k['TAUS_4']
    aLTe_sparse[k - 1] = inputtglf_k['RLTS_1']
    aLTi_sparse[k - 1] = inputtglf_k['RLTS_2']
    nimisum_sparse[k-1] = sum([inputtglf_k['MASS_'+str(p)]*inputtglf_k['AS_'+str(p)] for p in arange(1,inputtglf_k['NS']+1)])
#    s[k-1]=tglfout['out.tglf.localdump_'+str(k)]['SHAT_SA']
# dimension paramter calculation
Te_sparse=1.e3*interp(rho_sparse,inputpro['rho'],inputpro['Te'])
omega0_sparse=interp(rho_sparse,inputpro['rho'],inputpro['omega0'])
qe=1.6e-19;   # charge of a electron
mp=1.67e-27;  # mass of a proton
mu0=4*pi*1.e-7;
mass_ion=inputtglf_k['MASS_2']
cs=sqrt(Te_sparse*qe/mp/mass_ion/2.)  # mass_ion is the mass normalized to D, Also, here cs=sqrt(Te/mD), the number here 2 is the mass of D
Vf=sqrt(TfoverTe)*cs                  # fast ion velocity
a=inputpro['rmin'][-1]
cs_over_a_sparse=cs/a # in unit of rad/s
# the frequency below comes from Van Zeeland-NF-2016
# omega_GAM=1./Rmaj_sparse*cs_over_a_sparse*(2*(1+7./4.*TioverTe)*(1+1./2/q_sparse**2)*(2/(kappa_sparse**2+1)))**0.5
omega_ti=1/q_sparse/Rmaj_sparse*sqrt(2*TioverTe)*cs_over_a_sparse  # transi frequency of thermal particles, in unit of rad/s
omega_GAM=omega_ti*(q_sparse*sqrt(7/4+1/TioverTe))*((1+1./2/q_sparse**2)*(2/(kappa_sparse**2+1)))**0.5
epsl_g=(kappa_sparse**2-1)/(kappa_sparse**2+1)
TAE_mdf_fac=abs(2-(1+3./4.*epsl_g**2)**0.5)/(1-epsl_g**2/4)**0.5
omega_grad=1./Rmaj_sparse*cs_over_a_sparse*(2*rmin_sparse*(aLTe_sparse/(1+TioverTe)+aLTi_sparse/(1+1./TioverTe))*(1-1./q_sparse**2)*(2/(kappa_sparse**2+1)))**0.5
omega_RSAE_min=(omega_GAM**2+omega_grad**2)**0.5
Bt=inputpro['BT_EXP']
Bunit=Bt*kappa_sparse*(1+s_kappa_sparse/2.-0.5*shift_sparse*rmin_sparse/Rmaj_sparse)
qion=inputpro['IONS'][1][1]
# shear alfven wave frequency with k_par=1/qR
VA=sqrt(2/betae_sparse/nimisum_sparse*cs_over_a_sparse**2)*a # in absolute value
#omega_a_sparse=sqrt(2/betae_sparse/nimisum_sparse/q_sparse**2/Rmaj_sparse**2*cs_over_a_sparse**2)
omega_a_sparse=VA/q_sparse/Rmaj_sparse/a
ky=array([0.06])  # mostly we will focus on looking at kyrhos_unit=0.1
#rho_s==H12*E32*C42/H10/E35/D32
# rho_s=mp*2*mass_ion*cs/qe/Bt/qion
rhosunit_over_a=mp*2*mass_ion*cs_over_a_sparse/qe/Bunit/qion
lenky=len(ky)
ky_dim=zeros([lenky,p_tgyro])           # unit of m^-1
n_sparse=zeros([lenky,p_tgyro])
omega_nondim=zeros([lenky,p_tgyro])
omega_dim=zeros([lenky,p_tgyro])     # in the unit of s^-1
omega_dim_Er=zeros([lenky,p_tgyro])  # polodal velocity contributed by Er, which is omega0/q
omega_dim_lab=zeros([lenky,p_tgyro]) # dimensional frequency in the lab frame
# calculate the toroidal mode number versus ky*rho_s
# still not sure about the sign of Er versus the mode frequency;
# n=ky*a/rho_s*rmin/q_sparse
for k in range(lenky):
    n_sparse[k]=ky[k]/rhosunit_over_a*rmin_sparse/q_sparse  #n value for a given kyrhos
    # omega_dim[k]=omega_nondim*cs_over_a_sparse/2./pi/1.e3
    omega_dim_Er[k]=n_sparse[k]*omega0_sparse/2./pi/1.e3

# c_s/a, rho_s_unit/a, V_a/a, n(kyrhos_unit=0.1)
figure(figsize=[18,12])
lab=['-bo','-ro','-ko','-mo']
fs1=24
fs2=20
fs3=16
subplot(241)
plot(rho_sparse, cs_over_a_sparse/2./pi/1.e3,'-bo',linewidth=lw)
xlabel('$\\rho$',fontsize=fs2,family='serif')
title('c_s/a(kHz)')
xticks(fontsize=fs1,family='serif')
yticks(fontsize=fs1,family='serif')
subplot(242)
plot(rho_sparse, rhosunit_over_a,'-bo',linewidth=lw)
xlabel('$\\rho$',fontsize=fs2,family='serif')
title('$\\rho_{s,unit}/a$')
xticks(fontsize=fs1,family='serif')
yticks(fontsize=fs1,family='serif')
subplot(243)
plot(rho_sparse, Bunit,'-bo',linewidth=lw,label='$B_{unit}$')
plot(rho_sparse, Bt*ones([len(rho_sparse)]),'-ro',linewidth=lw,label='B_t')
xlabel('$\\rho$',fontsize=fs2,family='serif')
title('$Toroidal Field B$')
legend(loc=0,fontsize=fs2).draggable(True)
xticks(fontsize=fs1,family='serif')
yticks(fontsize=fs1,family='serif')
subplot(244)
plot(rho_sparse, Vf/VA,'-bo',linewidth=lw)
title('$V_{fast}/V_A$')
legend(loc=0,fontsize=fs2).draggable(True)
xticks(fontsize=fs1,family='serif')
yticks(fontsize=fs1,family='serif')
subplot(245)
plot(rho_sparse, omega_a_sparse/2./pi/1.e3,'-bo',linewidth=lw)
xlabel('$\\rho$',fontsize=fs2,family='serif')
title('$\\omega_A(kHz)(V_A/qR)$')
xticks(fontsize=fs1,family='serif')
yticks(fontsize=fs1,family='serif')
subplot(246)
plot(rho_sparse, n_sparse[0],'-bo',linewidth=lw)
xlabel('$\\rho$',fontsize=fs2,family='serif')
title('$n(kyrhos='+str(ky[0])+')$')
xticks(fontsize=fs1,family='serif')
yticks(fontsize=fs1,family='serif')
subplot(247)
plot(rho_sparse, omega_dim_Er[0],'-bo',linewidth=lw)
xlabel('$\\rho$',fontsize=fs2,family='serif')
title('$Doppler Shift(kHz) for (kyrhos='+str(ky[0])+')$')
xticks(fontsize=fs1,family='serif')
yticks(fontsize=fs1,family='serif')
subplot(248)
plot(rho_sparse, omega_GAM/2/pi/1.e3,'-bo',linewidth=lw,label='$f_{GAM}$')
plot(rho_sparse, omega_a_sparse/2./pi/1.e3/2,'--r',linewidth=lw,label='$f_{TAE}$')
plot(rho_sparse, omega_a_sparse*TAE_mdf_fac/2./pi/1.e3/2,'-ro',linewidth=lw,label='$f_{TAE}-TAEFL$')
plot(rho_sparse, omega_RSAE_min/2./pi/1.e3,'-ko',linewidth=lw,label='$f_{RSAE-min}$')
xlabel('$\\rho$',fontsize=fs2,family='serif')
title('$AE frequency$')
legend(loc=0,fontsize=fs2).draggable(True)
xticks(fontsize=fs1,family='serif')
yticks(fontsize=fs1,family='serif')
