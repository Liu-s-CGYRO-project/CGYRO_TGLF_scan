# 维护与扩展接口

适用于工程 1.24.49。这是 OMFIT 数据树工程；`root` 在总控页面指工程，在 CGYRO 子脚本中指 `CGYRO_scan`。普通 Python 包的导入、字典和对象生命周期不能直接套用。先读 [架构](ARCHITECTURE.md) 和 [兼容要求](OMFIT_COMPATIBILITY.md)。

## 输入传递和更新完整性（1.24.49 / 管理器 1.10.35）

`ProjectActions.replace` 返回是否实际改变输入。剖面传递的结果备份通过其 backup 回调准备，仅在改变时执行；输入副本、结果备份均成功后才安装输入并清除失效缓存。备份与 previous_inputs 在同一活动记录保留，不能在 replace 返回 False 后继续归档或清缓存。

模板 pull 必须具备 GitHub asset.digest；正文摘要只追加验证，缓存也不能跳过。管理器原始 manifest 的摘要和预期版本在 API 验证后写入独立 XDG_CONFIG_HOME；不能从安装收据重建信任，也不能在普通开窗访问 API。锚点目录必须位于 XDG_DATA_HOME 和安装目录之外。缺锚点安装不启用，可信原启动器可继续运行并提示重新下载。

## constant 与普通参数覆盖（1.24.48）

constant 重用 `PHYSICS.fixed_parameters[name].value`，是否生效由 `constant_parameter` 指定，不能仅按 `enabled` 判断。计算参数页刷新只同步未启用且非 constant 的值；本页沿用输入跳过 constant，全部沿用输入明确清空选择。不要通过强制设置普通 enabled 标志修复，以免取消 constant 后残留覆盖。回归须提交真实 Entry、切页修改其他参数并返回，同时断言最终提交副本、原输入保留与局部刷新边界。

## 标签页的自然高度（1.24.46）

原生 OMFIT Tab 的 pane 使用 pack。`NativeLayout._fit_tab` 只根据选中状态设置 pane 的尺寸传播：当前页正常传播，隐藏页固定为最小尺寸；Notebook 保留自动高度。不要把当前页的 `winfo_reqheight()` 快照写回 Notebook.height：内容稍后变高时，实际分配尺寸可能保持不变，不再触发 Configure，造成永久截断。隐藏页控件保留缓存，选中后恢复传播，不销毁重建。

既有合并定时器继续负责根 Canvas 的局部高度与滚动范围，不调用原生 GUI.update、update_idletasks 或结果读取来补救。回归必须断言所选的每层 pane 容纳完整内容、最后一个控件可滚动到达，并覆盖尺寸稳定后的内容增高/缩短、首次构建、快速切换及返回缓存页；只断言窗口已显示不足以发现截断。

## 开窗、尺寸与回调所有权（1.24.45）

项目标签通过 `ProjectWidgets.Label` 创建：保留原生构造行为，只从待安装列表移除该标签独占行的原生换行钩子，由既有 `NativeLayout` 合并处理换行。不要同时安装同步换行和局部布局两个尺寸控制者。原生 `GUI.update()` 在显示窗口前调用 `update_idletasks()`；此时 `<Configure>` 或 `after_idle` 内改变请求宽度，可能持续触发新的尺寸事件，让窗口始终无法显示。项目布局使用可取消的短定时器，按真实变化更新；不要给所有回调套全局锁或任意次数截断。

管理器的 `_on_resize` 同样只处理绑定控件的排版，销毁时取消自己的定时器。Python 3.9 的 `unbind(sequence, funcid)` 会清掉同一事件的其他绑定；需使用共享 `unbind_callback` 精确移除自己注册的 Tcl 回调。项目与管理器的字体库副本必须一致，不修改全局 Tk 行为。

涉及开窗、标签、字体或参数列表的修改，发布前必须运行 `test_gui_open_native`、`test_gui_tab_pages`、`test_gui_refresh_native`、`test_gui_font_performance`、`test_font_ui_boundaries`、`manager_test_ui` 和 `manager_test_manager_startup`。除本地测试外，必须在目标 Python 3.9/Linux/Tk 或等价环境验证开窗、缩放、关闭重开和清空搜索；Windows 字体度量不能代替 Linux 的排版回归。缺少现场环境时明确标注未验证，不把测试宿主称作完整 OMFIT 会话。

`test_gui_open_native` 使用原生 GUI/Label/帮助按钮代码，保留记忆中的计算参数页，覆盖所有总控工作页外壳；测试哨兵禁止参数页遍历结果库。结果、作业和远程动作仍由各自边界套件验证，不由开窗测试代跑。

## 完整 CGYRO 目录与搜索刷新（1.24.44）

原生解析器 247 个展开定义由 tests/fixtures/cgyro_parser_defaults.json 固定核对名称、默认值和整数/实数类型。FIELDS 包含 199 个可覆盖项，COMMON 独立限制常用设置，不随目录扩展而变成全部参数。其余 48 个 ky、线性单模和离子身份字段继续使用原有专属流程。太原的 7 个站点扩展仅在输入具备对应字段时提供，不把它们当作通用原生默认值。目录更新只添加禁用的参考项，不能把参考值批量覆盖到源文件。

ParameterList 捕获轻量目录并分页；清空只恢复所选分组、匹配计数和参数行。DeferredSection.rebuild 保留构建期间的新请求，补绘时使用最新筛选值，不递增整个 GUI 的数据版本。保存延迟后，只在该参数面板及其祖先标签选中时恢复；这些监听随工具条销毁解除。不能在所有 DeferredSection 上绑定 Map 自动构建：Map 可能先于标签状态回写，使其他页面按过期状态构建。搜索不重查输入目录，不读取结果、做哈希或复制 ZIP。

用户 tmp 启动前阈值为 200 GiB，运行中允许超过；不提供后台自动删除。完整校验与归档整理继续由明确的维护入口执行。

## 旧版 Slurm 与同步诊断（1.24.43）

`slurm_account_query` 与既有 `slurm_queue_query` 都只生成只读 Bash 查询。状态同步和按作业号恢复共用记账查询：优先 `sacct --array`，仅在 C locale 的明确“不认识 --array”错误时去除此选项重查。连接、数据库、权限和其他选项失败保持失败；空响应不是完成。不要通过忽略返回码、替换本地状态或扩大作业筛选范围来解除收集保护。

旧客户端的合并数组由 `array_task_ranges` 验证语法，状态解析只匹配原清单索引，不展开任意大范围。恢复允许精确主号下的合法合并 ID，继续要求当前用户、唯一工作目录、冻结提交脚本与 sidecar。`queue_sync_summary` 仅读所选任务元数据，分别报告终态、活动及未确认数量；查询失败保留完整原始输出，界面最多展示 1200 字符错误。`queue_summary` 仍专门表示结果收集数量。同步不触发结果解析、ZIP 复制、哈希或全库整理。

## CGYRO 单变量收敛扫描（1.24.42）

`OMFITlib_cgyro_convergence` 将公共基准、各方向取值及额外固定项转换成普通一维扫描计划。完整配置在所选输入内去重，重复基准归属首次请求它的方向，其他方向只保存共享来源。`PHYSICS.scan_mode` 区分普通与 convergence；原生 SETUP.idimrun 仍只接受 0–3，GUI 的 cgyro_scan_content 负责映射。切换模式保留两种设置，不把新模式编码为非法的第四维。

准备和提交共用 cgyro_plan / ProjectActions 的输入变换。批量键追加 convergence:参数，准确的作业身份仍由独立 token、冻结输入、点表及 sidecar 持有。每份提交只临时安装自己的输入、扫描轴和维度，finally 恢复编辑器。选择性提交的坐标必须出现在该组原始参数 × ky 中；恢复使用冻结点表，不重建未提交的笛卡尔点。

复用查询只检查当前 runid、半径/离子及对应轴的现有索引。新点收集时在原任务行缓存已验证的显式 input_requested_parameters，配合现有生成参数、result_summary 和文件 owner 判断输入、输出选项、精度与完成时间。旧元数据不足、引用失效或 PROFILE_MODEL=2 的额外文件无法证明匹配时不复用，也不在查询时补读文件。复用坐标合并进既有覆盖 scope；若相应结果后来被移除，本次有效输出仍归档，但不能宣称整分支完整。未建立新的结果库、历史链或整批快照。

整数取值默认值由 `parameter_range_defaults` 生成，非等步长列表使用公约数间隔初始化范围。更换参数从新参数自身的输入值开始；切换方式和普通重绘保留手填列表与有效自定义范围。字段回调只刷新所属 section，基准数字和方向勾选不立即重绘，复用预览是显式动作。增加检查方向时同步更新 DIRECTIONS、参数校验和去重/提交/恢复回归，不能在开窗时解析结果文件。

## TGLF 扫描控制与参数预设（1.24.31）

`OMFITlib_tglf_workbench.scan_parameter_names` 仅根据 mode、轴名称和 UQ 数量计算控制范围。完整参数页、输入准备页和 `parameter_overrides` 共用这一判断：被扫描字段不显示固定值编辑器，也不参与生成输入或计划的固定值覆盖。倍数扫描继续按各输入自身原值计算。不要仅禁用控件而让旧覆盖值继续影响执行。

`SCENARIOS` 是内置方案的唯一数据表；两个页面复用 `preset_controls`。用户预设位于 `SETTINGS/WORKBENCH/tglf/presets/名称`，只保存 `parameter_overrides` 返回的标量及可选 UNITS，选择键为 `user:名称`，不复制输入或结果，也不保存扫描列表。内置方案只合并其定义字段；用户预设先完整验证再替换固定值覆盖集合，避免前一个预设的残留覆盖。初始化只补充空 presets 容器；模板更新 keep 设置策略保留它。

`parameter_editor` 只为布尔值使用选择框，其余数值一律 Entry；默认值来自当前输入或参数目录，不再维护单独的数值选项表。普通编辑 updateGUI=False，并就地标记“自定义”；切换轴、预设或删除预设只使当前 section 重绘，其他标签在下次打开时失效重建。`test_tglf_parameters` 验证计划、预设隔离与保存元数据往返；`test_gui_tab_pages` 使用原生 OMFIT/Tk 控件验证切轴、应用预设、回车提交及无整窗刷新。后者的业务库 reader 使用隔离夹具，未将其等同于真实服务器工程保存重开测试。

## 转换方案与跨记录比较（1.24.30）

