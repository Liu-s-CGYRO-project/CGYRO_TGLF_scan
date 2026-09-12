"""CGYRO/TGLF comparison: flux.

Extracted from the reviewed project; data is read from the supplied OMFIT tree.
"""

# OMFIT libraries inherit a pylab namespace; keep Python scalar/iterator semantics.
from builtins import (
    Exception,
    all,
    bytes,
    enumerate,
    float,
    getattr,
    hasattr,
    isinstance,
    len,
    list,
    min,
    range,
    str,
    sum,
)

import builtins
from numpy import (
    argsort,
    array,
    isfinite,
    nan,
    newaxis,
    transpose,
)
from OMFITlib_compare_core import (
    _fmt_curve_value,
    _maybe_abs_ky,
    normalize_flux_species_option,
    resolve_2d_param_node,
    resolve_key,
)


def _safe_axis_labels(values, prefix):
    """Convert coordinate values to robust string labels."""
    labels = []
    for i, v in enumerate(values):
        try:
            if isinstance(v, bytes):
                labels.append(v.decode(errors='ignore'))
            else:
                labels.append(str(v))
        except Exception:
            labels.append(f'{prefix}{i + 1}')
    return labels


def _format_species_label(label):
    """Keep 'elec' lowercase, capitalize first letter for other species labels."""
    text = str(label).strip()
    if len(text) == 0:
        return text
    if text.lower() == 'elec':
        return 'elec'
    return text[0].upper() + text[1:]


def _normalize_species_labels(labels):
    """Normalize species labels for display on y-axis."""
    return [_format_species_label(x) for x in labels]


def _read_species_labels_from_sum_flux(sum_flux):
    """
    Read species labels from sum_flux_spectrum['species'] when available.
    """
    # Preferred path: sum_flux_spectrum['species']
    if hasattr(sum_flux, 'keys'):
        sp_key = resolve_key(sum_flux, 'species')
        if sp_key is not None:
            try:
                sp_obj = sum_flux[sp_key]
                sp_vals = array(getattr(sp_obj, 'values', sp_obj)).ravel()
                return _safe_axis_labels(sp_vals, 'species')
            except Exception:
                pass

    # Fallback path: sum_flux_spectrum.coords['species']
    coords = getattr(sum_flux, 'coords', None)
    if coords is not None:
        try:
            if 'species' in coords:
                return _safe_axis_labels(array(coords['species']).ravel(), 'species')
        except Exception:
            pass

    return []


def _default_field_labels(n_fields):
    """Fallback names for field axis when coordinates are unavailable."""
    base = ['phi', 'B_perp', 'B_par']
    if n_fields <= len(base):
        return base[:n_fields]
    return base + [f'field{i + 1}' for i in range(len(base), n_fields)]


