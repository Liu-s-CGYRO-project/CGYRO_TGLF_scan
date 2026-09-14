# 99949 version.
import sys
import os

# Set this env var to "1" before importing collect to load only class/function definitions.
_COLLECT_IMPORT_ONLY = os.environ.get('CGYRO_COLLECT_IMPORT_ONLY', '0') == '1'

if (not _COLLECT_IMPORT_ONLY) and ('root' in globals()):
    with open(root['PLOTS']['CGYROalone']['assist']['getglobal.py'].filename, 'r') as _helper_source:
        exec(compile(_helper_source.read(), _helper_source.name, 'exec'), globals())

# this is a class inherient from OMFITcgyro_base
# this script will mostly focus on handling the nonlinear CGYRO object
import numpy as np
from scipy import integrate
from scipy.interpolate import interp1d
from scipy.special import j0
from omfit_classes.omfit_gacode import OMFITcgyro

class OMFITcgyro_nonlin(OMFITcgyro):
    """
    Class used for handling the nonlinear behaviors, functions included:
    get_flux_n, get_phi_n, get_quasiweight_n,
    """
    def __init__(self,filename=None,extra_files=[],test_mode=False,window=0.3,t_end=1):
        OMFITcgyro.__init__(self,filename,extra_files,test_mode)
        print('You have entered OMFITcgyro_nonlin!')
        # get the background parameters
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
        alpha=np.sum([inputcgyro['DENS_'+str(m)]*inputcgyro['TEMP_'+str(m)]*\
              (inputcgyro['DLNNDR_'+str(m)]+inputcgyro['DLNTDR_'+str(m)]) for m in np.arange(1,inputcgyro['N_SPECIES']+1) ])
        alpha=alpha*inputcgyro['BETAE_UNIT']*inputcgyro['Q']**2*inputcgyro['RMAJ']
        self.alpha=alpha*inputcgyro['BETA_STAR_SCALE']  # this parameter will be used
        self.betastar=self.alpha/self.q**2/self.Rmaj
        # resolution parameters
        self.n_theta=inputcgyro['N_THETA']
        self.ky=abs(self['kyrhos'])    #note that we will always use positive kyrhos, regardless of IPCCW&BTCCT
        self.n_n=self['n_n']
        if self.n_n>1:
            self.dky = abs(self.ky[1]-self.ky[0])
        else:
            self.dky=abs(self.ky[0])
        self.kx = self['kxrhos']
        self.n_r=self['n_r']
#        if not len(self.kx)==self.n_r: # to deal with some case that len(self.kx)=n_r-1, which is not correct
#           self.kx=linspace(self.kx[0],self.kx[-1],self.n_r)
        self.dkx = abs(self.kx[1]-self.kx[0])
        self.t=self['t']
        self.n_time=self['n_time']
        # others
        self.field_tags=self['field_tags']
        self.n_field=self['n_field']
        self.species_tags=self['species_tags']
        self.n_species=self['n_species']
        # time averaging related
        self.n_theta_plot = self['theta_plot']
        if self.n_theta_plot==1:
            self.ftheta_plot=array([0.,0.])
        else:
            self.ftheta_plot=np.linspace(-np.pi,np.pi,self.n_theta_plot+1)
        self.window=window
        self.ind_t_ave=np.arange(int((t_end-window)*self.n_time),int(self.n_time*t_end))
        n_ind_temp=len(self.ind_t_ave)
        n_precies=10
        self.ind_t_ave = np.arange(int(self.n_time * t_end)-int(n_precies*ceil(n_ind_temp/n_precies)), int(self.n_time * t_end))  # sparse outline
        # also add a function on fluctuating issues, which is very time consuming
        self.getbigfield()
        self.phi_cmplx_t = self.kxky_phi[0, :, :, :, :] + 1j * self.kxky_phi[1, :, :, :,:]  # phi_cmplx[i_r,i_theta_plot,i_n,self.ind_t_ave]), includes the time dynamics
        if self.n_field>1:
            self.apar_cmplx_t = self.kxky_apar[0, :, :, :, :] + 1j * self.kxky_apar[1, :, :, :, :]
        if self.n_field>2:
            self.bpar_cmplx_t = self.kxky_bpar[0, :, :, :, :] + 1j * self.kxky_bpar[1, :, :, :, :]

