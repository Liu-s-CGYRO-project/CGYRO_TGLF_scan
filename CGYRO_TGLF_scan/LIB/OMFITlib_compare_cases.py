"""Case and scan-value selection for the four comparison workflows."""
from OMFITlib_cgyro_archive import catalog_runs
from builtins import next, iter
from OMFITlib_plot_sources import run_choices, source_dimension, selected_tglf_source, tglf_results
# OMFIT libraries inherit a pylab namespace; keep Python scalar/iterator semantics.
from builtins import (
    ValueError,
    any,
    delattr,
    dict,
    enumerate,
    getattr,
    len,
    list,
    str,
)
from collections import Counter, OrderedDict
from contextlib import contextmanager
from OMFITlib_cgyro_archive import latest_cases, remap_case_selection, remap_pair_flags
from OMFITlib_cgyro_scan_view import multiaxis_scans, axis_values
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
    @contextmanager
    def _catalog_scope(self, catalog=None):
        """Share requested run metadata while constructing sibling selectors.

        The GUI is synchronous. Clear the snapshot even if rendering is
        aborted, so the next update sees newly collected/replaced archives.
        Only this transient controller attribute holds the view; the project
        tree and result owners are never changed or copied.
        """
        previous = getattr(self, '_cgyro_catalog', None)
        if catalog is None:
            # Plot/style options need no archive catalog. Case selectors fill
            # this render-local mapping only for the explicitly selected run.
            catalog = previous if previous is not None else {}
        self._cgyro_catalog = catalog
        try:
            yield catalog
        finally:
            if previous is None:
                delattr(self, '_cgyro_catalog')
            else:
                self._cgyro_catalog = previous

    def _multi_axis_entries(self, state, path, run, radii, name, selected, nr=None):
        """Select each real axis; the remaining fixed coordinates form slices."""
        scans = [multiaxis_scans(run[case], selected=[name]).get(str(name), None) for case in radii if case in run]
        scans = [scan for scan in scans if scan is not None]
        if not scans:
            return False
        choices = [axis_values(scan) for scan in scans]
        names = list(choices[0])
        if any(list(values) != names for values in choices):
            raise ValueError('同名扫描的参数轴不一致，请勾选“各输入案例分别选择参数”。')
        if nr is None:
            configs = state.setdefault('cgyro_multi', {})
            cfg_path = lambda *keys: path('cgyro_multi', name, *keys)
        else:
            configs = state.setdefault('cgyro_multi_by_nr', {}).setdefault(str(nr), {})
            cfg_path = lambda *keys: path('cgyro_multi_by_nr', str(nr), name, *keys)
        cfg = configs.setdefault(str(name), {})
        if cfg.get('axis', None) not in names:
            cfg['axis'] = names[0]
        values = cfg.setdefault('values', {})
        self.ui.Separator(' × '.join(names))
        for axis in names:
            available = self._normalize_value_list(value for choice in choices for value in choice[axis])
            if axis not in values:
                values[axis] = selected[name] if axis == names[0] else available.copy()
            self._parameter_entry(cfg_path('values', axis), axis, values[axis], default_values=available)
        self.ui.ComboBox(cfg_path('axis'), names, '变化参数', default=names[0], updateGUI=True,
                         width=20, kwlabel={'width': 20, 'anchor': 'w'},
                         help='指定 ky、增长率比值和三维图使用此参数作为变化轴，其余参数逐个固定分组。\n'
                              '各轴取值共同筛选实际保存的组合；部分结果中的缺点保留为空，不混合不同参数组合。')
        # Keep the inline hint short. Some X11 fallback fonts report less line
        # height than their CJK glyphs need; a wrapped ttk.Label then overlaps.
        # Full guidance lives in the scrollable help window with real leading.
        note = self.ui.Label('按完整组合筛选，缺失结果留空。', align='left')
        if note is not None:
            note._cgyro_role = 'note'
        # Retain the old first-axis selection shape for saved-setting migration.
        selected[name] = values[names[0]]
        return True

    def _activate_pairing(self, owner, cgyro, tglf, field):
        """A radius pairing belongs to both runs, even when rho labels match.

        Each workflow stores pairings under its secondary model's selection
        state. Source snapshots preserve that state, while this guard prevents
        a different run of the other model from inheriting its pairings.
        """
        source = '{}|{}'.format(cgyro.get('runid', ''), tglf.get('result_source', ''))
        if owner.get('_pairing_run', None) not in (None, source):
            owner[field] = {}
        owner['_pairing_run'] = source

    def _cgyro_radius_groups(self, cases):
        """Group isotope result keys under their original radial input."""
        groups = OrderedDict()
        for index, case in enumerate(cases):
            parts = self._case_parts(case)
            if parts is None:
                key, nr = 'legacy:' + str(case), ''
                caption, _ = self._choice_label(case)
                ion = '已有结果'
            else:
                nr, rho, ion = parts
                key = 'nr={}__rho={}'.format(nr, rho)
                caption = 'nr=' + nr if rho == 'unknown' else 'ρ=' + rho
                if rho == 'unknown' and nr.startswith('RMIN='):
                    caption = nr
                elif rho == 'unknown' and nr.startswith('legacy-output-'):
                    caption = '未标识旧结果 ' + nr.rsplit('-', 1)[-1]
                ion = '原始' if ion == 'BASE' else '未标识' if ion == 'UNKNOWN' else ion
            group = groups.setdefault(key, dict(caption=caption, nr=nr, cases=[]))
            group['cases'].append(dict(index=index, key=case, ion=ion))
        counts = Counter(group['caption'] for group in groups.values())
        ion_order = {'原始': 0, 'H': 1, 'D': 2, 'T': 3}
        for group in groups.values():
            if counts[group['caption']] > 1 and group['nr']:
                group['caption'] += ' · nr=' + group['nr']
            group['cases'].sort(key=lambda case: ion_order.get(case['ion'], 4))
        return groups

    def _select_cgyro_cases(self, state, path, cases, selected_key='nr_selected'):
        """A single-case radius is sufficient; expose choices only when needed."""
        remap_case_selection(state, getattr(self, '_cgyro_case_aliases', {}))
        flags = sync_flags(state, 'nr_flag', cases, selected_key)
        groups = self._cgyro_radius_groups(cases)
        keys = list(groups)
        if 'cgyro_radius_flag' not in state and 'cgyro_radius_selected' not in state:
            # Preserve old flat selections on the first visit to each source.
            state['cgyro_radius_selected'] = [key for key, group in groups.items()
                if any(flags.get(case['index'], False) for case in group['cases'])]
        radius_flags = sync_flags(state, 'cgyro_radius_flag', keys, 'cgyro_radius_selected')
        labels = {key: (group['caption'], '单一离子随半径自动选择；多个离子可在下方全选或逐项调整。')
                  for key, group in groups.items()}
        self.ui.Label('1 选择 CGYRO 半径', align='left')
        def select_radii(enabled):
            for index, key in enumerate(keys):
                radius_flags[index] = enabled
            # The GUI refresh applies the radius selection to exact case keys.
        if keys:
            with self.ui.same_row():
                self.ui.Button('全选半径', lambda: select_radii(True), updateGUI=True)
                self.ui.Button('清空半径', lambda: select_radii(False), updateGUI=True)
        self._render_index_checkbox_grid(path('cgyro_radius_flag') + '[{idx}]', keys, labels=labels)
        state['cgyro_radius_selected'] = selected_items(radius_flags, keys)
        choices = [groups[key] for key in state['cgyro_radius_selected']
                   if len(groups[key]['cases']) > 1]
        if choices:
            self.ui.Label('2 选择所选半径的离子', align='left')
            def select_ions(enabled):
                # Only groups with a real choice need isotope flags. A sole
                # case remains controlled by its radius, including on clear.
                for group in choices:
                    for case in group['cases']:
                        flags[case['index']] = enabled
            with self.ui.same_row():
                self.ui.Button('全选离子', lambda: select_ions(True), updateGUI=True)
                self.ui.Button('清空离子', lambda: select_ions(False), updateGUI=True)
        for index, key in enumerate(keys):
            group = groups[key]
            if not radius_flags.get(index, False):
                for case in group['cases']:
                    flags[case['index']] = False
                continue
            if len(group['cases']) == 1:
                # Choosing a radius with only one available case already
                # identifies the data; do not require the same choice twice.
                flags[group['cases'][0]['index']] = True
                continue
            self.ui.Separator(group['caption'])
            indices = {case['key']: case['index'] for case in group['cases']}
            ion_labels = {case['key']: (case['ion'], str(case['key'])) for case in group['cases']}
            self._render_key_checkbox_grid(lambda case: path('nr_flag', indices[case]),
                                           list(indices), labels=ion_labels)
        # Readers retain exact archive identities; a multiple-case radius
        # still requires its explicit individual or bulk isotope selection.
        state[selected_key] = selected_items(flags, cases)

    def _choose_cgyro(self, state, path, select_radii=True, legacy=False):
        module = self.root.get('CGYRO_scan', {})
        runs = getattr(self, '_cgyro_catalog', None)
        if runs is None:
            runs = {}
        state.setdefault('runid', '')
        self.ui.Separator('CGYRO 数据来源')
        self.ui.ComboBox(path('runid'), stable_keys(module.get('RUN_DB', {})), '运行记录', default='', updateGUI=True,
                         width=28, kwlabel={'width': 16, 'anchor': 'w'})
        runid = state['runid']
        activate_source(state, str(runid))
        if runid not in runs:
            runs.update(catalog_runs(module, runid=runid))
        visible, self._cgyro_case_aliases = latest_cases(module, runid, catalog=runs)
        radii = stable_keys(dict.fromkeys(visible))
        if not radii:
            self.ui.Label('请选择包含已保存线性扫描结果的运行记录。', align='left')
        selected_key = 'nr_CGYRO' if legacy else 'nr_selected'
        if select_radii:
            self._select_cgyro_cases(state, path, radii, selected_key)
        return runs.get(runid, {}), radii

    def _choose_tglf(self, state, path, target='Spectra', select_radii=True):
        self.ui.Separator('TGLF 数据来源')
        choices = run_choices(self.root)
        if not choices:
            self.ui.Label('尚无已完成的 TGLF 计算。', align='left')
            return {}, []
        source = selected_tglf_source(self.root, state, choices=choices)
        state['result_source'] = source if source in choices.values() else next(iter(choices.values()))
        self.ui.ComboBox(path('result_source'), choices, '运行记录', updateGUI=True,
                         state='readonly', width=36, kwlabel={'width': 12, 'anchor': 'w'})
        dimension = source_dimension(self.root, state['result_source'])
        state['spectra_mode'] = dimension
        activate_source(state, state['result_source'] + ':' + target)
        results = tglf_results(self.root, state, target)
        radii = stable_keys(results)
        if not radii:
            self.ui.Label('这次运行没有可用的{}；请选择其他运行记录。'.format(
                '频率 / 增长率谱' if target == 'Spectra' else '通量'), align='left')
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
            lambda name: (v for nr in radii if name in run.get(nr, {}) for v in run[nr][name].keys()),
            entry_renderer=lambda name, selected: self._multi_axis_entries(state, path, run, radii, name, selected))

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
        run, radii = self._choose_cgyro(cg, lambda *k: path('CGYRO', *k))
        labels = self._choice_labels(radii)
        results, rhos = self._choose_tglf(tg, lambda *k: path('TGLF', *k), select_radii=False)
        self._activate_pairing(tg, cg, tg, 'rho_pair_flags')
        remap_pair_flags(tg, self._cgyro_case_aliases)
        selected = cg.get('nr_selected', [])
        pairs = tg.setdefault('rho_pair_flags', {})
        paired_rhos = []
        for nr in selected:
            key = str(nr)
            flags = pairs.setdefault(key, {})
            for rho in rhos:
                flags.setdefault(str(rho), False)
            self._prune_mapping_keys(flags, [str(rho) for rho in rhos])
            self.ui.Label('{} → 配对 TGLF 半径'.format(labels[nr][0]), align='left')
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
        self._activate_pairing(cg, cg, tg, 'rho_pair_cfg')
        pairs = cg.setdefault('rho_pair_cfg', {})
        paired_radii = []
        for rho in tg.get('rho_selected', []):
            cfg = pairs.setdefault(str(rho), {})
            self.ui.Label('TGLF {} → 配对 CGYRO 输入案例'.format(rho), align='left')
            self._select_cgyro_cases(cfg, lambda *keys: path('CGYRO', 'rho_pair_cfg', str(rho), *keys), radii)
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
        run, available = self._choose_cgyro(state, path, legacy=True)
        labels = self._choice_labels(available)
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
                lambda name: (v for nr in radii if name in run.get(nr, {}) for v in run[nr][name].keys()),
                entry_renderer=lambda name, selected: self._multi_axis_entries(state, path, run, radii, name, selected))
            return
        by_nr = state.setdefault('selected_paras_by_nr', {})
        flags_by_nr = state.setdefault('para_list_flag_by_nr', {})
        aggregate = {}
        for nr in radii:
            self.ui.Separator('{} · 扫描参数'.format(labels[nr][0]))
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
                if not self._multi_axis_entries(state, path, run, [nr], name, values, nr=nr):
                    self._parameter_entry(path('selected_paras_by_nr', str(nr), name), name, values[name],
                                          default_values=self._normalize_value_list(node[name].keys()))
                aggregate.setdefault(name, []).extend(values[name])
        state['selected_paras'] = {name: self._normalize_value_list(values) for name, values in aggregate.items()}
