nj=201
fs1=14
fs2=20
fs3=20
lw=3;  #linewidth
iexch=1
rho=linspace(0,1,nj);
figure(312,figsize=[28,11])
if not 'trpltout.nc' in root['INPUTS'].keys():
    itrpltout=0
    statefile=root['INPUTS']['statefile.nc']
else:
    itrpltout=1
    trpltout=root['INPUTS']['trpltout.nc']
#	 electron part
if itrpltout==1:
    qbeame=trpltout['qbeame']['data'][-1];	# beam on electrons
    pwrbme=trpltout['pwrbme']['data'][-1];
    qrfeiv=trpltout['qrfeiv']['data'][-1];	# rf on electrons
    prfe=trpltout['prfe']['data'][-1];
    qfusev=trpltout['qfusev']['data'][-1];	# fusion on electrons
    pfuse=trpltout['pfuse']['data'][-1];
    qrad=trpltout['qrad']['data'][-1];		# radiation on  electrons
    prad=trpltout['prad']['data'][-1];
    qohm=trpltout['qohm']['data'][-1];		# ohm heating on electrons
    pohm=trpltout['pohm']['data'][-1];
    qdelten=trpltout['qdelten']['data'][-1];		# electron-ion power exchange
    pdelten=trpltout['pdelten']['data'][-1];
#    iexch=1  # determine whether to include the energy exchange between ion and electron channels
#    if iexch==1:
#        qsume=qbeame+qrfeiv+qfusev+qohm+qrad-qdelten;
#        psume=pwrbme+prfe+pfuse+pohm+prad+pdelten;
#    else:
#        qsume=qbeame+qrfeiv+qfusev+qohm+qrad;
#        psume=pwrbme+prfe+pfuse+pohm+prad;
    #	ion part
    qbeami=trpltout['qbeami']['data'][-1];	# beam on ions
    pwrbmi=trpltout['pwrbmi']['data'][-1];
    qrfiiv=trpltout['qrfiiv']['data'][-1];	# rf on ions
    prfi=trpltout['prfi']['data'][-1];
    qfusiv=trpltout['qfusiv']['data'][-1];	# fusion on electrons
    pfusi=trpltout['pfusi']['data'][-1];
#    if iexch==1:
#        qsumi=qbeami+qrfiiv+qfusiv+qdelten;
#        psumi=pwrbmi+prfi+pfusi-pdelten;
#    else:
#        qsumi=qbeami+qrfiiv+qfusiv;
#        psumi=pwrbmi+prfi+pfusi;
    storqueb=trpltout['storqueb']['data'][-1];
#    smagtorque=trpltout['smagtorque']['data'][-1];
    finttorque=root['INPUTS']['input.profiles']['flow_mom']
else:
    qbeame=statefile['qbeame']['data']
    qbeami=statefile['qbeami']['data']
    qrfeiv=statefile['qrfe']['data']
    qrfiiv=statefile['qrfi']['data']
    qfusev=statefile['qfuse']['data']
    qfusiv=statefile['qfuse']['data']
    qdelten=statefile['qdelt']['data']
    qohm=statefile['qohm']['data']
    qrad=statefile['qrad']['data']
    storqueb=statefile['storque']['data']
# the integrated power source is not available in statefile, so the p* won't be read and set to be 0 in plotting
    pwrbme=zeros(nj)
    pwrbmi=zeros(nj)
    prfe=zeros(nj)
    prfi=zeros(nj)
    pfuse=zeros(nj)
    pfusi=zeros(nj)
    pdelten=zeros(nj)
    pohm=zeros(nj)
    prad=zeros(nj)
    finttorque=root['INPUTS']['input.profiles']['flow_mom']
if iexch==1:
    qsume=qbeame+qrfeiv+qfusev+qohm+qrad-qdelten;
    qsumi=qbeami+qrfiiv+qfusiv+qdelten;
    if itrpltout==1:
        psume=pwrbme+prfe+pfuse+pohm+prad+pdelten;
        psumi=pwrbmi+prfi+pfusi-pdelten;
    else:
        psume=root['INPUTS']['input.profiles']['pow_e']*1.e6
        psumi=root['INPUTS']['input.profiles']['pow_i']*1.e6
else:
    qsume=qbeame+qrfeiv+qfusev+qohm+qrad
    qsumi=qbeami+qrfiiv+qfusiv;
    if itrpltout==1:
        psume=pwrbme+prfe+pfuse+pohm+prad
        psumi=pwrbmi+prfi+pfusi
    else:
        psume=root['INPUTS']['input.profiles']['pow_e']*1.e6
        psumi=root['INPUTS']['input.profiles']['pow_i']*1.e6
h1=subplot(2,4,1)
get(h1)
#get(h1.position)
plot(rho,qbeame,'-g',label='beam',linewidth=lw)
plot(rho,qrfeiv,'-k',label='rf',linewidth=lw)
#plot(rho,qfusev,'-y',label='fusion',linewidth=lw)
plot(rho,-qrad,'-c',label='radiation',linewidth=lw)
plot(rho,qohm,'-r',label='ohm',linewidth=lw)
if iexch==1:
    plot(rho,-qdelten,'-b',label='exchange',linewidth=lw)