# some assist functions
    def changeorder(self, arr):
        # called by miller_drffreq
        n_arr = len(arr)
        arr_new = np.zeros(n_arr)
        n_arr_half = int(np.round((n_arr + 1) / 2))
        arr_new[0:n_arr_half - 1] = arr[n_arr_half - 1:n_arr - 1]
        #    arr_new[n_arr_half-1:n_arr-1]=arr[0:n_arr_half-1];
        arr_new[n_arr_half - 1:n_arr] = arr[0:n_arr_half]
        return arr_new

    # some assist functions
    def fft_jian(self, tt, yt):
        """Return signed angular FFT frequencies and the normalized complex spectrum."""
        tt, yt = np.asarray(tt, dtype=float), np.asarray(yt)
        if tt.ndim != 1 or yt.ndim != 1 or len(tt) != len(yt) or len(tt) < 2:
            raise ValueError('FFT requires matching one-dimensional arrays with at least two samples')
        steps = np.diff(tt)
        dt = steps[0]
        if not np.all(np.isfinite(tt)) or dt <= 0 or not np.allclose(steps, dt, rtol=1e-6, atol=abs(dt)*1e-9):
            raise ValueError('FFT requires finite, increasing, uniformly sampled times')
        if not np.all(np.isfinite(yt)):
            raise ValueError('FFT signal contains non-finite samples')
        w = 2.0 * np.pi * np.fft.fftshift(np.fft.fftfreq(len(yt), d=dt))
        yw = np.fft.fftshift(np.fft.fft(yt)) / len(yt)
        return w, yw
    # return the index of the value which is the closest to the target flux
    def find_index(self, arr, target):
        left, right = 0, len(arr) - 1
        while left <= right:
            mid = (left + right) // 2
            if arr[mid] == target:
                return mid
            elif arr[mid] < target:
                left = mid + 1
            else:
                right = mid - 1
        if left==0:
            return 0
        if left == len(arr):
            return len(arr) - 1
        if abs(arr[left] - target) < abs(arr[left - 1] - target):
            return left
        return left - 1


    def get_flux_t(self,i_field=0,i_species=0):
        """
        Usage: get_flux_n(self)
        functionality: get the time averaged flux for all channels versus time
        output: self.Gamma_t, Q_t, Pi_t, Gamma_t_ave, Q_t_ave, Pi_t_ave
        :return:
        """
        flux_t=self['flux_t']
        # use i_field<0 to do the sum
        if i_field<0:
            Gamma_t = flux_t['particle'].isel(species=i_species).sum(axis=0)
            Q_t = flux_t['energy'].isel(species=i_species).sum(axis=0)
            Pi_t = flux_t['momentum'].isel(species=i_species).sum(axis=0)
        else:
            Gamma_t = flux_t['particle'].isel(species=i_species,field=i_field)
            Q_t     = flux_t['energy'].isel(species=i_species, field=i_field)
            Pi_t    = flux_t['momentum'].isel(species=i_species, field=i_field)
        self.Gamma_t=Gamma_t
        self.Q_t=Q_t
        self.Pi_t=Pi_t
        self.Gamma_t_ave=self.Gamma_t[self.ind_t_ave].mean().data
        self.Q_t_ave = self.Q_t[self.ind_t_ave].mean().data
        self.Pi_t_ave = self.Pi_t[self.ind_t_ave].mean().data
        self.Gamma_t_std=self.Gamma_t[self.ind_t_ave].std().data
        self.Q_t_std = self.Q_t[self.ind_t_ave].std().data
        self.Pi_t_std = self.Pi_t[self.ind_t_ave].std().data

    def get_flux_n(self,i_field=0,i_species=0):
        """
        Usage: get_flux_n(self)
        functionality: get the time averaged flux for all kinetic channels versus n
        output: self.Gamma_n_ave,self.Q_n_ave, self_Pi_n_ave
        :return:
        """
        flux_n=self['flux_ky']
        if i_field<0:
            Gamma_n_ave=flux_n['particle'].isel(species=i_species,t=self.ind_t_ave).sum(axis=0).mean(axis=1).data
            Q_n_ave = flux_n['energy'].isel(species=i_species,  t=self.ind_t_ave).sum(axis=0).mean(axis=1).data
            Pi_n_ave = flux_n['momentum'].isel(species=i_species,  t=self.ind_t_ave).sum(axis=0).mean(axis=1).data
        else:
            Gamma_n_ave=flux_n['particle'].isel(species=i_species,field=i_field,t=self.ind_t_ave).mean(axis=1).data
            Q_n_ave = flux_n['energy'].isel(species=i_species, field=i_field, t=self.ind_t_ave).mean(axis=1).data
            Pi_n_ave = flux_n['momentum'].isel(species=i_species, field=i_field, t=self.ind_t_ave).mean(axis=1).data
        self.Gamma_n_ave=Gamma_n_ave/self.dky
        self.Q_n_ave=Q_n_ave/self.dky
        self.Pi_n_ave=Pi_n_ave/self.dky

    def get_quasiweight_n(self,i_field=0,i_species=0):
        """
        Usage: get_quasiweight_n(self,i_field.i_species)
        functionality: get the quasi-linear weight versu n, the quasilinear weight is flux/dky/phi^2
        output: self.quasiweight_Gamma,self.quasiweight_Q,self.quasiweight_Pi
        :return:
        """
        self.get_flux_n(i_field,i_species)
        self.get_phi_n(i_field, i_species)
        self.quasiweight_Gamma=self.Gamma_n_ave/self.dky/self.phi_n_ave
        self.quasiweight_Q = self.Q_n_ave /self.dky/ self.phi_n_ave
        self.quasiweight_Pi = self.Pi_n_ave /self.dky/ self.phi_n_ave

    def get_freq_n(self):
        """
        Usage: get_freq_n(self)
        functionality: get frequency  versus n
        output: self.freq_n
        :return:
        """
        self.freq_n=self['freq']['omega'].isel(t=self.ind_t_ave).mean(axis=1)


    # def get_phi_freq(self,i_theta_plot=self.n_theta_plot//2+1,i_r=self.n_r//2,i_n=3):
    def get_phi_freq(self,i_theta_plot=1,i_r=1,i_n=3,i_field=0):
        """
        Usage: get_phi(i_theta_plot=self.n_theta_plot//2+1,i_r=self.n_r//2,i_n=2)
        functionality: get phi plot on different dimensions
        phi_omega: for a given (i_theta_plot,i_r,i_n)   # 1D: frequency spectrum
        phi_kx_omega: for a given (i_theta_plot, i_n)   # 2D:over kx and freq
        phi_ky_omega: for a given (i_theta_plot)        # 2D: averaged over kx
        phi_ithetaplot_omega: for a given(i_n)          # 2D: kx averaged
        :return:
        """
        # self.getbigfield()
        t_ft=self.t[self.ind_t_ave]   # the time series for doing the fourier transform, ft is short for fourier transform
        n_t_ft=len(self.ind_t_ave)
        ## caution, don't write to be : phi_cmplx = casek.kxky_phi[0, :, :, :, case.t_ind_ave] + 1j * casek.kxky_phi[1, :, :, :, case.t_ind_ave]
        if i_field==0:
            phi_cmplx=self.kxky_phi[0,:,:,:,:]+1j*self.kxky_phi[1,:,:,:,:]
        elif i_field==1:
            phi_cmplx=self.kxky_apar[0,:,:,:,:]+1j*self.kxky_apar[1,:,:,:,:]
        else:
            phi_cmplx = self.kxky_bpar[0, :, :, :, :] + 1j * self.kxky_bpar[1, :, :, :, :]
        # get the frequency phi_omega
        omega_ft, phi_omega= OMFITcgyro_nonlin.fft_jian(self,t_ft,phi_cmplx[i_r,i_theta_plot,i_n,self.ind_t_ave])
        self.omega_ft=omega_ft  # the omega_ft is determined by the time series that we choose
        self.phi_omega=phi_omega
        # get the frequency phi_kx_omega
        phi_kx_omega = np.zeros([self.n_r, n_t_ft],dtype='complex')
        for i_rr in range(self.n_r):
            data = phi_cmplx[i_rr, i_theta_plot, i_n, self.ind_t_ave]
            omega, phi_kx_omega[i_rr, :] =  OMFITcgyro_nonlin.fft_jian(self,t_ft, data)
        kx_omega_grid, omega_kx_grid = np.meshgrid(self.kx,omega)
        self.kx_omega_grid = kx_omega_grid
        self.omega_kx_grid=omega_kx_grid
        self.phi_kx_omega=phi_kx_omega
