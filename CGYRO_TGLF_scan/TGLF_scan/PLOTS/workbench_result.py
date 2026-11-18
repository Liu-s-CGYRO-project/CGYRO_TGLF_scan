"""Plot archived TGLF results without changing current inputs or legacy caches."""
from builtins import all, enumerate, len, range, set, sorted, str, sum, tuple, zip
import numpy as np
from OMFITlib_plot_style import plot_context
from OMFITlib_tglf_records import point_current, point_result

with plot_context(root):

    defaultVars(record=None, point_id=None)
    if record is None:
        raise ValueError('Select a TGLF run first')
    points = [(key, point) for key, point in record['points'].items() if point_current(root, point)]
    if not points:
        raise ValueError('This run has no completed results')
    if point_id is not None:
        point = record['points'][point_id]
        spectrum = point_result(root, point)['eigenvalue_spectrum']
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
        figure.suptitle(point_id + ' · ' + point['preset_label'] if 'preset_label' in point else point_id)
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
        radial = not x_name and all(sources.get(tuple(p.get('source', ())), {}).get('rho', None) is not None for _, p in points)
        preset_scan = record['mode'] == 'preset'
        if preset_scan:
            radii = [s.get('rho', None) for s in sources.values()]
            coordinates = {s.get('coordinate', 'rho') for s in sources.values()}
            radial = len(radii) > 1 and None not in radii and len(set(radii)) == len(radii) and len(coordinates) == 1
            present = {point['preset_key'] for _, point in points}
            presets = [p for p in record['plan']['presets'] if p['key'] in present]
            positions = {p['key']: i for i, p in enumerate(presets)}
        groups = {}
        for index, (key, point) in enumerate(points, 1):
            group = point['label']
            for axis in axes_plan[1:]:
                name = axis['name']
                group += ' · {}={:g}'.format(name, point['parameters'][name])
            source = sources.get(tuple(point.get('source', ())), {})
            x = point['parameters'][x_name] if x_name else (source['rho'] if radial else index)
            if radial:
                group = source.get('coordinate', 'rho')
            if preset_scan:
                group = point['preset_label'] if radial else point['label']
                x = source['rho'] if radial else positions[point['preset_key']]
            qe = sum(row['heat'] for row in point['fluxes'] if row['species'] == 'elec')
            qi = sum(row['heat'] for row in point['fluxes'] if row['species'] != 'elec')
            groups.setdefault(group, []).append((x, qe, qi))
        figure, axes = subplots(2, 1, sharex=True, figsize=(7, 7))
        for label, values in groups.items():
            if preset_scan and radial:
                by_radius = {row[0]: row for row in values}
                values = [by_radius.get(s['rho'], (s['rho'], np.nan, np.nan)) for s in sources.values()]
            data = np.asarray(sorted(values))
            marker = 'o' if record['mode'] == 'uq' or (record['mode'] in ('single', 'preset') and not radial) else 'o-'
            for index, axis in enumerate(axes):
                axis.plot(data[:, 0], data[:, index + 1], marker, label=label)
        axes[0].set_ylabel(r'$Q_e/Q_{GB}$')
        axes[1].set_ylabel(r'$Q_i/Q_{GB}$')
        axes[1].set_xlabel(x_name or ('Radius' if radial else 'Point'))
        if preset_scan and not radial:
            axes[1].set_xticks(range(len(presets)))
            axes[1].set_xticklabels([p['label'] for p in presets], rotation=25, ha='right')
            axes[1].set_xlabel('TGLF 预设')
        for axis in axes:
            axis.legend(fontsize='small')
        figure.tight_layout()