plot(rho,qsume,'-m',label='tot',linewidth=lw)
#ylim([-0.40,1.2])
xticks(fontsize=fs1,family='serif')
yticks(fontsize=fs1,family='serif')
title('Power on Electron',fontsize=fs2,family='serif')
ylabel('$MW.m^{-3}$',fontsize=fs2,family='serif')
text(0.5,0.45,'(a)',fontsize=fs3)
legend(loc=0,fontsize=fs1).draggable(True)
subplot(2,4,5)
plot(rho,pwrbme/1.e6,'-g',label='beam',linewidth=lw)
plot(rho,prfe/1.e6,'-k',label='rf',linewidth=lw)
#plot(rho,pfuse/1.e6,'-y',label='fusion',linewidth=lw)
plot(rho,prad/1.e6,'-c',label='radiation',linewidth=lw)
#plot(rho,pohm/1.e6,'-r',label='ohm',linewidth=lw)
if iexch==1:
    plot(rho,pdelten/1.e6,'-b',label='exchange',linewidth=lw)
plot(rho,psume/1.e6,'-m',label='tot',linewidth=lw)
xticks(fontsize=fs1,family='serif')
yticks(fontsize=fs1,family='serif')
#ylim([-1,3])
xlabel('$rho$',fontsize=fs2,family='serif')
ylabel('$MW$',fontsize=fs2,family='serif')
title('Integrated Power on Electron',fontsize=fs2,family='serif')
legend(loc=0,fontsize=fs1).draggable(True)
subplot(2,4,2)
plot(rho,qbeami,'-g',label='beam',linewidth=lw)
plot(rho,qrfiiv,'-k',label='rf',linewidth=lw)
#plot(rho,qfusiv,'-y',label='fusion',linewidth=lw)
if iexch==1:
    plot(rho,qdelten,'-b',label='exchange',linewidth=lw)
plot(rho,qsumi,'-m',label='tot',linewidth=lw)
xticks(fontsize=fs1,family='serif')
yticks(fontsize=fs1,family='serif')
#ylim([-0.40,1.2])
ylabel('$MW.m{-3}$',fontsize=fs2,family='serif')
title('Power on Ion',fontsize=fs2,family='serif')
text(0.5,0.45,'(b)',fontsize=fs3)
legend(loc=0,fontsize=fs1).draggable(True)
subplot(2,4,6)
plot(rho,pwrbmi/1.e6,'-g',label='beam',linewidth=lw)
plot(rho,prfi/1.e6,'-k',label='rf',linewidth=lw)
#plot(rho,pfusi/1.e6,'-y',label='fusion',linewidth=lw)
if iexch==1:
    plot(rho,-pdelten/1.e6,'-b',label='exchange',linewidth=lw)
plot(rho,psumi/1.e6,'-m',label='tot',linewidth=lw)
xticks(fontsize=fs1,family='serif')
yticks(fontsize=fs1,family='serif')
xlabel('$rho$',fontsize=fs2,family='serif')
ylabel('$MW$',fontsize=fs2,family='serif')
#ylim([-1,3])
title('Integrated Power on Ion',fontsize=fs2,family='serif')
legend(loc=0,fontsize=fs1).draggable(True)
subplot(2,4,3)
swall=root['INPUTS']['statefile.nc']['sion']['data'][0]
sbeam=root['INPUTS']['statefile.nc']['sbeam']['data'][-1]
semilogy(rho,swall,'-k',label='wall',linewidth=lw)
semilogy(rho,sbeam,'-g',label='beam',linewidth=lw)
semilogy(rho,swall+sbeam,'-m',label='tot',linewidth=lw)
#xlabel('$rho$',fontsize=fs2,family='serif')
ylabel('$m^{-3}s^{-1}$',fontsize=fs2,family='serif')
#ylim([1.e16,1.e21])
text(0.5,1e43**0.5,'(c)',fontsize=fs3)
title('Particle Source',fontsize=fs2,family='serif')
legend(loc=0,fontsize=fs1).draggable(True)
subplot(2,4,7)
flow_wall=root['INPUTS']['input.profiles']['flow_wall']
flow_beam=root['INPUTS']['input.profiles']['flow_beam']
semilogy(rho,flow_wall,'-k',label='wall',linewidth=lw)
semilogy(rho,flow_beam,'-g',label='beam',linewidth=lw)
semilogy(rho,flow_wall+flow_beam,'-m',label='total',linewidth=lw)
xticks(fontsize=fs1,family='serif')
yticks(fontsize=fs1,family='serif')
xlabel('$rho$',fontsize=fs2,family='serif')
ylabel('$MW.keV^{-1}$',fontsize=fs2,family='serif')
title('Integrated Particle Source',fontsize=fs2,family='serif')
legend(loc=0,fontsize=fs1).draggable(True)
subplot(2,4,4)
plot(rho,storqueb,'-g',label='beam',linewidth=lw)
#plot(rho,smagtorque,'-ok',label='magnetic breaking')
xticks(fontsize=fs1,family='serif')
yticks(fontsize=fs1,family='serif')
ylabel('$N.m^{-2}$',fontsize=fs2,family='serif')
title('Torque Density',fontsize=fs2,family='serif')
#ylim([0,0.5])
text(0.5,0.55,'(d)',fontsize=fs3)
legend(loc=0,fontsize=fs1).draggable(True)
subplot(2,4,8)
plot(rho,finttorque,'-ob',label='beam',linewidth=lw)
xticks(fontsize=fs1,family='serif')
yticks(fontsize=fs1,family='serif')
xlabel('$rho$',fontsize=fs2)
title('Integrated Torque',fontsize=fs2,family='serif')
ylabel('$N.m$',fontsize=fs2,family='serif')
legend(loc=0,fontsize=fs1).draggable(True)