#        contourf(kx_omega_grid, omega_kx_grid, abs(phi_kx_omega).T)
        # get the phi_ky_omega & phi_ky_omega_kx0
        i_r_kx0 = list(self.kx).index(0)  # find the index of kx=0
        phi_ky_omega = np.zeros([self.n_n, n_t_ft], dtype='complex')
        phi_ky_omega_kx0 = np.zeros([self.n_n, n_t_ft], dtype='complex')
        phi_kx_omegaa = np.zeros([self.n_r, n_t_ft], dtype='complex')
        for i_nn in np.arange(self.n_n):
            for i_rr in np.arange(self.n_r):
                data = phi_cmplx[i_rr, i_theta_plot, i_nn, self.ind_t_ave]
                omega, phi_kx_omegaa[i_rr, :] =  OMFITcgyro_nonlin.fft_jian(self,t_ft, data)
                phi_f = np.sum(phi_kx_omegaa, axis=0)
                phi_f_kx0 = phi_kx_omegaa[i_r_kx0,:]
                phi_ky_omega[i_nn] = phi_f  / max(abs(phi_f))  # will be normalized
                phi_ky_omega_kx0[i_nn] = phi_f_kx0 / max(abs(phi_f_kx0))  # will be normalized
        ky_omega_grid, omega_ky_grid = np.meshgrid(self.ky, omega)
        # contourf(ky_omega_grid, omega_ky_grid, abs(phi_ky_omega).T)  # can be compared to the linear/nonlinear frequency
        self.ky_omega_grid=ky_omega_grid
        self.omega_ky_grid=omega_ky_grid
        self.phi_ky_omega=phi_ky_omega
        self.phi_ky_omega_kx0 = phi_ky_omega_kx0
        # get the phi_ithetaplot_omega & phi_ithetaplot_omega_kx0 for a given i_n
        phi_ithetaplot_omega = np.zeros([self.n_theta_plot, n_t_ft],dtype='complex')
        phi_ithetaplot_omega_kx0 = np.zeros([self.n_theta_plot, n_t_ft], dtype='complex')
        for i_theta_plott in np.arange(self.n_theta_plot):
            for i_rr in np.arange(self.n_r):
                data = phi_cmplx[i_rr, i_theta_plott, i_n, self.ind_t_ave]
                omega, phi_kx_omegaa[i_rr, :] = OMFITcgyro_nonlin.fft_jian(self,t_ft, data)
                phi_f = sum(phi_kx_omegaa, axis=0)
                phi_f_kx0 = phi_kx_omegaa[i_r_kx0,:]
                phi_ithetaplot_omega[i_theta_plott] = phi_f #/max(abs(phi_f))  # will not be normalized to show the strength over poloidal plane
                phi_ithetaplot_omega_kx0[i_theta_plott] = phi_f_kx0  # /max(abs(phi_f))
        ftheta_plot = self.ftheta_plot[0:-1]
        ftheta_omega_grid, omega_ftheta_grid = np.meshgrid(ftheta_plot, omega)
        self.ftheta_omega_grid=ftheta_omega_grid
        self.omega_ftheta_grid=omega_ftheta_grid
        self.phi_ithetaplot_omega=phi_ithetaplot_omega
        self.phi_ithetaplot_omega_kx0 = phi_ithetaplot_omega_kx0
        # contourf(theta_omega_grid, omega_theta_grid, abs(phi_ithetaplot_omega).T)
        # get the omega_ky by averaged over phi from phi_ky_omega
        omega_n = np.zeros(self.n_n)
        for i_nn in np.arange(self.n_n):
            omega_n[i_nn] = np.sum(abs(self.phi_ky_omega[i_nn]) * self.omega_ft) / np.sum(abs(self.phi_ky_omega[i_nn]))
        self.omega_n=omega_n

    def get_kxky_phi(self, i_theta_plot=1):
        """Average amplitude over time, then over ky, retaining the kx axis."""
        field = self.phi_cmplx_t[:, i_theta_plot, :, :]
        if field.shape[0] == len(self.kx) + 1:
            field = field[1:]
        if field.shape[:2] != (len(self.kx), len(self.ky)):
            raise ValueError('Field spectrum does not match the kx/ky coordinates')
        phi_cmplx = np.take(field, self.ind_t_ave, axis=-1)
        if phi_cmplx.shape[-1] == 0:
            raise ValueError('Time averaging window is empty')
        self.kxky_phi_avet = np.mean(np.abs(phi_cmplx), axis=-1)
        self.kx_phi_avetky = np.mean(self.kxky_phi_avet, axis=-1)

    def get_kx_ky(self, i_field=0, i_theta_plot=1):
        """Compute the amplitude-weighted spectral width independently at each ky."""
        if i_field not in (0, 1, 2):
            raise ValueError('i_field must be 0, 1 or 2')
        field = getattr(self, ('phi_cmplx_t', 'apar_cmplx_t', 'bpar_cmplx_t')[i_field])
        field = field[:, i_theta_plot, :, :]
        selected = np.take(field, self.ind_t_ave, axis=-1)
        if selected.shape[-1] == 0:
            raise ValueError('Time averaging window is empty')
        amplitude = np.mean(np.abs(selected), axis=-1)
        kx = np.asarray(self.kx, dtype=float)
        ky = np.asarray(self.ky, dtype=float)
        # CGYRO output may retain one extra Nyquist entry before the stored kx grid.
        if amplitude.shape[0] == len(kx) + 1:
            amplitude = amplitude[1:]
        if amplitude.shape != (len(kx), len(ky)):
            raise ValueError('Field spectrum does not match the kx/ky coordinates')
        weight = amplitude ** 2
        total = np.sum(weight, axis=0)
        kx0 = np.divide(np.sum(kx[:, None] * weight, axis=0), total,
                        out=np.full(len(ky), np.nan), where=total > 0)
        variance = np.divide(np.sum((kx[:, None] - kx0[None, :])**2 * weight, axis=0),
                             total, out=np.full(len(ky), np.nan), where=total > 0)
        self.kx0 = kx0
        self.kx_rms = np.sqrt(np.maximum(variance, 0))
        self.kx_over_ky = np.divide(self.kx_rms, ky, out=np.full(len(ky), np.nan),
                                    where=(ky != 0) & (total > 0))
        self.kx_over_ky_valid = (ky != 0) & (total > 0) & np.isfinite(self.kx_over_ky)


    def get_phi_n(self,i_field=0,theta=0,i_n=1):
        """
        Usage: get_phi_n(self,i_field,theta=0)
        functionality: get the time averaged fluctuation amplitude versus n
        output: self.phi_n_ave
        This is abs(phi), not phi^2
        theta is in unit of phi ,should be in the range of [-1,1],
        theta=0 (-1/1) :the outboard/inboard midplane
        :return:
        """
        # self.getbigfield()
#        moment='phi'
#        fk,ftk = self.kxky_select(theta,i_field,moment,0) # ft[i_r,i_n,i_t]
        itheta=self.find_index(self.ftheta_plot,theta)
        if i_field==0:
            fk=self.phi_cmplx_t[1:,itheta,:,:] ## phi_cmplx[i_r,i_theta_plot,i_n,self.ind_t_ave])
        elif i_field==1:
            fk = self.apar_cmplx_t[1:, itheta, :, :]
        else:
            fk = self.bpar_cmplx_t[1:, itheta, :, :]
        phi_ave_t=np.mean(abs(fk[:,:,self.ind_t_ave]),axis=-1)/self.rho  # for phi over ky
        phi_m_ave = np.sum(phi_ave_t, axis=-1)
        phi_n_ave = np.sum(phi_ave_t, axis=0)
        phi_n_overkx = phi_ave_t.T[i_n]
        self.phi_n_ave=phi_n_ave
        self.phi_m_ave = phi_m_ave
        self.phi_n_overkx=phi_n_overkx

    def get_npv_n(self,theta=0,i_n=1, i_species=-1, i_moment=0):
        """
        Usage: get_npv_n(self,i_field,theta=0)
        functionality: get the time averaged intensity of fluctuating density/pressure/velocity versus toroidal mode number
        i_moment: 0: den; 1: pressure; 2: v
        output: self.den_n_ave, self_p_ave, self_v_ave
        theta is in unit of phi ,should be in the range of [-1,1],
        theta=0 (-1/1) :the outboard/inboard midplane
        :return:
        """
        # self.getbigfield()
        moment_arr={0:'n', 1: 'e', 2:'v'}
        moment=moment_arr[i_moment]
        fk,ftk = self.kxky_select(theta,0,moment, i_species) # ft[i_r,i_n,i_t]
        npv_ave_t=np.mean(abs(fk[:,:,self.ind_t_ave]),axis=-1)/self.rho  # for phi over ky
        npv_m_ave = np.sum(npv_ave_t, axis=-1)
        npv_n_ave = np.sum(npv_ave_t, axis=0)
        npv_n_overkx = npv_ave_t.T[i_n]
        self.npv_n_ave=npv_n_ave
        self.npv_m_ave = npv_m_ave
        self.npv_n_overkx=npv_n_overkx
    
    def get_zonal_pro(self,theta=0, i_species=-1, i_moment=0,imthd=0,kx_pvt=0.05,ishape=1,k0=5):
        """
        Usage: get_zonal_pro(self, i_species=-1, i_moment=0)
        Functionality: get the time averaged zonal profiles in both the k and x space
        density, velocity and pressure are normalized to n*rho_norm, n*V*rho_norm and n*T*rho_norm, respectively
        """
        moment_arr={0:'n', 1: 'e', 2:'v'}
        moment=moment_arr[i_moment]
        if imthd==0:
            #kxky_select(self,theta,field,moment,species,gbnorm=False):
            fk = self.kxky_select(theta,0,moment,i_species) # ft[i_r,i_n,i_t]
        else:
            self.getbigfield()
            theta_in_code=self.ftheta_plot.flat[np.abs(self.ftheta_plot-theta).argmin()]
            itheta=where(self.ftheta_plot==theta_in_code)[0][0]
#            itheta=find_index(self.ftheta_plot,theta)
            if moment=='n':
                fk = self.kxky_n[0,1:,itheta,i_species,:,:]+1j*self.kxky_n[1,1:,itheta,i_species,:,:]
            elif moment=='e':
                fk = self.kxky_e[0,1:,itheta,i_species,:,:]+1j*self.kxky_e[1,1:,itheta,i_species,:,:]
            else:
                fk = self.kxky_v[0,1:,itheta,i_species,:,:]+1j*self.kxky_v[1,1:,itheta,i_species,:,:]
