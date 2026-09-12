"""Four-step comparison panel: cases, plot, style, export/checks."""

# OMFIT libraries inherit a pylab namespace; keep Python scalar/iterator semantics.
from builtins import (
    ValueError,
    dict,
)
from collections import (
    OrderedDict,
)
from OMFITlib_compare_cases import (
    CaseSelection,
)
from OMFITlib_compare_state import (
    MODES,
    MODE_LABELS,
    STYLE_DEFAULTS,
    initialize_settings,
    plot_state,
    selection_check,
)


class ComparisonUI(CaseSelection):
    def render(self, open_templates=None):
        physics = initialize_settings(self.root)
        self.mode = physics['compare_mode']
        self.state = physics[self.mode]
        self.plot_settings = plot_state(self.mode, self.state)
        self.prefix = "root['SETTINGS']['PHYSICS'][{!r}]".format(self.mode)
        self.ui.TitleGUI('CGYRO / TGLF comparison')
        self.ui.ComboBox("root['SETTINGS']['PHYSICS']['compare_mode']",
                         OrderedDict((MODE_LABELS[mode], mode) for mode in MODES),
                         'Workflow', default='CGYRO_vs_TGLF', updateGUI=True)
        if self.mode == 'TGLF_vs_TGLF':
            self.ui.ComboBox(self._plot_path('tglf_vs_tglf_mode'),
                             OrderedDict([('Linear spectra', 'Spectra'), ('Integrated flux', 'Flux')]),
                             'Data to compare', default='Spectra', updateGUI=True)
        with self.ui.same_row():
            self.ui.Button('Plot selected data', self._plot)
            self.ui.Button('Check selection', self._refresh_check, updateGUI=True)
            if 'TGLF_multi' in self.root.get('GUIS', {}):
                self.ui.Button('TGLF 多 input.gacode 计算', lambda: self.root['GUIS']['TGLF_multi'].run())
            if open_templates is not None:
                self.ui.Button('Templates / GitHub', open_templates)
        self.ui.Tab('1. Cases')
        renderer = {
            'CGYRO_vs_TGLF': self.render_mode_cgyro_vs_tglf,
            'CGYRO_vs_CGYRO': self.render_mode_cgyro_vs_cgyro,
            'TGLF_vs_TGLF': self.render_mode_tglf_vs_tglf,
            'TGLF_vs_CGYRO': self.render_mode_tglf_vs_cgyro,
        }[self.mode]
        renderer(self.state)
        self.ui.Tab('2. Plot')
        self._render_plot()
        self.ui.Tab('3. Style')
        self._render_style()
        self.ui.Tab('4. Export & checks')
        self._render_actions()

    def _path(self, *keys):
        return self._dict_path(self.prefix, *keys)

    def _plot_path(self, key):
        return self._path(key) if self.mode == 'CGYRO_vs_CGYRO' else self._path('plot', key)

    def _entry(self, key, label, default):
        self.ui.Entry(self._plot_path(key), label, default=default)

    def _check(self, key, label, default=False):
        self.ui.CheckBox(self._plot_path(key), label, default=default, updateGUI=True)

    def _combo(self, key, options, label, default):
        self.ui.ComboBox(self._plot_path(key), options, label, default=default, updateGUI=True)

    def _render_scaling(self):
        self.ui.ComboBox(
            [self._plot_path('divide_by_ky'), self._plot_path('divide_by_ky2')],
            OrderedDict([('Raw omega and gamma', [False, False]),
                         ('omega / ky and gamma / ky', [True, False]),
                         ('omega / ky² and gamma / ky²', [False, True])]),
            'Spectrum scaling', default=[True, False], updateGUI=True)

    def _render_ratio(self, cross_model=False):
        self._combo('gamma_ref_mode', ['all ky', 'single ky'], 'Reference statistic', 'all ky')
        self._entry('gamma_ref_value', 'Reference scan value (blank = first valid selected value)', '')
        if self.plot_settings.get('gamma_ref_mode', 'all ky') == 'single ky':
            self._entry('gamma_ref_ky_values', 'ky values (comma-separated)', '')
        elif cross_model:
            with self.ui.same_row():
                self._entry('gamma_ref_ky_min', 'Minimum ky (blank = all)', '')
                self._entry('gamma_ref_ky_max', 'Maximum ky (blank = all)', '')
        if cross_model:
            self._check('gamma_ref_split_panels', 'Separate CGYRO and TGLF panels')
            if self.state.get('TGLF', {}).get('spectra_mode') == '2D':
                self._combo('gamma_ref_tglf2d_x_axis', ['para1', 'para2'], 'Scan axis for ratio', 'para1')
            self._render_tolerance_toggle(self._plot_path, self.plot_settings,
                                          'gamma_ref_error_filter', 'Filter unconverged CGYRO points')
        self.ui.Label('Ratios use gamma itself, independent of the spectrum /ky scaling.', align='left')

    def _render_plot(self):
        settings = self.plot_settings
        self_mode = self.mode == 'CGYRO_vs_CGYRO'
        tglf_only = self.mode == 'TGLF_vs_TGLF'
        if tglf_only:
            flux = settings.get('tglf_vs_tglf_mode') == 'Flux'
            dimension = self.state.get('TGLF', {}).get('spectra_mode', '1D')
            if dimension == '2D':
                if not flux:
                    self._combo('tglf2d_plot_mode', ['2D', '3D'], 'Spectrum view', '2D')
                self._combo('tglf2d_x_axis', ['para1', 'para2'],
                            'Varying scan parameter (other parameter is fixed)', 'para1')
            if flux:
                self._combo('tglf_flux_species', ['Both', 'Electron only', 'Ion only'], 'Flux species', 'Both')
                if settings.get('tglf_flux_species', 'Both') != 'Electron only':
                    self._check('tglf_flux_merge_ions', 'Sum all ion channels', True)
            else:
                self._render_scaling()
                self._check('show_flux_spectra', 'Include particle and energy flux spectra', True)
            return
        modes = OrderedDict([('Frequency / growth-rate spectra', 'Plot 2D')])
        if self_mode:
            modes.update([('Scan at selected ky', 'Plot single ky'),
                          ('Growth-rate ratio', 'Plot γ/γ_ref'),
                          ('3D scan view', 'Plot 3D'), ('Ballooning eigenfunctions', 'Plot eigen ball')])
        else:
            modes['Growth-rate ratio'] = 'Plot γ/γ_ref'
        self._combo('plot_mode', modes, 'Plot content', 'Plot 2D')
        mode = settings.get('plot_mode', 'Plot 2D')
        ratio, eigen = mode == 'Plot γ/γ_ref', mode == 'Plot eigen ball'
        if self_mode and mode != 'Plot 3D':
            self._check('merge_all_nr_plot', 'Combine selected radii in one figure')
        if self_mode:
            self._check('abs_ky', 'Use absolute ky (combines +/- ky in scan views)')
        self.ui.Separator()
        self._entry('ave_window', 'Final fraction used for averaging (0.02 = 2%)', .02)
        if ratio:
            self._render_ratio(cross_model=not self_mode)
        elif eigen:
            self.ui.Label('Uses saved balloon fields. Missing E-parallel is shown as unavailable.', align='left')
            self._combo('eigen_ky_mode', ['max gamma', 'single ky'], 'Choose ky by', 'max gamma')
            if settings.get('eigen_ky_mode', 'max gamma') == 'single ky':
                self._entry('eigen_ky_values', 'ky values (comma-separated)', '')
            else:
                self._render_tolerance_toggle(self._plot_path, settings, 'eigen_error_filter', 'Filter unconverged points')
            self._check('eigen_abs', 'Show absolute field amplitude (otherwise Re / Im)')
        else:
            if mode == 'Plot single ky':
                self._entry('single_ky_values', 'ky values (blank = all; nearest saved ky is used)', '')
            if self_mode and mode == 'Plot 2D':
                self._combo('error_flag', OrderedDict([
                    ('Spectra + relative time fluctuation', 'CGYRO'), ('Spectra only', 'No_error')]),
                    'Panels', 'CGYRO')
            if not self_mode:
                self._combo('error_flag', OrderedDict([
                    ('Spectra only', 'No_error'),
                    ('CGYRO relative time fluctuation', 'CGYRO'),
                    ('Model difference / |CGYRO|', 'CGYRO-TGLF')]), 'Comparison panels', 'CGYRO')
                if settings.get('error_flag') == 'No_error':
                    self._combo('comparison_layout', ['Overlay', 'Separate models'], 'Panel layout', 'Overlay')
                if settings.get('error_flag') == 'CGYRO-TGLF':
                    self.ui.Label('Select exactly one reference curve in at least one model per page.', align='left')
            self._render_scaling()
        if not eigen:
            self._check('normalize_main_ion', 'Normalize using the main ion')
        if self_mode and not eigen:
            self._render_tolerance_toggle(self._plot_path, settings, 'error_filter', 'Filter unconverged points')
            if mode == 'Plot 2D':
                self._check('highlight_max_gamma', 'Mark maximum raw gamma (before /ky scaling)')

    def _render_style(self):
        style = self.state['style']
        self.ui.Label('Figure and line appearance', align='left')
        for key, label in [('font_size', 'Axis / title font size'), ('legend_font_size', 'Legend font size'),
                           ('line_width', 'Line width')]:
            self.ui.Entry(self._path('style', key), label, default=STYLE_DEFAULTS[key])
        with self.ui.same_row():
            self.ui.Entry(self._path('style', 'figure_width'), 'Width, inches (0 = auto)', default=0.)
            self.ui.Entry(self._path('style', 'figure_height'), 'Height, inches (0 = auto)', default=0.)
        self.ui.CheckBox(self._path('style', 'show_grid'), 'Light grid', default=True)
        with self.ui.same_row():
            self._check('plot_log_x', 'Log X')
            self._check('plot_log_y', 'Log Y')
            if self.mode == 'CGYRO_vs_CGYRO' and self.plot_settings.get('plot_mode') == 'Plot 3D':
                self._check('plot_log_z', 'Log Z')
        if self.plot_settings.get('plot_log_y'):
            self.ui.Label('Log Y hides zero and negative values; linear Y preserves signed spectra.', align='left')
        self.ui.Separator()
        self.ui.ComboBox(self._path('style', 'legend_location'), ['best', 'upper right', 'upper left', 'outside'],
                         'Legend position', default='best')
        cg = self.state if self.mode == 'CGYRO_vs_CGYRO' else self.state.get('CGYRO', {})
        tg = self.state.get('TGLF', {})
        names = self._selected_param_keys(cg.get('selected_paras', {}))
        names += self._selected_param_keys(tg.get('selected_paras', {}))
        names += self._selected_param_keys(tg.get('selected_paras_2d', {}))
        self._render_legend_order_controls(self._path, self.state, ','.join(dict.fromkeys(names)))
        self.ui.Button('Restore appearance defaults', self._reset_style, updateGUI=True)

    def _reset_style(self):
        self.state['style'] = dict(STYLE_DEFAULTS)

    def _render_actions(self):
        report = selection_check(self.root)
        self.ui.Label(report['summary'], align='left')
        for message in report['errors'] + report['warnings']:
            self.ui.Label('• '+message, align='left')
        self.ui.Separator()
        spectra = not (self.mode == 'TGLF_vs_TGLF' and self.plot_settings.get('tglf_vs_tglf_mode') == 'Flux')
        if spectra:
            self.ui.Button('Export selected omega / gamma data...', self._export)
            self.ui.Label('A new export folder keeps existing files. Raw spectra and settings are recorded.', align='left')
        if self.mode == 'CGYRO_vs_CGYRO':
            self.ui.Button('Show CGYRO run-status map', self._status)
        self.ui.Label('Use the figure toolbar to save PNG / PDF / SVG.', align='left')
        self.ui.Label('Opening this panel reads selections only; Plot loads the requested result data.', align='left')

    def _refresh_check(self):
        return selection_check(self.root)

    def _assert_selection(self):
        report = selection_check(self.root)
        if report['errors']:
            raise ValueError('\n'.join(report['errors']))

    def _plot(self):
        self._assert_selection()
        key = 'CGYRO_vs_CGYRO' if self.mode == 'CGYRO_vs_CGYRO' else 'CGYRO_vs_TGLF'
        # OMFIT controls its own script cache; do not reload over unsaved editor changes.
        self.root['PLOTS'][key].plot()

    def _export(self):
        flag = 'linear_export_now' if self.mode == 'CGYRO_vs_CGYRO' else 'comparison_export_now'
        old = self.state.get(flag, False)
        self.state[flag] = True
        try:
            self._assert_selection()
            directory = self._select_export_directory(self.state.get('linear_export_dir', ''))
            if directory is None:
                return
            self.state['linear_export_dir'] = directory
            self._plot()
        finally:
            self.state[flag] = old

    def _status(self):
        old = self.state.get('check_cgyro_output_now', False)
        self.state['check_cgyro_output_now'] = True
        try:
            self.root['PLOTS']['CGYRO_vs_TGLF'].plot()
        finally:
            self.state['check_cgyro_output_now'] = old
