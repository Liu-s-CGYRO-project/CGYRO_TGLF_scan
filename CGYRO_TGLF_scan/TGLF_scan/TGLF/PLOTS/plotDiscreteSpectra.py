# -*-Python-*-
# Created by pablorf at 08 Jul 2017  15:42

"""
This script makes a simple plot with the growth rates separated by electron and ion branches.
It also eliminates 0's that created problems with log plots

"""

import numpy as np


def cleanValues(x, y, yf):

    ind = (yf < 0) & (y > 1e-6)
    xIon = x[ind]
    yIon = y[ind]
    ind2 = (yf > 0) & (y > 1e-6)
    xEle = x[ind2]
    yEle = y[ind2]

    return yIon, xIon, yEle, xEle


# Growth rates and frequencies
# -----------------------------------------------------------
# Get values from the directory
root['FILES']['Discrete_ky'] = copy.deepcopy(root['FILES']['eigenvalue_spectrum'])
DirectoryNew = root['FILES']['Discrete_ky']


# ---------- MOST UNSTABLE GROWTH RATE
x = DirectoryNew['ky']
y = DirectoryNew['gamma(1)']
yf = DirectoryNew['freq(1)']
[yIon1, xIon1, yEle1, xEle1] = cleanValues(x, y, yf)

# ---------- SECOND MOST UNSTABLE GROWTH RATE
x = DirectoryNew['ky']
y = DirectoryNew['gamma(2)']
yf = DirectoryNew['freq(2)']
[yIon2, xIon2, yEle2, xEle2] = cleanValues(x, y, yf)


fn = FigureNotebook(0, 'Discrete Eigenvalues')
# Plot
fig, ax = fn.subplots(label='Growth Rates')
h1 = ax.scatter(xEle1, yEle1, color='red', s=50)
h2 = ax.scatter(xIon1, yIon1, color='blue', s=50)
h3 = ax.scatter(xEle2, yEle2, color='red', s=5)
h4 = ax.scatter(xIon2, yIon2, color='blue', s=5)
# ax.set_title('Spectrum at')
ax.set_ylabel('$\\gamma (c_s/a)$')
ax.set_xlabel('$k_{\\theta}\\rho_s$')
ax.set_xscale('log')
ax.set_yscale('log')

minx = 5e-2
miny = 1e-2
maxx = 60
maxy = 1e2

if len(xIon1) > 0 and len(xEle1):
    minx = min(min(xEle1), min(xIon1), minx)
    miny = min(min(yEle1), min(yIon1), miny)
    maxx = max(max(xEle1), max(xIon1), maxx)
    maxy = max(max(yEle1), max(yIon1), maxy)

ax.set_xlim([minx * 0.5, maxx * 1.5])
ax.set_ylim([miny * 0.5, maxy * 1.5])
ax.legend([h1, h2], ['Electron Direction', 'Ion Direction'])


# Temperature and density fluctuations
# -----------------------------------------------------------
aux = ['temperature', 'density']
aux2 = ['T', 'n']
cont = 0
for i in aux:
    DirectoryNew = root['FILES'][i + '_spectrum']
    x = DirectoryNew['ky']
    yE = DirectoryNew[i + '_spec_1']
    yI = DirectoryNew[i + '_spec_2']

    # Plot
    fig, ax = fn.subplots(label=i + ' fluctuations')
    ax.plot(x, yE, color='red')
    h1 = ax.scatter(x, yE, color='red')
    ax.plot(x, yI, color='blue')
    h2 = ax.scatter(x, yI, color='blue')
    ax.set_xlabel('$k_{\\theta}\\rho_s$')
    ax.set_ylabel('$\\delta ' + aux2[cont] + '/' + aux2[cont] + '$')
    ax.set_xscale('log')

    minx = 5e-2
    miny = 0
    maxx = 60
    maxy = 3e1

    minx = min(min(x), minx)
    miny = miny
    maxx = max(max(x), maxx)
    maxy = max(max(yE), max(yI), maxy)

    ax.set_xlim([minx, maxx])
    ax.set_ylim([miny, maxy])

    ax.legend([h1, h2], ['Electrons', 'Main Ions'])
    cont = cont + 1


# Quasilinear weights
# -----------------------------------------------------------

fieldPlot = 1

DirectoryNew = root['FILES']['sum_flux_spectrum']
x = DirectoryNew['ky']

aux = ['energy', 'particle']
minx = 5e-2
minyO = [0, -3]
maxx = 60
maxyO = [20, 3]

cont = 0
for iL in aux:

    yF = DirectoryNew[iL + '_field_' + str(fieldPlot) + '_spec_elec']
    yFi = DirectoryNew[iL + '_field_' + str(fieldPlot) + '_spec_lump']

    # Plot
    fig, ax = fn.subplots(label=iL + ' Spectrum')

    ax.plot(x, yF, color='red')
    h1 = ax.scatter(x, yF, color='red')
    ax.plot(x, yFi, color='blue')
    h2 = ax.scatter(x, yFi, color='blue')

    ax.set_xlabel('$k_{\\theta}\\rho_s$')
    # ax.set_ylabel('$$')
    ax.set_xscale('log')

    minx = min(min(x), minx)
    miny = min(min(yF), min(yFi), minyO[cont])
    maxx = max(max(x), maxx)
    maxy = max(max(yF), max(yFi), maxyO[cont])

    ax.set_xlim([minx, maxx])
    ax.set_ylim([miny, maxy])

    ax.legend([h1, h2], ['Electrons', 'Main Ions'])
    cont = cont + 1
