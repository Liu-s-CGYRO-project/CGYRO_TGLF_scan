# -*-Python-*-
# Created by meneghini at 2013/04/10 23:46

# In ONETWO the impurity density is calculated based on Zeff, the impurity species and the temperature
# The temperature is used to evaluate the ionization state of the impurities according to a coronal approximation.
# This means that for example for Carbon, Zimp is not always 6. In fact it will be lower at the edge.

x = profpowbal['rho_grid']['data']
x = (x - min(x)) / (max(x) - min(x))
nmain = profpowbal['enion']['data'].T[:, 0]
nimp = profpowbal['enion']['data'].T[:, 1]
nb = profpowbal['enbeam']['data'].T[:, 0]
ne = profpowbal['ene']['data']
Zeff = profpowbal['zeff']['data']

plot(x, (nmain + nb + nimp * 36) / (nmain + nb + nimp * 6))
plot(x, Zeff)

Zimp = 6
Zmain = 1
nimp_good = ne * (Zeff - Zmain) / (Zimp - Zmain) / Zimp
nmain_good = (-Zimp * nimp + ne) / Zmain

# plot(x,nimp)
# plot(x,nimp_good)

# profpowbal['enion']['data'].T[:,1]=nimp_good