`OMFITlib_transfer_schemes` 仅组织已有 Transfer 流程。`generate_schemes` 预检查全部所选方案，每轮使用独立的 INPUTS/OUTPUTS/Transfer_file 工作分支；不复制原结果。finally 恢复原分支和 SETUP，全部成功后一次安装 `OUTPUTS/CGYRO_schemes`。文件容器必须使用传入的原生 OMFITtree factory，才能随工程保存与更新正确跟随文件引用；不要把文件 reader 塞进普通元数据字典。

每组只持有局部输入与 `particle_record` 的 options/main_count/local_inputs，以及源剖面摘要。不得复制完整 plot_profile 或 TGYRO 输出。`scheme_sources` 仅读半径元数据和输入键，复用 `cgyro_plan` 的输入路径及同位素准备；批量键为 scheme:nr，结果名称为基础 runid + `__transfer_` + scheme。原来的单方案仍用 nr 键和原 runid。提交时临时切换输入与 runid，finally 恢复编辑器状态；准确作业身份、恢复、收集和 RUN_DB 归档保持原接口。

跨记录绘图使用现有 `_selection_sources` 保存的选择，不另建结果库。`selected_cgyro_runs` 只组合所选记录的半径、轴、取值与共同样式；未配置记录不能借用其他记录的选择。`force_read_all_nr_items` 也随来源保存。每个上下文只查询对应 runid 的索引，collect 只读选定结果。渲染时加来源图例；3D 页键包含来源，不能跨方案组装数据面。导出复用原接口，每个来源单独输出并注明统计窗口。

方案及运行记录的普通勾选设置 updateGUI=False；切换来源只重建所属选择区域，生成动作刷新其页面。完整性检查和输入复制只在显式生成/准备/提交中执行。`test_transfer_schemes` 用不可访问对象守住未选结果边界，覆盖生成失败/中断回滚、同点编号输入隔离、提交名称恢复、选择记忆、跨记录曲线与导出。转换/提交使用夹具，服务器实际 TGYRO/CGYRO 与原生工程保存重开仍需现场验收。



## 结果定位、摘要与续算（1.24.26）

`OMFITlib_cgyro_result_index` 复用 `__SCANS__/{info,tasks}` 和 `__RESULT_REF__`。`scan:` 选择键按 runid/case_id/scan 直接取索引；点选择冻结 owner ID、完整参数身份与文件路径。缺失/替换的 owner 不得改选另一份结果。`RUN_HISTORY`、`source_token` 和作业号仅用于追溯或准确的作业管理，不参与当前结果读取、绘图、续算。

`OMFITlib_cgyro_input_identity` 读取实际 `input.cgyro.gen` 的 `value NAME` 格式，规范化数值后缓存在现有点行。身份包括半径、物种、全部扫描/联动维度、实际默认参数和带符号 ky。MAX_TIME、输出/并行控制不形成新的物理坐标；DELTA_T、ERROR_TOL 等精度参数仍参与比较。旧工程缺 gen 时只使用已知参数；收集冲突点时定向补读它的小输入文件，不猜缺失默认值。

`store_result(..., summary_row=row)` 在新点验证完成后写入 `result_summary`：结果 ID、求解器状态、末模拟时间、样本数、检查点可用性/时间/原因、总字节和逐文件大小。检查点摘要复用既有 `__STORAGE__/checkpoints`；不可变 owner/文件复用原校验信息。摘要不缓存时间平均值，数值表每次按所选比例计算并列出实际时间窗口和样本数；图题标注末段比例。

`ensure_layout` 对当前 schema 的常规调用只查历史顶层标记，不能递归检查每个旧 manifest 的 point_table。旧 schema、遗留分支和显式 `audit_history=True` 保留完整迁移检查；全库 compact/prune 与整理入口开启深检，有界提交和有界回收不扩大范围。历史记录的写入方必须保持其仅含元数据的契约，不能在已迁移记录的深层塞入结果文件或引用。

选择器只读扫描头，选定结果直接取一个扫描的点表。任务列表使用头部 `task_counts`；旧索引缺少计数时显示未计数，不为了填数字解析全部点。同步只查询当前任务元数据。下载重试复用同点目录、匹配 owner 的已验证摘要；一个点下载失败不覆盖它的旧结果，其他验证完成的点仍可归档。全库哈希、统计与清理只在明确维护入口执行。

归档在树外准备和验证后安装：新扫描替换相同完整坐标；续算优先收敛，再比较最后模拟时间，失败续算不能覆盖原有正常结果。未选坐标保留。不同扫描视图指向相同完整输入时复用同一当前物理结果，不保存整批历史快照。`submission_complete` 与 `scan_complete` 分开；未知旧计划不宣称完整。尚未发布的独有输出留在 RUN_DB 的任务记录，处理完成才释放冗余引用。

续算只从所选点自己的 input/gen、检查点与 tag/time/freq/prec/timing 等配套文件暂存。逐点验证 SHA、v3 结构、尺寸、有限值和输入一致性；准备阶段再校验，防止选择后文件变化。坏点单独报告，可用点继续。新运行目录和作业身份独立；追加 MAX_TIME 不改变冻结物理参数。

任务删除默认只删记录。显式勾选结果删除才解除对应公开点引用；两次点击确认仍绑定范围和版本。无历史链保护。物理文件清理由显式维护检查所有当前结果及待处理任务引用后执行；任务删除不触发全库剪枝、哈希或统计。

旧工程用 1.24.28 仅更新代码并保留输入/结果/设置，关闭旧结果窗口后重新打开；无需先整理整库或恢复历史快照。已有索引直接使用，缺少轻量摘要显示待校验；实际使用或收集对应点时补齐必要信息。不能确定坐标或文件的旧点单独报告并保留，不凭 p 点号或目录猜匹配。


## 当前 GUI 刷新边界

`OMFITlib_gui_api.adapt` 按控件所属区域路由刷新，不能把 `updateGUI=True` 一律解释成整窗刷新，也不能一律改成 `False`。局部区域由 `gui_deferred.DeferredSection` / `TabPages` 声明；`local=True` 提供字段边界，`action=True` 提供业务动作边界。同一刷新区域的多次请求合并执行，其他窗口不随之重建。

| 操作 | 刷新边界 | 实现与理由 |
| --- | --- | --- |
| 下拉框、勾选框、影响结构或预览的参数 | 最近的 `section` | 字段默认找 `_cgyro_local_refresh`；保留原生提交、校验与重置语义。 |
| 不改变可见布局的普通数值 | 不立即重绘 | `updateGUI=False` 提交后仅使相关缓存页面失效，下一次进入预览或运行页时重新构建。 |
| 全选、清空选择、单项/分组“沿用输入” | 当前 `section` | 这类按钮显式传 `refresh_scope='section'`；不重建父工作页。 |
| 提交、收集、恢复、实际删除、应用配置 | 最近的 `page` | 按钮默认找 `_cgyro_action_refresh`，更新当前工作页正文或当前比较模式，使相关提示和任务/结果入口保持一致。 |
| 运行配置字段 | 环境配置页正文 | 内部标签使用 `local=False`，与上方共用的“应用”状态一起更新；隐藏标签仍不构建。 |
| 工作页面导航、内层标签切换 | 目标工作页正文或选中标签 | 使用 `ProjectUI.select_page` / `nav` 或 `TabPages`；只构建需要显示的区域，已经构建且未失效的标签可复用。 |
| 顶部显式“刷新” | 当前原生 `window` | `refresh_scope='window'` 重新执行该窗口脚本和库导入；用于明确要求重载的操作。 |
| 没有局部区域的旧独立 GUI | 该 GUI 所属表单 | 找不到 `section` / `page` 时只回退到实际 owner，不扩大为所有用户设置窗口。 |

“page”在这里表示声明的动作区域，不等同于整个原生 TopLevel。主工作页正文、独立结果浏览器、独立样式工具、TGLF 多输入工具以及比较模式分别声明动作区域。业务动作可能需要让同页的其他标签失效；这不要求立即创建隐藏标签。`gui._cgyro_view_revision` 只管理界面失效，不缓存科学结果或绕过提交检查。

异步完成和弹窗保存不能在触发时读取进程全局 `_aux['parentGUI']`。应在创建按钮或弹窗之前调用 `ui.refresh_callback(scope='section' 或 'page', widget=可选锚点)`，把返回的回调传入操作。指定的锚点必须属于发起操作的区域；省略时捕获当前构建区域。图例保存使用当前比较区域的回调，运行配置应用使用当前工作页回调。普通视图回调的区域已关闭后直接结束，不重建旧页，也不自动转向其他页。不要把这些运行时回调写入工程树。

任务管理的数据变更是明确例外：独立 `TaskManager` 弹窗可跨工作页面导航和显式原生刷新存活。`CgyroPage.cgyro_tasks_refresh` 先固定所属顶层窗口，在删除完成时从该窗口注册项取得当前 `parentGUI`，然后只请求其当前 `page` 正文。这样删除后的记录、结果选项和提示会更新，而不依赖已经销毁的结果标签、不重开旧页、不广播所有窗口，也不解析全部结果。所属窗口关闭后不再刷新；复用任务管理弹窗时可重新绑定当前所属窗口的回调。

```python
# 局部视图按钮：只重建选择列表所在标签。
ui.Button('全选', select_all, updateGUI=True, refresh_scope='section', refresh_tree=False)

# 弹窗可能在其他页面构建之后才结束，提前固定其发起区域。
changed = ui.refresh_callback(scope='section')
ui.Button('编辑…', lambda: open_editor(on_changed=changed), updateGUI=False)
```

主窗口的工作页面选择器和导航按钮是纯视图控件，不发送原生 `<<update_treeGUI>>`，避免一次导航先刷新主树、再重建整个 GUI。真实输入修改仍保留原生树通知、值校验及 `postcommand`；不能全局屏蔽主树事件来提速。按需结果代理必须在主树分类和折叠展示时返回轻量属性，不能借一次正常树通知解析结果数组。

比较绘图的显示字段显式使用 `adapt(ui).view_only()`，仅过滤其原生树重绘事件；它仍保存显示设置、执行重置和本地回调，不适用于物理输入。频率统计缓存只属于当前绘图 context，键包含物理 owner/模块和平均窗口，不能使用 p 编号或作业号替代。TGLF 的谱转换缓存只属于当次 `ResultView`；下次绘图创建新视图。两者都不能写进 RUN_DB 或变成跨操作缓存，以免平均窗口或结果变化后复用旧值。原生 CGYRO reader 首次读取所选点仍可能同时解码该点场文件，本轮没有替换其科学格式解析器。

