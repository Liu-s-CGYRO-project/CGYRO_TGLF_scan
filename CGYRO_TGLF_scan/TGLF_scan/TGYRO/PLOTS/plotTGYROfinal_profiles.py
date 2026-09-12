# -*-Python-*-
# Created by smithsp at 2013/08/21 09:44

defaultVars(exp_profiles=input_gacode, output=root['OUTPUTS']['output'], input_tgyro=root['INPUTS']['input.tgyro'], plot_kw={}, smooth=True)

plot_kw.setdefault('lw', 1.5)

n_ion = input_tgyro['LOC_N_ION']

ncol = n_ion + 1 + 1
nrow = 2
if smooth:
    rho = output.sprofile('rho')
else:
    rho = output['rho'][0, :]

kk = 0
for scale_len in ['']:
    for row in range(nrow):
        for col in range(ncol):
            key = ''
            norm = 1
            if col == 0:
                if row == 0:
                    key = 'ne'
                    norm = 1e13
                    keyExp = 'ne'
                else:
                    key = 'te'
                    keyExp = 'Te'
            elif col <= n_ion:
                if row == 0:
                    key = 'ni%d' % col
                    norm = 1e13
                    keyExp = 'ni_%d' % col
                else:
                    key = 'ti%d' % col
                    keyExp = 'Ti_%d' % col
            key = scale_len + key
            if scale_len == 'a/L':
                key = key.replace('t', 'T')
            if col == n_ion + 1:
                if row == 0:
                    key = 'w0'
                    keyExp = 'omega0'
                else:
                    continue

            kk += 1
            if kk == 1:
                ax = ax1 = subplot(nrow, ncol, kk)
            else:
                ax = subplot(nrow, ncol, kk, sharex=ax1)

            if smooth:
                plot(rho, output.sprofile(key)[:, -1] / norm, **plot_kw)
            else:
                plot(rho, output[key][-1, :] / norm, **plot_kw)

            try:
                plot(exp_profiles['rho'], exp_profiles[keyExp], '--k', lw=1.5)
            except Exception as _excp:
                print(repr(_excp))

            if col == n_ion + 1:
                if row == 0:
                    legend().draggable(True)
            text(0.5, 0.95, key, ha='center', va='top', transform=ax.transAxes)
            ylim(auto=True)
            if key != 'w0':
                ylim(ymin=0)
            xlim([0, 1])

    autofmt_sharex()
