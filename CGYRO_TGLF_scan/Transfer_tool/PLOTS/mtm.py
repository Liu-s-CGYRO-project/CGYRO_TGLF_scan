# this script is used to plot the MTM frequency of different ky versus rho
# the input needs to be input.tgyro, input.gaocde
# we will also need to add the Er value and evaluate its effect on the frequency in the lab frame 
if not 'input.gacode' in root['INPUTS'].keys():
    raise Exception('input.gacode must exist')
#if not 'out.tglf.localdump_1' in root['OUTPUTS']['TGYRO']['TGLF'].keys():
#    root['SCRIPTS']['TGYRO_tglf.py'].run()
# plot the kinetic profiles and profile gradient
inputpro=root['INPUTS']['input.gacode']
inputtgyro=root['INPUTS']['input.tgyro']
rho=inputpro['rho']
p_tgyro=len(inputtgyro['DIR'])
rho_sparse=linspace(inputtgyro['TGYRO_RMIN'],inputtgyro['TGYRO_RMAX'],p_tgyro)
lw=2
aLTe_sparse=zeros([p_tgyro])
aLne_sparse=zeros([p_tgyro])
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
tglfout=root['OUTPUTS']['Profiles_gen']
for k in range(1,p_tgyro+1):
    inputtglf_k=tglfout['input.tglf_'+str(k)]
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
    nu_sparse[k-1]=inputtglf_k['XNUE']
    zeff_sparse[k - 1] = inputtglf_k['ZEFF']
# dimension paramter calculation
Te_sparse=1.e3*interp(rho_sparse,inputpro['rho'],inputpro['Te'])
omega0_sparse=interp(rho_sparse,inputpro['rho'],inputpro['omega0'])
qe=1.6e-19;   # charge of a electron
mp=1.67e-27;  # mass of a proton
mu0=4*pi*1.e-7;
mass_ion=inputtglf_k['MASS_2']
cs=sqrt(Te_sparse*qe/mp/mass_ion/2.)
a=inputpro['rmin'][-1]
cs_over_a_sparse=cs/a
Bt=inputpro['BT_EXP']
Bunit=Bt*kappa_sparse*(1+s_kappa_sparse/2.-0.5*shift_sparse*rmin_sparse/Rmaj_sparse)
qion=inputpro['IONS'][1][1]
BunitOverBt=Bunit/Bt
# shear alfven wave frequency with k_par=1/qR
omega_a_sparse=sqrt(2/betae_sparse/nimisum_sparse/q_sparse**2/Rmaj_sparse**2*cs_over_a_sparse**2)
ky=array([0.1])  # mostly we will focus on looking at kyrhos_unit=0.1
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
    kyrhos_over_n=q_sparse*rhosunit_over_a/rmin_sparse
    n_sparse[k]=ky[k]/kyrhos_over_n
    omega_nondim[k]=ky[k]*(aLne_sparse+aLTe_sparse)
    omega_dim[k]=omega_nondim*cs_over_a_sparse/2./pi/1.e3
#    omega_dim_Er[k]=n_sparse[k]*omega0_sparse/q_sparse/2./pi/1.e3
    omega_dim_Er[k]=n_sparse[k]*omega0_sparse/2./pi/1.e3
    omega_dim_lab[k]=omega_dim[k]+omega_dim_Er[k]
    ky_dim[k]=ky[k]/rhosunit_over_a
# plotprint('cs='c)
#print('cs(km/s)=',cs/1.e3)
figure(figsize=[18,12])
lab=['-bo','-ro','-ko','-mo']
fs1=24
fs2=20
fs3=16
rct1=[0.1,0.1,0.2,0.35]
rct4=[0.1,0.5,0.2,0.35]
rct2=[0.4,0.1,0.2,0.35]
rct5=[0.4,0.5,0.2,0.35]
rct3=[0.7,0.1,0.2,0.35]
rct6=[0.7,0.5,0.2,0.35]
ax1=plt.axes(rct1)
#subplot(131)
for k in range(lenky):
    plot(rho_sparse,omega_dim[k]/n_sparse[k]*BunitOverBt,lab[k],linewidth=lw,label='n=1')
legend(loc=0,fontsize=fs3).draggable(True)
ylim([0,max(omega_dim[k]/n_sparse[k]*BunitOverBt)*1.2])
xlabel('$\\rho$',fontsize=fs1,family='serif')
ylabel('w(kHz)',fontsize=fs1,family='serif')
xticks(fontsize=fs1,family='serif')
#xticks(linspace(0.2,0.8,4),fontsize=fs1,family='serif')
yticks(fontsize=fs1,family='serif')
#subplot(132)
ax2=plt.axes(rct2)
for k in range(lenky):
    plot(rho_sparse,omega_dim[k]/n_sparse[k]*BunitOverBt,lab[k],linewidth=lw,label='n=1')
    plot(rho_sparse, omega_dim[k] / n_sparse[k]*BunitOverBt + abs(omega_dim_Er[k] / n_sparse[k]), '--k', linewidth=lw/2)
    plot(rho_sparse, omega_dim[k] / n_sparse[k]*BunitOverBt - abs(omega_dim_Er[k] / n_sparse[k]), '--k', linewidth=lw / 2)