绘图按钮还需显式指定 `refresh_tree=False`，并通过同一库的 `plot_view(script, **kwargs)` 执行原生绘图方法。只设置 `updateGUI=False` 不能阻止原生 Button 和 plot 各自 finally 中的主树刷新；太原实测这两次刷新占了约 96% 的按钮耗时。`plot_view` 复用原生方法的本次 globals 副本，保留其运行器、异常、返回值、工作目录恢复及 idle 画布绘制；没有修改共享 OMFITaux、类方法或事件绑定。项目库依赖在加载时导入，不能移入按钮回调。默认业务按钮和脚本内部明确发送的事件仍通知主树；不要给数据变更操作机械加此选项。原生 Tk 回归同时覆盖按钮和方法，避免只测其中一处而遗漏另一处。

保留的整窗例外需要明确说明原因：顶部“刷新”由用户主动重载；模板 apply/undo 替换脚本对象后只重建受影响的已打开窗口；原生模块载入仍由宿主管理。`ShotTimeDevice` 写入共享 `MainSettings`，不在通用字段局部化范围。`UpdateGUI(all_windows=True)` 仅是兼容接口，普通工程业务不应调用它。同步、收集和任务结束不因“状态可能变化”而请求所有窗口更新。

当前有以下 23 个旧 GUI 脚本仍使用原生条件表单、`Tab` 或 `CompoundGUI`。它们都经过适配器；嵌入已有局部区域时服从外层边界，直接独立打开且没有局部区域时仍重建自身表单。不能宣称这些旧界面已经做到每个字段独立重绘。

| 目录（相对于 `CGYRO_TGLF_scan`） | 仍使用表单边界的脚本 |
| --- | --- |
| `TGLF_scan/GUIS` | `DV_scans_subgui.py`、`main_DV_gui.py`、`particleDandVgui.py`、`selection_GUI.py`、`tglf_radial_gui.py`、`tglf_scan_gui.py` |
| `TGLF_scan/TGLF/GUIS` | `constraints_GUI.py`、`scanGUI.py`、`TGLFfromTGYROgui.py`、`TGLF_GUI.py`、`uqGUI.py` |
| `TGLF_scan/TGYRO/GUIS` | `D_and_v_gui.py`、`Plotgui.py`、`Rungui.py`、`TGLFinputGUI.py`、`TGYROgui.py` |
| `TGLF_scan/TGYRO/PROFILES_GEN/GUIS` | `blendEPEDgui.py`、`modifyIonsGUI.py`、`standaloneGUI.py`、`vgenGUI.py` |
| `TGLF_scan/TGYRO/PROFILES_GEN/TRXPL/GUIS` | `TRXPLgui.py` |
| `Transfer_tool/GUIS` | `convert.py`、`transfer.py` |

继续缩小这些表单时，先识别物种数、扫描轴、输入源等字段对同表单其他控件的依赖，再迁移对应标签/分组到 `TabPages`。不要机械关闭刷新，留下与新值不符的旧控件；也不要另建第二套标签生命周期。

刷新范围与数据读取范围是两项独立约束。切页、修改参数、同步状态和删除任务只查询所需元数据或索引摘要，不遍历并解析全部结果，不触发全库整理、哈希、空间统计或输入 ZIP 复制。结果列表先读取扫描头，选中扫描后读取其点摘要；绘图、数值表和续算才读取所选结果及相应文件。所选点缺少摘要时显示待校验，不为了填满列表而扫描整库。文件验证仍在收集当前点、准备选中点续算或显式维护时执行。

回归至少核对 `test_gui_refresh_native` 的 section/page/window 路由、跨窗口回调、保存锁和关闭行为，`test_gui_tab_pages` / `test_cgyro_scan_refresh` / `test_workbench_navigation` 的导航及标签生命周期，以及 `test_cgyro_task_manager` 的删除、图例保存和运行配置回调。`test_refresh_boundaries` 验证独立工具边界、隐藏 TGLF 多输入结果零读取，以及任务弹窗跨导航/显式原生刷新后更新当前正文。用 `test_cgyro_read_boundaries` 检查非数据操作零结果解析；只观察重绘次数不能证明文件读取已按需。

## 热更新时布局对象的生命周期（1.24.24）

原生 `GUI.update` 销毁 `parentGUI` 内的控件，但保留该 Frame 及其 Python 属性。`_cgyro_gui_layout` 因此可能仍是上一版类的实例；导入新 LIB 不会给这个实例补上新方法。`TabPages` 在构建过程中立即显示所选标签，先调用 `finish_gui_subtree`，随后外层页面才调用 `finish_gui_layout`。1.24.23 在此直接调用旧实例的 `prune`，导致由 1.24.22 热更新时失败。

`finish_gui_subtree` 先检查布局锚点。锚点已销毁或不存在时交给最后的 `finish_gui_layout` 统一构造新布局，不能遍历旧控件，也不把正常整页重建当作增量扩展。仍挂载的旧布局通过当前模块的 `_prune_layout(layout)` 清理共用列表，不要求旧类新增方法。保留 `NativeLayout.prune` 入口供可能存活的 1.24.23 调用方使用。不要全局改类或捕获 AttributeError 后宣称升级成功；管理器事务与回滚继续保留。

`tests/test_gui_tab_pages.py` 覆盖持久 Frame 中无 prune 的旧布局以及仍挂载旧布局的局部更新。`tools/validate_template_live.py --previous-project <已发布纯代码ZIP> <原生omfit目录> --output <报告JSON>` 从发行包载入真实旧 GUI LIB，使用原生 SortedDict、导入器和 GUI.update，在同一 TopLevel 中运行管理器 apply/undo；新版夹具必须包含按需标签，只有 Label 的旧夹具无法覆盖这条调用顺序。该工具使用文件节点/会话适配器，不等于完整服务器 OMFIT 验收。离线字体与 LIB 路径沿用回归运行器的 environment 配置。

## 页面构建与续算归档边界（1.24.23）

`gui_deferred.TabPages` 统一 CGYRO、TGLF、转换、运行配置与对比页面的标签生命周期。真实 Tk 只构建当前页；切页保留已构建控件及未提交文字。无 Tk 的结构检查仍遍历全部标签。不得再次为每个页面复制 Notebook 事件处理，也不要用窗口重建模拟切页。

页面内编辑通过 `_cgyro_local_refresh` 定位最近的局部区域；原生回调先提交值，再合并一次重绘。普通数值编辑使用 `updateGUI=False`，只让其他已缓存页失效；打开“运行”或“检查配置”、真正提交时仍执行完整校验。结构、预览会随之改变的下拉项保留局部重绘。按钮改变任务/结果或顶层提示时，当前实现按上表刷新动作区域；运行配置页使用 `local=False`，保证“应用”状态与表头同步，不因追求局部刷新而显示旧状态。

`gui._cgyro_view_revision` 是窗口内瞬态失效代数，只缓存控件，不缓存科学结果或验证结论。修改参数后其他页在下次选中时重建；当前区域及其祖先标为最新，避免切回父页又整体重绘。`DeferredSection` 保留原生 `_aux`/`pythonFile` 上下文，保存锁期间延后，关闭时撤销回调；构造失败保留旧区域。销毁旧区域后须剔除 `gui.notebooks` 和布局记录中的失效 Tk 对象，否则下一次原生 GUI.update 会访问已不存在的 Tcl 路径。适配器缓存构造函数，不得长期持有旧 Entry 或已关闭页面。

已迁移的 `case_layout=radius-scans` 在普通发布中仅处理当前运行；`recover_archives` 的全库兼容恢复只用于旧布局首次迁移或显式维护。手工导入未迁移的旧分支后应使用整理入口，不能让每次提交/收集都遍历物理结果。布局标志不替代所选点的输入、检查点与结果保留校验。

回归入口：`test_gui_tab_pages` 覆盖真实 Tk 局部刷新、未提交文字、预览失效、原生 CompoundGUI、多窗口上下文、保存锁、失败重试及旧控件释放；`test_cgyro_storage` 覆盖来源头被替换后的部分/完整归档、重复收集、读错误及已迁移无关结果零读取。验证记录和本地基准范围见 [VALIDATION.md](VALIDATION.md)。

## 已应用配置的持久化身份（1.24.22）

PROJECT_STATE 下普通 dict 会保存为 pickle，重开时由 OMFITlazyLoad 代理；SETTINGS 下同样数据通过 JSON/SettingsName 保存。不要对代理与字典直接做 ==/!=，也不要用“不是 dict”判断配置丢失。server_capabilities.matching_profile 只对指定的小型能力报告调用 items 并返回实际映射；gacode_installations.same_endpoint 只读取 server/tunnel 字段。绝不能通过全工程递归加载解决身份比较。

shared_issues 比较 runtime_capability_contract，并继续调用 resource_issues。契约包括检测格式、服务器/隧道、Slurm 检测状态、所选队列的可用性、CPU 上限、按规格分组的节点数量/内存与数值化时限；其他队列、checked、hostname、登录限制、tools 和 draft_changes 不影响已应用配置。节点组排序后比较；同一时限的不同 Slurm 写法视为相同。新增会影响运行的能力字段时，同时更新契约与 resource_issues 的测试。缺失报告、过期格式和端点变化不能当作“没变化”。

安装自动检测的时间戳继续用于显式应用时的短期安装文件复核，不代表队列能力的有效期；普通切页不触发网络检测。scan=False 复核必须保留同一端点的能力报告。apply_runtime 保持配置事务与回滚，不悄悄改写用户选择或已提交作业。

test_runtime_persistence 使用未修改的原生 OMFITlazyLoad、SortedDict 与 SettingsName，宿主路径解析和 pickle/JSON I/O 是隔离适配；覆盖首次读取、重复重开、安装状态、复核保留、真实变化拦截与结果文件零读取。它不是完整服务器 OMFIT 会话的保存验收。测试仅恢复注入的注册表模块，不可通过恢复整个 sys.modules 快照反复移除/导入 C 扩展；结束时解除原生节点的宿主引用。

## 历史结果按需读取（1.24.20）

`CgyroPage.render_cgyro` 从 1.24.23 起通过 `gui_deferred.TabPages` 管理全部标签，其局部构造由 `DeferredSection` 完成。内层扫描标签和外层结果标签不是同一个 Notebook；回调必须核对所属 Notebook，保存各自的标签选择，不得用 UpdateGUI 实现切页。首次选中结果页只补建该区域，未失效时复用；参数编辑刷新所需区域，任务操作刷新动作区域，顶部手动“刷新”才重建所属原生窗口。失效的其他页到下次选中才构建。

延后构造时，必须恢复捕获的 `_aux` 和所属 GUI 的 `pythonFile`，使相对位置、锁和控件回调仍指向原工程；`finally` 恢复此前其他窗口的构造上下文。不能在事件回调中借用进程最后一次渲染的全局状态。只对新子树应用布局和按钮绑定，保留其他控件与尚未提交的文字。保存锁未释放时延后；已经切走则取消这次加载，关闭 Frame 时取消定时器。构造失败销毁未完成子树，下一次选择可重试。运行时 Frame/回调只属于当前窗口，不写入 SETTINGS。

