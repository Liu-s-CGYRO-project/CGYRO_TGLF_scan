"""Plot triad transfer with per-case windows and actual result dimensions."""
import numpy as np
import matplotlib.pyplot as plt

def _average_transfer(case, quantity, windows, window, end, theta, kx, ky, species=0):
    if windows < 1 or not 0 < window <= end <= 1:
        raise ValueError('Expected windows >= 1 and 0 < window <= end <= 1')
    original_indices = case.ind_t_ave
    values, normalized, transfers, samples = [], [], [], []
    suffix = 'phi' if quantity == 'phi' else 'p'
    method = getattr(case, 'Energy_transfer_' + suffix)
    coupling = None
    try:
        for split in range(windows):
            upper = end - split*window/windows
            lower = upper - window/windows
            start, stop = int(round(lower*case.n_time)), int(round(upper*case.n_time))
            case.ind_t_ave = np.arange(start, stop)
            if len(case.ind_t_ave) == 0:
                raise ValueError('A transfer averaging window contains no samples')
            options = dict(i_theta_plot=theta, kx_select=kx, ky_select=ky)
            if quantity == 'p':
                options['i_s'] = species
            method(**options)
            current = np.asarray(getattr(case, 'S_k_kp_'+suffix))
            weight = np.asarray(getattr(case, 'S_k_kp_norm_'+suffix))
            transfer = np.asarray(getattr(case, 'T_'+suffix))
            current_coupling = np.asarray(getattr(case, 'Lamda_'+suffix))
            if current.ndim != 2 or current.shape != weight.shape or current.shape != transfer.shape:
                raise ValueError('Triad result arrays have inconsistent dimensions')
            if current.shape != current_coupling.shape:
                raise ValueError('Coupling and transfer grids differ')
            if coupling is not None and not np.array_equal(coupling, current_coupling):
                raise ValueError('Coupling grid changed between time windows')
            coupling = current_coupling.copy()
            values.append(current.copy())
            normalized.append(weight.copy())
            transfers.append(transfer.copy())
            samples.append(len(case.ind_t_ave))
    finally:
        case.ind_t_ave = original_indices
    return coupling, np.average(np.stack(values),axis=0,weights=samples), np.average(np.stack(normalized),axis=0,weights=samples), np.average(np.stack(transfers),axis=0,weights=samples)

def _transfer_grid(case, shape):
    kx, ky = np.asarray(case.kx), np.asarray(case.ky)
    if len(kx) == shape[0]+1:
        kx = kx[1:]
    if shape != (len(kx),len(ky)):
        raise ValueError('Triad result does not match its wavenumber coordinates')
    return np.meshgrid(kx,ky)

def _symmetric_levels(values, count=11):
    finite = np.asarray(values)[np.isfinite(values)]
    if finite.size == 0:
        raise ValueError('Triad plot has no finite values')
    scale = float(np.max(np.abs(finite)))
    # A finite symmetric display range for an identically zero diagnostic.
    return np.linspace(-scale,scale,count) if scale else np.linspace(-1.,1.,count)

settings = root['SETTINGS']['PLOTS']['nl']
defaultVars(n_split=1, kx_select=0.0, ky_select=0.24, iplotp=False, pressure_species=1)
if int(n_split) != n_split:
    raise ValueError('n_split must be an integer')
n_split = int(n_split)
loader = 'collect.py' if root['SETTINGS']['SETUP']['icgyro']==1 else 'collect_gyro.py'
root['PLOTS']['CGYROalone']['assist'][loader].run()
outputs = root['OUTPUTS']['NonLinear']
case_names = list(settings['case_plot'])
if not case_names:
    raise ValueError('Select at least one nonlinear case')
windows = np.asarray(settings['t_ave'])
ends = np.asarray(settings['t_end'])
for quantity in (['phi','p'] if iplotp else ['phi']):
    fig, axes = plt.subplots(3,len(case_names),squeeze=False,figsize=(5*len(case_names),10))
    for column,name in enumerate(case_names):
        case = outputs[name]
        if quantity == 'p' and (int(pressure_species) != pressure_species or not 1 <= pressure_species <= case.n_species):
            raise ValueError('pressure_species must identify a stored species (1-based)')
        window = float(windows if windows.ndim==0 else windows[column])
        end = float(ends if ends.ndim==0 else ends[column])
        theta = case.n_theta_plot//2
        coupling,value,normalized,transfer = _average_transfer(
            case,quantity,n_split,window,end,theta,kx_select,ky_select,int(pressure_species)-1)
        grid = _transfer_grid(case,value.shape)
        for row,(data,label) in enumerate([(coupling,'Coupling coefficient'),(value,'Bicoherence'),(transfer,'Transfer '+quantity)]):
            ax = axes[row,column]
            contour = ax.contourf(*grid,data.T,levels=_symmetric_levels(data),cmap='seismic')
            fig.colorbar(contour,ax=ax)
            ax.set_title(name+' — '+label)
            ax.set_xlabel('kx rho_s')
            ax.set_ylabel('ky rho_s')
    fig.tight_layout()