#        pro_k=np.mean(fk[:,0,self.ind_t_ave],axis=-1)/self.rho  # for zonal profiles in the k space
        pro_k=np.mean(fk[:,0,self.ind_t_ave],axis=-1)  # for zonal profiles in the k space
        if ishape==1:
            shape_func=np.exp(-k0* np.maximum(np.abs(self.kx) - kx_pvt, 0))
            pro_k=shape_func*pro_k
        dkxrhos=self.kx[1]-self.kx[0]

        x=linspace(-np.pi/dkxrhos,np.pi/dkxrhos,len(self.kx)) # in unit of rhos
        dx=x[1]-x[0]
        pro_x=np.fft.ifftshift(pro_k)
        pro_x=np.fft.ifft(pro_x)
        pro_x=np.fft.fftshift(pro_x)
        pro_x=pro_x*dkxrhos*2*pi  # normalization to keep the total energy conserved
        # check whether the energy is conserved or not
        energy_x=sum(abs(pro_x)*dx)
        energy_k=sum(abs(pro_k)*dkxrhos)
        energy_diff=abs(energy_x-energy_k)/abs(energy_x)
#        self.kxrhos=kxrhos # used when self.n_r!=len(self.kx)
        self.x=x
        self.pro_k=pro_k
        self.pro_x=pro_x
        self.energy_diff=energy_diff  # a diagnostic to see whether the energy is conserved in the fourier transform

    def get_stress(self,theta=0, i_species=0):
        """
        Usage: get_stress(self, theta=0, i_species=0)
        Functionality: get_stress(self,theta=0, i_species=0)
        """
        self.getbigfield()
        theta_in_code=self.ftheta_plot.flat[np.abs(self.ftheta_plot-theta).argmin()]
        itheta=where(self.ftheta_plot==theta_in_code)[0][0]
        phi_stress_cmplx= self.stress_phi[0,1:,itheta,i_species,:,:]+1j*self.stress_phi[1,1:,itheta,i_species,:,:]
        apar_stress_cmplx= self.stress_apar[0,1:,itheta,i_species,:,:]+1j*self.stress_apar[1,1:,itheta,i_species,:,:]
        bpar_stress_cmplx= self.stress_bpar[0,1:,itheta,i_species,:,:]+1j*self.stress_bpar[1,1:,itheta,i_species,:,:]
        self.phi_stress_cmplx=phi_stress_cmplx
        self.apar_stress_cmplx=apar_stress_cmplx
        self.bpar_stress_cmplx=bpar_stress_cmplx


    def get_zonal_field(self,theta=0,field=0,imthd=0,kx_pvt=0.05,ishape=1,k0=5):
        """
        Usage: get_zonal_field(self,theta=0,field=0)
        functionality: get the zonal_field, including phi, apar/B_theta and bpar in both k and x space
        """
        #kxky_select(self,theta,field,moment,species,gbnorm=False):
        if imthd==0:
            fk = self.kxky_select(theta,field,'phi',0) # ft[i_r,i_n,i_t]
        else:
            theta_incode=self.ftheta_plot.flat[np.abs(self.ftheta_plot-theta).argmin()] 
            ind_theta=where(self.ftheta_plot==theta_incode)[0][0]
#            ind_theta=find_index(self.ftheta_plot, theta)
            if field==0:
                fk=self.phi_cmplx_t[1:,ind_theta,:,:]   # fk[i_r,i_n,i_t]
            elif field==1:
                fk=self.apar_cmplx_t[1:,ind_theta,:,:]   # fk[i_r,i_n,i_t]
            else:
                fk=self.bpar_cmplx_t[1:,ind_theta,:,:]   # fk[i_r,i_n,i_t]
        field_k=np.mean(fk[:,0,self.ind_t_ave],axis=-1)/self.rho  # for zonal field in the k space
        if ishape==1:
            shape_func=np.exp(-k0* np.maximum(np.abs(self.kx) - kx_pvt, 0))
            field_k=field_k*shape_func
        dkxrhos=self.kx[1]-self.kx[0]
        x=linspace(-pi/dkxrhos,pi/dkxrhos,len(self.kx)) # in unit of rhos
        dx=x[1]-x[0]
        field_x=np.fft.ifftshift(field_k)
        field_x=np.fft.ifft(field_x)
        field_x=np.fft.fftshift(field_x)
        field_x=field_x*dkxrhos*2*pi  # normalization to keep the total energy conserved
        # check whether the energy is conserved or not
        energy_x=sum(abs(field_x)*dx)
        energy_k=sum(abs(field_k)*dkxrhos)
        energy_diff=abs(energy_x-energy_k)/abs(energy_x)
        B_theta_k=zeros(self.n_r)
        B_theta_x=zeros(self.n_r)
        if field==1:
            B_theta_k=(-1j)*self.kx*field_k
            if ishape==1:
                B_theta_k=B_theta_k*shape_func
            B_theta_x=np.fft.ifftshift(B_theta_k)
            B_theta_x=np.fft.ifft(B_theta_x)
            B_theta_x=np.fft.fftshift(B_theta_x)
            B_theta_x=B_theta_x*dkxrhos*2*pi  # normalization to keep the total energy conserved
        self.x=x
        self.field_k=field_k
        self.field_x=field_x
        self.B_theta_k=B_theta_k
        self.B_theta_x=B_theta_x
        self.energy_diff=energy_diff  # a diagnostic to see whether the energy is conserved in the fourier transform

    def get_zfshear(self,i_theta_plot=1):
        """
        Usage: get_zfshear(i_theta_plot=1)
        functionality: get the zonal flow shearing rate at differnet poloidal places &
         zonal flow kx spectrum for a given poloidal space
        :return:
        """
        phi_cmplx=self.phi_cmplx_t#/self.rho#phi_cmplx[i_r,i_theta_plot,i_n,self.ind_t_ave])
        zf_shear=np.zeros(self.n_theta_plot)
        for i_theta_plott in np.arange(self.n_theta_plot):
            zf_cmplx=phi_cmplx[1:,i_theta_plott,0,self.ind_t_ave]
            zf_kx=np.mean(abs(zf_cmplx),axis=-1) # average over the time window
            if i_theta_plott == i_theta_plot:
                self.zf_kx=zf_kx
                self.gamma_zf=self.kx**2*zf_kx/self.rho/self.dkx  # in unit of cs/a, confirmed in 2024-Sep
            # zf_shear[i_theta_plott]=sum(self.kx**2*zf_kx*self.dkx)**0.5
            zf_shear[i_theta_plott]=sum(self.kx**2*zf_kx)/self.rho
        self.zf_shear=zf_shear  # sum gamma_zf over kx

    def get_shear_stress(self,theta=0):
        """
        :param theta:
        :return:
        the shear stress(S_stress) across ky_arr, shear address is defined in Candy-PPCF-2007, secion 3.2
        """
        moment='phi'
        i_field=0
        fk,ftk = self.kxky_select(theta,i_field,moment,0) # ft[i_r,i_n,i_t]
        phi_ave_t=np.mean(abs(fk[:,:,self.ind_t_ave]),axis=-1)
        phi_norm=phi_ave_t/self.dkx
        S_stress=np.zeros(self.n_n) # shear stress
        sign=-1;
        for k_n in np.arange(self.n_n):
            S_stress[k_n]=abs(sum((self.ky[k_n]**2+sign*self.kx**2)*abs(phi_norm[:,k_n])))*self.dkx
        self.S_stree=S_stress/self.rho  # has the unit of c_s/a


    def get_ReyMaxStress(self,i_theta_plot=0):
    #     Calculate the Reynold stress and Maxwell Stress
    #     self.getbigfield()
        phi_cmplx = self.phi_cmplx_t[1:,i_theta_plot,:,:]   # phi_cmplx[i_r,i_theta_plot,i_n,self.ind_t_ave])
        apar_cmplx = self.apar_cmplx_t[1:,i_theta_plot,:,:]   # phi_cmplx[i_r,i_theta_plot,i_n,self.ind_t_ave])
        betaE=self['input.cgyro.gen']['BETAE_UNIT']         # the betaE in the input.cgyro.gen
        phi_cmplx=phi_cmplx/self.rho
        apar_cmplx=apar_cmplx/self.rho
        kx_arr=self.kx#[1:]
        kxmax=kx_arr[-1]
        kx0_arr=kx_arr   # kx of zonal components
        nkx=len(kx_arr)
        dkx=kx0_arr[1]-kx0_arr[0]
        ky_arr=self.ky#[1:]
        nky=len(ky_arr)
        len_ind_t_ave=len(self.ind_t_ave)
        # construct the meshgrid
        kx_grid, ky_grid = np.meshgrid(kx_arr, ky_arr, indexing='ij')
        # calculate the dkx to for indices