不可让隐藏结果页在每次扫描参数刷新时重建未完成任务的 ancestry。结果页的公开索引和未归档任务切片入口仍保留。

`cgyro_payload.resolve_browser` 调用 `resolve_owner(..., defer_native=True)`，让旧原生目录及文件清单两种所有者都先返回 DeferredResult。原生 OMFIT 加载工程时会求值全部保存的表达式，并调用 iter(value) 判断类型；因此 `DeferredResult.__iter__` 必须是生成器，不能直接返回 iter(self._payload_reader())。前者直到 next/实际遍历才触发读者，后者在分类时已经完整加载。不要通过静音 pygacode 日志掩盖实际 I/O，也不要把此运行时类型或数组缓存存进 RUN_DB。

`_payload_file` 对旧原生所有者只返回指定小文件路径，对文件清单验证并读取对应文件；小文件检查不必复制整个检查点目录。普通 resolve_owner 的旧目录兼容行为不变，明确的数据动作仍使用原生读者。

主树的 `_update_treeGUI` / `itemTagsValues` 会对折叠结果检查 `dynaLoad`、`modifyOriginal`、`readOnly` 和 `__tree_repr__`。这些属性必须在适配器本地回答；不要通过通用 `__getattribute__` 转发而创建读者。已打开读者仅用弱引用跟踪，目录缓存仍有容量上限。不要用 `__getattr__` 回退到原生 SortedDict 的自动加载。

`OMFITcgyro` 本身是 dict 子类；判断 `__CGYRO_FILES__`、`__FILE_REF__` 或 `zip` 等标记之前必须先排除 `is_native_file`。成员检查、`get`、`len`、`items` 都可能加载全部科学数组。删除/引用回收只遍历元数据。提交和 `save_current` 调用 `compact_storage(..., run_token=token)`，只转换当前记录；`None` 才代表显式全工程维护，空 token 也不扩大范围。局部整理不提升全局 checkpoint_policy，事务回滚恢复原目标分支及物理所有者。

`selected_linear_keys` 在调用原生数据映射前根据持久 ky 索引筛选。时间曲线保留带符号原始 ky，显示绝对值及主离子归一化仍遵守原绘图语义；归一化预选只读 input.cgyro.gen。指定 ky 模式只读所选结果；谱图和最大 γ 需要当前选中半径/参数的候选谱，不能扩大到其他案例。TGLF/cross-model 沿用 `plot_sources` 的按项读取。

时间曲线列表只读点行 `result_summary`，旧点没有摘要时显示待校验；不能在列出候选时调用 `point_status` 补扫。`point_status(..., verify_checkpoint=False)` 只供实际收集的当前旧点补读小型元数据。它不能作为提交安全条件。真正续算的 `resume_source` / `continuation_plan` / staging 仍完整校验选中点；不能因列表显示时间而跳过二进制尺寸、SHA、有限值和物理输入检查。未开始点先按原输入溯源显示候选，不在列出全部点时解压或哈希每份 ZIP。

`test_cgyro_scan_refresh` 使用真实 Tk 与未经改写的原生 Tab 函数体，结合原生 GUI.update / Entry，检查普通刷新无结果枚举、切页不重建窗口/不发主树更新、输入文字保留、首次与重复选择、跨窗口相对位置、保存锁、关闭与失败重试。几何测试使用本机字体以避免网络字体下载。`test_cgyro_file_dedup` 使用原生表达式、主树与 dynaLoader 函数体，覆盖超过运行时目录缓存容量的旧目录与文件清单，分类/折叠行不物化，主动展开仍能读取。两套需指定 --omfit-source。`test_cgyro_read_boundaries` 使用 dict 子类读者，未授权的数值读取立即报错，覆盖任务删除、提交、回滚、各绘图范围、归一化和真实 Tk 选点窗口；完整续算校验仍可拒绝损坏检查点。Linux 真实 Tk 需 DISPLAY。

## 服务器 CPU 容量检测（1.24.19）

