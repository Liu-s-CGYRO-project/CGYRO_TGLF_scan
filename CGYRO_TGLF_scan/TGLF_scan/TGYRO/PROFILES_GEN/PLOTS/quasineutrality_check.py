# -*-Python-*-
# Created by smithsp at 2013/07/15 09:08

fig = figure('Quasineutrality Check')
fig.clear()
input_gacode = root['OUTPUTS']['input.gacode']
ne = input_gacode['ne']
zarr = []
sum_nizi = ne * 0
rho = input_gacode['rho']
for i, k in enumerate(input_gacode['IONS'], start=1):
    z = input_gacode['IONS'][k][1]
    nizi = input_gacode['ni_%d' % i] * z
    plot(rho, nizi, label='$%dn_{%s}$' % (z, input_gacode['IONS'][k][0]))
    sum_nizi = sum_nizi + nizi
plot(rho, ne, label='$n_e$')
plot(rho, sum_nizi, '--', label='$\sum n_i Z_i$', linewidth=2)
legend(loc='best').draggable(True)
