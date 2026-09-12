"""

This script plots persantage of deviation of predicted profiles and inverse gradeint lenghts from experimental values
This script also plot RMS and Offset defined in J.E. Kinsey et al 2011 Nucl. Fusion 51 083001 and later articles

"""


defaultVars(
    run_db=scratch.get('plot_runids', []),  # RUN_DB outputs
    labels=scratch.get('plot_runids', []),
)


raw = 2
fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(raw, raw, sharex=True, figsize=(raw * 7, raw * 4))

# ---for plot RMS and offset ---
rms_Te = []
rms_Ti = []
offset_Te = []
offset_Ti = []
# -----------------------------

for n, ids in enumerate(run_db):
    rho_tgyro = root['RUN_DB'][ids]['OUTPUTS']['output']['rho'][-1, :]
    Te_tgyro = root['RUN_DB'][ids]['OUTPUTS']['output']['te'][-1, :]
    Ti_tgyro = root['RUN_DB'][ids]['OUTPUTS']['output']['ti1'][-1, :]

    rho = root['RUN_DB'][ids]['PROFILES_GEN']['input.gacode']['rho']
    Te = root['RUN_DB'][ids]['PROFILES_GEN']['input.gacode']['Te']
    Ti = root['RUN_DB'][ids]['PROFILES_GEN']['input.gacode']['Ti_1']

    alte_tgyro = root['RUN_DB'][ids]['OUTPUTS']['output']['a/Lte'][-1, :]
    alti_tgyro = root['RUN_DB'][ids]['OUTPUTS']['output']['a/Lti1'][-1, :]

    alte = root['RUN_DB'][ids]['PROFILES_GEN']['input.gacode']['dlntedr']
    alti = root['RUN_DB'][ids]['PROFILES_GEN']['input.gacode']['dlntidr_1']

    a = np.max(root['RUN_DB'][ids]['PROFILES_GEN']['input.gacode']['rmin'])
    alte = alte * a  # need integration for gradeints
    alti = alti * a

    def find_nearest(array, value):
        idx = np.searchsorted(array, value, side="left")
        if idx > 0 and (idx == len(array) or math.fabs(value - array[idx - 1]) < math.fabs(value - array[idx])):
            return idx - 1
        else:
            return idx

    diff_te = []
    diff_grad_te = []
    diff_ti = []
    diff_grad_ti = []

    for i, rr in enumerate(rho_tgyro):
        diff_te.append((Te_tgyro[i] - Te[find_nearest(rho, rr)]) / Te[find_nearest(rho, rr)] * 100)
        diff_grad_te.append((alte_tgyro[i] - alte[find_nearest(rho, rr)]) / alte[find_nearest(rho, rr)] * 100)
        diff_ti.append((Ti_tgyro[i] - Ti[find_nearest(rho, rr)]) / Ti[find_nearest(rho, rr)] * 100)
        diff_grad_ti.append((alti_tgyro[i] - alti[find_nearest(rho, rr)]) / alti[find_nearest(rho, rr)] * 100)

    # -------for RMS and offset calculations ------
    sigma_te = []
    sigma_te2 = []
    Te_exp = []
    Ti_exp = []
    sigma_ti = []
    sigma_ti2 = []

    # ------------------------------------------------

    for j, rr2 in enumerate(rho_tgyro[1:-1]):  # remove axis and boundary point

        sigma_te.append((Te_tgyro[j + 1] - Te[find_nearest(rho, rr2)]))
        sigma_te2.append((Te_tgyro[j + 1] - Te[find_nearest(rho, rr2)]) ** 2)
        Te_exp.append((Te[find_nearest(rho, rr2)]) ** 2)

        sigma_ti.append((Ti_tgyro[j + 1] - Ti[find_nearest(rho, rr2)]))
        sigma_ti2.append((Ti_tgyro[j + 1] - Ti[find_nearest(rho, rr2)]) ** 2)
        Ti_exp.append((Ti[find_nearest(rho, rr2)]) ** 2)

    N = 1 / (len(rho_tgyro) - 2)  # -2 as we do not include axis and boundary points
    rms_Te.append(((N * sum(sigma_te2)) ** 0.5) / ((N * sum(Te_exp)) ** 0.5))
    rms_Ti.append(((N * sum(sigma_ti2)) ** 0.5) / ((N * sum(Ti_exp)) ** 0.5))
    offset_Te.append((N * sum(sigma_te)) / ((N * sum(Te_exp)) ** 0.5))
    offset_Ti.append((N * sum(sigma_ti)) / ((N * sum(Ti_exp)) ** 0.5))
    # --------------------------------------------------------

    ax1.plot(rho_tgyro, diff_te, 'o-', label=f'{labels[n]}')
    ax1.grid(color='k', linestyle='-', linewidth=2, alpha=0.2)
    ax1.set_ylabel('$\Delta \; T_e \; [\%]$')
    ax1.axhline(y=0, linestyle='--', color='r')
    ax1.legend()

    ax2.plot(rho_tgyro, diff_ti, 'o-')
    ax2.grid(color='k', linestyle='-', linewidth=2, alpha=0.2)
    ax2.set_ylabel('$\Delta \; T_i \; [\%]$')
    ax2.axhline(y=0, linestyle='--', color='r')

    ax3.plot(rho_tgyro, diff_grad_te, 'o-')
    ax3.grid(color='k', linestyle='-', linewidth=2, alpha=0.2)
    ax3.set_ylabel('$\Delta \; a/L_{T_e} \; [\%]$')
    ax3.set_xlabel(r'$\rho$')
    ax3.axhline(y=0, linestyle='--', color='k')

    ax4.plot(rho_tgyro, diff_grad_ti, 'o-')
    ax4.grid(color='k', linestyle='-', linewidth=2, alpha=0.2)
    ax4.set_ylabel('$\Delta \; a/L_{T_i} \; [\%]$')
    ax4.set_xlabel(r'$\rho$')
    ax4.axhline(y=0, linestyle='--', color='k')

    fig.tight_layout()

# -----plot of RMS and offset------
raw = 2
fig, (ax1, ax2) = plt.subplots(2, 1, sharex=True, figsize=(raw * 7, raw * 4))
x = np.arange(len(run_db))
width = 0.35  # width of bars

te_rms = ax1.bar(x - width / 2, rms_Te, width, label='Te')
ti_rms = ax1.bar(x + width / 2, rms_Ti, width, label='Ti')

ax1.legend()
ax1.set_xticks(x)
ax1.set_xticklabels(labels)
ax1.set_ylabel(r'RMS error $\sigma$')

te_offset = ax2.bar(x - width / 2, offset_Te, width, label='Te')
ti_offset = ax2.bar(x + width / 2, offset_Ti, width, label='Ti')

ax2.axhline(y=0, linewidth=2, linestyle='-', color='k')
ax2.legend()
ax2.set_xticks(x)
ax2.set_xticklabels(labels)
ax2.set_ylabel(r'Offset $f_T$')


def autolabel(ax, rects):
    """Attach a text label above each bar in *rects*, displaying its height."""
    for rect in rects:
        height = rect.get_height()

        ax.annotate(
            '{:.2f}'.format(height),
            xy=(rect.get_x() + rect.get_width() / 2, height),
            xytext=(0, 6),  # 3 points vertical offset
            textcoords="offset points",
            ha='center',
            va='bottom',
        ).draggable()


autolabel(ax1, te_rms)
autolabel(ax1, ti_rms)
autolabel(ax2, te_offset)
autolabel(ax2, ti_offset)