ylim([0,max(omega_dim[k]/n_sparse[k]*BunitOverBt+abs(omega_dim_Er[k]/n_sparse[k]))*1.2])
legend(loc=0,fontsize=fs3).draggable(True)
xlabel('$\\rho$',fontsize=fs1,family='serif')
#ylabel('w(kHz)(MTM-Theory)',fontsize=fs1,family='serif')
ylabel('w(kHz)(lab)',fontsize=fs1,family='serif')
xticks(fontsize=fs1,family='serif')
#xticks(linspace(0.2,0.8,4),fontsize=fs1,family='serif')
yticks(fontsize=fs1,family='serif')
#subplot(133)
ax3=plt.axes(rct3)
for k in range(lenky):
    plot(rho_sparse,2*pi/(kyrhos_over_n/rhosunit_over_a),lab[k],linewidth=lw,label='n=1')
legend(loc=0,fontsize=fs3).draggable(True)
xlabel('$\\rho$',fontsize=fs1,family='serif')
#xticks(linspace(0.2,0.8,4),fontsize=fs1,family='serif')
ylabel('$labma(m)$',fontsize=fs1,family='serif')
xticks(fontsize=fs1,family='serif')
yticks(fontsize=fs1,family='serif')
# plot the frequency contributed by Er
ax4=plt.axes(rct4)
for k in range(lenky):
    plot(rho_sparse,omega_dim_Er[k]/n_sparse[k],lab[k],linewidth=lw,label='n=1')
legend(loc=0,fontsize=fs3).draggable(True)
#xlabel('$\\rho$',fontsize=fs1,family='serif')
# xticks(linspace(0.2,0.8,4),fontsize=fs1,family='serif')
ylabel('$f_{Doppler}(kHz)$',fontsize=fs1,family='serif')
xticks(fontsize=fs1,family='serif')
yticks(fontsize=fs1,family='serif')
# plot the toroial mode number for different ky
ax5=plt.axes(rct5)
for k in range(lenky):
    plot(rho_sparse,ky[k]/n_sparse[k],lab[k],linewidth=lw,label='n=1')
legend(loc=0,fontsize=fs3).draggable(True)
#xlabel('$\\rho$',fontsize=fs1,family='serif')
#xticks(linspace(0.2,0.8,4),fontsize=fs1,family='serif')
ylabel('$k_y\\rho_s$',fontsize=fs1,family='serif')
xticks(fontsize=fs1,family='serif')
yticks(fontsize=fs1,family='serif')
ax5=plt.axes(rct6)
plot(rho_sparse,zeff_sparse*nu_sparse/(aLne_sparse+aLTe_sparse)/kyrhos_over_n/BunitOverBt,'-bo',linewidth=lw)
legend(loc=0,fontsize=fs3).draggable(True)
#xlabel('$\\rho$',fontsize=fs1,family='serif')
#xticks(linspace(0.2,0.8,4),fontsize=fs1,family='serif')
ylabel('$n$',fontsize=fs1,family='serif')
title('$\\omega_{MTM} best match \\nu$')
xticks(fontsize=fs1,family='serif')
yticks(fontsize=fs1,family='serif')

# plot the relevant for kyrhos=0.1
figure(figsize=[18,12])
lab=['-bo','-ro','-ko','-mo']
fs1=24
fs2=20
fs3=16
rct1=[0.1,0.1,0.2,0.35]
rct4=[0.1,0.5,0.2,0.35]
rct2=[0.4,0.1,0.2,0.35]
rct5=[0.4,0.5,0.2,0.35]
rct3=[0.7,0.1,0.2,0.35]
rct6=[0.7,0.5,0.2,0.35]
ax1=plt.axes(rct1)
#subplot(131)
for k in range(lenky):
    plot(rho_sparse,omega_dim[k]*BunitOverBt,lab[k],linewidth=lw,label=str(ky[k]))
legend(loc=0,fontsize=fs3).draggable(True)
ylim([0,max(omega_dim[lenky-1]*BunitOverBt)*1.2])
xlabel('$\\rho$',fontsize=fs1,family='serif')
ylabel('w(kHz)(MTM)',fontsize=fs1,family='serif')
xticks(fontsize=fs1,family='serif')
#xticks(linspace(0.2,0.8,4),fontsize=fs1,family='serif')
yticks(fontsize=fs1,family='serif')
#subplot(132)
ax2=plt.axes(rct2)
for k in range(lenky):
    plot(rho_sparse,omega_dim[k]*BunitOverBt,lab[k],linewidth=lw,label=str(ky[k]))
    plot(rho_sparse, omega_dim[k]*BunitOverBt - abs(omega_dim_Er[k]), '--k', linewidth=lw)
    plot(rho_sparse, omega_dim[k]*BunitOverBt + abs(omega_dim_Er[k]), '--k', linewidth=lw)
