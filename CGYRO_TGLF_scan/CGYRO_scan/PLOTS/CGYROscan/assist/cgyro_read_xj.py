# this script is used to gather all the reading scripts of CGYRO, which is read by XiangJian
# read out.cgyro.freq, can handle both data method of both OMFITcgyro and OMFITgacode
import numpy as np
def readfreq(filename, flag_read=1, ave_window=0.02):
    """Mean frequency/growth and nonnegative relative tail standard deviation.

    A zero mean has infinite relative uncertainty; no convergence claim is made.
    At least two samples are required, including for a short averaging window.
    """
    if not 0 < ave_window <= 1:
        raise ValueError('ave_window must be in (0, 1]')
    if flag_read == 0:
        values = np.loadtxt(filename, ndmin=2)
        if values.shape[1] != 2:
            raise ValueError('Expected two columns: frequency and growth rate')
        values = values[-2:]
    else:
        omega = np.asarray(filename['freq']['omega'][0], dtype=float)
        gamma = np.asarray(filename['freq']['gamma'][0], dtype=float)
        if omega.shape != gamma.shape:
            raise ValueError('Frequency and growth time series lengths differ')
        count = max(2, int(np.ceil(len(omega) * ave_window)))
        values = np.column_stack((omega[-count:], gamma[-count:]))
    if len(values) < 2 or not np.all(np.isfinite(values)):
        raise ValueError('At least two finite frequency samples are required')
    w = values.mean(axis=0)
    deviation = values.std(axis=0)
    err_w = np.full(2, np.inf)
    np.divide(deviation, np.abs(w), out=err_w, where=np.abs(w) > np.finfo(float).eps)
    return w, np.maximum(err_w, 1.e-6)


def ql_species_flux(case, icgyro=1, ion_species=-1, nfield=3):
    """Extract the final time by dimension name, retaining species provenance.

    Missing physical fields contribute zero; missing/corrupt data raise. Ion
    particle sums are charge weighted, matching the original Gi convention.
    """
    generated = case['input.cgyro.gen' if icgyro else 'input.gyro.gen']
    raw = {}
    for channel in ('particle', 'energy', 'momentum'):
        value = case['qlflux_ky'][channel]
        if hasattr(value, 'dims'):
            value = value.isel(t=-1)
            if 'ky' in value.dims:
                if value.sizes['ky'] != 1:
                    raise ValueError('Linear qlflux requires a single ky per case')
                value = value.isel(ky=0)
            value = value.transpose('species', 'field')
        else:
            value = np.asarray(value)
            if value.ndim != 3:
                raise ValueError('Expected qlflux axes (species, field, time)')
            value = value[:, :, -1]
        raw[channel] = np.asarray(value, dtype=float)
    shape = raw['particle'].shape
    if any(v.shape != shape for v in raw.values()) or len(shape) != 2:
        raise ValueError('Quasilinear channel dimensions disagree')
    ns, nf = shape
    if nf != int(generated['N_FIELD']) or nf > nfield:
        raise ValueError('Flux field count differs from input')
    if not all(np.all(np.isfinite(v)) for v in raw.values()):
        raise ValueError('Nonfinite quasilinear flux')
    if icgyro:
        charge = np.array([generated['Z_' + str(i + 1)] for i in range(ns)])
    else:
        # GYRO stores its first ion charge as Z; kinetic electrons are appended.
        charge = np.array([generated.get('Z' if i == 0 else 'Z_' + str(i + 1), -1 if i == ns - 1 and not generated.get('AE_FLAG', 0) else np.nan) for i in range(ns)])
    if not np.all(np.isfinite(charge)) or np.any(charge == 0):
        raise ValueError('Species charges are missing or invalid')
    electrons = np.flatnonzero(charge < 0)
    ions = np.flatnonzero(charge > 0)
    if ion_species != -1:
        index = int(ion_species) - 1
        if index not in ions:
            raise ValueError('Requested 1-based ion index does not identify an ion')
        ions = np.array([index])
    totals = {}
    padded = {}
    for channel, short in [('particle', 'G'), ('energy', 'Q'), ('momentum', 'P')]:
        values = raw[channel]
        totals[short + 'e'] = np.zeros(nfield)
        totals[short + 'i'] = np.zeros(nfield)
        totals[short + 'e'][:nf] = values[electrons].sum(axis=0)
        ion_values = values[ions]
        if channel == 'particle' and ion_species == -1:
            ion_values = ion_values * charge[ions, None]
        totals[short + 'i'][:nf] = ion_values.sum(axis=0)
        padded[channel] = np.zeros((ns, nfield))
        padded[channel][:, :nf] = values
    labels = ['electron' if z < 0 else 'ion_' + str(i + 1) for i, z in enumerate(charge)]
    return totals, padded, labels


# get the chi_i
def readchi(cgyrodir):
    # import numpy as np
    ball=cgyrodir['balloon']
    theta=ball['theta_b_over_pi']
    phi=ball['balloon_phi'].T[-1]
    num=np.sum(theta**2*phi**2*np.gradient(theta))
    den=np.sum(phi**2*np.gradient(theta))
    thetabar=np.abs(num/den)
    inputcgyro=cgyrodir['input.cgyro.gen']
    ky=np.abs(inputcgyro['KY'])
    s=np.abs(inputcgyro['S'])
    krbar=thetabar*ky**2*s**2
    gamma=float(cgyrodir['freq']['gamma'][0][-1])
    epsl_n=1./(inputcgyro['DLNNDR_1']*inputcgyro['RMAJ'])
    chi_i=gamma/krbar*ky/epsl_n
    return chi_i


#get the basic output information of the linear run
def getoutmsg(filename):
    import numpy as np
    f=open(filename,'r')
    fread=f.readlines()
    lastline=fread[-1]
    if 'Linear converged' in lastline:
        outmsg=0
    elif 'Linear terminated at max time' in lastline:
        outmsg=1
    elif 'Integration error exceeded limit.' in lastline:
        outmsg=2
    else:
        outmsg=3
    f.close()
    return outmsg


def num2str_xj(val,effnum):
   return format(val,'.'+str(int(effnum))+'f')
