"""Plot archived TGLF results without changing current inputs or legacy caches."""
from builtins import all, enumerate, len, sorted, str, sum, tuple, zip
import numpy as np
from OMFITlib_plot_style import plot_context

with plot_context(root):

    defaultVars(record=None, point_id=None)
    if record is None:
        raise ValueError('Select a TGLF run first')
    points = [(key, point) for key, point in record['points'].items() if point.get('status', None) == 'complete']
    if not points:
        raise ValueError('This run has no completed results')
    if point_id is not None:
        point = record['points'][point_id]
        spectrum = point['result']['eigenvalue_spectrum']
        ky = np.asarray(spectrum['ky'])
        figure, axes = subplots(2, 1, sharex=True, figsize=(7, 7))
        if 'gamma' in spectrum and 'freq' in spectrum:
            for axis, name in zip(axes, ('gamma', 'freq')):
                values = spectrum[name]
                if hasattr(values, 'transpose') and hasattr(values, 'dims'):
                    values = values.transpose('mode_num', 'ky')
                for index, series in enumerate(np.atleast_2d(np.asarray(values)), 1):
                    axis.plot(ky, series, 'o-', label='mode ' + str(index))
        else:
            # Older OMFIT versions expose one key per mode instead of DataArrays.
            for name in spectrum:
                if str(name).startswith('gamma('):
                    axes[0].plot(ky, spectrum[name], 'o-', label=str(name))
                elif str(name).startswith('freq('):
                    axes[1].plot(ky, spectrum[name], 'o-', label=str(name))
        if not axes[0].lines or not axes[1].lines:
            raise ValueError('This result does not contain a frequency / growth-rate spectrum')
        axes[0].set_ylabel(r'$\gamma\;(c_s/a)$')
        axes[1].set_ylabel(r'$\omega\;(c_s/a)$')
        axes[1].set_xlabel(r'$k_y\rho_s$')
        figure.suptitle(point_id)
        for axis in axes:
            axis.axhline(0, color='0.6', linewidth=0.7)
            axis.legend()
        figure.tight_layout()
    else:
        axes_plan = record['plan']['axes']
        x_name = axes_plan[0]['name'] if axes_plan else None
        if record['mode'] == 'uq':
            x_name = record['plan']['uq'][0]['name']
        sources = {tuple(source['path']): source for source in record['plan'].get('sources', [])}
        radial = not x_name and all(sources.get(tuple(p.get('source', ())), {}).get('rho') is not None for _, p in points)
        groups = {}
        for index, (key, point) in enumerate(points, 1):
            group = point['label']
            if len(axes_plan) == 2:
                name = axes_plan[1]['name']
                group += ' · {}={:g}'.format(name, point['parameters'][name])
            source = sources.get(tuple(point.get('source', ())), {})
            x = point['parameters'][x_name] if x_name else (source['rho'] if radial else index)
            if radial:
                group = source.get('coordinate', 'rho')
            qe = sum(row['heat'] for row in point['fluxes'] if row['species'] == 'elec')
            qi = sum(row['heat'] for row in point['fluxes'] if row['species'] != 'elec')
            groups.setdefault(group, []).append((x, qe, qi))
        figure, axes = subplots(2, 1, sharex=True, figsize=(7, 7))
        for label, values in groups.items():
            data = np.asarray(sorted(values))
            marker = 'o' if record['mode'] == 'uq' or (record['mode'] == 'single' and not radial) else 'o-'
            for index, axis in enumerate(axes):
                axis.plot(data[:, 0], data[:, index + 1], marker, label=label)
        axes[0].set_ylabel(r'$Q_e/Q_{GB}$')
        axes[1].set_ylabel(r'$Q_i/Q_{GB}$')
        axes[1].set_xlabel(x_name or ('Radius' if radial else 'Point'))
        for axis in axes:
            axis.legend(fontsize='small')
        figure.tight_layout()
