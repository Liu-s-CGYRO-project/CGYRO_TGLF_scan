# -*-Python-*-
# Created by avdeevag at 16 Dec 2022  20:20


"""
This script checks if the resistive interchange stability criteria is satisfied DR<0.
DR is computed in TGLF from the Miller equilibrium implementation of Glasser's formula.

The DR and DI are interchange stability factors and both should be negative for stability.
You can have local interchange instability without global sawteeth but DR, DI > 0 if q < 1.



"""

import numpy as np


def interchange_status(dr, di):
    """Classify finite nonempty D(R), D(I) arrays; zero is marginal."""
    dr, di = np.asarray(dr, dtype=float), np.asarray(di, dtype=float)
    if dr.size == 0 or dr.shape != di.shape or not np.all(np.isfinite(dr)) or not np.all(np.isfinite(di)):
        raise ValueError('Stability classification requires paired, finite D(R), D(I) data')
    if np.any(dr > 0) or np.any(di > 0):
        return 'unstable'
    if np.any(dr == 0) or np.any(di == 0):
        return 'marginal'
    return 'stable'


defaultVars(
    scan=root.get('Experimental_spectra', None),
)

if scan is None or len(scan) == 0 or None in scan:
    raise ValueError("Specify nonempty data: Experimental_spectra or scanResults_spectra[r][variable_to_scan]")


# array for D()
DR = []
DI = []
rho_array = []

fig, ax = plt.subplots(nrows=1, ncols=1)

for rho in scan.keys():

    DR.append(scan[rho]['run']['D(R)'])
    DI.append(scan[rho]['run']['D(I)'])
    rho_array.append(rho)

status = interchange_status(DR, DI)

for i, r in enumerate(rho_array):
    if DR[i] > 0 or DI[i] > 0:
        color = 'r'

    else:
        color = 'k'

    ax.plot(r, DR[i], 's', color=color, label='D(R)')
    ax.plot(r, DI[i], 'o', label='D(I)', color=color)
    if i == 0:
        ax.legend().draggable()
ax.axhline(y=0, linestyle='--', color='k')
ax.set_xlabel(r'$\rho$')

ax.set_ylabel('D(R),D(I)')
text = {
    'unstable': 'Positive D(R) or D(I): interchange criterion violated (TGLF Miller geometry)',
    'marginal': 'D(R) or D(I) = 0: marginal interchange criterion, not strictly stable',
    'stable': 'All D(R), D(I) < 0: no interchange instability indicated (TGLF Miller geometry)',
}[status]
shot = root['SETTINGS']['EXPERIMENT']['shot']
time = root['SETTINGS']['EXPERIMENT']['time']

suptitle(f'#{shot}; t= {time} ms')
ax.annotate(f'{text}', xy=(0.01, 1), xycoords='axes fraction', ha='left', va='top', fontsize=16, color='r').draggable()
