fs1=12
fs2=16
fs3=20
#plt.close()
plt.figure(311,figsize=[8,12])
# get the pressure and q profile from EFIT output gfile
#gdata=root['OUTPUTSRec']['EFITOutput']['Out'][int(k)]['gfile']
gdata=root['INPUTS']['gfile']
if not 'trpltout.nc' in root['INPUTS'].keys():
    itrpltout=0
else:
    itrpltout=1
    trpltout=root['INPUTS']['trpltout.nc']
difab=gdata['SIMAG']-gdata['SIBRY']
numgrid=len(gdata['QPSI'])
qpsi=gdata['QPSI']
rhop=linspace(0,1,numgrid)
Pres=linspace(0,0,numgrid)
rhot=linspace(0,0,numgrid)
rhopres=(rhop[0:numgrid-1]+rhop[1:numgrid])/2;
pppsi=spline(rhop,gdata['PPRIME'],rhopres)
q=spline(rhop,abs(gdata['QPSI']),rhopres)
dpsi=difab/(numgrid-1);
for m in linspace(numgrid-2,0,numgrid-1): #numgrid-1:-1:1
    m=int(m)
    Pres[m]=Pres[m+1]+pppsi[m]*dpsi;
for m in linspace(0,numgrid-2,numgrid-1):
    m=int(m)
    rhot[m+1]=rhot[m]+q[m]/float(numgrid-1)
rhot=sqrt(rhot/max(rhot))
# get the current density for all components
if itrpltout==1:
    # then we use the data in the trpltout for visulization
    trpltout=root['INPUTS']['trpltout.nc']
    curden=trpltout['curden']['data'][-1]/1.e2;
    dim_n3d=size(curden,0);
#    dim_nj=size(curbeam,1);
    curohm=trpltout['curohm']['data'][-1]/1.e2;
    curni=trpltout['curni']['data'][-1]/1.e2;
    curboot=trpltout['curboot']['data'][-1]/1.e2;
    currf=trpltout['currf']['data'][-1]/1.e2;
    curbeam=trpltout['curbeam']['data'][-1]/1.e2;
    paux=trpltout['paux']['data'][-1]/1.e2;
    qdt=trpltout['qdt']['data'][-1]/1.e2;
    etor=trpltout['etor']['data'][-1]/1.e2;
else:
    # we will use the data in statefile to visulize
    statefile=root['INPUTS']['statefile.nc']
    curden=statefile['curden']['data']/1.e6
    curohm=statefile['curohm']['data']/1.e6
#    curni=statefile['curni']['data']/1.e6
    curboot=statefile['curboot']['data']/1.e6
    currf=statefile['currf']['data']/1.e6
    curbeam=statefile['curbeam']['data']/1.e6
    etor=statefile['etor']['data']/1.e6
dim_nj=size(curbeam)
rho=linspace(0,1,dim_nj);
#   distribution of each current component
#h1=subplot(3,2,1)
rct1=[0.15,0.66,0.28,0.25]
ax1=plt.axes(rct1)
#get(h1.frame_on)
# get the geometry information from EFIT output
GridR,GridZ=meshgrid(gdata['AuxQuantities']['R'],gdata['AuxQuantities']['Z'])
PsiGrid=gdata['PSIRZ']
ax1.contourf(GridR,GridZ,PsiGrid,36,levels=linspace(gdata['SIMAG'],gdata['SIBRY'],16))
axis('equal')
ylim([-1.4,1.4])
xlim(0.8,2.4)
text(0.8,0.5,'(a)',fontsize=fs3,family='serif')
plot(gdata['RBBBS'],gdata['ZBBBS'],'-r',linewidth=1.6)
plot(gdata['RLIM'],gdata['ZLIM'],linewidth=3.6)
xlabel('R',fontsize=fs2,family='serif')
ylabel('Z',fontsize=fs2,family='serif')
xticks(fontsize=fs1,family='serif')
yticks(fontsize=fs1,family='serif')
subplot(3,2,2)
currff=curden-curohm-curboot-curbeam
plot(rho,curden,'-m',label='tot',linewidth=2)
plot(rho,curohm,'-r',label='ohmic',linewidth=2)
plot(rho,curboot,'-y',label='BS',linewidth=2)
plot(rho,currff,'-k',label='rf',linewidth=2)
plot(rho,curbeam,'-g',label='beam',linewidth=2)
legend(loc=0,fontsize=fs1).draggable(True)
xticks(fontsize=fs1,family='serif')
yticks(fontsize=fs1,family='serif')
#xlabel('$rho$',fontsize=fs2,family='serif')
ylabel('$Jt(MA.m^{-2})$',fontsize=fs2,family='serif')
text(0.2,1.6,'(b)',fontsize=fs3,family='serif')
#ylim([0,2])
subplot(3,2,3)
if itrpltout==1:
    totohm=trpltout['totohm']['data'][-1];
    totboot=trpltout['totboot']['data'][-1];
    totb=trpltout['totb']['data'][-1];
    totrf=trpltout['totrf']['data'][-1];
#    dim_time=len(totb);
else:
    totohm=statefile['totohm_cur']['data']
    totboot=statefile['totboot_cur']['data']
    totb=statefile['totbeam_cur']['data']
    totrf=statefile['totrf_cur']['data']
