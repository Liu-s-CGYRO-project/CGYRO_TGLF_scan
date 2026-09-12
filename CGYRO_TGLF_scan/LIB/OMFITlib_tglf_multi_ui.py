"""OMFIT page for importing, configuring and running multiple input.gacode files."""
from builtins import bool, dict, len, list, str, sum
from OMFITlib_tglf_multi_data import DEFAULTS, case_plan, duplicate_case, initialize

STATUS = {'ready': '输入已生成', 'preparing': '正在生成输入', 'prepare_failed': '生成失败',
          'running': '运行中', 'complete': '完成', 'failed': '失败', 'partial': '部分完成', 'cancelled': '已中止'}


class MultiInputUI:
    def __init__(self, root, ui, factory=dict):
        self.root, self.ui, self.factory = root, ui, factory
        self.settings, self.cases = initialize(root, factory)
        self.prefix = "root['SETTINGS']['TGLF_MULTI']"

    def command(self, script, **kwargs):
        return lambda: self.root['SCRIPTS'][script].run(**kwargs)

    def check(self):
        messages = []
        for case in self.cases.values():
            if not case['enabled']:
                continue
            try:
                plan = case_plan(self.settings, case)
                messages.append('{}: {}={}；{}'.format(case['label'], plan['coordinate'], plan['radii'], plan['parameters']))
            except Exception as exc:
                messages.append(case['label'] + ': ' + str(exc))
        self.settings['status'] = '\n'.join(messages) or '请先导入并勾选案例。'

    def render(self):
        ui = self.ui
        ui.TitleGUI('TGLF 多 input.gacode 计算')
        ui.Label('导入剖面 → 设置半径和 TGLF 参数 → 生成输入 → 计算与对比', align='left')
        with ui.same_row():
            ui.Button('导入多个 input.gacode', self.command('import_tglf_multi'), updateGUI=True)
            ui.Button('从目录批量导入', self.command('import_tglf_multi', directory=True), updateGUI=True)
            ui.Button('检查所选案例', self.check, updateGUI=True)
        ui.Tab('1. 文件与案例')
        with ui.same_row():
            ui.ComboBox(self.prefix + "['coordinate']", {'rho（input.gacode 的 rho）': 'rho', 'r/a（归一化小半径）': 'r/a'},
                        '半径坐标', default='rho', updateGUI=True)
            ui.Entry(self.prefix + "['radii']", '共用半径', default='0.5')
        ui.Label('案例半径留空时使用共用半径。复制案例可对同一剖面使用不同参数。', align='left')
        if not self.cases:
            ui.Label('尚未导入文件。支持不同目录下同名的 input.gacode。', align='left')
        for key, case in list(self.cases.items()):
            path = "root['TGLF_CASES'][{!r}]".format(key)
            ui.Separator(case['label'])
            with ui.same_row():
                ui.CheckBox(path + "['enabled']", '参与运行与对比', default=True)
                ui.Entry(path + "['label']", '案例名称')
                ui.Button('复制为新案例', lambda key=key: duplicate_case(self.root, key, self.factory), updateGUI=True)
            with ui.same_row():
                ui.Entry(path + "['radii']", '此案例半径（可留空）', default='')
                ui.Entry(path + "['extra']", '此案例参数', default='', help='例如 SAT_RULE=2; NKY=24; USE_BPER=true；覆盖共用参数。')
            ui.Label('{}\n{} 个径向点；{} 个离子；输入 SHA-256: {}'.format(
                case['source'], case['info']['points'], case['info']['ions'], case['sha256'][:16]), align='left')
        ui.Tab('2. 计算设置')
        ui.Separator('共用 TGLF 设置')
        ui.Label('计算增长率/频率谱和通量；局部几何、梯度和物种由每个 input.gacode 生成。', align='left')
        with ui.same_row():
            for key in ('SAT_RULE', 'NKY', 'NMODES'):
                ui.Entry(self.prefix + '[{!r}]'.format(key), key, default=DEFAULTS[key])
        with ui.same_row():
            for key in ('USE_BPER', 'USE_BPAR'):
                ui.CheckBox(self.prefix + '[{!r}]'.format(key), key, default=DEFAULTS[key])
        ui.ComboBox(self.prefix + "['include_ions']", {'全部离子': 'all', '仅热离子': 'thermal'},
                    '参与 TGLF 的离子', default='all')
        ui.Entry(self.prefix + "['extra']", '共用附加参数', default='', multiline=True,
                 help='每行 KEY=value，或用分号分隔；例如 KYGRID_MODEL=1; NBASIS_MAX=8。')
        ui.Separator('执行环境')
        ui.ComboBox(self.prefix + "['execution']", {'本机 Linux': 'local', '使用 OMFIT 的 TGYRO / TGLF 服务器配置': 'module'},
                    '执行位置', default='local', updateGUI=True)
        if self.settings['execution'] == 'module':
            for name in ('TGYRO', 'TGLF'):
                remote = self.root['TGLF_scan'][name]['SETTINGS']['REMOTE_SETUP']
                ui.Label('{}: {}；目录 {}'.format(name, remote.get('serverPicker') or remote.get('server') or '未配置',
                                                 remote.get('workDir') or 'OMFIT 自动工作目录'), align='left')
            ui.Label('服务器在相应模块 Setup 中配置；命令在登录节点或已分配的计算节点同步执行。', align='left')
        ui.Entry(self.prefix + "['environment']", '环境初始化', default='', multiline=True,
                 help='例如 source /path/to/gacode/shared/bin/gacode_setup；在 TGYRO / TGLF 命令之前执行。')
        ui.Entry(self.prefix + "['tgyro_command']", 'TGYRO 输入生成命令', default=DEFAULTS['tgyro_command'],
                 help='{n_radii} 自动替换为转换半径数。保留 -t 使用测试模式生成 localdump。')
        ui.Entry(self.prefix + "['tglf_command']", 'TGLF 计算命令', default=DEFAULTS['tglf_command'])
        ui.CheckBox(self.prefix + "['continue_on_error']", '单项失败后继续其他计算', default=True)
        ui.Tab('3. 运行与结果')
        selected = sum(bool(case['enabled']) for case in self.cases.values())
        ui.Label('已选择 {} / {} 个案例。每次“生成输入”均新建记录；完成的结果会保留。'.format(selected, len(self.cases)), align='left')
        with ui.same_row():
            ui.Button('生成输入', self.command('run_tglf_multi', action='prepare'), updateGUI=True)
            ui.Button('运行已生成输入 / 重试失败项', self.command('run_tglf_multi', action='run'), updateGUI=True)
            ui.Button('生成并运行', self.command('run_tglf_multi', action='all'), updateGUI=True)
        with ui.same_row():
            ui.Button('对比所选记录的频率与增长率', lambda: self.root['PLOTS']['TGLF_multi'].run())
            ui.Button('刷新状态', lambda: None, updateGUI=True)
        ui.Label('结果选择独立于当前设置。更改参数后先重新生成输入；计算按案例和半径依次执行。', align='left')
        ui.Label('显示各案例原始 TGLF 归一化数值；不同剖面的物理单位比较需另行转换。', align='left')
        for key, case in self.cases.items():
            if not case['runs']:
                continue
            ui.Separator(case['label'])
            choices = {'{} | {} | {}'.format(run['created'], STATUS.get(run['status'], run['status']), run_id[-8:]): run_id
                       for run_id, run in case['runs'].items()}
            ui.ComboBox("root['TGLF_CASES'][{!r}]['selected_run']".format(key), choices, '运行记录', updateGUI=True)
            run = case['runs'].get(case['selected_run'])
            if run is None:
                continue
            ui.Label('{}={}；参数 {}'.format(run['plan']['coordinate'], run['plan']['radii'], run['plan']['parameters']), align='left')
            if run.get('error'):
                ui.Label(run['error'], align='left')
            for point in run['points'].values():
                ui.Label('{}={}：{}{}'.format(run['plan']['coordinate'], point['radius'], STATUS.get(point['status'], point['status']),
                                            '；' + point['error'] if point['status'] == 'failed' else ''), align='left')
                attempt = point['attempts'].get(point.get('selected_attempt'))
                if attempt and attempt['status'] == 'complete':
                    ui.Label('结果目录：' + attempt['workdir'], align='left')
                    from OMFITlib_tglf_multi_plot import flux_summary
                    ui.Label(flux_summary(attempt['result']), align='left')
        ui.Separator('检查与运行消息')
        ui.Label(self.settings['status'] or '就绪。计算结果随当前 OMFIT 工程保存，不进入 GitHub 模板。', align='left')