def _extract_flux_spectrum_quantity(node, quantity_name):
    """
    Extract one flux-spectrum quantity from node['sum_flux_spectrum'].

    Returns dict with:
      ky: 1D float array
      values: 3D float array shaped (species, field, ky)
      species_labels: list[str]
      field_labels: list[str]
    """
    if not hasattr(node, 'get'):
        return None

    sum_flux = node.get('sum_flux_spectrum', None)
    if sum_flux is None:
        return None

    q_obj = None
    qname = str(quantity_name).strip().lower()

    # Mapping / Dataset-like lookup.
    if hasattr(sum_flux, 'keys'):
        q_key = resolve_key(sum_flux, quantity_name)
        if q_key is None:
            for k in list(sum_flux.keys()):
                sk = str(k).strip().lower()
                if sk == qname or qname in sk:
                    q_key = k
                    break
        if q_key is not None:
            try:
                q_obj = sum_flux[q_key]
            except Exception:
                q_obj = None

    # Direct indexing fallback.
    if q_obj is None:
        try:
            q_obj = sum_flux[quantity_name]
        except Exception:
            q_obj = None

    # If sum_flux itself is a DataArray named particle/energy.
    if q_obj is None:
        if qname in str(getattr(sum_flux, 'name', '')).lower():
            q_obj = sum_flux

    if q_obj is None:
        return None

    try:
        raw_vals = array(getattr(q_obj, 'values', q_obj), dtype=float)
    except Exception:
        try:
            raw_vals = array(q_obj, dtype=float)
        except Exception:
            return None

    if raw_vals.size == 0:
        return None

    dims = list(getattr(q_obj, 'dims', []))
    if len(dims) != raw_vals.ndim:
        dims = []

    ky_axis = dims.index('ky') if 'ky' in dims else (raw_vals.ndim - 1)
    species_axis = dims.index('species') if 'species' in dims else None
    field_axis = dims.index('field') if 'field' in dims else None

    if raw_vals.ndim == 3:
        axes = [0, 1, 2]
        if species_axis is None:
            candidates = [a for a in axes if a not in [ky_axis, field_axis]]
            species_axis = candidates[0] if len(candidates) > 0 else 0
        if field_axis is None:
            candidates = [a for a in axes if a not in [ky_axis, species_axis]]
            field_axis = candidates[0] if len(candidates) > 0 else 1
        vals = transpose(raw_vals, (species_axis, field_axis, ky_axis))
    elif raw_vals.ndim == 2:
        if ky_axis not in [0, 1]:
            ky_axis = 1
        other_axis = 1 - ky_axis
        if species_axis is not None:
            mat = transpose(raw_vals, (species_axis, ky_axis))
            vals = mat[:, newaxis, :]
        elif field_axis is not None:
            mat = transpose(raw_vals, (field_axis, ky_axis))
            vals = mat[newaxis, :, :]
        else:
            mat = transpose(raw_vals, (other_axis, ky_axis))
            vals = mat[:, newaxis, :]
    elif raw_vals.ndim == 1:
        vals = raw_vals[newaxis, newaxis, :]
    else:
        return None

    coords = getattr(q_obj, 'coords', None)
    species_labels = _read_species_labels_from_sum_flux(sum_flux)
    field_labels = []
    ky = array(range(vals.shape[2]), dtype=float)

    if coords is not None:
        try:
            if len(species_labels) == 0 and 'species' in dims and 'species' in coords:
                species_labels = _safe_axis_labels(array(coords['species']).ravel(), 'species')
        except Exception:
            species_labels = []
        try:
            if 'field' in dims and 'field' in coords:
                field_labels = _safe_axis_labels(array(coords['field']).ravel(), 'field')
        except Exception:
            field_labels = []
        try:
            if 'ky' in dims and 'ky' in coords:
                ky_raw = array(coords['ky']).ravel()
                ky_try = []
                for x in ky_raw:
                    try:
                        ky_try.append(float(x))
                    except Exception:
                        ky_try.append(nan)
                ky_try = array(ky_try, dtype=float)
                if len(ky_try) == vals.shape[2] and all(isfinite(ky_try)):
                    ky = ky_try
        except Exception:
            pass

    if len(species_labels) >= vals.shape[0]:
        species_labels = species_labels[:vals.shape[0]]
    else:
        species_labels = [f'species{i + 1}' for i in range(vals.shape[0])]
    species_labels = _normalize_species_labels(species_labels)
    if len(field_labels) != vals.shape[1]:
        field_labels = _default_field_labels(vals.shape[1])
    if len(ky) != vals.shape[2]:
        ky = array(range(vals.shape[2]), dtype=float)

    sort_idx = argsort(ky)
    ky = ky[sort_idx]
    vals = vals[:, :, sort_idx]

    return {
        'ky': ky,
        'values': vals,
        'species_labels': species_labels,
        'field_labels': field_labels,
    }


