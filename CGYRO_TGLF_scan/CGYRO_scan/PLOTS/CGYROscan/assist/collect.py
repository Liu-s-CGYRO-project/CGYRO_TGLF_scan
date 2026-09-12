import sys
#sys.path.append('/home/users/chenly_dut/mymodule/CGYRO_SCAN/PLOTS/CGYROscan/assist')
from cgyro_read_xj import *
#from cgyro_ball_class import OMFITcgyro_eigen
f = open(root['PLOTS']['CGYROscan']['assist']['getglobal.py'].filename, 'r')
for line in f:
    exec(line)
f.close()

# this is a class inherient from OMFITcgyro_base
# this class will mainly focus on writting some methods for handling the eigenfunction
# from now on, we will mainly focus on object-oriented coding
import numpy as np
from scipy import integrate
from scipy.interpolate import interp1d
from classes.omfit_gacode import OMFITcgyro

#class OMFITcgyro_eigen(omfit_gacode.OMFITcgyro_base.OMFITcgyro):
class OMFITcgyro_eigen(OMFITcgyro):
    """
    Class used for handling the eigenfunctions, functions included:
    turn_ball2r, turn_ball2theta, turn_ball2RZ, miller_wd_s
    """
    def __init__(self,filename=None,extra_files=[],test_mode=False,theta_p=np.linspace(-np.pi,np.pi,37)):
        OMFITcgyro.__init__(self,filename,extra_files,test_mode)
        print('You have entered OMFITcgyro_eigen!')
    	# get the background parameters, which will be frequency used in the subsequent functions
        inputcgyro=self['input.cgyro.gen']
        # geometric parameters
        self.Rmaj=inputcgyro['RMAJ']
        self.rmin=inputcgyro['RMIN']
        self.shift=inputcgyro['SHIFT']
        self.kappa=inputcgyro['KAPPA']
        self.skappa=inputcgyro['S_KAPPA']
        self.delta=inputcgyro['DELTA']
        self.sdelta=inputcgyro['S_DELTA']
        self.q=inputcgyro['Q']
        self.shear=inputcgyro['S']
        # resolution parameters
        self.ky=inputcgyro['KY']
        self.n_r=inputcgyro['N_RADIAL']
        self.n_theta=inputcgyro['N_THETA']
        self.temp_1=inputcgyro['TEMP_1']
        alpha=np.sum([inputcgyro['DENS_'+str(m)]*inputcgyro['TEMP_'+str(m)]*\
              (inputcgyro['DLNNDR_'+str(m)]+inputcgyro['DLNTDR_'+str(m)]) for m in np.arange(1,inputcgyro['N_SPECIES']+1) ])
        alpha=alpha*inputcgyro['BETAE_UNIT']*inputcgyro['Q']**2*inputcgyro['RMAJ']
        self.alpha=alpha*inputcgyro['BETA_STAR_SCALE']  # this parameter will be used
        self.betastar=self.alpha/self.q**2/self.Rmaj
        # get the ballooning functions
        balloon=self['balloon']
        # note that theta_b_cgyro is not uniformly distributed, while we want a uniform version, so the transform will be required
        # phi_b_cgyro->phi_b;
        theta_b_cgyro=balloon['theta_b_over_pi']
        self.theta_b_cgyro=theta_b_cgyro*np.pi
        theta_b=np.linspace(np.amin(self.theta_b_cgyro),np.amax(self.theta_b_cgyro),len(self.theta_b_cgyro))  #
        self.theta_b=theta_b
        self.phi_b_cgyro=balloon['balloon_phi'].T[-1].data # the phi in the ballooning space
        # do the transform from theta_b_cgyro to theta_b
        f_spline_phi = interp1d(self.theta_b_cgyro, self.phi_b_cgyro, kind='cubic')
        self.phi_b=f_spline_phi(self.theta_b)
        self.iapar=0
        self.apar_b=np.zeros(len(self.phi_b))
        self.ibpar=0
        self.bpar_b = np.zeros(len(self.phi_b))
        if 'balloon_apar' in balloon.keys():
            self.iapar=1
            self.apar_b_cgyro=balloon['balloon_apar'].T[-1].data
            # do the transform from theta_b_cgyro to theta_b
            f_spline_apar = interp1d(self.theta_b_cgyro, self.apar_b_cgyro, kind='cubic')
            self.apar_b = f_spline_apar(self.theta_b)
        if 'balloon_bpar' in balloon.keys():
            self.ibpar = 1
            self.bpar_b_cgyro = balloon['balloon_bpar'].T[-1].data
            # do the transform from theta_b_cgyro to theta_b
            f_spline_bpar = interp1d(self.theta_b_cgyro, self.bpar_b_cgyro, kind='cubic')
            self.bpar_b = f_spline_bpar(self.theta_b)
        # self.ntheta_b=len(theta_b)  # ballooning space, inputcgyro['ntheta']*inputcgyro['nr']
        self.theta_p=theta_p   # poloidal theta, really theta
        self.n_theta_p=len(self.theta_p)
        # get the eigenfunction of Epar # parallel electrical field
        self.miller_wd_s()
        q_loc_b = self.turn_thetap2thetab(self.q_loc)
        Rs_b = self.turn_thetap2thetab(self.Rs)
        epar_es_b = -1 / q_loc_b / Rs_b * np.gradient(self.phi_b / np.gradient(self.theta_b))
        self.epar_es_b=epar_es_b
        omega=complex(self['freq']['omega'].T[-1].data,self['freq']['gamma'].T[-1].data)
        epar_b=epar_es_b
        self.epar_em_b = np.zeros(len(epar_b))
        if self.iapar==1:
            epar_em_b=1j*omega*self.apar_b
            epar_b=epar_es_b+epar_em_b
            self.epar_em_b=epar_em_b
        self.epar_b=epar_b
        # read the growth rate and frequency
        self.gamma=self['freq']['gamma'].isel(ky=0,t=-1).data
        self.omega = self['freq']['omega'].isel(ky=0, t=-1).data

    def turn_ball2theta(self):
        """
        Usage: turn_ball2theta(self)
        functionality: turn the eigefunction from ballooning space to real theta space, theta_p
        output: self.phi_p, self.apar_p
        :return:
        """
        n = 0  # toroidal mode number, remove the eikon function
        phi_p=np.zeros(self.n_theta+1,dtype='complex')
        apar_p = np.zeros(self.n_theta + 1, dtype='complex')
        epar_p = np.zeros(self.n_theta + 1, dtype='complex')
        epar_es_p = np.zeros(self.n_theta + 1, dtype='complex')
        epar_em_p = np.zeros(self.n_theta + 1, dtype='complex')
        theta_p=np.linspace(-np.pi,np.pi,self.n_theta+1)  # temporary theta_p, not the self.theta_p
        # for i_theta in range(self.n_theta):
        #     phi_p[i_theta]=\
        #         np.sum([np.exp(1j*n*self.q*self.theta_b[i_theta+p*self.n_theta])*\
        #             self.phi_b[i_theta+p*self.n_theta] for p in range(self.n_r)])
        #     if self.iapar==1:
        #         apar_p[i_theta]=\
        #             np.sum([np.exp(1j*n*self.q*self.theta_b[i_theta+p*self.n_theta])*\
        #                     self.apar_b[i_theta+p*self.n_theta] for p in range(self.n_r)])
        # rewrite to increase the running efficiency
        # exp_theta_b=np.exp(1j*n*self.q*self.theta_b)
        exp_theta_b=np.exp(1j*n*self.q*self.theta_b_cgyro)
        phi_p[:-1]=np.reshape(exp_theta_b*self.phi_b,(self.n_r,self.n_theta)).sum(0)
        phi_p[-1]=phi_p[0]
        f_intp=interp1d(theta_p,phi_p,'cubic')
        self.phi_p = f_intp(self.theta_p)
        # parallel electrical field
        epar_p[:-1]=np.reshape(exp_theta_b*self.epar_b,(self.n_r,self.n_theta)).sum(0)
        epar_p[-1]=epar_p[0]
        f_intp=interp1d(theta_p,epar_p,'cubic')
        self.epar_p = f_intp(self.theta_p)
        epar_es_p[:-1]=np.reshape(exp_theta_b*self.epar_es_b,(self.n_r,self.n_theta)).sum(0)
        epar_es_p[-1]=epar_es_p[0]
        f_intp=interp1d(theta_p,epar_es_p,'cubic')
        self.epar_es_p = f_intp(self.theta_p)
        if self.iapar==1:
            epar_em_p[:-1]=np.reshape(exp_theta_b*self.epar_em_b,(self.n_r,self.n_theta)).sum(0)
            epar_em_p[-1]=epar_em_p[0]
            f_intp=interp1d(theta_p,epar_em_p,'cubic')
            self.epar_em_p = f_intp(self.theta_p)
            apar_p[:-1] = np.reshape(exp_theta_b * self.apar_b, (self.n_r, self.n_theta)).sum(0)
            apar_p[-1]=apar_p[0]
            f_intp=interp1d(theta_p,apar_p,'cubic')
            self.apar_p=f_intp(self.theta_p)

    def miller_wd_s(self):
        """
        Usage: miller_wd_s(self)
        Functionality: get the self.wd1, wd2,wd3, Rs,Zs,Gq,rc_theta,l, BoverBunit,Gtheta, gcos1, gcos2, gsin, gradr, k_perp
        output: self.q_loc, self.s_loc as a function of self.theta_p
        :return:
        """
        xd=np.arcsin(self.delta)
        arg=self.theta_p+xd*np.sin(self.theta_p)
        Rs= self.Rmaj+self.rmin*np.cos(arg)  # R position
        Zs=self.kappa*self.rmin*np.sin(self.theta_p) # Z Position
    #  calculate the Jocobian
        dRdtheta=-1*self.rmin*np.sin(arg)*(1+np.cos(self.theta_p)*xd)
        dZdtheta=self.kappa*self.rmin*np.cos(self.theta_p)
        dldtheta=(dRdtheta**2+dZdtheta**2)**0.5
        dRdr=self.shift+np.cos(arg)-np.sin(self.theta_p)*np.sin(arg)*self.sdelta
        dZdr=self.kappa*np.sin(self.theta_p)*(1+self.skappa)
        det=Rs*(dRdr*dZdtheta-dRdtheta*dZdr)
    # look at grad r
        gradr=dldtheta*Rs/det
        l=integrate.cumtrapz(dldtheta,self.theta_p,initial=0)
        d2Zdtheta2=np.gradient(dZdtheta)/np.gradient(self.theta_p)
        d2Rdtheta2=np.gradient(dRdtheta)/np.gradient(self.theta_p)
        rc_theta=dldtheta**3/(dRdtheta*d2Zdtheta2-dZdtheta*d2Rdtheta2)
