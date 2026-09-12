# -*-Python-*-
# Created by grierson at 25 Apr 2016  14:37

fn = FigureNotebook(0, 'Particle Transport')
for i, rho in enumerate(root['D_and_v']['rhoList']):
    fig, ax = fn.subplots(label='{}'.format(rho))
    ax.plot(root['D_and_v']['nisl'][i, :], root['D_and_v']['gamma_n'][i, :], marker='o')
    ax.set_title('$\\rho = {}$'.format(rho))
    ax.set_xlabel('$\\nabla_r n /n$  $(1/m)$')
    ax.set_ylabel('$\\Gamma/n$  $(m/s)$')

fig, ax = fn.subplots(2, 2, label='Profiles', sharex=True)
ax[0, 0].plot(root['D_and_v']['rhoList'], root['D_and_v']['D'], marker='o', label='$D (m^2/s)$')
ax[1, 0].plot(root['D_and_v']['rhoList'], root['D_and_v']['v'], marker='o', label='$V(m/s)$')
ax[0, 1].plot(root['D_and_v']['rhoList'], root['D_and_v']['v'] / root['D_and_v']['D'], marker='o', label='$V/D (m^{-1})$')
ax[1, 1].plot(root['D_and_v']['gzrho'], root['D_and_v']['gzprof'], label='$\\Gamma=0$ Profile')

for axf in ax.flatten():
    axf.legend().draggable()
ax[1, 1].set_xlim([0, np.max(root['D_and_v']['rhoList'])])
ax[1, 1].set_xlabel('$\\rho$')
ax[0, 1].set_xlabel('$\\rho$')