def collect_tglf_flux_spectrum_curves(rho, tglf_selected_paras, root, quantity_name, ctx=None):
    """
    Collect flux-vs-ky curves from sum_flux_spectrum for one rho.

    Output:
      {
        'species_labels': [...],
        'field_labels': [...],
        'curves': {(i_species, i_field): [{'label','ky','y'}, ...]}
      }
    """
    out = {'species_labels': [], 'field_labels': [], 'curves': {}}
    spectra = root['TGLF_scan'].get('scanResults_spectra', {})
    rho_key = resolve_key(spectra, rho)
    if rho_key is None:
        return out
    rho_data = spectra[rho_key]

    for para, values in tglf_selected_paras.items():
        para_key = resolve_key(rho_data, para)
        if para_key is None:
            continue

        if hasattr(values, '__iter__') and not isinstance(values, str):
            vals = list(values)
        else:
            vals = [values]
        if len(vals) == 0:
            continue

        para_node = rho_data[para_key]
        for value in vals:
            value_key = resolve_key(para_node, value)
            if value_key is None:
                continue
            node = para_node[value_key]

            parsed = _extract_flux_spectrum_quantity(node, quantity_name)
            if parsed is None:
                continue

            ky = _maybe_abs_ky(parsed['ky'], ctx)
            data_3d = parsed['values']
            sp_labels = parsed['species_labels']
            fd_labels = parsed['field_labels']
            if len(ky) == 0 or data_3d.size == 0:
                continue

            if len(out['species_labels']) == 0:
                out['species_labels'] = sp_labels
            if len(out['field_labels']) == 0:
                out['field_labels'] = fd_labels

            n_sp = min(data_3d.shape[0], len(sp_labels))
            n_fd = min(data_3d.shape[1], len(fd_labels))
            curve_label = f'{para}={value}'

            for i_sp in range(n_sp):
                for i_fd in range(n_fd):
                    y = array(data_3d[i_sp, i_fd, :], dtype=float).ravel()
                    if len(y) != len(ky):
                        continue
                    out['curves'].setdefault((i_sp, i_fd), []).append({
                        'label': curve_label,
                        'ky': ky,
                        'y': y,
                    })

    return out


def find_flux_container(node):
    """
    Find nested flux payload.

    Supported payload styles:
    1) rec.array with dtype names containing 'Gam/Gam_GB' and 'Q/Q_GB'
    2) dict-like object with keys 'Gam/Gam_GB' and 'Q/Q_GB' (legacy fallback)
    """
    flux_keys = ['Gam/Gam_GB', 'Q/Q_GB']

    try:
        dtype_names = getattr(getattr(node, 'dtype', None), 'names', None)
        if dtype_names is not None and builtins.all(k in dtype_names for k in flux_keys):
            return node
    except Exception:
        pass

    if hasattr(node, 'keys'):
        keys = list(node.keys())
        if builtins.all(k in keys for k in flux_keys):
            return node
        for _k, v in node.items():
            found = find_flux_container(v)
            if found is not None:
                return found
    return None


def split_flux_species(flux_arr, flux_species='Both', merge_ions=True):
    """
    Split one legacy flux array into species components.

    Convention: index 0 is electron, the rest are ion channels.
    """
    arr = array(flux_arr, dtype=float).ravel()
    out = {}
    if len(arr) == 0:
        return out
    flux_species = normalize_flux_species_option(flux_species)

    if flux_species != 'Ion only':
        out['e'] = float(arr[0])

    ions = arr[1:]
    if len(ions) == 0 or flux_species == 'Electron only':
        return out

    if merge_ions:
        out['ion_sum'] = float(sum(ions))
    else:
        for i, val in enumerate(ions, start=1):
            out[f'i{i}'] = float(val)
    return out


