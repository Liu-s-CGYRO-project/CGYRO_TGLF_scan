"""Compare completed case records on their native TGLF ky grids."""
from OMFITlib_plot_sources import spectrum_arrays
from OMFITlib_plot_window import fit_figure_window
from builtins import enumerate, float, len, list, range, str
import numpy as np


from OMFITlib_tglf_multi_data import flux_summary  # Public compatibility alias.


def plot_cases(root, notebook):
    curves = []
    for case in root.get('TGLF_CASES', {}).values():
        if not case['enabled']:
            continue
        run = case['runs'].get(case['selected_run'], None)
        if run is None:
            continue
        for point in run['points'].values():
            attempt = point['attempts'].get(point.get('selected_attempt', None), None)
            if attempt is None or attempt['status'] != 'complete':
                continue
            spectrum = attempt['result']['eigenvalue_spectrum']
            ky, freq, gamma = spectrum_arrays(spectrum)
            for index in range(len(gamma)):
                label = '{} | {}={} | mode {}'.format(run['label'], run['plan']['coordinate'], point['radius'], index + 1)
                curves.append((ky, gamma[index], freq[index], label))
    if not curves:
        raise ValueError('所选运行记录中没有完成的 TGLF 谱。')
    nb = notebook('TGLF multi-input comparison')
    fig, axes = nb.subplots(2, 1, sharex=True, figsize=(9, 7), label='TGLF spectra')
    for ky, gamma, freq, label in curves:
        line, = axes[0].plot(ky, gamma, marker='.', label=label)
        axes[1].plot(ky, freq, marker='.', color=line.get_color())
    axes[0].set_ylabel(r'$\gamma$ (TGLF units)')
    axes[1].set_ylabel(r'$\omega$ (TGLF units)')
    axes[1].set_xlabel(r'$k_y\rho_s$ (TGLF grid)')
    for axis in axes:
        axis.axhline(0, color='0.6', linewidth=.7)
        axis.grid(alpha=.2)
    axes[0].legend(fontsize=8, loc='upper left', bbox_to_anchor=(1.01, 1.))
    fig.tight_layout()
    fit_figure_window(fig)
    return fig