#        dkx = (2 * kxmax) / (nkx - 1)
        dkx = kx_arr[1]-kx_arr[0]
        stress_denominator = 1 - j0(kx0_arr)**2
        stress_valid = np.abs(stress_denominator) > 32*np.finfo(float).eps
        if len_ind_t_ave == 0:
            raise ValueError('Time averaging window is empty')
        if betaE <= 0:
            raise ValueError('Maxwell stress requires positive BETAE_UNIT')
        Maxwell_arr=zeros((len_ind_t_ave,nkx),dtype=complex)
        Reynold_arr=zeros((len_ind_t_ave,nkx),dtype=complex)
        # precalculate the Bessel values
        k_mag = np.sqrt(kx_grid**2 + ky_grid**2)
        J0_k2 = j0(k_mag)**2  
        imethod=0 # 0: use the index mapping method,which is faster 1: use the direct calculation method; both methods give the same result
        for pt in np.arange(len_ind_t_ave):
            phi_arr=phi_cmplx[:,:,self.ind_t_ave[pt]]
            apar_arr=apar_cmplx[:,:,self.ind_t_ave[pt]] #(i_r, i_n, i_t)
            # go over each kx0
            for ikx0, kx0 in enumerate(kx0_arr):
                if not stress_valid[ikx0]:
                    continue
                if imethod==0:
                    # kx' = kx - kx0
                    kx_prime = kx_arr - kx0
                    # construct the indice mapping
                    idx = np.round((kx_prime + kxmax) / dkx).astype(int)
                    valid = (idx >= 0) & (idx < nkx)
                    # initialize the A_prime and phi_prime
                    A_prime = np.zeros((nkx, nky), dtype=complex)
                    phi_prime = np.zeros((nkx, nky), dtype=complex)
                    # fill the valid value
                    A_prime[valid] = apar_arr[idx[valid], :]
                    phi_prime[valid] = phi_arr[idx[valid], :]
                else:
                # 1. 璁＄畻A(kx - kx0, ky)鐨勫钩绉绘暟缁?                    A_prime = np.zeros_like(apar_arr, dtype=complex128)
                    for ikx in range(nkx):
                        target_kx = kx_arr[ikx] - kx0
                        if -kxmax <= target_kx <= kxmax:
                            p = int(round((target_kx + kxmax) / dkx))
                            if 0 <= p < nkx:
                                A_prime[ikx, :] = apar_arr[p, :]
                    # 2. 璁＄畻phi(kx - kx0, ky)鐨勫钩绉绘暟缁?                    phi_prime = np.zeros_like(phi_arr, dtype=complex128)
                    for ikx in range(nkx):
                        target_kx = kx_arr[ikx] - kx0
                        if -kxmax <= target_kx <= kxmax:
                            p = int(round(target_kx/dkx))
                            phi_prime[ikx, :] = phi_arr[p, :]
                        else:
                            phi_prime[ikx, :]=0
                            p = int(round((target_kx + kxmax) / dkx))
                            if 0 <= p < nkx:
                                phi_prime[ikx, :] = phi_arr[p, :]
                # calculate the maxwell stress
                maxwell_term = 2./betaE*(kx0 * ky_grid * (kx0**2 - 2*kx0*kx_grid) * 
                                apar_arr * np.conj(A_prime))
                # calculate the reynold stress
                k_prime_mag = np.sqrt((kx0 - kx_grid)**2 + ky_grid**2)
                J0_k_prime_2 = j0(k_prime_mag)**2
                reynold_term = -1*(kx0 * ky_grid * (J0_k2 - J0_k_prime_2) * 
                                phi_prime * np.conj(phi_arr))            
                # sum over the kx and ky space
                Maxwell_arr[pt,ikx0] = np.sum(maxwell_term)/(1-j0(kx0)**2)
                Reynold_arr[pt,ikx0] = np.sum(reynold_term)/(1-j0(kx0)**2)
        Maxwell_Stress=np.real(np.mean(Maxwell_arr,0))
        Reynold_Stress=np.real(np.mean(Reynold_arr,0))
        self.stress_valid_kx = stress_valid
        self.Maxwell_Stress = np.ma.array(Maxwell_Stress, mask=~stress_valid)
        self.Reynold_Stress = np.ma.array(Reynold_Stress, mask=~stress_valid)


    def Energy_transfer_phi(self,i_theta_plot=0, kx_select=0.0, ky_select=0.2):

    #     do the kinetic energy transfer analysis for a given k_select=[kx_select,ky_select] from the whole [kx,ky] space
    #     self.getbigfield()
    #     phi_cmplxx = self.kxky_phi[0, :, :, :, :] + 1j * self.kxky_phi[1, :, :, :,:]  # phi_cmplx[i_r,i_theta_plot,i_n,self.ind_t_ave])
        phi_cmplx = self.phi_cmplx_t[1:,i_theta_plot,:,:]
        n_kx = phi_cmplx.shape[0]
        if len(self.kx) == n_kx:
            kx_arr = self.kx
        elif len(self.kx) == n_kx + 1:
            kx_arr = self.kx[1:]
        else:
            raise ValueError('dimension of kxrhos and phi_cmplx does not match!')
        phi_cmplx=phi_cmplx/self.rho
        # print(np.size(phi_cmplxx,axis=-2))
        # print(np.size(phi_cmplx, axis=-2))
        # find the the index of the kx_select and ky_select
        delta_k_err=0.01  # used to avoid unneccesary error
        if kx_select>np.max(kx_arr)+delta_k_err or kx_select<np.min(kx_arr)-delta_k_err:
            raise ValueError('Please choose the kx value in between'+str(kx_arr[0])+' and '+str(kx_arr[-1]))
        else:
            kx_select_incode=kx_arr.flat[np.abs(kx_arr-kx_select).argmin()]  # the real selected kx value in code
            ind_kx=np.where(kx_arr==kx_select_incode)[0][0]
            print('The kxrhos that you really select is '+str(kx_select_incode))    # find the index of the kx_select_incode
        if ky_select>np.max(self.ky)+delta_k_err or ky_select < np.min(self.ky)-delta_k_err:
            raise ValueError('Please choose the ky value in between' + str(self.ky[0]) + ' and ' + str(self.ky[-1]))
        else:
            ky_select_incode = self.ky.flat[np.abs(self.ky - ky_select).argmin()]  # the real selected ky value in code
            ind_ky = np.where(self.ky == ky_select_incode)[0][0]
            print('The kyrhos that you really select is ' + str(ky_select_incode))  # find the index of the kx_select_incode
        # do the calculation
        len_ind_t_ave=len(self.ind_t_ave)
        S_k_kp=np.zeros([n_kx,self.n_n],dtype=complex)
        S_k_kp_norm = np.zeros([n_kx, self.n_n], dtype=complex)
        Lamda=np.zeros([n_kx,self.n_n]) # the coupling coefficient
        ind_kx_0=np.abs(kx_arr).argmin()
