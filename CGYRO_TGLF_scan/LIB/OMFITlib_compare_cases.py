"""Case and scan-value selection for the four comparison workflows."""

# OMFIT libraries inherit a pylab namespace; keep Python scalar/iterator semantics.
from builtins import (
    dict,
    list,
    str,
)
from OMFITlib_compare_widgets import (
    ComparisonWidgets,
)
from OMFITlib_compare_state import (
    activate_source,
    stable_keys,
    sync_flags,
    selected_items,
)


class CaseSelection(ComparisonWidgets):
    def _choose_cgyro(self, state, path, select_radii=True, legacy=False):
        runs = self.root.get('CGYRO_scan', {}).get('RUN_DB', {})
        state.setdefault('runid', '')
        self.ui.Separator('CGYRO 数据来源')
        self.ui.ComboBox(path('runid'), stable_keys(runs), '运行记录', default='', updateGUI=True,
                         width=28, kwlabel={'width': 16, 'anchor': 'w'})
        runid = state['runid']
        activate_source(state, str(runid))
        radii = stable_keys(runs.get(runid, {}))
        if not radii:
            self.ui.Label('请选择包含已保存线性扫描结果的运行记录。', align='left')
        selected_key = 'nr_CGYRO' if legacy else 'nr_selected'
        if select_radii:
            sync_flags(state, 'nr_flag', radii, selected_key)
            self.ui.Label('选择 CGYRO 输入案例', align='left')
            self._render_index_checkbox_grid(path('nr_flag')+'[{idx}]', radii)
            state[selected_key] = selected_items(state['nr_flag'], radii)
        return runs.get(runid, {}), radii

    def _choose_tglf(self, state, path, target='Spectra', select_radii=True):
        state.setdefault('spectra_mode', '1D')
        self.ui.Separator('TGLF 数据来源')
        self.ui.ComboBox(path('spectra_mode'), ['1D', '2D'], '扫描维度', default='1D', updateGUI=True,
                         width=18, kwlabel={'width': 16, 'anchor': 'w'})
        dimension = state['spectra_mode']
        key = 'scanResults2D' if dimension == '2D' else 'scanResults'
        if target == 'Spectra':
            key += '_spectra'
        activate_source(state, key)
        results = self.root.get('TGLF_scan', {}).get(key, {})
        radii = stable_keys(results)
        if not radii:
            self.ui.Label('没有已保存的 TGLF {} {}数据。'.format(dimension, '谱' if target == 'Spectra' else '通量'), align='left')
        if select_radii:
            sync_flags(state, 'rho_flag', radii, 'rho_selected')
            self.ui.Label('选择 TGLF 半径', align='left')
            self._render_index_checkbox_grid(path('rho_flag')+'[{idx}]', radii)
            state['rho_selected'] = selected_items(state['rho_flag'], radii)
        return results, radii

    def _cgyro_parameters(self, state, path, run, radii):
        if not radii:
            return
        self.ui.Separator('CGYRO 扫描参数与取值')
        parameters = self._intersection_of_keysets({nr: run[nr].keys() for nr in radii if nr in run})
        self._render_parameter_entries(
            state, 'para_flag', 'selected_paras', parameters,
            lambda i, name: path('para_flag', i), lambda name: path('selected_paras', name),
            lambda name: (v for nr in radii if name in run.get(nr, {}) for v in run[nr][name].keys()))

    def _tglf_parameters(self, state, path, results, radii):
        if not radii:
            return
        self.ui.Separator('TGLF 扫描参数与取值')
        parameters = self._intersection_of_keysets({rho: results[rho].keys() for rho in radii if rho in results})
        self._render_tglf_parameter_selection_block(
            state, path, results, parameters, state.get('spectra_mode', '1D'), radii)

    def render_mode_cgyro_vs_tglf(self, state):
        prefix = "root['SETTINGS']['PHYSICS']['CGYRO_vs_TGLF']"
        path = lambda *keys: self._dict_path(prefix, *keys)
        cg, tg = state.setdefault('CGYRO', {}), state.setdefault('TGLF', {})
        run, _ = self._choose_cgyro(cg, lambda *k: path('CGYRO', *k))
        results, rhos = self._choose_tglf(tg, lambda *k: path('TGLF', *k), select_radii=False)
        pairing_source = '{}|{}'.format(cg.get('runid', ''), tg.get('spectra_mode', '1D'))
        if tg.get('_pairing_run', None) not in (None, pairing_source):
            tg['rho_pair_flags'] = {}
        tg['_pairing_run'] = pairing_source
        selected = cg.get('nr_selected', [])
        pairs = tg.setdefault('rho_pair_flags', {})
        paired_rhos = []
        for nr in selected:
            key = str(nr)
            flags = pairs.setdefault(key, {})
            for rho in rhos:
                flags.setdefault(str(rho), False)
            self._prune_mapping_keys(flags, [str(rho) for rho in rhos])
            self.ui.Label('{} → 配对 TGLF 半径'.format(nr), align='left')
            self._render_key_checkbox_grid(lambda rho: path('TGLF', 'rho_pair_flags', key, str(rho)), rhos)
            paired_rhos.extend(rho for rho in rhos if flags.get(str(rho), None))
        self._cgyro_parameters(cg, lambda *k: path('CGYRO', *k), run, selected)
        self._tglf_parameters(tg, path, results, list(dict.fromkeys(paired_rhos)))

    def render_mode_tglf_vs_cgyro(self, state):
        prefix = "root['SETTINGS']['PHYSICS']['TGLF_vs_CGYRO']"
        path = lambda *keys: self._dict_path(prefix, *keys)
        cg, tg = state.setdefault('CGYRO', {}), state.setdefault('TGLF', {})
        results, _ = self._choose_tglf(tg, lambda *k: path('TGLF', *k))
        run, radii = self._choose_cgyro(cg, lambda *k: path('CGYRO', *k), select_radii=False)
        pairs = cg.setdefault('rho_pair_cfg', {})
        paired_radii = []
        for rho in tg.get('rho_selected', []):
            cfg = pairs.setdefault(str(rho), {})
            sync_flags(cfg, 'nr_flag', radii, 'nr_selected')
            self.ui.Label('TGLF {} → 配对 CGYRO 输入案例'.format(rho), align='left')
            self._render_index_checkbox_grid(path('CGYRO', 'rho_pair_cfg', str(rho), 'nr_flag')+'[{idx}]', radii)
            cfg['nr_selected'] = selected_items(cfg['nr_flag'], radii)
            paired_radii.extend(cfg['nr_selected'])
        self._tglf_parameters(tg, path, results, tg.get('rho_selected', []))
        self._cgyro_parameters(cg, lambda *k: path('CGYRO', *k), run, list(dict.fromkeys(paired_radii)))

    def render_mode_tglf_vs_tglf(self, state):
        prefix = "root['SETTINGS']['PHYSICS']['TGLF_vs_TGLF']"
        path = lambda *keys: self._dict_path(prefix, *keys)
        tg = state.setdefault('TGLF', {})
        target = state.get('plot', {}).get('tglf_vs_tglf_mode', 'Spectra')
        results, _ = self._choose_tglf(tg, lambda *k: path('TGLF', *k), target=target)
        self._tglf_parameters(tg, path, results, tg.get('rho_selected', []))

    def render_mode_cgyro_vs_cgyro(self, state):
        prefix = "root['SETTINGS']['PHYSICS']['CGYRO_vs_CGYRO']"
        path = lambda *keys: self._dict_path(prefix, *keys)
        state['plotcgyro'] = True
        run, _ = self._choose_cgyro(state, path, legacy=True)
        radii = state.get('nr_CGYRO', [])
        if not radii:
            return
        self.ui.Separator('扫描参数与取值')
        self.ui.CheckBox(path('force_read_all_nr_items'), '各输入案例分别选择参数',
                         default=False, updateGUI=True)
        if not state.get('force_read_all_nr_items', None):
            parameters = self._intersection_of_keysets({nr: run[nr].keys() for nr in radii if nr in run})
            self.ui.Label('选择共同参数，再填写需要比较的扫描值。', align='left')
            self._render_parameter_entries(
                state, 'para_list_flag', 'selected_paras', parameters,
                lambda i, name: path('para_list_flag', i), lambda name: path('selected_paras', name),
                lambda name: (v for nr in radii if name in run.get(nr, {}) for v in run[nr][name].keys()))
            return
        by_nr = state.setdefault('selected_paras_by_nr', {})
        flags_by_nr = state.setdefault('para_list_flag_by_nr', {})
        aggregate = {}
        for nr in radii:
            self.ui.Separator('{} · 扫描参数'.format(nr))
            node = run.get(nr, {})
            names = stable_keys(node)
            values = by_nr.setdefault(str(nr), {})
            flags = flags_by_nr.setdefault(str(nr), {})
            for name in names:
                flags.setdefault(name, name in values and self._is_nonempty_selection(values[name]))
            self._render_key_checkbox_grid(lambda name: path('para_list_flag_by_nr', str(nr), name), names)
            for name in names:
                if not flags.get(name, None):
                    values.pop(name, None)
                    continue
                values.setdefault(name, self._normalize_value_list(node[name].keys()))
                self._parameter_entry(path('selected_paras_by_nr', str(nr), name), name, values[name])
                aggregate.setdefault(name, []).extend(values[name])
        state['selected_paras'] = {name: self._normalize_value_list(values) for name, values in aggregate.items()}