#        IoverBunit=2*np.pi*self.rmin/integrate.trapz(1/Rs/gradr,l) # scale
        IoverBunit=2*np.pi*self.rmin/np.trapz(1/Rs/gradr,l) # scale
        BtoverBunit=IoverBunit/Rs
        BpoverBunit=self.rmin/Rs*gradr/self.q
        BoverBunit=(BtoverBunit**2+BpoverBunit**2)**0.5
    #    geometric components
        cosu=np.gradient(Zs)/np.gradient(l)     #   dZ/dl
        sinu=-np.gradient(Rs)/np.gradient(l)    # - dR/dl
        gsin=BtoverBunit/BoverBunit*self.Rmaj/BoverBunit*np.gradient(BoverBunit)/np.gradient(l)
        gcos1=(BtoverBunit/BoverBunit)**2*self.Rmaj/Rs*cosu+(BpoverBunit/BoverBunit)**2*self.Rmaj/rc_theta
        gcos2=-1./2./BoverBunit**2*self.Rmaj*gradr*self.betastar
    # E series for mu
        E1kernel=2./Rs/gradr*BtoverBunit/BpoverBunit*(self.rmin/rc_theta-self.rmin/Rs*cosu)
        E2kernel=1./Rs/gradr*(BoverBunit/BpoverBunit)**2
        E3kernel=1./2./Rs*BtoverBunit/BpoverBunit/BpoverBunit**2
    # chang the order[0~2*pi], denoted new
        E1kernel_new=OMFITcgyro_eigen.changeorder(self,E1kernel)
        E2kernel_new=OMFITcgyro_eigen.changeorder(self,E2kernel)
        E3kernel_new=OMFITcgyro_eigen.changeorder(self,E3kernel)
        ntheta_half=int(np.round((self.n_theta_p+1)/2))
        l_new=np.zeros(self.n_theta_p)
        l_new[0:ntheta_half-1]=l[ntheta_half-1:self.n_theta_p-1]-l[ntheta_half-1]
        l_new[ntheta_half-1:self.n_theta_p-1]=l[0:ntheta_half-1]+l[ntheta_half-1]
        E1_new=integrate.cumtrapz(E1kernel_new,l_new,initial=0)
        E2_new=integrate.cumtrapz(E2kernel_new,l_new,initial=0)
        E3_new=integrate.cumtrapz(E3kernel_new,l_new,initial=0)  # in the order of 0~2*pi
    # change back to [-pi,pi]
        E1=OMFITcgyro_eigen.changeorder(self,E1_new)
        E2=OMFITcgyro_eigen.changeorder(self,E2_new)
        E3=OMFITcgyro_eigen.changeorder(self,E3_new)
        E1[0:ntheta_half-1]=E1[0:ntheta_half-1]-(E1[ntheta_half-2]+E1[ntheta_half])
        E2[0:ntheta_half-1]=E2[0:ntheta_half-1]-(E2[ntheta_half-2]+E2[ntheta_half])
        E3[0:ntheta_half-1]=E3[0:ntheta_half-1]-(E3[ntheta_half-2]+E3[ntheta_half])
        fstar=1/E2_new[-1]*(2*np.pi*self.q*self.shear/self.rmin-1/self.rmin*E1_new[-1]+self.betastar*E3_new[-1])
        THETA=Rs*BpoverBunit/BoverBunit*abs(gradr)*(1/self.rmin*E1+fstar*E2-self.betastar*E3)
        Gq=1/self.q*(self.rmin/Rs*BoverBunit/BpoverBunit)
        Gtheta=BoverBunit*Rs/self.Rmaj/self.rmin/gradr*dldtheta
    # assuming partial/partial(self.theta_p)=-i k_theta, partial/partial(r)=-i k_r
        ktheta=self.ky   # the ktheta is the kyrho_s specified in input.cgyro
        kr=0
        vpar2v=1/2  # assuming an isotropic distribution
    #  the sign here is consistent with the s-alpha geometry
    # the Rmaj exist in the denominator so that the output drift frequency has the unit of c_s/a,consistent with cgyro units
        wd1=ktheta*Gq*1*(gcos1+gcos2+THETA*gsin)/self.Rmaj
        wd2=-1*ktheta*Gq*vpar2v*gcos2/self.Rmaj
        wd3=-1*kr*1*gradr*gsin/self.Rmaj
        k_perp=(ktheta*Gq*THETA )**2+(ktheta*Gq)**2
        k_perp=k_perp**0.5
        #  the local q and magnetic shear
        IoverBp=IoverBunit/BpoverBunit
        q_loc=IoverBp/Rs**2*np.gradient(l)/np.gradient(self.theta_p)
    # solute for I' with given s
        D0_kernel=1./Rs*(2./rc_theta/Rs-2*cosu/Rs**2)*IoverBp
        D1_kernel_part=1./Rs**2.*(BoverBunit/BpoverBunit)**2        # the dI/dr is unknow yet
        D2_kernel=-1./2*1./Rs**2.*IoverBp*self.betastar/BpoverBunit**2
        D0=integrate.cumtrapz(D0_kernel,l,initial=0)
        D1_part=integrate.cumtrapz(D1_kernel_part,l,initial=0)
        D2=integrate.cumtrapz(D2_kernel,l,initial=0)
        dqdr=self.shear*self.q/self.rmin
        dIdr=(2*np.pi*dqdr-D0[-1]-D2[-1])/D1_part[-1]
        D1_kernel=1./Rs**2.*(BoverBunit/BpoverBunit)**2*dIdr
        D1=integrate.cumtrapz(D1_kernel,l,initial=0)
        # mu1=D0+D1+D2
        s_loc=self.rmin/q_loc*(D0_kernel+D1_kernel+D2_kernel)*np.gradient(l)/np.gradient(self.theta_p)
    #     get the output
        self.wd1=wd1
        self.wd2=wd2
        self.wd3=wd3
        self.k_perp=k_perp
        self.Rs=Rs
        self.Zs=Zs
        self.l=l
        self.rc_theta=rc_theta
        self.BoverBunit=BoverBunit
        self.Gq=Gq
        self.Gtheta=Gtheta
        self.gcos1=gcos1
        self.gcos2=gcos2
        self.gsin=gsin
        self.gradr=gradr
        self.THETA=THETA
        self.q_loc=q_loc
        self.s_loc=s_loc

    def changeorder(self,arr):
        # called by miller_drffreq
        n_arr=len(arr)
        arr_new=np.zeros(n_arr)
        n_arr_half=int(np.round((n_arr+1)/2))
        arr_new[0:n_arr_half-1]=arr[n_arr_half-1:n_arr-1]
    #    arr_new[n_arr_half-1:n_arr-1]=arr[0:n_arr_half-1];
        arr_new[n_arr_half-1:n_arr]=arr[0:n_arr_half]
        return arr_new

    def turn_ball2r(self,alpha_scale=0):
        """
        #   usage: turn_ball2r(self):
        #   functunality : turn the eigefunction from ballooning to r space
        #   output: self.r_arr,phi_r_arr, apar_r_arr, jpar_r_arr
        :return:
        """
        theta_bdry=min(abs(self.theta_b[0]),abs(self.theta_b[-1]))
        theta_new=np.linspace(-1*theta_bdry,theta_bdry,self.n_r*self.n_theta)
        f2_phi = interpolate.interp1d(self.theta_b, self.phi_b, kind='cubic')
        kys = self.ky * self.shear
        phi_new = f2_phi(theta_new)
        kr = theta_new * kys-alpha_scale*self.alpha*self.ky*np.sin(theta_new)
        dkr = (kr[-1] - kr[0])/(len(kr)-1)
        nkr= len(kr)
        r_arr=np.linspace(-1.*np.pi/dkr,np.pi/dkr,nkr)
        phi_r_arr = np.fft.ifft(np.fft.fftshift(phi_new))
        phi_r_arr = np.fft.fftshift(phi_r_arr)
        if self.iapar==1:
            f2_apar = interpolate.interp1d(self.theta_b, self.apar_b, kind='cubic')
            apar_new=f2_apar(theta_new)
            btheta_new=kr*apar_new
            jpar_new=(kr**2+self.ky**2)*apar_new
            apar_r_arr=np.fft.ifft(np.fft.fftshift(apar_new))
            btheta_r_arr=np.fft.ifft(np.fft.fftshift(btheta_new))
            jpar_r_arr=np.fft.ifft(np.fft.fftshift(jpar_new))
            apar_r_arr = np.fft.fftshift(apar_r_arr)
            btheta_r_arr = np.fft.fftshift(btheta_r_arr)
            jpar_r_arr = np.fft.fftshift(jpar_r_arr)
        else:
            apar_r_arr=np.zeros(nkr)
            btheta_r_arr = np.zeros(nkr)
            jpar_r_arr=np.zeros(nkr)
        self.r_arr=r_arr
        self.phi_r_arr=phi_r_arr
        self.apar_r_arr=apar_r_arr
        self.btheta_r_arr = btheta_r_arr
        self.jpar_r_arr=jpar_r_arr
        # print(self.phi_r_arr)


    def turn_ball2RZ(self,ieikon=1,box_size=4,n=2,rhos_over_a=4.e-2,n_dense=4):
        """
        Usarge: turn_ball2RZ(self,ieikon=1,box_size=4,n=2,rhos_over_a=4.e-2,n_dense=4):
        Functionality: turn the eigenfunction from ballooning space to RZ space
        Output: self.r_grid_2d, theta_grid_2d, phi_r_theta, apar_r_theta
        :param ieikon: 1
        :param box_size: 4
        :param n: 2
        :param rhos_over_a: 4.e-2
        :param n_dense: 4
        :return:
        """
        delta_r=1./self.ky/self.shear/n  # in unit of rho_s
        nr=self.n_r*box_size*n_dense
        r_arr=np.linspace(-box_size/2*delta_r,box_size/2*delta_r,nr)
        kr=self.theta_b*self.ky*self.shear
        phi_r_theta = np.zeros((self.n_theta + 1, nr), dtype='complex')  # self.n_theta=inputcgyro['N_THETA']
        epar_r_theta = np.zeros((self.n_theta + 1, nr), dtype='complex')  # self.n_theta=inputcgyro['N_THETA']
        apar_r_theta = np.zeros([self.n_theta + 1, nr], dtype='complex')
        kr = np.reshape(kr, (self.n_r, self.n_theta))
        phi_b = np.reshape(self.phi_b, (self.n_r, self.n_theta))
        epar_b = np.reshape(self.epar_b, (self.n_r, self.n_theta))
        apar_b = np.reshape(self.apar_b, (self.n_r, self.n_theta))
        theta_p_2d = np.reshape(self.theta_b, (self.n_r, self.n_theta))
        theta=np.linspace(-np.pi,np.pi,self.n_theta+1)
        if ieikon == 0:
            n=0
        exp_arg = np.exp(1j * n * self.q * theta_p_2d) * np.exp(1j * kr * r_arr[:, None, None])
        phi_r_theta[:-1] = np.sum(exp_arg * phi_b, 1).T
        phi_r_theta[-1] = phi_r_theta[0]
        epar_r_theta[:-1] = np.sum(exp_arg * epar_b, 1).T
        epar_r_theta[-1] = epar_r_theta[0]
        if self.iapar == 1:
            apar_r_theta[:-1] = np.sum(exp_arg * apar_b, 1).T
            apar_r_theta[-1]=apar_r_theta[0]
        [r_grid,theta_grid]=np.meshgrid(self.rmin/rhos_over_a+r_arr,theta)
        self.r_grid_2d=r_grid
        self.theta_grid_2d=theta_grid
        self.phi_r_theta=phi_r_theta
        self.epar_r_theta = epar_r_theta
        self.apar_r_theta=apar_r_theta

    def eigen_ave(self, imthd=1):
        """
        Functionality: eigenfunction avaraged of a given function
        Output: self.s_loc_ave, q_loc_ave, wd1_ave, k_par_ave, k_perp_ave,
               : k_perp_squal_ave, theta_width. for the linear estimation of flux
        imthd=1, the eigenfunction average is over the ballooning space
        imthd=2, the eigenfunction average is over the poloidal space
        I would suggest to look at and compare the output of both methods
        :return:
        """
        self.miller_wd_s()
        geo_fac_p = self.Gq / self.BoverBunit
        if imthd==1:
            s_loc_b =self.turn_thetap2thetab(self.s_loc)
            q_loc_b =self.turn_thetap2thetab(self.q_loc)
            wd1_b   =self.turn_thetap2thetab(self.wd1)
            Rs_b    =self.turn_thetap2thetab(self.Rs)
    #        k_perp_b   =self.turn_thetap2thetab(self.k_perp) # this is wrong
            self.get_kperp_b()
            kperp_b=self.kperp_b
            abs_phi_b=np.abs(self.phi_b)
    #        geo_fac = self.Rs / self.Rmaj/self.rmin / abs(self.gradr) * np.gradient(self.l) / np.gradient(self.theta_p)
            geo_fac_b = self.turn_thetap2thetab(geo_fac_p)
            k_par_b = 1 / q_loc_b / Rs_b * np.gradient(abs_phi_b / np.gradient(self.theta_b))
            k_par_ave = (sum(k_par_b ** 2 * geo_fac_b) / sum(geo_fac_b * abs_phi_b ** 2)) ** 0.5  # unit of 1/a
            s_loc_ave=sum(s_loc_b*abs_phi_b**2*geo_fac_b)/sum(abs_phi_b**2*geo_fac_b)
            abss_loc_ave=sum(abs(s_loc_b)*abs_phi_b**2*geo_fac_b)/sum(abs_phi_b**2*geo_fac_b)
            q_loc_ave = sum(q_loc_b * abs_phi_b ** 2 * geo_fac_b) / sum(abs_phi_b ** 2 * geo_fac_b)
            k_perp_ave = sum(kperp_b * abs_phi_b ** 2 * geo_fac_b) / sum(abs_phi_b ** 2 * geo_fac_b) #
            k_perp_squal_ave = sum(kperp_b**2 * abs_phi_b ** 2 * geo_fac_b) / sum(abs_phi_b ** 2 * geo_fac_b)  #
            wd1_ave = sum(wd1_b * abs_phi_b ** 2 * geo_fac_b) / sum(abs_phi_b ** 2 * geo_fac_b)
            # the averaged of epar comes from D.Hatch-nf-2016, and is different from other averaged algorithm
            epar_ave=np.abs(sum(self.epar_b*geo_fac_b))/(sum(np.abs(self.epar_es_b*geo_fac_b))+sum(np.abs(self.epar_em_b*geo_fac_b)))
            # apar from B.S.Pratel-achieve-2021
            apar_ave = np.abs(sum(self.apar_b * geo_fac_b)) / sum(np.abs(self.apar_b) * np.abs(geo_fac_b))  # 1 for fully tearing and 0 for no tearing
            epar_esratio_ave=sum(np.abs(self.epar_es_b*geo_fac_b))/(sum(np.abs(self.epar_es_b*geo_fac_b))+sum(np.abs(self.epar_em_b*geo_fac_b)))
            # theta_width=sum(abs_phi_b ** 2 * geo_fac_b*np.gradient(self.theta_b))/max(abs_phi_b**2)/np.mean(geo_fac_b)
            #       we may want to know the profiles of the k_par_b etc in order to debug this scritp
            # k_||*v_ti/|omega|, to represent the ion resonance effect, likely to be a slab like mode if k_||*v_ti/|omega|~1
            kparvtioveromega_ave=k_par_ave*sqrt(self.temp_1)/abs(self.omega)