def split_flux_species_recarray(rec, field_name, flux_species='Both', merge_ions=True):
    """
    Split one rec.array flux field into species curves.

    Expected rec-array row labels like: elec, ion1, ion2, ...
    """
    out = {}
    flux_species = normalize_flux_species_option(flux_species)
    dtype_names = getattr(getattr(rec, 'dtype', None), 'names', None)
    if dtype_names is None or field_name not in dtype_names:
        return out

    species_col = None
    for name in dtype_names:
        if name == field_name:
            continue
        try:
            kind = rec.dtype.fields[name][0].kind
        except Exception:
            kind = ''
        if kind in ('U', 'S', 'O'):
            species_col = name
            break

    ion_sum = 0.0
    ion_count = 0
    for idx, row in enumerate(rec):
        try:
            val = float(row[field_name])
        except Exception:
            continue

        if species_col is not None:
            try:
                species = str(row[species_col]).strip()
            except Exception:
                species = ''
        else:
            species = 'elec' if idx == 0 else f'ion{idx}'

        sp = species.lower()
        is_electron = (idx == 0 and species_col is None) or sp.startswith('elec') or sp in ('e', 'electron')
        if is_electron:
            if flux_species != 'Ion only':
                out['e'] = val
            continue

        if flux_species == 'Electron only':
            continue

        ion_count += 1
        if not merge_ions:
            if sp.startswith('ion') and len(species) > 0:
                ion_label = species
            else:
                ion_label = f'ion{ion_count}'
            out[ion_label] = val
        else:
            ion_sum += val

    if merge_ions and ion_count > 0:
        out['ion_sum'] = ion_sum
    return out


def extract_flux_components(node, flux_species='Both', merge_ions=True):
    """
    Return species-resolved dictionaries for Gamma and Q flux channels.
    Output: (gam_dict, q_dict)
    """
    container = find_flux_container(node)
    if container is None:
        return {}, {}

    flux_species = normalize_flux_species_option(flux_species)
    dtype_names = getattr(getattr(container, 'dtype', None), 'names', None)
    try:
        if dtype_names is not None:
            # Current data format: rec.array rows of species (elec/ion1/ion2...).
            gam = split_flux_species_recarray(container, 'Gam/Gam_GB', flux_species, merge_ions)
            q = split_flux_species_recarray(container, 'Q/Q_GB', flux_species, merge_ions)
        else:
            # Backward-compatible fallback for old dict-of-arrays flux payloads.
            gam = split_flux_species(container.get('Gam/Gam_GB', []), flux_species, merge_ions)
            q = split_flux_species(container.get('Q/Q_GB', []), flux_species, merge_ions)
    except Exception:
        return {}, {}
    return gam, q


def collect_tglf2d_flux_spectrum_curves(
    param_node, fixed_values, varying_values, fixed_is_para2, quantity_name, varying_name, fixed_name, ctx=None
):
    """
    Collect particle/energy flux-vs-ky curves from 2D spectra nodes.

    Output format matches collect_tglf_flux_spectrum_curves().
    """
    out = {'species_labels': [], 'field_labels': [], 'curves': {}}

    for fixed_val in fixed_values:
        for varying_val in varying_values:
            if fixed_is_para2:
                p1_val, p2_val = varying_val, fixed_val
            else:
                p1_val, p2_val = fixed_val, varying_val

            node = resolve_2d_param_node(param_node, p1_val, p2_val)
            if node is None:
                continue

            parsed = _extract_flux_spectrum_quantity(node, quantity_name)
            if parsed is None:
                continue

            ky = _maybe_abs_ky(parsed['ky'], ctx)
            data_3d = parsed['values']
            sp_labels = parsed['species_labels']
            fd_labels = parsed['field_labels']
            if len(ky) == 0 or data_3d.size == 0:
                continue

            if len(out['species_labels']) == 0:
                out['species_labels'] = sp_labels
            if len(out['field_labels']) == 0:
                out['field_labels'] = fd_labels

            n_sp = min(data_3d.shape[0], len(sp_labels))
            n_fd = min(data_3d.shape[1], len(fd_labels))
            curve_label = (
                f"{varying_name}={_fmt_curve_value(varying_val)}, "
                f"{fixed_name}={_fmt_curve_value(fixed_val)}"
            )

            for i_sp in range(n_sp):
                for i_fd in range(n_fd):
                    y = array(data_3d[i_sp, i_fd, :], dtype=float).ravel()
                    if len(y) != len(ky):
                        continue
                    out['curves'].setdefault((i_sp, i_fd), []).append({
                        'label': curve_label,
                        'ky': ky,
                        'y': y,
                    })

    return out