ylim([0,max(omega_dim[k]*BunitOverBt+abs(omega_dim_Er[k]))*1.2])
legend(loc=0,fontsize=fs3).draggable(True)
xlabel('$\\rho$',fontsize=fs1,family='serif')
ylabel('w(kHz)(lab)',fontsize=fs1,family='serif')
# ylabel('w(kHz)(MTM-Theory,lab Frame)',fontsize=fs1,family='serif')
xticks(fontsize=fs1,family='serif')
#xticks(linspace(0.2,0.8,4),fontsize=fs1,family='serif')
yticks(fontsize=fs1,family='serif')
#subplot(133)
ax3=plt.axes(rct3)
for k in range(lenky):
    plot(rho_sparse,2*pi/ky_dim[k],lab[k],linewidth=lw,label=str(ky[k]))
legend(loc=0,fontsize=fs3).draggable(True)
xlabel('$\\rho$',fontsize=fs1,family='serif')
#xticks(linspace(0.2,0.8,4),fontsize=fs1,family='serif')
ylabel('$lamda(m)$',fontsize=fs1,family='serif')
xticks(fontsize=fs1,family='serif')
yticks(fontsize=fs1,family='serif')
# plot the frequency contributed by Er
ax4=plt.axes(rct4)
for k in range(lenky):
    plot(rho_sparse,omega_dim_Er[k],lab[k],linewidth=lw,label=str(ky[k]))
legend(loc=0,fontsize=fs3).draggable(True)
#xlabel('$\\rho$',fontsize=fs1,family='serif')
# xticks(linspace(0.2,0.8,4),fontsize=fs1,family='serif')
ylabel('$f_{Doppler}(kHz)$',fontsize=fs1,family='serif')
xticks(fontsize=fs1,family='serif')
yticks(fontsize=fs1,family='serif')
# plot the toroial mode number for different ky
ax5=plt.axes(rct5)
for k in range(lenky):
    plot(rho_sparse,n_sparse[k],lab[k],linewidth=lw,label=str(ky[k]))
legend(loc=0,fontsize=fs3).draggable(True)
#xlabel('$\\rho$',fontsize=fs1,family='serif')
#xticks(linspace(0.2,0.8,4),fontsize=fs1,family='serif')
ylabel('$n$',fontsize=fs1,family='serif')
xticks(fontsize=fs1,family='serif')
yticks(fontsize=fs1,family='serif')
ax5=plt.axes(rct6)
plot(rho_sparse,zeff_sparse*nu_sparse/(aLne_sparse+aLTe_sparse)/BunitOverBt,'-bo',linewidth=lw)
legend(loc=0,fontsize=fs3).draggable(True)
#xlabel('$\\rho$',fontsize=fs1,family='serif')
#xticks(linspace(0.2,0.8,4),fontsize=fs1,family='serif')
ylabel('$k_y\\rho_s$',fontsize=fs1,family='serif')
title('$\\omega_{MTM} best match \\nu$')
xticks(fontsize=fs1,family='serif')
yticks(fontsize=fs1,family='serif')

# ## plot those basic parameters
# # c_s/a, rho_s_unit/a, V_a/a, n(kyrhos_unit=0.1)
# figure(figsize=[18,12])
# subplot(141)
# plot(rho_sparse, cs_over_a_sparse/2./pi/1.e3,'-bo',linewidth=lw)
# xlabel('$\\rho$',fontsize=fs2,family='serif')
# title('c_s/a(kHz)')
# xticks(fontsize=fs1,family='serif')
# yticks(fontsize=fs1,family='serif')
# subplot(142)
# plot(rho_sparse, rhosunit_over_a,'-bo',linewidth=lw)
# xlabel('$\\rho$',fontsize=fs2,family='serif')
# title('$\\rho_{s,unit}/a$')
# xticks(fontsize=fs1,family='serif')
# yticks(fontsize=fs1,family='serif')
# subplot(143)
# plot(rho_sparse, omega_a_sparse/2./pi/1.e3,'-bo',linewidth=lw)
# xlabel('$\\rho$',fontsize=fs2,family='serif')
# title('$\\omega_A(kHz)$')
# xticks(fontsize=fs1,family='serif')
# yticks(fontsize=fs1,family='serif')
# subplot(144)
# plot(rho_sparse, n_sparse[0],'-bo',linewidth=lw)
# xlabel('$\\rho$',fontsize=fs2,family='serif')
# title('$toroidal mode n(kyrhos='+str(ky[0])+')$')
# xticks(fontsize=fs1,family='serif')
# yticks(fontsize=fs1,family='serif')
