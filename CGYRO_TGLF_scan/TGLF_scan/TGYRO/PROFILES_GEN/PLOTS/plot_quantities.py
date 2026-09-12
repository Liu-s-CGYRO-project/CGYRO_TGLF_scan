# -*-Python-*-
# Created by meneghini at 08 Jun 2016  15:14

defaultVars(rho_name='rho', quantity=['Er', 'Vpol', 'Jboot'][1])

input_gacode = root['OUTPUTS']['input.gacode']

psi = input_gacode['polflux']
if psi[0] < psi[-1]:
    psi = (psi - min(psi)) / (max(psi) - min(psi))
else:
    psi = (-psi - min(-psi)) / (max(-psi) - min(-psi))

if rho_name == 'rho' and 'jboot' in root['OUTPUTS']:
    rho = root['OUTPUTS']['jboot'][rho_name]
elif rho_name in ['psi', 'psin']:
    rho = psi
else:
    rho = input_gacode[rho_name]

if quantity == 'Er':
    qNEO = root['OUTPUTS']['Er']['Er_midplane']
    plot(rho, qNEO, linewidth=2, label='NEO')

    if profpowbal is not None and 'er' in profpowbal:
        q = interp1e(profpowbal['er']['psinorm'], profpowbal['er']['data'])(psi)
        plot(rho, q, '--', linewidth=2, label='p-File')

    title('Midplane radial electric field')
    ylabel('$[kV/m]$')

elif quantity == 'Vpol':
    colors = {}
    for k in input_gacode['IONS']:
        qNEO = input_gacode['vpol_%d' % k] / 1e3
        plot(rho, qNEO, linewidth=2, label='NEO (%s - %s)' % (input_gacode['IONS'][k][0], input_gacode['IONS'][k][3]))
        colors[k] = gca().lines[-1].get_color()

    for k in input_gacode['IONS']:
        if profpowbal is not None and 'vpol%d' % (k - 1) in profpowbal:
            q = interp1e(profpowbal['vpol%d' % (k - 1)]['psinorm'], profpowbal['vpol%d' % (k - 1)]['data'])(psi)
            plot(
                rho,
                q,
                '--',
                linewidth=2,
                label='p-File (%s - %s)' % (input_gacode['IONS'][k][0], input_gacode['IONS'][k][3]),
                color=colors[k],
            )

    title('Poloidal velocity')
    ylabel('$[km/s]$')

elif quantity == 'Jboot':

    JbootNEO = copy.deepcopy(input_gacode['jbs'])
    Bunit = root['OUTPUTS']['input.gacode']['bunit']
    Bcentr = root['OUTPUTS']['input.gacode']['BT_EXP']
    JbootNEO *= Bunit / Bcentr
    plot(rho, sign(sum(JbootNEO)) * JbootNEO, linewidth=2, label='NEO')

    if 'JbootONETWO' in root['OUTPUTS']['jboot']:
        JbootONETWO = root['OUTPUTS']['jboot']['JbootONETWO'] / 1e6
        plot(rho, JbootONETWO, '--', linewidth=2, label='Sauter (from ONETWO)')

    JbootSauter = root['OUTPUTS']['jboot']['JbootSauter'] / 1e6
    plot(rho, sign(sum(JbootSauter)) * JbootSauter, '--', linewidth=2, label='Sauter (from NEO)')

    title('Bootstrap current')
    ylabel('$[MA/m^2]$')

legend(loc=0).draggable(True)
if rho_name == 'rho':
    xlabel('$\\rho$')
elif rho_name in ['psi', 'psin']:
    xlabel('$\\psi$')
else:
    xlabel(rho_name)
