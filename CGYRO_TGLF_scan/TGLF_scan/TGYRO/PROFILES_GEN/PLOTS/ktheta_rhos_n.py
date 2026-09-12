# -*-Python-*-
# Created by grierson at 09 Jun 2018  13:13

"""
This script plots the conversion between the (C)GYRO input chosen poloidal mode
L_Y (gyro, linear) and KY (cgyro) and and toroidal mode number "n"

The relationship is that
  k_theta rho_s = (nq/r)*rho_{s,unit}
where
  k_theta is the poloidal mode number (nq/r)
  rho_s is the sonic Larmor radius that is adjusted internally inside
    of (C)GYRO to give an integer mode number.
    For GYRO this is for n=30, for CGYRO this is for n=1.
  n - toroidal mode number
  r - minor radius (m)
  rho_{s,unit} - experimental rho_s

defaultVars parameters
----------------------
:param ky: L_Y (gyro) or KY (cgyro)
:param n: Toroidal mode number
:param xname: Name of x-coordinate ('r/a', 'rho', 'psi_n')
:param xval: Value of x-coordinate for which to evaluate the ky(n) or n(ky)
"""

defaultVars(ky=0.3, n=30, xname='r/a', xval=0.5)

# If no inputs then default to using ky=0.3
if ky is None and n is None:
    ky = 0.3

r = root['OUTPUTS']['input.gacode']['rmin']
q = root['OUTPUTS']['input.gacode']['q']
rho_s_unit = root['OUTPUTS']['input.gacode']['rhos']
if xname == 'r/a':
    xo = r / r[-1]
    xlab = '$r_{min}$'
if xname == 'rho':
    xo = root['OUTPUTS']['input.gacode']['rho']
    xlab = '$\\rho$'
if xname == 'psi_n':
    psi = root['OUTPUTS']['input.gacode']['polflux']
    xo = (psi - psi[0]) / (psi[-1] - psi[0])
    xlab = '$\\psi_n$'

if ky is not None:
    no = ky * (r / q) / rho_s_unit
    fig, ax = plt.subplots()
    ax.plot(xo, no, label='n')
    if xval is not None:
        nval = interpolate.interp1d(xo, no)(xval)
        print('At {}={} for ky={} --> n={}'.format(xname, xval, ky, nval))
    ax.set_title('n for $k_\\theta\\rho_s$={0:0.3f}'.format(ky))
    ax.set_xlabel(xlab)
    ax.legend(loc='best')

if n is not None:
    kyo = n * (q / r) * rho_s_unit
    fig, ax = plt.subplots()
    ax.plot(xo, kyo, label='$k_\\theta\\rho_s$')
    if xval is not None:
        kyoval = interpolate.interp1d(xo, kyo)(xval)
        print('At {}={} for n={} --> ky={}'.format(xname, xval, n, kyoval))
    ax.set_title('$k_\\theta\\rho_s$ for n={}'.format(n))
    ax.set_xlabel(xlab)
    ax.legend(loc='best')