`server_capabilities.VERSION=2` 使旧版折叠 profile 失效。probe 使用只读、限时的 `sinfo --local -h -e`，保留 `%c` CPU/节点、`%m` 内存、`%B` MaxCPUsPerNode 和 `%D` 节点数。`_partition_row` 按节点配置累积 node_groups；不同节点规格不能用 min 折叠为队列上限。每节点可申请量是存在节点可满足的最大值，并受真实 MaxCPUsPerNode 限额约束，登录节点 CPU 数不参与判断。字段定义见 [Slurm sinfo](https://slurm.schedmd.com/sinfo.html)。

`resource_issues` 按完整 MPI×线程数和 nodes 校验：32/64 混合队列的 64 CPU/node 合法；若请求三台但只有两台符合容量则提示。节点数是配置总量，不是瞬时空闲量；忙碌节点交由调度器排队。内存范围仅展示，不组合为虚假的单节点规格。分区政策不一致、缺失计数或聚合后的 `32+` 格式均拒绝整个探测，保留旧设置。

`launch_spec` 先解析实际 nodes、ntasks_per_node、cpus_per_task 再检查容量，不能读取 UI 的 cores 旧副本代替实际启动值。检测只调整超过真实上限的草稿，不自动把 32 增大为 64，也不改变已提交运行。新增检测字段和版本时，应同时更新匹配、草稿应用、UI 摘要和实际启动回归。

## 快照退休与文件存储接口（1.24.18）

- `retention_plan` 只规划，不写树；`retire_superseded` 提交逐点/整次退休，并在 prune 返回后的 Abort 仍恢复所有者和引用。不得以日期或失败状态直接删历史。
- `cgyro_payload` 负责文件清单、原生文件 owner、校验复制与按需读取；`cgyro_storage` 负责结果身份/全树引用；`cgyro_reference` 仅定义不可变引用和固定浏览表达式。新增读取程序通过 `resolve_result`，小文件通过 `archive.result_file`，不得按 __STORE__ 节点的具体 Python 类型猜格式。
- 原生 execGlobLoc 会移除 LIB 顶层 OMFITobject/SortedDict 子类，惰性 reader 必须由函数内部定义，且不得写入持久树。全局 import 清理后，浏览表达式须经本模块 LIB.importCode；管理器同时支持旧/新固定表达式和文件清单，不能只更新工程而回退管理器。
- 剩余点续算通过 effective manifest；原始点表不变，以免错配 Slurm 数组。旧收集/恢复/finally 需检查 retired_points，不能复活已清理载荷。
- `test_cgyro_point_retention/test_cgyro_file_dedup` 覆盖逐点替代、共享 owner、篡改、读者隔离、元数据重开与 Abort；`validate_native_execution --test test_file_manifest_browser_works_after_native_import_cleanup` 检查真实原生导入器。`validate_native_file_storage.py` 用安装了 OMFIT 的 Python 检查原生保存/重开，只创建独立小工程，不能拿用户 ZIP 充当测试夹具。

## 归档结果身份比较（1.24.17）

`cgyro_reference.same_result_reference(first, second)` 是归档保留校验的结果比较接口。先 `metadata_value` 解开元数据容器、再验证索引；只比较 `__RESULT_REF__`，不得用完整字典 `==/!=`、浏览表达式 `data` 的比较或结果数组比较来证明保留。原生 OMFITexpression 的比较运算符会执行 `_value_()`，而重建的浏览链接实例本来就不同。摘要相同且两个索引都合法才证明引用同一不可变所有者；未索引文件不能按同名路径判等。

`validate_preserved_scans` 必须在安装新 case 和清理旧引用之前校验。新增坐标可以替换该点，其他坐标和其他参数扫描必须保留原来的结果标识，不止保留相同路径。不要通过删除此校验来绕过误报。新增测试覆盖真实 publisher、三种维度和符号 ky；`test_cgyro_archive_reference` 要求指定原生 OMFIT 源码，使用其未经改写的表达式比较方法，求值边界由测试记录器替代。

## 任务删除接口（1.24.15）

- `cgyro_task_catalog.task_catalog` 只在任务窗口打开/刷新时读取元数据，不创建结果缓存，不调用调度器或文件读取器。任务由完整 run_token 标识，自动重试在同一行披露全部作业号，续算单独记录。不要以行号、p000001、截断标签或作业数字跨服务器匹配。
- `cgyro_task_cleanup.preview_tasks/remove_tasks` 是唯一任务删除业务入口。先构建具体坐标变更与预览，提交前核对 revision 和内部确认凭据。`case_sources` 的半径直存视图会过滤 H/D/T，不能把该视图直接写回半径节点；本实现从实际路径复制容器，保留邻居。
- 不按 `info.run_token` 删除整个混合扫描；使用每行的 `run_token`，在旧单来源格式中才允许索引头回退。多来源且缺失逐点身份时中止。重建 `__SCANS__` 和兼容头时必须选择保留的来源，不能引用已删除任务。
- `cgyro_cleanup_state.commit_cleanup` 在每次原生写入前记录旧引用；仅在事务内部转换新原生容器，保留兼容头别名。不复制物理结果。回滚先恢复所有者再恢复索引，覆盖原生写入后才抛错与 prune 返回后 Abort。
- `cgyro_db.run_is_deleted` 使用 `__STORAGE__.deleted_tasks[token]=True` 防止旧 GUI/收集 finally 重建任务；仅保存 token 布尔值。`save_current/require_retained_run/saved_run` 必须遵守此边界。只有已经验证原始身份和输入的显式恢复事务可移除此标记，并在 Abort 时恢复。
- 任务窗口使用独立 Tk Toplevel，筛选只处理当前内存行，清除隐形选择；两次确认间处理事件后，必须再次检查选择和后台数据。第一次确认可滚动且按钮固定，1.24.16 起第二次使用按钮确认，默认取消；GUI 在确认后传递预览绑定的内部凭据，不让用户输入。删除完成通过已捕获的所属窗口查找当前正文再请求局部更新，即使原结果标签或旧正文已被替换也不能丢失通知；不能广播 UpdateGUI。
- 全工程清空通过 `manifest_sources` 检查所有保留记录，不能用当前 RUN_BATCH/focus 代替全局活动任务检查。删除按钮不具备 SSH、scancel、重新提交或文件系统清理权限。
- 扩展删除对象时先补充新的身份/依赖规则与故障测试，再增加清单写入；不可在 GUI 回调中直接 pop 任意结果分支。详见 `test_cgyro_task_cleanup/test_cgyro_task_manager/test_gui_refresh_native/test_cgyro_job_recovery`。

## 状态、选择与异常接口（1.24.11）

### 按作业号恢复（本地开发版，2026-10-24）

- `cgyro_recovery_manifest` 负责 JSON sidecar、身份和输入校验。`write_sidecar` 在无提交权限的上传阶段前调用，所有输入与清单上传完成后才进入既有 gate。新增元数据不得带结果数组或原生文件对象，不执行恢复文件中的 Python/shell。
- `cgyro_job_probe` 只生成只读、已引用路径的 Bash 查询。查询失败与队列为空严格区分；用户、WorkDir、回执共同绑定作业身份。脚本使用 Base64 保留原始字节。旧清单只按当前用户暂存目录固定层次查找，不遍历结果目录。
- `cgyro_job_recovery.recover_job` 注入 `remote_execute`、`remote_downsync` 和文件读取器。远端与输入验证完成后，以赋值日志提交 RUN_DB 内部记录、历史、当前清单和收集队列。Abort 尝试全部回滚；赋值开始后不删除可能获得原生 owner 的暂存文件。
- 恢复不调用提交、取消、等待器或求解器重试。状态查询复用 `refresh_run_state`，结果由原有手动收集入口处理。GUI 物理参数不参与旧扫描身份推断。按钮只调用原生脚本 `recover_job.py`。
- `RUN_DB` 是原输入及结果的 owner。`resume_source` 在旧 `/tmp` 不存在时通过 `submission_file` 查原生输入，保证另存、重开后的未启动点仍能续算。
- `test_cgyro_job_recovery` 覆盖归档保留、重复恢复、错误身份、活动/取消状态、缺失 ZIP、损坏输入、并发回调和原生映射 Abort。实际远端查询仅验证读取链路，不代表已在用户 GUI 完成收集。

离线更新可使用 `build_maintenance_commandbox.py --install-only`，保留数据和设置，只更新代码，不自动整理归档；用户随后在原工程点击恢复/收集。操作说明见 [按作业号恢复](CGYRO_TGLF_scan/DOCS/JOB_RECOVERY.md)。

### 本地审查修复的维护约定（1.24.12）

- `cgyro_db.rollback_actions(original_error, actions)` 是 CGYRO 多步恢复的共同接口。`actions` 为 `(步骤名, 无参恢复函数)` 序列，返回本轮失败的字符串列表。调用方仍须 `raise` 原异常；返回非空时不能继续自动重试，也不能清理可能仍被公开索引引用的新 owner。不要以捕获异常代替验证恢复是否完成。
- `freeze_run_inputs` 必须先验证非空 token，先安装新引用、再移除来源。原生映射可能先修改再抛异常，不能使用 `target[key] = source.pop(key)`。迁移遇到同 token 的不同 cases 快照时，必须在写活树前拒绝；文件路径相同不证明两个未保存原生对象内容相同，不能猜选“较新”对象。
- `cgyro_archive._finite_final_time` 在合并前检查双方元数据。`None` 表示未知，`0` 为有效时间；NaN/Inf 既不是未知也不能证明有进展。不得让浮点比较的 False 结果绕过旧完整点的保护。
- `cgyro_run_state.uncollected_job` 保护已有 job_id 的未收集运行，包括 failed/cancelled；这些状态不代表没有部分输出。明确拒绝且没有作业号的提交可重新开始，提交不确定仍由 `submission_pending` 保护。
- 启动参数只追加到一个明确的 `cgyro -e` 调用。带未引用 `;`、管道或后台操作符的同一行须拒绝，不能把核数追加到下一条 shell 命令。本地显式 `-nomp` 与生成的 `OMP_NUM_THREADS/OMP_THREAD_LIMIT` 必须一致，调度器配置明确指定时按配置处理。
- TGLF 完成标记须在非空一维 ky、相同的非零模态数、有限谱值以及完整通量字段校验后写入。数值零不等于缺失；输出失败应保留失败尝试，允许修正后再计算。

```python
try:
    commit_changes()
except BaseException as original:
    failures = rollback_actions(original, [
        ('restore index', restore_index),
        ('restore metadata', restore_metadata),
    ])
    # Only release newly created owners if all their references were restored.
    if not failures:
        rollback_actions(original, [('release new owners', release_new_owners)])
    raise
```

更新工具的信任与并发边界：

- 发布版离线安装器先用其内嵌摘要核验整个模板，包括本地 `--template`，再导入其中的更新引擎。源码目录运行时只导入仓库内的引擎。模板自述 author/id 和内部文件摘要只是完整性信息，不能授予自身代码执行信任；dry-run 也必须遵循此规则。
- 验证、预览和写入使用同一份有大小上限的私有模板快照。`deploy_project._isolated_runtime` 仅用于独立 CLI；它暂时切换 `sys.modules` 并在退出时还原，不是多线程嵌入接口。
- 管理器激活使用非阻塞跨进程文件锁；交互调用 `activate_installation(..., receipt=True)`，回滚传入原回执。回执同时包含写前和写后字节及唯一激活标识，旧窗口不得恢复掉另一窗口的后续选择。默认返回旧字节的接口只为已有调用者兼容保留。
- 项目切换和 bootstrap 的 Abort 必须尝试恢复；若恢复失败，保留备份路径、临时文件与二次诊断，不隐藏最初的 Abort，也不能清理仍可能被活树引用的文件。
- ZIP 文件和空目录都通过同一主机路径边界检查后才创建。Linux 合法的反斜杠文件名不能未经 Windows 路径检查直接解包。

针对这些约定的用例集中在 `test_cgyro_storage`、`test_execution_audit`、`test_tool_entrypoints` 以及管理器 `test_github/test_incremental/test_live`，故障注入覆盖首次写入和回滚再次失败。完整发现与验证边界见 [本轮审查报告](CODE_REVIEW_20261024.md)。

修改状态判断前，先区分以下证据；不能用一个 `done` 或 `failed` 替代全部阶段：

| 判断 | 统一入口 | 含义与限制 |
| --- | --- | --- |
| 调度器终态 | `cgyro_run_state.all_terminal` | 空状态表不证明作业结束；不能据此认定结果可用 |
| 已记录收集结果 | `collection_recorded` | complete / partial / empty 均可记录；complete 还不证明已发布 |
| 自动收集已结束 | `collection_finished` | 已发布，或已封存 partial / empty；不授予补算权限 |
| 运行已稳定 | `run_settled` | 检查保存阶段及调度证据；仍须单独检查替代覆盖和续算依赖 |
| 点可作为完整结果 | `point_complete` | loaded 且没有 resume_pending；只有旧公开扫描合并可显式使用历史默认值 |

`cgyro_queue._commit_synced_manifest` 同步外部历史、RUN_DB 内部运行记录及当前清单。保存副本必须精确替换，不能用增量 update 留下旧提交字段。原生映射在写入或回滚中也可能抛 Abort：逐视图尝试恢复，将二次失败附在原异常的 `cgyro_rollback_errors`，继续传播原异常。不要把附带诊断解释为“回滚一定成功”。这仅保护进程内可捕获异常，不能承诺 kill -9 或掉电事务。

输出探测必须一次验证整批点身份、结果标记及各可读点的字节统计。缺失、重复、负数或外来点记录都使探测失败，不能把它们解释成“该点没有结果”后继续发布。通过全部探测后才读取结果。等待节奏在 `cgyro_run_state` 的 `QUEUE_*` / `WAIT_*` / `STOP_*` 常量中维护；网络错误不等于终态，取消确认有次数上限。

比较页面统一调用 `compare_cgyro_selection.iter_selected_parameter_items(ctx, nr)`。独立半径模式中没有选择就是空，不回退到全局已选参数；零值有效，重复值只产生一次曲线。旧私有名称保留别名供已有回调使用。统计默认值只在 `compare_options.STAT_DEFAULTS` 维护，不在界面、状态表和绘图各写一份。

TGLF 来源解析使用 `plot_sources.selected_tglf_source`。明确保存的 result_source 优先；旧记录没有该字段时，按旧 spectra_mode 选择相应一维/二维来源。界面和纯读取入口共用解析，不在打开窗口时把二维选择改成一维。每次绘图的元数据视图缓存仅属于本次 ctx，不持久化，也不跨来源复用。

TGLF 多剖面恢复先调用 `tglf_multi_data.prepared_run_issues(run, plan, digest)`，界面与执行入口共用。输入准备阶段和执行阶段有独立状态：准备中断后只保留部分半径时不能运行；完整输入后的计算中断可恢复并跳过已完成点。旧记录没有 preparation_status 时仍须检查全部半径和输入清单，不能单靠 cancelled 状态判断可恢复。

运行环境的写入与一致性检查都使用 `project_runtime.module_runtime_fields`。新增字段先扩展该函数，再补写入和漂移检测的同一测试。TGYRO 将 `{n_radii}` 替换为实际半径数的运行命令是有意行为，只允许对应位置的正整数替换。应用事务同时覆盖各模块设置、共享设置和 applied 快照；最后一项失败也要恢复前面已写入的项。

## 后台任务扩展（管理器 1.10.26）

`OMFITlib_template_tasks.BackgroundTasks` 负责线程间传递，`TemplateManager` 负责主线程控件与动作。每个 channel 有独立 generation 和取消事件；旧任务的延迟结果不能更新新任务。进度按 channel 合并，轮询每次处理有上限，并在回调失败后继续调度。等待登录的消息不能挡住已完成的前台任务。

新增任务沿 `TemplateManager._run(title, work, success, ...)` 接入。worker 不操作 Tk 或活 OMFIT 树，success / failure 在主线程执行。worker 的 BaseException 也必须送回主线程，释放 busy 状态；不能只捕获 Exception 后让界面永久等待。对新任务分别测正常完成、开始前取消、结束后取消、替换任务后的迟到消息和关闭窗口。

只有已产生持久副作用的成功动作才传 `receipt`：如生成 ZIP、发布或安装。取消与成功同时到达时报告真实完成结果，取消后不再链式启动上传、连接或切换版本。准备、读取任务不要冒充已提交。`dispose` 只用于尚未交给 success 回调的暂存结果；交给会话管理的 Prepared 由会话持有，不能在普通任务清理时释放。取消不等于撤销远端已提交操作。

构建入口统一使用 `tools/release_policy.py` 的大小约束。脚本和包先完整写入临时文件、校验再以独占目标发布；不覆盖已有产物。工程 ZIP 发布与仓库清单刷新是两个提交步骤，后一项失败时应报告已经生成的包，不能声称两者具备跨文件原子性。旧的字节级 ZIP 整理器已退役，维护走原生整理任务或配套离线脚本，避免出现第二套归档协议。

## 浏览引用与历史保留（1.24.10）

`cgyro_reference` 是结果引用格式的唯一入口。`__RESULT_REF__` 保存内容摘要；可选的 `data` 是受控原生表达式，供树浏览器展开同一物理结果。保存只写表达式文本，禁止把解析后的对象或 `result_view` 写回这个节点。元数据遍历必须先识别引用并停止，不能递归进入 `data`；归档合并须通过引用工厂复制，避免表达式 deepcopy 在离树时求值。管理器迁移器需要同步识别这两个键。新增引用字段必须更新格式验证及原生保存重开测试。

`cgyro_retention.retention_plan(module, resolve, reference)` 只计划，不改树。`retire_superseded` 仅用于显式维护：要求旧作业每个完整坐标都被公开 loaded 点覆盖，时间不回退且不损失已验证检查点；缺少索引、未知输入字段和当前/未收集记录仍保留，历史祖先不构成保护依赖。普通收集使用 `release_published_results` 更新已验证坐标的冗余引用，不运行全库可达性剪枝。`payload_retired` 只保存替代来源和原点号，原 manifest 不变。禁止仅按 failed 状态、运行名或 p000001 进行清理。

退休、可达性剪枝各自带 BaseException 回滚；外层事务还保留物理池的浅引用日志，覆盖 prune 返回之后的 Abort。这里仅解除保存树的引用，源目录和原工程 ZIP 不删除。`require_retained_run` 保护已删除/退休任务的激活和手动收集；从公开 RUN_DB 结果发起续算不经过该历史任务门禁。批量收集跳过退休记录，不能重新下载它的旧数据。

普通状态保存只检查当前运行记录中新插入的数据，没有转换时不再复制整个 __STORAGE__；其他历史只由显式整理处理。不要用长期 bool 缓存跳过当前记录检查；用户可能在两次保存之间导入旧原生结果。性能测试应分别报告目录 I/O、解析、元数据复制和真实界面延迟，不能把合成本机基准说成集群实测。

`archived_case(..., allow_inherited=True)` 参数仅为旧调用方保留；实现直接查询结果索引，不重建祖先。选择冻结 owner 与完整坐标，旧窗口引用被替换时要求重新选择。

离线维护脚本由 `tools/build_maintenance_commandbox.py` 从代码包生成，内嵌校验摘要且不联网。必须同时更新工程和管理器，使用 `Prepared(..., data_policy='keep', settings_policy='keep')`，不能直接加载覆盖当前项目。`LivePlan.apply/undo` 覆盖 BaseException；回滚逐步尝试并保留原中断，二次错误只存字符串。Session 在第一处写入前持有 Prepared，防止半回滚时临时新代码被清理。

## 先找到修改层

| 目标 | 修改位置 | 边界 |
| --- | --- | --- |
| 新页面、模块路径、状态文案 | `LIB/OMFITlib_workbench_catalog.py` | 纯数据定义，保存键保持稳定 |
| 总控导航、通用按钮与说明 | `LIB/OMFITlib_project_ui.py` | `ProjectUI` 保留公共入口与界面上下文 |
| CGYRO 页面 | `LIB/OMFITlib_workbench_cgyro_ui.py` | 输入、参数、运行入口、结果概览 |
| 运行配置页面 | `LIB/OMFITlib_workbench_runtime_ui.py` | 编辑草稿，显式点击后才探测或应用 |
| 服务器能力 | `LIB/OMFITlib_server_capabilities.py` | 只读探测、端点身份、Slurm 容量约束与草稿修正；不执行环境脚本或求解器 |
| 转换页面和输入编辑器 | `LIB/OMFITlib_workbench_transfer_ui.py` | 编辑副本，摘要复核通过后才保存 |
| CGYRO / TGLF 共用扫描字段 | `LIB/OMFITlib_workbench_scan_ui.py` | 取值列表、区间、倍率；不提交作业 |
| CGYRO 收集编排 | `LIB/OMFITlib_cgyro_workflow.py` | 原生脚本执行由调用方注入 |
| CGYRO 并行资源 | `LIB/OMFITlib_cgyro_launch.py` | Slurm 申请、MPI / OpenMP 参数、冻结重试及检查点实际布局；`slurm_process_limits` 只调软限制，`upgrade_slurm_limits` 仅修复重试副本中的旧生成前缀 |
| 短名称、状态、记录详情 | `LIB/OMFITlib_cgyro_present.py` | 仅读取元数据；不能读取数组或联网 |
| 控件与自适应排版 | `LIB/OMFITlib_gui_api.py`、`OMFITlib_gui_layout.py` | 保留原生回调、重置、帮助和绑定 |
| 用户动作和输入交接 | `LIB/OMFITlib_project.py` | 校验 → 调用 → 保存记录；错误继续传播 |

表中 `LIB` 均指 `CGYRO_TGLF_scan/LIB`。`ProjectActions`、`ProjectUI` 和原 `GUIS/SCRIPTS/PLOTS` 路径保持兼容。页面拆分通过无构造函数的 mixin 实现，旧的 `view.render_cgyro()`、`view.scan_value_fields()` 等调用仍可使用。

## TGLF 参数目录与说明

`OMFITlib_tglf_parameters` 是工作台扫描轴、参数页和类型校验的共用标量目录；`OMFITlib_tglf_parameter_help` 提供本地中文说明。目录只读取当前 input.tglf，不读取 RUN_DB。默认值与 GACODE `tglf/bin/tglf_defaults.py` 核对（2026-10-27，Git blob `56136c7d8756e6ff9e111adf728e3257dcc21049`），物理说明来自官网字母列表和参数表，补充项对照官方接口与 ky 网格源码。不要把“官网未说明”填成猜测的单位，也不要将默认值批量写入用户输入。

添加参数时同步目录及说明，核对原生 int/float/bool 类型；物种参数按当前 NS 展开。NS 和输运运行开关不作为独立轴，UNITS 使用独立控件。场景预设与解析器默认不同是有意设计。计划只为明确选中而输入中省略的轴补一个基准值，供执行脚本校验类型；二维/UQ 同样处理，原输入保持不变。更新包必须在总工程、工程模块及 TGLF_scan 需要的 LIB 中注册目录，避免运行时缺模块。

`test_tglf_parameters` 验证省略字段的一维/二维/UQ 实际执行边界、多半径倍数、int/bool 类型、零基准、输入优先、旧设置重开、帮助来源及不读结果；批处理由夹具返回通量，不提交真实任务。界面及帮助依赖均在模块顶部导入，避免原生 OMFIT 清理 importer 后回调失败。

## 页面接口

页面使用共享的 `self.root`、`self.settings`、`self.actions`、`self.ui`、`self.prefix`，不自行创建第二套上下文。常用方法：

```python
self.label('简短的状态说明')
self.note('简短提示', '完整说明、原始名称或目录')
self.guarded('执行动作', self.actions.some_action, issues, help='动作的实际效果')
self.task('已有脚本入口', ('模块', 'SCRIPTS', '脚本名'), issues)
self.nav('返回概览', 'overview')
```

`issues` 非空时禁用按钮，并将原因放在帮助中；动作被直接调用时仍要重新校验，不能把禁用按钮当作执行保护。页面渲染只能初始化选择状态和显示字段，不能自动调用提交、收集、远程探测或输入覆盖。

新增页面按下面的顺序接入：

1. 在 `workbench_catalog.PAGES` 添加 `(显示名称, 稳定键)`；例如 `('8 诊断工具', 'diagnostics')`。自动映射到 `render_diagnostics`，勿用用户文字拼接可执行表达式。
2. 新建 `OMFITlib_workbench_diagnostics_ui.py`，定义 `DiagnosticsPage.render_diagnostics(self)`。继承共享上下文，不定义 `__init__`。
3. 在 `OMFITlib_project_ui` 顶部导入该类，并加入 `ProjectUI` 的基类列表。方法名不能与其他页面重复。
4. 用 `self.actions` 调用显式动作，或用 `self.task` 调用已注册的原生入口。所有 `OMFITlib_*` 依赖在文件顶部导入。
5. 同步根工程和子工程 `OMFITsave.txt` 的 LIB 注册。若入口在另一个 OMFIT 子模块中执行，还需给那个模块登记完整依赖。

不要把页面对象、Tk 控件、回调或导入的模块写入 `SETTINGS`。这里只持久化原生树可保存的数据。`PAGES`、`MODULES`、`LABELS` 仍从 `OMFITlib_project` 兼容导出，状态表仍可从 `OMFITlib_project_ui.STATUS` 读取。

## 收集接口与动作权限

```python
from OMFITlib_cgyro_workflow import collect_run, collect_batch

# cg 是 CGYRO_scan 子树。执行器必须使用原生 SCRIPTS，不直接 exec 文件。
def run_script(title, name, **kwargs):
    return actions.call(title, ('CGYRO_scan', 'SCRIPTS', name), **kwargs)

collect_run(cg, run_script)  # 读取当前案例；allow_solver_retries=False
collect_batch(cg, run_script, factory=OMFITtree)  # 读取整批；默认不等待、不补算
```

`collect_batch(..., automatic=True)` 仅用于用户明确启动的运行流程：等待已经提交的案例，并按原重试规则处理失败点。这个开关不是 GUI 全局偏好，不得从“失败点重试次数”推断。所有手动收集入口继续使用默认 False。

`run_script(title, name, **kwargs)` 必须同步返回、保留原生异常，并让 `KeyboardInterrupt` / `EndAllOMFITpython` 原样传播。执行器不保存到树中。接口通过 `finally` 恢复临时 SETUP 控制，整批收集逐案例保存快照；部分成功不会因另一个案例失败而丢失。

| 动作 | 入口 | 可以做什么 |
| --- | --- | --- |
| 新扫描 | `ProjectActions.run_cgyro()` | 校验、准备、提交、等待、收集；符合原策略才重试 |
| 手动收集 | `ProjectActions.collect()` | 收集并归档已有输出；活动案例报告后继续其他案例 |
| 同步状态 | `ProjectActions.sync_cgyro_run()` | 查询原身份、恢复提交回执、落实已记录的取消请求 |
| 续算 | `ProjectActions.continue_cgyro(token, point_ids, additional_time)` | 从冻结的原输入和检查点继续，延长时间，合并选定点 |

提交、Slurm 解析、检查点校验分别留在 `cgyro_submission`、`cgyro_run_state`、`cgyro_checkpoint`。新增操作不能绕过这些保护，也不能为了恢复界面而手动清除 `submission_uncertain`。Kill local、Abort、进程被强杀的不同边界见 [流程审查](WORKFLOW_AUDIT.md)。

## 新程序接入

页面接口允许添加工具页面，但不会自动把任意程序变成可调度求解器。新程序须同时提供：

1. 原生模块及 `INPUTS/SETTINGS/SCRIPTS` 注册，并在 `MODULES/LABELS` 中定义逻辑名与实际路径。
2. 无副作用的输入校验、计划生成函数，以及明确的单位、参数和输入来源。
3. 独立动作适配器，沿 `ProjectActions.call()` 记录日志并传播错误。远程执行前冻结输入和作业身份。
4. `OMFITlib_project_runtime` 中对应的运行资源映射；只有采用兼容 GACODE 安装结构的程序才加入 `OMFITlib_gacode_installations.PROGRAMS`。检查路径存在不等于求解器可正确运行。
5. 明确的结果读取、部分成功、取消、恢复和归档约定。不能直接复用 CGYRO 的文件名、重启格式或收敛判据。

最小实现先提供“准备输入”和“查看计划”，再接提交。不同求解器之间不要共享可变运行记录；若共享调度适配，必须保留 server、workDir、token、job_id 四项身份。

## 服务器检测接口

`server_capabilities.probe_script()` 只生成有界只读 Bash；`parse_probe(stdout, config)` 校验完整标记后返回普通元数据。`matching_profile` 按 server / tunnel 隔离结果。`resource_issues` 供应用与生成前重复校验；`adapt_draft` 仅由显式“自动检测”动作调用，不能在页面渲染时改资源。扩展其他调度器时保留明确的未知状态，不把工具缺失、查询失败或登录节点 CPU 数当成队列容量。异构队列取此次读到的保守每节点容量。

扫描记录保存在 PROJECT_STATE.gacode_detection.capabilities，应用后为 CGYRO 服务器配置保存独立副本；重检后需再应用。内存只展示，账户 / QOS 上限、闲置资源和计算所需内存不据此推测。实际分配中的进程限制由 `cgyro_launch.slurm_process_limits` 在启动时读取，仅调软限制；不要把登录会话限制写死到批处理。

`gacode_installations.program_guard` 在环境加载后核对文件与平台启动器。修改其只读检查时，同时维护 `checkpoint_environment_identity` 的精确历史尾部匹配：只允许已知生成预检变化，保留用户环境和程序路径；不可用宽泛正则删除用户 shell 内容。MPI / OpenMP 变化需实际暂存检查点的 v3 校验报告，不能用 GUI 开关绕过校验。

## 参数、绘图和数据归属

- 新 CGYRO 参数进入 `OMFITlib_cgyro_parameters.FIELDS` 和 `OMFITlib_cgyro_parameter_help.PARAMETER_HELP`，同时核对扫描取值解析与物理限制。UI 文案不能隐式改变物理默认值。
- 新绘图类型从 `OMFITlib_compare_state` 的选项、对应 `compare_*` 调度入口和渲染函数接入。多轴扫描使用完整任务坐标，不将组合键当作单个参数。详见 [绘图接口](CGYRO_TGLF_scan/DOCS/PLOTTING_API.md)。
- 仅读取结果元数据的页面使用 `cgyro_present`；需要数值时才调用 `resolve_result/result_view`。后者返回的临时视图不能写回保存树。`RUN_DB/__STORE__` 仍是物理结果唯一拥有者。
- `record_options(records)` 返回“显示文字 → 原 token”；同名和缩略重名会加标识区分。完整身份由 `record_details(record, token)` 提供，不可用短名反查目录或构造归档键。
- `collection_status` 与作业状态独立。`COMPLETED` 只说明调度器执行返回，不能用它推断已收集、完整结果或物理收敛。

## 排版约定

采用原生 `same_row`、`Tab` 和已适配的控件，不为单个页面修改全局主题。普通行由 `NativeLayout` 根据可用宽度调整列数；参数行标记 `frame._cgyro_inline = True`，不足一行时把名称放到输入框上方。行内控件顺序、绑定和帮助按钮都保持不变。

正文保持短句，完整说明使用 `help=` 或 `view.note()`。不要为了缩短显示而改动选项值、输入值或归档键。宽度以实际字体测量为准；字体变更会重新测量并排版。绘图中的文字继续采用英文，界面使用中文。

Tk 变量使用 `master=`，布尔框走 `gui_controls.checkbox`。不要在 `Configure` 回调中运行计算、读取大结果、重新渲染整个页面或更改用户选择。

## 静态检查与发布

构建执行静态和安装包检查；针对数据保留缺陷另执行隔离回归检查；下面三条命令不会导入应用界面或运行求解器：

```bash
python tools/check_workbench.py
python tools/audit_omfit_compatibility.py /path/to/omfit --output audit.json
python tools/build_project.py --output /path/to/review/project.zip
```

构建时会自动检查页面登记、mixin 方法冲突、回调导入位置、收集默认权限、原生 API 和每个模块的依赖注册。提交前还需检查 Python 3.9 AST/符号、ZIP 成员、CRC、源文件与包摘要、完整字体许可，并记录哪些分支未做真实服务器验证。

管理器测试源码保留在 `OMFITtemplates/tests`，不再登记到运行树或打入工程安装包；它们仍可由后续显式授权的开发验证使用。不能通过删除字体许可、检查点保护或恢复信息缩减安装包。真实 GUI、工程保存重开和集群任务需单独验证；隔离测试不能声称这些流程已通过。

## 续算输入归档接口

OMFITlib_cgyro_storage_files.SubmissionFiles 只计划新所有者与索引，不直接修改工程；compact_storage 负责提交与回滚。ZIP 所有者放在 RUN_DB/__STORE__/__FILES__，外部叶用 __FILE_REF__。需要文件时使用 result_view / submission_file，不复制解析后的视图回树。prune_storage 同时检查结果引用和文件引用。迁移器独立理解 __RESULT_REF__，不能依赖更新完成后才可导入的工程库。

已读结果、未开始点 ZIP、部分历史和本次提交的输入是不同职责；不能通过删除整个 Cases / RUN_HISTORY 或删旧结果达到去重。保留旧 ZIP 的原始成员摘要，重试只从本次运行的冻结记录取文件，并恢复上传文件名。


## RUN_DB 唯一存储接口（1.24.0）

新增 CGYRO 写入使用 cgyro_db.run_cases / set_run_cases；冻结输入使用 freeze_run_inputs，结果安装使用 store_result。作业快照使用 save_current，外部 RUN_HISTORY 仅保留元数据。绘图仅通过 RUN_DB 和 resolve_result 读取，不创建持久结果缓存。迁移入口 consolidate_storage 统一旧数据、恢复索引、检查引用后清理。store_scan 按全部参数坐标与 ky 更新点，validate_preserved_scans 在安装前保护未重算坐标及其他扫描。持久路径是 runid / nr=..._rho=... / ion；catalog_runs 仅返回不保存的逻辑案例视图，case_destination 解析实际路径。新增读者不能把 case_id 直接拼到 RUN_DB 后。停止作业读取原始点表，不能从合并后的点号重建提交顺序。详见 RESULT_STORAGE_DESIGN.md。

## CGYRO Slurm 资源一致性（1.24.2）

`cgyro_launch.command_template()` 将旧命令的固定 `-n` / `-nomp` 改为 `{mpi}` / `{threads}`，保留非并行参数，NUMA 放置交给所选平台。`launch_spec()` 在打包前生成每点 MPI、线程、CPU 预算和实际命令；Slurm 每个数组元素独占这一份申请。自定义启动器接入时需要扩展此解析层，不能绕过资源检查或只更改 SBATCH 行。

`validate_slurm_script()` 用于冻结脚本重试，复用原申请；加核请走明确续算。`validate_checkpoint_runtime(previous, current, checkpoint=report)` 接收实际暂存 v3 检查点的有效候选报告，允许改变 MPI / OpenMP 数；仍核对程序环境并检查新 MPI 数能整除原速度 / 环向网格。`prepare_point(..., runtime=runtime)` 在目录和冻结 ZIP 两条路径均重新校验并保存原磁盘布局。首次检查仅核对程序环境，逐点格式、网格、时间标签和数据完整性检查必须在打包提交之前完成。取消后从未开始的点继续使用原冻结输入。服务器、停止标志和收集权限由原流程负责。

## 启动与临时空间（1.24.1）

check_start_capacity 只检查启动时已有占用；check_temp_start 通过三个原生脚本传递，批量仅首案例为 True，直接运行和新续算默认为 True。ensure_capacity 只检查真实剩余空间，禁止在逐点打包或保存输入时遍历整个 /tmp。该标志只作本次调用参数，不能写入 SETTINGS 作为持久跳过开关。准备进度按案例与计算点打印，取得作业号后单独输出记录状态；没有进度不能推断已经提交。

## GUI 刷新性能（1.24.8）

控件 updateGUI 会重新执行原生 GUI 和库导入。预检查只使用深拷贝的普通参数值；不得调用文件对象 duplicate，后者会创建临时文件。实际提交仍使用原生副本。半径标签优先读 Particle_processing.local_inputs 的 rho 元数据。

CaseSelection._catalog_scope 在一次同步渲染中按需共享 catalog_runs 视图，finally 释放；只有案例选择器请求当前 run 的目录，绘图设置、全局样式不建立目录。独立子页刷新建立新的惰性视图；latest_cases 可接收它。多轴选择及绘图只枚举所选 scan 的点表，不扫描未选择的其他 scan。不要以运行名、点数或对象 id 作为跨刷新有效性依据，不把目录或结果缓存写入 SETTINGS。ComparisonUI 的纯视图字段使用 ProjectWidgets.view_only()，保留原生写值、重置和局部刷新，但不发送 OMFIT 数据树重绘事件；科学输入及业务按钮仍使用正常通知。

绘图设置有自己的 section；选项变更只重建该设置区，selection_check 同步更新共享状态文字。数据是否可用在模式构建、检查选择、数据操作后的模式刷新时核验；点击绘图前再次核验，不把结果可用性永久缓存。TGLF 绘图选项不再为了刷新底部说明遍历全部作业的点状态。test_refresh_boundaries 用真实原生 CheckBox 验证三个 CGYRO run 共 3000 点在绘图选项打开/勾选时目录、点表、数据树事件、整窗刷新均为零；TGLF 选项不增加点访问，而显式检查仍能发现数据已不可用。

ResultBrowser.render 以 resolve_stopped=False 读取选择项；有公开索引的停止任务只读索引，数据动作仍用 selected_record 的默认完整解析。没有公开索引的当前 partial/续算任务保留完整回退，以维持未归档结果的切片与操作入口。

configure_window_fonts 在同一字体配置下只注册一次；显式导入字体或调整字号使用 refresh=True。Map 处理新增控件；FONT_PROFILE 变化及主题变化重扫现有控件。缓存只挂 Tk 对象，既不改变全局命名字体，也不保存到工程。字体查询必须观察原命名字体的实时变化。

## 控件刷新范围（1.24.9）

通过 OMFITlib_gui_api.adapt 构造本工程控件。普通 updateGUI=True 被替换为 _DeferredGUIRefresh 策略对象：原生代码在提交后测试其布尔值时，请求所属刷新区域并返回 False，阻止全局 <<update_GUI>>。1.24.9 初版只支持 owner 窗口，当前优先按本文“当前 GUI 刷新边界”选择 section/page。不要提前 bool()、序列化或复制该对象到工程树。绑定按控件祖先查找边界及 _GUIs，不能依赖全局最后绘制的 topGUI。每次 GUI 脚本渲染构造新的适配器，不跨渲染缓存构造函数快照。

定时器用 after 而非 after_idle，避免原生 update_idletasks 在当前回调内删除控件；合并同一刷新区域的请求，save lock 期间重排定时器，Destroy 取消。更新仍在 Tk 主线程执行；没有声明局部区域的旧 GUI 才回退到所属原生表单。

原生 Button 的非全局分支仍会安排 250 ms 后重新启用。仅跟踪该按钮实例的 after 回调，Destroy 时取消；按钮已因任务内部刷新被删除时不再安排回调。不能扫描或清理全局定时器，否则会影响其他窗口。测试必须捕获 Tcl bgerror，单看 Python report_callback_exception 会漏报此类失效命令。

保持原生参数校验、postcommand 和 reset 语义。不要用统一 postcommand 包装器代替原生刷新判断：norm 会覆盖它，delete_if_default 可能在构造时调用它，Entry 的重置只暂填文字而不提交。Entry 原生 showText 硬编码 True，必须通过仅替换 _Text 的本次构造函数副本转发请求；副本沿用原生代码与默认值，不重写输入编辑逻辑。ObjectPicker/ModulePicker 同样将内部控件导向适配器。

适配器 UpdateGUI() 默认从捕获的所有者寻找 page 边界；top 可指定目标，refresh_scope 可明确 section/page/window，all_windows=True 显式请求原生全局行为。延后执行应在构建时使用 refresh_callback 捕获边界。跨窗口例外及模板热更新范围见上表后的说明；不得为缩小范围而改变计算、归档或事务验证行为。

## 重跑隔离回归

CGYRO/TGLF 计算参数页共用 `OMFITlib_gui_controls.ParameterList`。它只接收当前输入的轻量目录，纯文本搜索合并 180 ms 内的变化，搜索跨分组、空搜索按分组过滤，每页最多创建 24 行。查询与翻页只重建列表的 `DeferredSection`，不使其他标签失效、不重读目录或结果；搜索框在列表外保持存活。页面销毁时取消其搜索定时器。

参数字段显式传 `refresh_tree=False`，沿用原生 Entry/ComboBox 的写值、校验、锁定与 postcommand，只抑制其无条件 `<<update_treeGUI>>`。`updateGUI=False` 仍保留隐藏运行预览的失效通知。适配器的普通/免主树重绘构造函数缓存必须分开，`_Text` 也必须使用相同事件目标。不要全局屏蔽树事件，其他修改仍保留原行为。完整参数目录的回归基准保存在 `tests/fixtures/tglf_defaults.json`，包含官方来源和 blob 身份；升级目录时一起核对默认值与运行时校验。

在仓库根目录使用有 NumPy、Matplotlib 和 Tk 的 Python 环境运行；`--omfit-source` 指向原生 OMFIT 的 `omfit/` 源码目录（含 `omfit_classes/OMFITx.py` 和 `utils_tk.py`）。Linux 的真实 Tk 测试需要可用 `DISPLAY`，可在桌面终端或 Xvfb 中执行。缺少显示或原生源码时，相关套件明确失败，不计作通过。

```bash
python -B tools/run_regressions.py \
  --omfit-source /path/to/omfit \
  --font-file /path/to/NotoSansCJKsc-Regular.otf \
  --adapters --log-dir /path/to/regression-logs --workers 3 --timeout 300
```

字体文件必须提前离线准备；运行器不会下载字体，并根据本仓库 `OMFITlib_gui_font_data.py` 中的 SHA-256 校验后复制到本次日志的独立缓存。可另传 `--font-sha256` 核对已知摘要，它仍须与仓库固定身份一致。每个测试文件使用独立子进程，避免原生模块替身互相污染。`--adapters` 复用存储测试的原生读取器替身，并把管理器自动启动发现限定到本地测试库；显式安装、更新、取消等操作仍调用生产处理函数。它不能代替真实 OMFIT 工程保存重开或集群作业验证。

日志包含 `environment.json`、每套测试输出及执行命令、`summary.json` 和 `totals.json`；超时、环境不满足、全部跳过及零测试都导致非零退出码。环境前置失败使用退出码 3，在汇总中单列 `status=environment_error`、`environment_errors` 和 `environment_failures`，仍然阻止把本轮称为通过。shell 套件检查其实际使用的 bash / WSL Ubuntu；没有安装 `omfit_classes` 时，需要明确选择 `--adapters`，提供源码路径本身不会安装该包。缺失本仓库模块仍作为代码错误，不能归因于环境。可重复指定 `--suite` 只跑相关套件，管理器套件可用 `manager_test_ui` 等带前缀名称消除歧义。无 GUI 的构建冒烟不需要字体或 OMFIT 源码：

```bash
python -B tools/run_regressions.py --suite test_build_project --suite test_maintenance_tools --log-dir /path/to/build-test-logs
```

## 原生远程执行环境（1.24.13）

CGYRO 的远程执行使用 `cgyro_run_state.native_remote_execute(ui, ...)`，参数和异常沿用原生 OMFIT 接口。该边界只在进程的 SHELL 缺失或为空时设置 `/bin/bash`，保留已有 shell。VNC/桌面启动器未必传递登录 shell；原生 remote_execute 的同主机分支会调用 execute，后者即便禁用 bang command 仍读取 SHELL 构造终端按钮。因此不能只在 shell 命令文本中 export，必须在调用宿主接口前准备进程环境。

恢复、同步、等待、取消和提交回执沿用此入口，后续原生下载也能使用相同进程默认值。不要捕获 KeyError 后重复远程命令，以免重放已有副作用。`test_cgyro_remote_environment` 从指定 OMFIT 源码提取未经改写的 execute/remote_execute 函数，隔离进程和连接边界，复现缺失环境及验证错误/Abort 仍可见；回归运行需提供 `--omfit-source`。

## 按作业号限制操作范围（1.24.14）

恢复时在 RUN_BATCH 写入 `focus_token`；该字段仅决定当前操作的范围。保留在 tokens/history 的其他记录不授予本次同步、收集或取消权限，`queue_records()` 默认仅返回 focus。`include_parked=True` 供明确的元数据检查使用，不能用于当前作业的执行循环。普通多案例提交没有 focus，仍按完整批次处理。

空或失效 focus 必须停止，不能回退到遍历全部历史。`collect_batch` 在改变执行设置前捕获并验证范围，汇总完成数与显示计数也使用同一范围。再次恢复已保存作业可以重选范围，无需重下输入；此分支仍检查查询期间的元数据变化并使用原有事务写入。归档结果和冻结输入仍只由 RUN_DB 拥有。

全工程清空检查必须显式读取 `queue_records(include_parked=True)`，不能因当前恢复只关注一个作业而忽略其他已提交记录。

## 定向删除半径（1.24.14）

`cgyro_radius_cleanup.preview_radius` 和 `remove_radius` 按 runid/nr/rho 及原始 case_id 核对身份，使用 1e-12 的绝对容差区分相邻半径。GUI 按钮只展开元数据选择器；平时刷新不遍历全归档。确认预览与执行前重新规划的范围必须一致。脚本 `remove_radius.py` 默认为预览，confirm 必须是布尔值。

删除先解除公共扫描与 RUN_HISTORY、RUN_DB/__RUNS__ 的指定引用，再更新当前清单/批次并调用现有可达性剪枝。暂存恢复日志只持有浅引用，不复制结果数组；Abort 和原生“删除后抛错”都按逆序恢复。剪枝保留其他半径仍引用的同一物理结果；不执行远程命令或文件系统删除。未知身份、冲突元数据和跨半径续算依赖不得猜测处理。

## 局部维护边界：W6 / W4 / W3、I2 / I3 / I6

- `OMFITlib_tk_callbacks.RetryWait` 在主线程用 `after` / `wait_variable` 派发 Tk 事件；只在无 Tk 或工作线程中使用 `sleep`。每个上下文拥有一个等待窗和一个计时器，结束、中止、销毁均释放。业务调用在等待前捕获作业身份、恢复时核对；取消等待不能推导调度器终态或触发重提。
- `OMFITlib_project_history` 只分类记录的顶层字段和状态。纯日志按独立的普通/失败限额裁剪；未知字段、待处理状态、输入及结果备份均受保护。清理输入备份是独立的确认动作；不要在历史显示、开窗、保存或参数编辑中遍历结果文件或统计体积。真正不同的输入仍保留独立副本，不把可变原对象当成不可变文件引用。
- `unbind_callback` 属于上述纯 Tk 模块，字体模块仅保留兼容导出。只在确实移除已知绑定、且剩余脚本没有该命令引用时删除 Tcl 命令。未识别的 Tcl 包装保持原状。不能回退到 Python 3.9 的 `unbind(sequence, funcid)`：它会连同邻接回调一起解绑。
- 跨模块控件属性的所有者、生命周期和缺省行为集中记录于 `OMFITlib_gui_context` 模块文档。保留旧属性名称以兼容更新前已经存在的回调；不新增全局 GUI 注册表。纯 Tk 帮助函数与原生 API 适配层隔离，防止循环导入。
- 布局尺寸策略使用 `gui_layout` 的命名常量；宽度和表单标签通过同一字体度量函数计算，首绘与字体更新共用。保存锁重试与滚动合并延迟有各自命名，不能与调度器轮询混用。
- 打包检查将 `SyntaxWarning` / `DeprecationWarning` 视为错误。旧字符串仅转义无效的反斜线，修复前后 AST（不含位置）相同；不用盲目加 `r` 改变同一字符串中有效的换行或制表符。

针对性回归：`test_tk_callbacks`、`test_cgyro_wait`、`test_project_history`、`test_source_escapes`。新共享库必须同时登记到顶层、独立工程与独立模板管理器的 `OMFITsave.txt`，并通过原生导入缓存清理测试；只更新磁盘文件不算完整交付。