#             self.s_loc_b = s_loc_b
#             self.q_loc_b = q_loc_b
#             self.wd1_b = wd1_b
#             self.kperp_b = kperp_b
#             self.abs_phi_b = abs_phi_b
# #            self.epar_ave=epar_ave
        else:
            s_loc_p=self.s_loc
            q_loc_p = self.q_loc
            wd1_p=self.wd1
            Rs_p=self.Rs
            kperp_p=self.k_perp
            self.turn_ball2theta()  # so that you got the self.phi_p
            abs_phi_p = np.abs(self.phi_p)
            k_par_p = 1 / q_loc_p / Rs_p * np.gradient(abs_phi_p / np.gradient(self.theta_p))
            k_par_ave = (sum(k_par_p ** 2 * geo_fac_p) / sum(geo_fac_p * abs_phi_p ** 2)) ** 0.5  # unit of 1/a
            s_loc_ave=sum(s_loc_p*abs_phi_p**2*geo_fac_p)/sum(abs_phi_p**2*geo_fac_p)
            abss_loc_ave=sum(abs(s_loc_p)*abs_phi_p**2*geo_fac_p)/sum(abs_phi_p**2*geo_fac_p)
            q_loc_ave = sum(q_loc_p * abs_phi_p ** 2 * geo_fac_p) / sum(abs_phi_p ** 2 * geo_fac_p)
            k_perp_ave = sum(kperp_p * abs_phi_p ** 2 * geo_fac_p) / sum(abs_phi_p ** 2 * geo_fac_p) #
            k_perp_squal_ave = sum(kperp_p**2 * abs_phi_p ** 2 * geo_fac_p) / sum(abs_phi_p ** 2 * geo_fac_p)  #
            wd1_ave = sum(wd1_p * abs_phi_p ** 2 * geo_fac_p) / sum(abs_phi_p ** 2 * geo_fac_p)
            epar_ave = sum(np.abs(self.epar_p * geo_fac_p)) / (
                        sum(np.abs(self.epar_es_p * geo_fac_p)) + sum(np.abs(self.epar_em_p * geo_fac_p)))
            apar_ave = np.abs(sum(self.apar_p * geo_fac_p)) /sum(np.abs(self.apar_p) *np.abs(geo_fac_p))
            epar_esratio_ave = sum(np.abs(self.epar_es_p * geo_fac_p)) / (
                        sum(np.abs(self.epar_es_p * geo_fac_p)) + sum(np.abs(self.epar_em_p * geo_fac_p)))
            # k_||*v_ti/|omega|, to represent the ion resonance effect, likely to be a slab like mode if k_||*v_ti/|omega|~1
            kparvtioveromega_ave=k_par_ave*sqrt(self.temp_1)/abs(self.omega)

        # theta_width will only have one definition , which is use the theta_p to define
        self.turn_ball2theta()  # so that you got the self.phi_p
        abs_phi_p = np.abs(self.phi_p)
        theta_width = sum(abs_phi_p ** 2 * geo_fac_p * np.gradient(self.theta_p)) / max(abs_phi_p ** 2) / np.mean(geo_fac_p)/np.pi
        # assign the data
        self.k_par_ave=k_par_ave
        self.q_loc_ave=q_loc_ave
        self.s_loc_ave = s_loc_ave
        self.abss_loc_ave = abss_loc_ave
        self.wd1_ave=wd1_ave
        self.k_perp_ave=k_perp_ave
        self.epar_ave=epar_ave
        self.apar_ave = apar_ave
        self.epar_esratio_ave = epar_esratio_ave
        self.k_perp_squal_ave=k_perp_squal_ave
        self.theta_width=theta_width
        self.kparvtioveromega_ave=kparvtioveromega_ave


    def turn_thetap2thetab(self,value):
        """
        # turn one value from theta_p space to theta_b space, which is used in the function eigen_ave
        """
        if len(value)!=len(self.theta_p):
            raise Exception('len(value)=len(theta_p) is required!')
        theta_bb=np.linspace(-np.pi,np.pi,self.n_theta+1)  # we will use the theta_bb to represent the ballooning angle in [-pi,pi]
        value_bb=np.interp(theta_bb,self.theta_p,value)
        value_b=np.zeros([self.n_r,self.n_theta])
        for k in np.arange(0,self.n_r):
            value_b[k,:]=value_bb[0:-1]
        value_b=np.reshape(value_b,[self.n_r*self.n_theta])
        return value_b

    def get_kperp_b(self):
        # get the k_perp in the ballooning space
        self.miller_wd_s()
        theta_bb=np.linspace(-np.pi,np.pi,self.n_theta+1)
        THETA_bb=np.interp(theta_bb,self.theta_p,self.THETA)
        gradr_bb=np.interp(theta_bb,self.theta_p,self.gradr)
        Gq_bb=np.interp(theta_bb,self.theta_p,self.Gq)
        kperp_b=np.zeros((self.n_r,self.n_theta),dtype='float')
        if np.mod(self.n_r,2)==0:
            p_arr=np.arange(-1*self.n_r//2,self.n_r//2)
        else:
            p_arr=np.arange(-1*(self.n_r-1)//2,(self.n_r-1)//2+1)
        kys=self.ky*self.shear
#        print(p_arr)
        for k in np.arange(self.n_r):
            p=p_arr[k]
            kx_2=(kys*2*np.pi*p*gradr_bb+self.ky*Gq_bb*THETA_bb)**2
            kperp_2=kx_2+(self.ky*Gq_bb)**2
            kperp=kperp_2**0.5
            kperp_b[k]=kperp[0:-1]
        kperp_b=np.reshape(kperp_b,[self.n_r*self.n_theta])
        self.kperp_b=kperp_b

    def get_flux_lin(self,C_lin=5):
        # get the flux estimated like Q_i=theta_width*gamma/k_perp^2, motivated by M.Kothereuter's work
        self.eigen_ave()
        self.flux_lin=C_lin*self.theta_width*self.gamma/self.k_perp_squal_ave

    def get_phi_n_ratio(self,theta=0, i_field=0,i_species=-1, moment='n'):
        """
        Usage: get_phi_n_ratio(self)
        functionality: get the ratio of ephi/Te over delta_n/n from the linear run
        output: self.phi_n_ratio
        :return:
        """
        norm = 'elec'
        self.getbigfield()
        self.getnorm(norm);
        t = self.tnorm
        f_phi, ft_phi = self.kxky_select(theta, i_field, 'phi', 0)
        p_phi = np.sum(abs(f_phi[:, :, :]), axis=0)# / self.rhonorm
        f_n, ft_n = self.kxky_select(theta, i_field, moment, i_species)
        p_n = np.sum(abs(f_n[:, :, :]), axis=0)# / self.rhonorm
        self.phi_n_ratio=p_phi[0,-1]/p_n[0,-1]  # 0: toroidal mode index; -1: time index

idimrun=root['SETTINGS']['SETUP']['idimrun']
dirname_arr=[];
if idimrun==1:
    for paraval_item in para_eigen:
        for ky_item in ky_eigen:
            datanode=root['OUTPUTScan'][Para][num2str_xj(paraval_item,effnum)]['lin'][num2str_xj(ky_item,effnum)]
            #datanode=OMFIT['OUTPUTS-CFETRphi']['nr=11']['lin']['1.00000']
            dirname='a'
            print('a')
            dirname=Para+'_'+num2str_xj(paraval_item,effnum)+'~ky_'+num2str_xj(ky_item,effnum)
            if isinstance(datanode,OMFITtree):
                datanode.deploy(deploypath+dirname)
                mounttree[dirname]=OMFITcgyro_eigen(deploypath+dirname)
            else:
                # mounttree[dirname]=copy.deepcopy(datanode)
                mounttree[dirname]=OMFITcgyro_eigen(datanode.filename)
            dirname_arr.append(dirname)
else:
    for para_x_item in para_x_eigen:
        for para_y_item in para_y_eigen:
            for ky_item in ky_eigen:
                datanode=root['OUTPUTScan'][Para_x][num2str_xj(para_x_item,effnum)][Para_y][num2str_xj(para_y_item,effnum)]['lin'][num2str_xj(ky_item,effnum)]
                dirname=Para_x+'_'+num2str_xj(para_x_item,effnum)+'~'+Para_y+'_'+num2str_xj(para_y_item,effnum)+'~ky_'+num2str_xj(ky_item,effnum)
                if isinstance(datanode,OMFITtree):
                    datanode.deploy(deploypath+dirname)
                    mounttree[dirname]=OMFITcgyro_eigen(deploypath+dirname)
                else:
                    # mounttree[dirname]=copy.deepcopy(datanode)
                    mounttree[dirname]=OMFITcgyro_eigen(datanode.filename)
                dirname_arr.append(dirname)
root['SETTINGS']['PLOTS']['dirname']=dirname_arr
