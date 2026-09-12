# plot the critical gradient of both a/LTi to ITG and a/LTe to ETG,and then compare it to experimental value
# in addition, the quantities that relates to the critical gradient will also be plot out
#############
# ITG.
# The critical gradient comes from the M.Kotchenreuter,pop,1995, Quantitative predictions of tokamak energy confinement from first?principles simulations with kinetic effects
def f(zeff,s, epsl,mu):
    f_value=1-0.2*zeff**0.5*s**(-0.7)*(14*epsl**1.3*mu**(-0.2)-1)
    return f_value
def g(s,RLn):
    g_value=(0.7+0.6*s-0.2*RLn)**2+0.4+0.3*RLn-0.8*s+0.2*s**2
    return g_value
def h(q,zeff,taub):
    h_value=1.5*(1.0+2.8/q**2)**0.26*zeff**0.7*taub**0.5
    return h_value
# get the experimental a/LT
inputtgyro=root['INPUTS']['input.tgyro']
p_tgyro=len(inputtgyro['DIR'])
rho_sparse=linspace(inputtgyro['TGYRO_RMIN'],inputtgyro['TGYRO_RMAX'],p_tgyro)
aLTi=zeros([p_tgyro])
aLTe=zeros([p_tgyro])
aLne=zeros([p_tgyro])
GammaE=zeros([p_tgyro])
#s=zeros([p_tgyro])
ProfOut=root['OUTPUTS']['Profiles_gen']
for k in range(1,p_tgyro+1):
    tglfout=ProfOut['input.tglf_'+str(k)]
    aLTi[k-1]=tglfout['RLTS_2']
    aLTe[k-1]=tglfout['RLTS_1']
    aLne[k-1]=tglfout['RLNS_1']
    GammaE[k-1]=tglfout['VEXB_SHEAR']
#    s[k-1]=tglfout['out.tglf.localdump_'+str(k)]['SHAT_SA']
# so the background paramter is
# zeff, s, epsl, mu, RLn, taub
inputpro=root['INPUTS']['input.gacode']
rho=inputpro['rho']
q=-1*inputpro['q']
zeff=inputpro['z_eff']
rmin=inputpro['rmin']
rmaj=inputpro['rmaj']
ne=inputpro['ne']
Te=inputpro['Te']
Ti=inputpro['Ti_1']
s=rmin/q*gradient(q)/gradient(rmin)
kappa=inputpro['kappa']
if 'TGYRO_RMIN' in inputtgyro.keys():
    rhomin=inputtgyro['TGYRO_RMIN']
rhomax=inputtgyro['TGYRO_RMAX']
epsl=rmin/rmaj
mu=2.1*rmaj*ne/(Te**1.5*Ti**0.5)
RLn=rmaj*gradient(ne)/gradient(rmin)/ne
RLn=max([6,max(RLn)])
taub=Ti/Te*(1-inputpro['ni_4']/inputpro['ne'])
tau=zeff*Te/Ti;
dkde=gradient(kappa)/gradient(epsl)
# plot the gradient
figure(figsize=[12,12])
lw=2
fs1=24
fs2=20
fs3=16
subplot(221)
aLTi_crit=f(zeff,s, epsl,mu)*g(s,RLn)*h(q,zeff,taub)/rmaj*max(rmin)
plot(rho,aLTi_crit,'-r',linewidth=lw,label='$a/LT_{i,crit}-theory$')
plot(rho_sparse,aLTi,'-bo',linewidth=lw,label='$a/LT_{i,exp}$')
legend(loc=0,fontsize=fs1).draggable(True)
title('ITG',fontsize=fs1,family='serif')
#xlabel('$\\rho$',fontsize=fs2,family='serif')
#ylabel('a/L_{Ti}',fontsize=fs2,family='serif')
# xlim([0.2,0.8])
xlim([rhomin,rhomax])
#ylim([0,5])
xticks(fontsize=fs2)
yticks(fontsize=fs2)
subplot(223)
aLTi_crit_sparse=interp(rho_sparse,rho,aLTi_crit)
plot(rho_sparse,aLTi/aLTi_crit_sparse,'-ko',linewidth=lw)
plot([0,1],[1,1],'--r',linewidth=lw/2.)
ylim([0,1.25])
xlim([rhomin,rhomax])
#ylabel('$aLT_{i_exp}/aLT_{i_crit}$',fontsize=fs2,family='serif')
text(0.3,0.25,'$aLT_{i,exp}/aLT_{i,crit}$',fontsize=fs1+2,family='serif',color='k')
xticks(fontsize=fs2,family='serif')
yticks(fontsize=fs2,family='serif')
xlabel('$\\rho$',fontsize=fs1,family='serif')
subplot(222)
aLTe_crit1=(1.+tau)*(1.33+1.91*s/q)*(1-1.5*epsl)*(1+0.3*epsl*dkde)
#aLTe_crit=[max([aLTe_crit1[k],0.8*RLn[k]]) for k in range(len(tau))]
aLTe_crit=aLTe_crit1
plot(rho,aLTe_crit1,'-r',linewidth=lw,label='$a/LT_{e,crit}-theory$')
plot(rho_sparse,aLTe,'-bo',linewidth=lw,label='$a/LT_{e-exp}$')
legend(loc=0,fontsize=fs1).draggable(True)
title('ETG',fontsize=fs1,family='serif')
#xlabel('$\\rho$',fontsize=fs2,family='serif')
#ylabel('a/L_{Te}',fontsize=fs2,family='serif')
xlim([rhomin,rhomax])
#xlim([0,1])
#ylim([0,5])
xticks(fontsize=fs2)
yticks(fontsize=fs2)
subplot(224)
aLTe_crit_sparse=interp(rho_sparse,rho,aLTe_crit)
plot(rho_sparse,aLTe/aLTe_crit_sparse,'-ko',linewidth=lw)
plot([0,1],[1,1],'--r',linewidth=lw/2.)
xlim([rhomin,rhomax])
ylim([0,1.25])
#ylabel('$aLT_{e_exp}/aLT_{e_crit}$',fontsize=fs2,family='serif')
text(0.25,0.75,'$aLT_{e,exp}/aLT_{e,crit}$',fontsize=fs1+2,family='serif',color='k')
xticks(fontsize=fs2,family='serif')
yticks(fontsize=fs2,family='serif')
xlabel('$\\rho$',fontsize=fs1,family='serif')