text(-0.8,1.00,'(c)',fontsize=fs3,family='serif')
curr=array([totboot,totohm,totb,totrf]);
# get the Ip from the rfile of EFIT
Ip=root['INPUTS']['gfile']['CURRENT']
frac=[int(round(item)) for item in (curr/Ip*100.)]
label=['BS '+str(frac[0]),'ohm '+str(frac[1]),'beam '+str(frac[2]),'rf '+str(frac[3])]
#label=['BS '+str(frac[1]),'beam '+str(frac[2]),'rf '+str(frac[3])]
pie([totboot,totohm,totb,totrf],explode=[0,0,0,0],labels=label)#,fontsize=fs1)
# safety factor q profile
subplot(3,2,4)
plot(rhot,abs(qpsi),linewidth=2)
#ylim([2,9])
ylim([0,9])
plot(array([0,1]),array([2,2]),'--r',linewidth=1)
q95=spline(rhop,abs(qpsi),0.95)
plot(array([0,1]),array([q95,q95]),'--r',linewidth=1)
xticks(fontsize=fs1,family='serif')
yticks(linspace(1,9,9),fontsize=fs1,family='serif')
#xlabel('$rho$',fontsize=fs2,family='serif')
ylabel('q',fontsize=fs2,family='serif')
text(0.2,7,'(d)',fontsize=fs3,family='serif')
#toroidal electrical field
subplot(3,2,5)
plot(rho,etor)
xticks(fontsize=fs1,family='serif')
yticks(fontsize=fs1,family='serif')
maxetor=max(abs(etor))
ylim([-1.2*maxetor,1.2*maxetor])
xlabel('$rho$',fontsize=fs2,family='serif')
ylabel('$E_{tor}(V.cm^{-1})$',fontsize=fs2,family='serif')
text(0.2,0.5e-6,'(e)',fontsize=fs3,family='serif')
# pressure profile
subplot(3,2,6)
plot(rhot,Pres,linewidth=2)
xticks(fontsize=fs1,family='serif')
yticks(fontsize=fs1,family='serif')
xlabel('$rho$',fontsize=fs2,family='serif')
#ylim([0,1.5e6])
text(0.8,max(Pres),'(f)',fontsize=fs3)
ylabel('P(pa)',fontsize=fs2,family='serif')
#   central ohmic current evolution
#subplot(2,2,4)
#plot(rho,curohm[dim_n3d-1]/100,'-bo')
#xticks(fontsize=fs1,family='serif')
#yticks(fontsize=fs1,family='serif')
#xlabel('$rho$',fontsize=fs2,family='serif')
#ylabel('J-ohmic MA/m^2',fontsize=fs2,family='serif')
#figure('current profile')
iextra=0
if iextra==1:
    plt.figure('current profile',figsize=[8,8])
    lw=4
    fsadd=6
#    subplot(3,1,1)
#    currff=curden-curohm-curboot-curbeam
#    plot(rho,curden[dim_n3d-1]/100,'-m',label='Total',linewidth=lw)
#    plot(rho,curohm[dim_n3d-1]/100,'-r',label='Ohmic',linewidth=lw)
#    plot(rho,curboot[dim_n3d-1]/100,'-y',label='Bootstrap',linewidth=lw)
#    #plot(rho,currf[dim_n3d-1]/100,'-k',label='rf',linewidth=2)
#    plot(rho,currff[dim_n3d-1]/100,'-k',label='RF',linewidth=lw)
#    plot(rho,curbeam[dim_n3d-1]/100,'-g',label='Beam',linewidth=lw)
#    legend(loc=0,fontsize=fs2).draggable(True)
#    xticks(fontsize=fs2+fsadd,family='serif')
#    yticks(fontsize=fs2+fsadd,family='serif')
#    #xlabel('$rho$',fontsize=fs2,family='serif')
#    ylabel('$J_t(MA.m^{-2})$',fontsize=fs3+fsadd,family='serif')
##    xlabel('$rho$',fontsize=fs2+fsadd,family='serif')
#    text(0.45,1.6,'(a)',fontsize=fs1+fsadd)
#    ylim([0,2])
    subplot(2,1,1)
    plot(rhot,qpsi,linewidth=lw)
    ylim([0,6])
    xticks(fontsize=fs2+fsadd,family='serif')
    yticks(linspace(1,6,6),fontsize=fs2+fsadd,family='serif')
    #xlabel('$rho$',fontsize=fs2,family='serif')
    ylabel('q',fontsize=fs3+fsadd,family='serif')
#    plot(array([0,1]),array([2,2]),'--r',linewidth=1)
#    q95=spline(rhop,qpsi,0.95)
#    plot(array([0,1]),array([q95,q95]),'--r',linewidth=1)
#    title('$q$',fontsize=fs2+fsadd,family='serif')
#    xlabel('$\\rho$',fontsize=fs3+fsadd,family='serif')
    text(0.45,5.0,'(a)',fontsize=fs1+fsadd)
    subplot(2,1,2)
# plot the beam pressure and the total pressure
    stateroot=root['INPUTS']['statefile.nc']
    press=stateroot['press']['data']  # total pressure, pa
    pressb=stateroot['pressb']['data'] # beam particle pressure
    plot(rho,press/1.e3,'-b',linewidth=lw,label='Total')
    plot(rho,pressb/1.e3,'-r',linewidth=lw,label='Beam')
    xticks(fontsize=fs2+fsadd,family='serif')
    yticks(fontsize=fs2+fsadd,family='serif')
#    yticks(linspace(1,6,6),fontsize=fs2+fsadd,family='serif')
    xlabel('$\\rho$',fontsize=fs3+fsadd,family='serif')
    ylabel('$P(kpa)$',fontsize=fs3+fsadd,family='serif')
    text(0.45,200,'(b)',fontsize=fs1+fsadd)
    legend(loc=0,fontsize=fs2).draggable(True)
