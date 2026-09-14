"""Native OMFIT comparison tabs with a shared check/plot action area."""

# OMFIT libraries inherit a pylab namespace; keep Python scalar/iterator semantics.
from builtins import (
    ValueError,
    dict,
    len,
)
from collections import (
    OrderedDict,
)
from OMFITlib_compare_cases import (
    CaseSelection,
)
from OMFITlib_project import comparison_issues
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
        self.ui.TitleGUI('CGYRO / TGLF · 对比绘图')
        self.ui.ComboBox("root['SETTINGS']['PHYSICS']['compare_mode']",
                         OrderedDict((MODE_LABELS[mode], mode) for mode in MODES),
                         '对比方式', default='CGYRO_vs_TGLF', updateGUI=True, width=28,
                         kwlabel={'width': 12, 'anchor': 'w'})
        if self.mode == 'TGLF_vs_TGLF':
            self.ui.ComboBox(self._plot_path('tglf_vs_tglf_mode'),
                             OrderedDict([('频率 / 增长率谱', 'Spectra'), ('积分通量', 'Flux')]),
                             '对比数据', default='Spectra', updateGUI=True, width=24,
                             kwlabel={'width': 12, 'anchor': 'w'})
        self.ui.Tab('1 案例选择')
        renderer = {
            'CGYRO_vs_TGLF': self.render_mode_cgyro_vs_tglf,
            'CGYRO_vs_CGYRO': self.render_mode_cgyro_vs_cgyro,
            'TGLF_vs_TGLF': self.render_mode_tglf_vs_tglf,
            'TGLF_vs_CGYRO': self.render_mode_tglf_vs_cgyro,
        }[self.mode]
        renderer(self.state)
        self.ui.Tab('2 绘图设置')
        self._render_plot()
        self.ui.Tab('3 图形样式')
        self._render_style()
        self.ui.Tab('4 导出与检查')
        self._render_actions()
        self._render_related_tools(open_templates)
        # EFIT/TGLF native GUIs return to the untabbed frame for common actions.
        self.ui.Tab('')
        self.ui.Separator()
        report = selection_check(self.root)
        missing = comparison_issues(self.root, self.mode)
        if missing:
            status = '暂无可绘图的数据：' + '；'.join(missing)
        elif report['errors']:
            status = '选择尚未完成 · {} 项待检查，请查看“导出与检查”。'.format(len(report['errors']))
        else:
            status = '当前选择已就绪 · 点击绘图读取所选结果。'
        self.ui.Label(status, align='left')
        with self.ui.same_row():
            self.ui.Button('检查选择', self._refresh_check, updateGUI=True, width=16)
            self.ui.Button('绘制所选数据', self._plot, state='disabled' if missing else 'normal', width=20,
                           help='按当前案例、参数和绘图设置生成图形。计算结果仅在点击后读取。')

    def _path(self, *keys):
        return self._dict_path(self.prefix, *keys)

    def _plot_path(self, key):
        return self._path(key) if self.mode == 'CGYRO_vs_CGYRO' else self._path('plot', key)

    def _entry(self, key, label, default, help='', width=18):
        self.ui.Entry(self._plot_path(key), label, default=default, help=help, width=width,
                      kwlabel={'width': 16, 'anchor': 'w'})

    def _check(self, key, label, default=False, help=''):
        self.ui.CheckBox(self._plot_path(key), label, default=default, updateGUI=True, help=help)

    def _combo(self, key, options, label, default, help=''):
        self.ui.ComboBox(self._plot_path(key), options, label, default=default, updateGUI=True,
                         help=help, width=24, kwlabel={'width': 16, 'anchor': 'w'})

    def _render_scaling(self):
        self.ui.ComboBox(
            [self._plot_path('divide_by_ky'), self._plot_path('divide_by_ky2')],
            OrderedDict([('原始 ω、γ', [False, False]),
                         ('ω / ky、γ / ky', [True, False]),
                         ('ω / ky²、γ / ky²', [False, True])]),
            '谱显示量', default=[True, False], updateGUI=True, width=24,
            kwlabel={'width': 16, 'anchor': 'w'})

    def _render_ratio(self, cross_model=False):
        self._combo('gamma_ref_mode', OrderedDict([('全部 ky', 'all ky'), ('指定 ky', 'single ky')]), '参考统计范围', 'all ky')
        self._entry('gamma_ref_value', '参考扫描值', '', help='留空时采用所选数据中的第一个有效扫描值。')
        if self.plot_settings.get('gamma_ref_mode', 'all ky') == 'single ky':
            self._entry('gamma_ref_ky_values', '参考 ky', '', help='多个 ky 用逗号分隔。')
        elif cross_model:
            with self.ui.same_row():
                self._entry('gamma_ref_ky_min', 'ky 下限', '', width=8)
                self._entry('gamma_ref_ky_max', 'ky 上限', '', width=8)
        if cross_model:
            self._check('gamma_ref_split_panels', 'CGYRO / TGLF 分开显示')
            if self.state.get('TGLF', {}).get('spectra_mode', None) == '2D':
                self._combo('gamma_ref_tglf2d_x_axis', ['para1', 'para2'], '比值扫描轴', 'para1')
            self._render_tolerance_toggle(self._plot_path, self.plot_settings,
                                          'gamma_ref_error_filter', '过滤未收敛 CGYRO 点')
        self.ui.Label('比值使用原始 γ，不受 /ky 或 /ky² 显示设置影响。', align='left')

    def _render_plot(self):
        settings = self.plot_settings
        self_mode = self.mode == 'CGYRO_vs_CGYRO'
        tglf_only = self.mode == 'TGLF_vs_TGLF'
        self.ui.Separator('绘图内容')
        if tglf_only:
            flux = settings.get('tglf_vs_tglf_mode', None) == 'Flux'
            dimension = self.state.get('TGLF', {}).get('spectra_mode', '1D')
            if dimension == '2D':
                if not flux:
                    self._combo('tglf2d_plot_mode', ['2D', '3D'], '谱图形式', '2D')
                self._combo('tglf2d_x_axis', ['para1', 'para2'],
                            '变化的扫描参数', 'para1', help='另一个扫描参数在各条曲线中保持固定。')
            if flux:
                self._combo('tglf_flux_species', OrderedDict([('电子与离子', 'Both'), ('仅电子', 'Electron only'), ('仅离子', 'Ion only')]), '通量物种', 'Both')
                if settings.get('tglf_flux_species', 'Both') != 'Electron only':
                    self._check('tglf_flux_merge_ions', '合并所有离子通道', True)
            else:
                self._render_scaling()
                self._check('show_flux_spectra', '同时显示粒子与能量通量谱', True)
            return
        modes = OrderedDict([('频率 / 增长率谱', 'Plot 2D')])
        if self_mode:
            modes.update([('指定 ky 的参数扫描', 'Plot single ky'),
                          ('增长率比值 γ / γ_ref', 'Plot γ/γ_ref'),
                          ('三维扫描图', 'Plot 3D'), ('Ballooning 本征函数', 'Plot eigen ball')])
        else:
            modes['增长率比值 γ / γ_ref'] = 'Plot γ/γ_ref'
        self._combo('plot_mode', modes, '绘图类型', 'Plot 2D')
        mode = settings.get('plot_mode', 'Plot 2D')
        ratio, eigen = mode == 'Plot γ/γ_ref', mode == 'Plot eigen ball'
        if self_mode:
            with self.ui.same_row():
                if mode != 'Plot 3D':
                    self._check('merge_all_nr_plot', '合并所选半径')
                self._check('abs_ky', '使用 |ky|', help='扫描图中将正、负 ky 按绝对值合并。')
        self.ui.Separator('统计与归一化')
        self._entry('ave_window', '末段平均比例', .02, help='0.02 表示采用时间序列最后 2% 的数据；取值必须大于 0 且不超过 1。', width=10)
        if not eigen:
            self._check('normalize_main_ion', '按主离子归一化')
        self.ui.Separator('当前绘图选项')
        if ratio:
            self._render_ratio(cross_model=not self_mode)
        elif eigen:
            self._combo('eigen_ky_mode', OrderedDict([('最大增长率', 'max gamma'), ('指定 ky', 'single ky')]), 'ky 选择方式', 'max gamma')
            if settings.get('eigen_ky_mode', 'max gamma') == 'single ky':
                self._entry('eigen_ky_values', 'ky 列表', '', help='多个 ky 用逗号分隔。')
            else:
                self._render_tolerance_toggle(self._plot_path, settings, 'eigen_error_filter', '过滤未收敛点')
            self._check('eigen_abs', '显示场幅值', help='未勾选时分别显示实部与虚部。')
            self.ui.Label('读取已保存的 balloon 场；缺失的平行电场标记为不可用。', align='left')
        else:
            if mode == 'Plot single ky':
                self._entry('single_ky_values', 'ky 列表', '', help='留空时使用全部 ky；输入多个值时用逗号分隔，匹配最近的已保存 ky。')
            if self_mode and mode == 'Plot 2D':
                self._combo('error_flag', OrderedDict([
                    ('谱 + 相对时间波动', 'CGYRO'), ('仅频率 / 增长率谱', 'No_error')]),
                    '子图内容', 'CGYRO')
            if not self_mode:
                self._combo('error_flag', OrderedDict([
                    ('仅频率 / 增长率谱', 'No_error'),
                    ('CGYRO 相对时间波动', 'CGYRO'),
                    ('模型差值 / |CGYRO|', 'CGYRO-TGLF')]), '子图内容', 'CGYRO')
                if settings.get('error_flag', None) == 'No_error':
                    self._combo('comparison_layout', OrderedDict([('叠加显示', 'Overlay'), ('按模型分图', 'Separate models')]), '子图布局', 'Overlay')
                if settings.get('error_flag', None) == 'CGYRO-TGLF':
                    self.ui.Label('每页至少有一个模型只选择一条曲线，用作差值参考。', align='left')
            self._render_scaling()
        if self_mode and not eigen:
            self._render_tolerance_toggle(self._plot_path, settings, 'error_filter', '过滤未收敛点')
            if mode == 'Plot 2D':
                self._check('highlight_max_gamma', '标记当前曲线最大 γ',
                            help='标记每条曲线当前显示的最大值：原始 γ、γ/ky 或 γ/ky²，跟随谱显示量、归一化与过滤设置；排除无效或被对数坐标隐藏的点。')

    def _render_style(self):
        self.ui.Separator('字体与线条')
        with self.ui.same_row():
            for key, label in [('font_size', '坐标字号'), ('legend_font_size', '图例字号')]:
                self.ui.Entry(self._path('style', key), label, default=STYLE_DEFAULTS[key], width=7,
                              kwlabel={'width': 10, 'anchor': 'w'})
        with self.ui.same_row():
            self.ui.Entry(self._path('style', 'line_width'), '线宽', default=STYLE_DEFAULTS['line_width'], width=7,
                          kwlabel={'width': 10, 'anchor': 'w'})
            self.ui.CheckBox(self._path('style', 'show_grid'), '显示浅色网格', default=True)
        self.ui.Separator('画布与坐标轴')
        with self.ui.same_row():
            for key, label in [('figure_width', '宽度 / in'), ('figure_height', '高度 / in')]:
                self.ui.Entry(self._path('style', key), label, default=0., width=7,
                              kwlabel={'width': 10, 'anchor': 'w'})
        self.ui.Label('宽度或高度设为 0 时自动决定。', align='left')
        with self.ui.same_row():
            self._check('plot_log_x', 'X 对数轴')
            self._check('plot_log_y', 'Y 对数轴')
            if self.mode == 'CGYRO_vs_CGYRO' and self.plot_settings.get('plot_mode', None) == 'Plot 3D':
                self._check('plot_log_z', 'Z 对数轴')
        if self.plot_settings.get('plot_log_y', None):
            self.ui.Label('Y 对数轴会隐藏零值和负值。', align='left')
        self.ui.Separator('图例')
        self.ui.ComboBox(self._path('style', 'legend_location'), OrderedDict([
            ('自动', 'best'), ('右上角', 'upper right'), ('左上角', 'upper left'), ('图外', 'outside')]),
                         '图例位置', default='best', width=22, kwlabel={'width': 16, 'anchor': 'w'})
        cg = self.state if self.mode == 'CGYRO_vs_CGYRO' else self.state.get('CGYRO', {})
        tg = self.state.get('TGLF', {})
        names = self._selected_param_keys(cg.get('selected_paras', {}))
        names += self._selected_param_keys(tg.get('selected_paras', {}))
        names += self._selected_param_keys(tg.get('selected_paras_2d', {}))
        self._render_legend_order_controls(self._path, self.state, ','.join(dict.fromkeys(names)))
        self.ui.Separator()
        self.ui.Button('恢复外观默认值', self._reset_style, updateGUI=True, width=18)

    def _reset_style(self):
        self.state['style'] = dict(STYLE_DEFAULTS)

    def _render_actions(self):
        self.ui.Separator('导出数据')
        spectra = not (self.mode == 'TGLF_vs_TGLF' and self.plot_settings.get('tglf_vs_tglf_mode', None) == 'Flux')
        if spectra:
            self.ui.Button('导出频率 / 增长率谱…', self._export, width=24,
                           help='在选择的目录中新建导出文件夹，保存原始谱及设置；不会覆盖已有文件。')
        self.ui.Label('图片请在绘图窗口中保存为 PNG、PDF 或 SVG。', align='left')
        self.ui.Separator('选择检查')
        report = selection_check(self.root)
        self.ui.Label('选择已通过检查。' if not report['errors'] else '请处理以下选择或设置：', align='left')
        for message in report['errors'] + report['warnings']:
            self.ui.Label('• '+message, align='left')
        if self.mode == 'CGYRO_vs_CGYRO':
            self.ui.Button('查看 CGYRO 运行状态图', self._status, width=24)

    def _render_related_tools(self, open_templates):
        guis = self.root.get('GUIS', {})
        if 'main' not in guis and 'TGLF_multi' not in guis and open_templates is None:
            return
        self.ui.Separator('其他工具')
        with self.ui.same_row():
            if 'main' in guis:
                self.ui.Button('工程总控', lambda: self.root['GUIS']['main'].run(), width=14)
            if 'TGLF_multi' in guis:
                self.ui.Button('TGLF 多输入', lambda: self.root['GUIS']['TGLF_multi'].run(), width=14)
            if open_templates is not None:
                self.ui.Button('模板 / GitHub', open_templates, width=14)

    def _refresh_check(self):
        return selection_check(self.root)

    def _assert_selection(self):
        report = selection_check(self.root)
        if report['errors']:
            raise ValueError('\n'.join(report['errors']))

    def _plot(self):
        missing = comparison_issues(self.root, self.mode)
        if missing:
            raise ValueError('；'.join(missing))
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