#        for i_m in np.arange(self.n_r):
        for i_m in np.arange(n_kx):
            for i_n in np.arange(self.n_n):
                kxp=kx_arr[i_m]   # kx_prime
                kyp=self.ky[i_n]   # ky_prime
                kx_kxp=kx_select_incode-kxp  # kx-kx_prime
                ky_kyp=ky_select_incode-kyp  # ky-ky_prime
                Lamda[i_m,i_n]=1./2*kx_select_incode*kyp-kxp*ky_select_incode         # coupling coefficient
                Lamda[i_m,i_n]=Lamda[i_m,i_n]*((kxp**2+kyp**2)-(kx_kxp**2+ky_kyp**2))
                S_k_kp_temp=np.zeros([len_ind_t_ave],dtype=complex)
                S_k_kp_temp_norm = np.zeros([len_ind_t_ave],dtype=complex)
                for i_t in np.arange(len_ind_t_ave):
                    # print(ind_kx,ind_ky,i_t)
                    phi_k_select=phi_cmplx[ind_kx,ind_ky,self.ind_t_ave[i_t]]  # phi(k)
                    phi_k_p=phi_cmplx[i_m,i_n,self.ind_t_ave[i_t]]             # phi(k_p)
                    # for phi(k-kp)
                    if abs(ind_kx-i_m)>self.n_r//2-1 or abs(ind_ky-i_n)>self.n_n:
                        phi_k_kp=0                                              # phi(k-k_p)
                    else:
                        ind_kx_m= ind_kx-i_m                                    #ind_kx-i_m
                        ind_ky_kyp= 0 + (ind_ky-i_n)
                    # f(-n,-m)=conj(f(n,m)) and f(-n,m)=conj(f(n,-m))
                        if ind_ky_kyp<0:                                        # n < 0, conjuction is required
                            ind_kx_kxp = ind_kx_0 - ind_kx_m                    # ind of kx-kxp
                            phi_k_kp = np.conj(phi_cmplx[ind_kx_kxp, -1*ind_ky_kyp, self.ind_t_ave[i_t]])
                        else:
                            ind_kx_kxp=ind_kx_0 + ind_kx_m                      # ind of kx-kxp
                            phi_k_kp=phi_cmplx[ind_kx_kxp,ind_ky_kyp,self.ind_t_ave[i_t]]
                    S_k_kp_temp[i_t]=np.conj(phi_k_select)*phi_k_p*phi_k_kp
                    if abs(S_k_kp_temp[i_t])!=0:
                        S_k_kp_temp_norm[i_t] = S_k_kp_temp[i_t]/(abs(phi_k_select)*abs(phi_k_p)*abs(phi_k_kp))
                    else:
                        S_k_kp_temp_norm[i_t] = 0
                S_k_kp[i_m,i_n]=np.real(np.mean(S_k_kp_temp))                  # the real part is required for the bicoherence
                S_k_kp_norm[i_m, i_n] = np.real(np.mean(S_k_kp_temp_norm))  # the real part is required for the bicoherence
        S_k_kp=-1*self['input.cgyro.gen']['IPCCW']*S_k_kp                       #I believe its sign should be affected by IPCCW
        S_k_kp_norm = -1 * self['input.cgyro.gen']['IPCCW'] * S_k_kp_norm
        T_phi=Lamda*S_k_kp
        self.Lamda_phi=Lamda                                                        # coupling coefficient
        self.kx_select_incode=kx_select_incode                                                      
        self.ky_select_incode=ky_select_incode                                                   
        self.S_k_kp_phi=S_k_kp                                                         # bicoherence
        self.S_k_kp_norm_phi =S_k_kp_norm                                           # normalized Bicoherence
        self.T_phi=T_phi                                                        # energy transfer function

    def Energy_transfer_phi_improve(self, i_theta_plot=0, kx_select=0.0, ky_select=0.2):
        phi_cmplx = self.phi_cmplx_t[1:, i_theta_plot, :, :]
        n_kx = phi_cmplx.shape[0]
        if len(self.kx) == n_kx:
            kx_arr = self.kx
        elif len(self.kx) == n_kx + 1:
            kx_arr = self.kx[1:]
        else:
            raise ValueError('dimension of kxrhos and phi_cmplx does not match!')
        phi_cmplx=phi_cmplx/self.rho
        delta_k_err = 0.01
        if kx_select > np.max(kx_arr) + delta_k_err or kx_select < np.min(kx_arr) - delta_k_err:
            raise ValueError('Please choose the kx value in between' + str(kx_arr[0]) + ' and ' + str(kx_arr[-1]))
        kx_select_incode = kx_arr.flat[np.abs(kx_arr - kx_select).argmin()]
        ind_kx = np.where(kx_arr == kx_select_incode)[0][0]
        if ky_select > np.max(self.ky) + delta_k_err or ky_select < np.min(self.ky) - delta_k_err:
            raise ValueError('Please choose the ky value in between' + str(self.ky[0]) + ' and ' + str(self.ky[-1]))
        ky_select_incode = self.ky.flat[np.abs(self.ky - ky_select).argmin()]
        ind_ky = np.where(self.ky == ky_select_incode)[0][0]

        n_r, n_n = n_kx, self.n_n

        time_indices = self.ind_t_ave
        total_time = len(time_indices)
        ind_kx_0 = np.abs(kx_arr).argmin()

        m_grid, n_grid = np.mgrid[:n_r, :n_n]
        kxp = kx_arr[m_grid]
        kyp = self.ky[n_grid]
        kx_diff = kx_select_incode - kxp
        ky_diff = ky_select_incode - kyp
        Lamda = (0.5 * kx_select_incode * kyp - kxp * ky_select_incode) * \
                ((kxp**2 + kyp**2) - (kx_diff**2 + ky_diff**2))

        delta_kx = ind_kx - m_grid
        delta_ky = ind_ky - n_grid
        valid_mask = (np.abs(delta_kx) <= self.n_r // 2 - 1) & (np.abs(delta_ky) <= n_n)
        pos_kx_all = ind_kx_0 + delta_kx
        neg_kx_all = ind_kx_0 - delta_kx
        valid_mask_pos = valid_mask & (delta_ky >= 0) & (pos_kx_all >= 0) & (pos_kx_all < n_r)
        valid_mask_neg = valid_mask & (delta_ky < 0) & (neg_kx_all >= 0) & (neg_kx_all < n_r)

        mem_bytes = 256 * 1024 * 1024
        bytes_per_element = phi_cmplx.itemsize
        denom = max(n_r * n_n * bytes_per_element, 1)
        block_size = max(1, min(total_time, mem_bytes // denom))

        S_k_kp_sum = np.zeros((n_r, n_n), dtype=np.complex128)
        S_k_kp_norm_sum = np.zeros((n_r, n_n), dtype=np.complex128)
        phi_k_select = phi_cmplx[ind_kx, ind_ky, time_indices]

        for t_start in range(0, total_time, block_size):
            t_end = min(t_start + block_size, total_time)
            t_slice = slice(t_start, t_end)
            phi_block = phi_cmplx[..., time_indices[t_slice]]
            phi_select_block = np.conj(phi_k_select[t_slice])[None, :]

            if valid_mask_pos.any():
                rows = m_grid[valid_mask_pos]
                cols = n_grid[valid_mask_pos]
                phi_k_p = phi_block[rows, cols]
                phi_k_kp = phi_block[pos_kx_all[valid_mask_pos], delta_ky[valid_mask_pos]]
                contrib = phi_select_block * phi_k_p * phi_k_kp
                contrib_norm = np.zeros_like(contrib)
                denom = np.abs(phi_select_block) * np.abs(phi_k_p) * np.abs(phi_k_kp)
                valid = denom != 0
                contrib_norm[valid] = contrib[valid] / denom[valid]
                S_k_kp_sum[rows, cols] += contrib.sum(axis=1)
                S_k_kp_norm_sum[rows, cols] += contrib_norm.sum(axis=1)

            if valid_mask_neg.any():
                rows = m_grid[valid_mask_neg]
                cols = n_grid[valid_mask_neg]
                phi_k_p = phi_block[rows, cols]
                phi_k_kp = np.conj(phi_block[neg_kx_all[valid_mask_neg], -delta_ky[valid_mask_neg]])
                contrib = phi_select_block * phi_k_p * phi_k_kp
                contrib_norm = np.zeros_like(contrib)
                denom = np.abs(phi_select_block) * np.abs(phi_k_p) * np.abs(phi_k_kp)
                valid = denom != 0
                contrib_norm[valid] = contrib[valid] / denom[valid]
                S_k_kp_sum[rows, cols] += contrib.sum(axis=1)
                S_k_kp_norm_sum[rows, cols] += contrib_norm.sum(axis=1)

        ipccw = self['input.cgyro.gen']['IPCCW']
        S_k_kp = -ipccw * np.real(S_k_kp_sum / total_time)
        S_k_kp_norm = -ipccw * np.real(S_k_kp_norm_sum / total_time)
        self.kx_select_incode=kx_select_incode
        self.ky_select_incode=ky_select_incode
        T_phi=Lamda*S_k_kp
        self.Lamda_phi=Lamda                                                        # coupling coefficient
        self.S_k_kp_phi=S_k_kp                                                      # Bicoherence,
        self.S_k_kp_norm_phi =S_k_kp_norm                                           # normalized Bicoherence
        self.T_phi=T_phi                                                        # energy transfer function
        
    def Energy_transfer_p(self, i_theta_plot=0, i_s=0, kx_select=0.0, ky_select=0.2):
        """Pressure triad transfer using the original per-sample normalization."""
        phi = self.phi_cmplx_t[1:, i_theta_plot, :, :] / self.rho
        pressure = (self.kxky_e[0, 1:, i_theta_plot, i_s, :, :]
                    + 1j*self.kxky_e[1, 1:, i_theta_plot, i_s, :, :]) / self.rho
        kx = np.asarray(self.kx)
        if len(kx) == phi.shape[0] + 1:
            kx = kx[1:]
        ky = np.asarray(self.ky)
        if phi.shape != pressure.shape or phi.shape[:2] != (len(kx), len(ky)):
            raise ValueError('Pressure, potential and wavenumber grids must match')
        times = np.asarray(self.ind_t_ave, dtype=int)
        if len(times) == 0 or np.any(times < 0) or np.any(times >= phi.shape[-1]):
            raise ValueError('Invalid or empty averaging window')
        if not np.min(kx) <= kx_select <= np.max(kx) or not np.min(ky) <= ky_select <= np.max(ky):
            raise ValueError('Selected wavenumber is outside the stored grid')
        ix, iy = int(np.abs(kx-kx_select).argmin()), int(np.abs(ky-ky_select).argmin())
        nx, ny = len(kx), len(ky)
        zero = int(np.abs(kx).argmin())
        if not np.isclose(kx[zero], 0) or (nx > 2 and not np.allclose(np.diff(kx), np.diff(kx)[0])):
            raise ValueError('Triad index mapping requires a uniform kx grid containing zero')
        if not np.isclose(ky[0], 0) or (ny > 2 and not np.allclose(np.diff(ky), np.diff(ky)[0])):
            raise ValueError('Triad index mapping requires a uniform ky grid starting at zero')
        rows, cols = np.mgrid[:nx, :ny]
        dx, dy = ix-rows, iy-cols
        reflected = dy < 0
        other_x = np.where(reflected, zero-dx, zero+dx)
        other_y = np.abs(dy)
        valid = (np.abs(dx) <= self.n_r//2-1) & (other_x >= 0) & (other_x < nx) & (other_y < ny)
        rr, cc = rows[valid], cols[valid]
        sums = np.zeros((nx, ny), dtype=complex)
        normalized = np.zeros_like(sums)
        block_size = max(1, min(len(times), (2**26)//max(1, nx*ny*16*6)))
        for start in range(0, len(times), block_size):
            time = times[start:start+block_size]
            p = np.take(pressure, time, axis=-1)
            f = np.take(phi, time, axis=-1)
            chosen = np.conj(p[ix, iy])[None, :]
            other = f[other_x[valid], other_y[valid]]
            other = np.where(reflected[valid, None], np.conj(other), other)
            product = chosen * p[rr, cc] * other
            denominator = np.abs(chosen) * np.abs(p[rr, cc]) * np.abs(other)
            unit = np.divide(product, denominator, out=np.zeros_like(product), where=denominator != 0)
            sums[rr, cc] += np.sum(product, axis=-1)
            normalized[rr, cc] += np.sum(unit, axis=-1)
        sign = -self['input.cgyro.gen']['IPCCW']
        self.Lamda_p = kx[ix]*ky[None, :] - kx[:, None]*ky[iy]
        self.S_k_kp_p = sign*np.real(sums)/len(times)
        self.S_k_kp_norm_p = sign*np.real(normalized)/len(times)
        self.T_p = self.Lamda_p*self.S_k_kp_p
        self.kx_select_incode, self.ky_select_incode = kx[ix], ky[iy]


    def Energy_transfer_p_improve(self, i_theta_plot=0, i_s=0, kx_select=0.0, ky_select=0.2):
        """Compatibility entry point for the shared, time-blocked implementation."""
        return self.Energy_transfer_p(i_theta_plot, i_s, kx_select, ky_select)
    
    # Restored from the supplied GACODE_module/CGYROalone/collect.py.
    def miller_wd_s(self,theta_p=np.linspace(-np.pi,np.pi,37)):
        """
        Usage: miller_wd_s(self)
        Functionality: get the self.wd1, wd2,wd3, Rs,Zs,Gq,rc_theta,l, BoverBunit,Gtheta, gcos1, gcos2, gsin, gradr, k_perp
        output: self.q_loc, self.s_loc as a function of theta_p
        :return:
        """
        n_theta_p=len(theta_p)
        xd = np.arcsin(self.delta)
        arg = theta_p + xd * np.sin(theta_p)
        Rs = self.Rmaj + self.rmin * np.cos(arg)  # R position
        Zs = self.kappa * self.rmin * np.sin(theta_p)  # Z Position
        #  calculate the Jocobian
        dRdtheta = -1 * self.rmin * np.sin(arg) * (1 + np.cos(theta_p) * xd)
        dZdtheta = self.kappa * self.rmin * np.cos(theta_p)
        dldtheta = (dRdtheta ** 2 + dZdtheta ** 2) ** 0.5
        dRdr = self.shift + np.cos(arg) - np.sin(theta_p) * np.sin(arg) * self.sdelta
        dZdr = self.kappa * np.sin(theta_p) * (1 + self.skappa)
        det = Rs * (dRdr * dZdtheta - dRdtheta * dZdr)
        # look at grad r
        gradr = dldtheta * Rs / det
        l = integrate.cumulative_trapezoid(dldtheta, theta_p, initial=0)
        d2Zdtheta2 = np.gradient(dZdtheta) / np.gradient(theta_p)
        d2Rdtheta2 = np.gradient(dRdtheta) / np.gradient(theta_p)
        rc_theta = dldtheta ** 3 / (dRdtheta * d2Zdtheta2 - dZdtheta * d2Rdtheta2)
        #        IoverBunit=2*np.pi*self.rmin/integrate.trapz(1/Rs/gradr,l) # scale
        IoverBunit = 2 * np.pi * self.rmin / integrate.trapezoid(1 / Rs / gradr, l)  # scale
        BtoverBunit = IoverBunit / Rs
        BpoverBunit = self.rmin / Rs * gradr / self.q
        BoverBunit = (BtoverBunit ** 2 + BpoverBunit ** 2) ** 0.5
        #    geometric components
        cosu = np.gradient(Zs) / np.gradient(l)  # dZ/dl
        sinu = -np.gradient(Rs) / np.gradient(l)  # - dR/dl
        gsin = BtoverBunit / BoverBunit * self.Rmaj / BoverBunit * np.gradient(BoverBunit) / np.gradient(l)
        gcos1 = (BtoverBunit / BoverBunit) ** 2 * self.Rmaj / Rs * cosu + (
                    BpoverBunit / BoverBunit) ** 2 * self.Rmaj / rc_theta
        gcos2 = -1. / 2. / BoverBunit ** 2 * self.Rmaj * gradr * self.betastar
        # E series for mu
        E1kernel = 2. / Rs / gradr * BtoverBunit / BpoverBunit * (self.rmin / rc_theta - self.rmin / Rs * cosu)
        E2kernel = 1. / Rs / gradr * (BoverBunit / BpoverBunit) ** 2
        E3kernel = 1. / 2. / Rs * BtoverBunit / BpoverBunit / BpoverBunit ** 2
        # chang the order[0~2*pi], denoted new
        E1kernel_new = OMFITcgyro_nonlin.changeorder(self, E1kernel)
        E2kernel_new = OMFITcgyro_nonlin.changeorder(self, E2kernel)
        E3kernel_new = OMFITcgyro_nonlin.changeorder(self, E3kernel)
        ntheta_half = int(np.round((n_theta_p + 1) / 2))
        l_new = np.zeros(n_theta_p)
        l_new[0:ntheta_half - 1] = l[ntheta_half - 1:n_theta_p - 1] - l[ntheta_half - 1]
        l_new[ntheta_half - 1:n_theta_p - 1] = l[0:ntheta_half - 1] + l[ntheta_half - 1]
        E1_new = integrate.cumulative_trapezoid(E1kernel_new, l_new, initial=0)
        E2_new = integrate.cumulative_trapezoid(E2kernel_new, l_new, initial=0)
        E3_new = integrate.cumulative_trapezoid(E3kernel_new, l_new, initial=0)  # in the order of 0~2*pi
        # change back to [-pi,pi]
        E1 = OMFITcgyro_nonlin.changeorder(self, E1_new)
        E2 = OMFITcgyro_nonlin.changeorder(self, E2_new)
        E3 = OMFITcgyro_nonlin.changeorder(self, E3_new)
        E1[0:ntheta_half - 1] = E1[0:ntheta_half - 1] - (E1[ntheta_half - 2] + E1[ntheta_half])
        E2[0:ntheta_half - 1] = E2[0:ntheta_half - 1] - (E2[ntheta_half - 2] + E2[ntheta_half])
        E3[0:ntheta_half - 1] = E3[0:ntheta_half - 1] - (E3[ntheta_half - 2] + E3[ntheta_half])
        fstar = 1 / E2_new[-1] * (
                    2 * np.pi * self.q * self.shear / self.rmin - 1 / self.rmin * E1_new[-1] + self.betastar *
                    E3_new[-1])
        THETA = Rs * BpoverBunit / BoverBunit * abs(gradr) * (1 / self.rmin * E1 + fstar * E2 - self.betastar * E3)
        Gq = 1 / self.q * (self.rmin / Rs * BoverBunit / BpoverBunit)
        Gtheta = BoverBunit * Rs / self.Rmaj / self.rmin / gradr * dldtheta
        # assuming partial/partial(theta_p)=-i k_theta, partial/partial(r)=-i k_r
        ktheta = self.ky[1]  # the ktheta is the kyrho_s specified in input.cgyro
        kr = 0
        vpar2v = 1 / 2  # assuming an isotropic distribution
        #  the sign here is consistent with the s-alpha geometry
        # the Rmaj exist in the denominator so that the output drift frequency has the unit of c_s/a,consistent with cgyro units
        wd1 = ktheta * Gq * 1 * (gcos1 + gcos2 + THETA * gsin) / self.Rmaj
        wd2 = -1 * ktheta * Gq * vpar2v * gcos2 / self.Rmaj
        wd3 = -1 * kr * 1 * gradr * gsin / self.Rmaj
        k_perp = (ktheta * Gq * THETA) ** 2 + (ktheta * Gq) ** 2
        k_perp = k_perp ** 0.5
        #  the local q and magnetic shear
        IoverBp = IoverBunit / BpoverBunit
        q_loc = IoverBp / Rs ** 2 * np.gradient(l) / np.gradient(theta_p)
        # solute for I' with given s
        D0_kernel = 1. / Rs * (2. / rc_theta / Rs - 2 * cosu / Rs ** 2) * IoverBp
        D1_kernel_part = 1. / Rs ** 2. * (BoverBunit / BpoverBunit) ** 2  # the dI/dr is unknow yet
        D2_kernel = -1. / 2 * 1. / Rs ** 2. * IoverBp * self.betastar / BpoverBunit ** 2
        D0 = integrate.cumulative_trapezoid(D0_kernel, l, initial=0)
        D1_part = integrate.cumulative_trapezoid(D1_kernel_part, l, initial=0)
        D2 = integrate.cumulative_trapezoid(D2_kernel, l, initial=0)
        dqdr = self.shear * self.q / self.rmin
        dIdr = (2 * np.pi * dqdr - D0[-1] - D2[-1]) / D1_part[-1]
        D1_kernel = 1. / Rs ** 2. * (BoverBunit / BpoverBunit) ** 2 * dIdr
        D1 = integrate.cumulative_trapezoid(D1_kernel, l, initial=0)
        # mu1=D0+D1+D2
        s_loc = self.rmin / q_loc * (D0_kernel + D1_kernel + D2_kernel) * np.gradient(l) / np.gradient(theta_p)
        #     get the output
        self.wd1 = wd1
        self.wd2 = wd2
        self.wd3 = wd3
        self.k_perp = k_perp
        self.Rs = Rs
        self.Zs = Zs
        self.l = l
        self.rc_theta = rc_theta
        self.BoverBunit = BoverBunit
        self.Gq = Gq
        self.Gtheta = Gtheta
        self.gcos1 = gcos1
        self.gcos2 = gcos2
        self.gsin = gsin
        self.gradr = gradr
        self.THETA = THETA
        self.q_loc = q_loc
        self.s_loc = s_loc

    def entropy_transfer(self,i_species=0):
        # the entropy is defined in Song-PRL-2025, it is a summation of all the other kx' and ky' to the kx,ky
        # the plot is about the kx,ky pairs
        self.getbigfield() # then we have self.triad = np.reshape(data[0:nd],(2,self.n_species,self.n_radial,8,self.n_n,nt),'F')
        f = self.triad[0,i_species,:,:,:,:]+1j*self.triad[1,i_species,:,:,:,:]
        # 0- Triad , 1- non-zonal pairs Triad , 2- d(Entropy)/dt, 3- W_k_{perp}/dt, 4- Entropy
        # 5- Diss.(radial) , 6- Diss.(theta) , 7- Diss.(Collision)
        f=f[:,0,:,:]  # select the first component which is the traid transfer, I would expect the imaginary part is 0
        f = np.real(f)
        f=f[1:,:,self.ind_t_ave].mean(axis=-1)
        self.entropy_transfer_value=f

# load cases that required to be plotted
if (not _COLLECT_IMPORT_ONLY) and ('root' in globals()):
    t_ave=root['SETTINGS']['PLOTS']['nl']['t_ave']
    t_end=root['SETTINGS']['PLOTS']['nl']['t_end'] # the t_end
    case_plot=root['SETTINGS']['PLOTS']['nl']['case_plot']
    ncase=len(case_plot)
    try:
        output_cases=outputs
    except NameError:
        output_cases=root['OUTPUTS']
    ncount=0
    for case in case_plot:
        try:
            case_node=output_cases[case]
        except Exception as exc:
            raise KeyError('Cannot find nonlinear case '+str(case)+' in the selected output tree') from exc
        if isinstance(t_ave,float):
            output_cases[case]=OMFITcgyro_nonlin(case_node.filename,window=t_ave,t_end=t_end)
        else:
            output_cases[case] = OMFITcgyro_nonlin(case_node.filename, window=t_ave[ncount], t_end=t_end[ncount])
        ncount=ncount+1

