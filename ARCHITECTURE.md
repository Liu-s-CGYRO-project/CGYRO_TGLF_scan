# 代码结构与维护入口

本工程是保存在 OMFIT 数据树中的模块集合，不是普通的 Python 安装包。界面和脚本由 OMFIT 执行，支持库通过当前模块的 `LIB` 加载。修改库时需要同时考虑调用代码、数据树路径和两个层级的 `OMFITsave.txt`。

新增页面、程序、扫描参数和绘图入口的步骤及接口签名见 [维护与扩展接口](MAINTAINER_GUIDE.md)。`tools/check_workbench.py` 是不导入应用的静态接口检查，构建安装包时自动执行。

## 按职责找代码

| 要修改的功能 | 主要入口 | 职责边界 |
| --- | --- | --- |
| 工程导航、操作历史、输入交接 | `CGYRO_TGLF_scan/LIB/OMFITlib_project.py` | `ProjectActions` 执行用户动作、保存结果和恢复临时设置；保留旧导入入口 |
| 页面登记与公共上下文 | `LIB/OMFITlib_workbench_catalog.py`、`OMFITlib_project_ui.py` | 稳定页面键、模块路径、状态文案；ProjectUI 组合页面并保留旧方法 |
| CGYRO / 运行环境 / 转换页面 | `LIB/OMFITlib_workbench_cgyro_ui.py`、`OMFITlib_workbench_runtime_ui.py`、`OMFITlib_workbench_transfer_ui.py` | 渲染和事件绑定；动作交给 ProjectActions |
| 共用扫描字段 | `LIB/OMFITlib_workbench_scan_ui.py` | CGYRO、TGLF 共享取值控件；不读大结果、不提交任务 |
| CGYRO 收集接口 | `LIB/OMFITlib_cgyro_workflow.py` | collect_run / collect_batch；注入原生脚本执行器，手动默认禁止等待和补算 |
| CGYRO 显示元数据 | `LIB/OMFITlib_cgyro_present.py` | 短名和完整详情分离；相同显示名消歧，token 不变 |
| 输入校验、摘要、差异比较 | `LIB/OMFITlib_project_inputs.py` | 读取与校验数据；不提交任务、不写文件、不替换输入 |
| CGYRO 半径、H/D/T 和扫描计划 | `LIB/OMFITlib_cgyro_plan.py` | 选择迁移、输入副本转换、运行前校验；不提交作业 |
| CGYRO 参数与取值 | `LIB/OMFITlib_cgyro_parameters.py`、`OMFITlib_cgyro_scan_values.py`、`OMFITlib_cgyro_parameter_help.py` | 参数定义、取值解析、离线帮助；预览和提交共用 |
| CGYRO 批量队列 | `LIB/OMFITlib_cgyro_queue.py` | 切换当前案例、保存整批进度、等待和整批取消 |
| CGYRO 重试 | `LIB/OMFITlib_cgyro_retry.py` | 确认提交结果、筛选可重试点、复用核对过的输入 |
| CGYRO 调度器状态 | `LIB/OMFITlib_cgyro_run_state.py` | 解析状态、核对作业身份、取消与已有 Kill local 接口 |
| CGYRO 准备、下载、归档 | `CGYRO_scan/SCRIPTS/subscan_lin.py`、`downsync.py`、`CGYROScan.py`、`LIB/OMFITlib_cgyro_archive.py` | 原生 OMFIT 任务适配；完整结果仅替换相同扫描参数组 |
| TGLF 工作台和多剖面 | `LIB/OMFITlib_tglf_workbench.py`、`OMFITlib_tglf_multi_run.py` | 准备计划和持久运行记录；底层执行在 `TGLF_scan/TGLF/SCRIPTS` |
| Transfer 粒子处理 | `Transfer_tool/LIB/OMFITlib_transfer_particles.py`、`OMFITlib_transfer_equivalent.py`、`OMFITlib_transfer_zeff.py` | 原始副本准中性 → 完整组成 Zeff → 粒子方案 → 局部输入复查 |
| CGYRO 单份结果归档 | `LIB/OMFITlib_cgyro_storage.py`、`tools/compact_cgyro_project.py` | 内容摘要唯一拥有原始结果；普通树索引持久化，读取才解析；保留独有历史；检查点验证择一保存 |
| CGYRO 多参数对比视图 | `LIB/OMFITlib_cgyro_scan_view.py` | 按任务坐标 / 原路径建立只读分组；任选变化轴，其余轴固定；不改归档或合并物理样本 |
| 对比选择、配对、绘图 | `LIB/OMFITlib_compare_state.py`、`OMFITlib_compare_cases.py`、`OMFITlib_compare_*` | 选择状态、结果读取、曲线构造、渲染分开；图中文字为英文 |
| GUI 外观 | `LIB/OMFITlib_gui_api.py`、`OMFITlib_gui_controls.py`、`OMFITlib_gui_fonts.py` | 控件适配、字体和尺寸；业务代码不单独重设主题 |
| 字体下载和设置窗口 | `LIB/OMFITlib_font_download_ui.py`、`OMFITlib_font_ui.py` | 下载层不依赖字体设置；设置窗口顶部导入 gui_fonts，回调只使用保留的引用；管理器副本保持一致 |
| 模板更新 | `OMFITtemplates/LIB/OMFITlib_template_*` | 下载与校验、更新预览、应用与回退；独立于科学计算 |
| 打包与静态兼容检查 | `tools/build_project.py`、`tools/check_omfit_api.py` | 从已登记引用构建代码包，校验 API、依赖、字体标识和包大小 |
| Command box / 旧归档迁移 | tools/bootstrap_manager.py、build_bootstrap.py、OMFITtemplates/LIB/OMFITlib_template_migration.py | 只安装管理模块；LivePlan 事务移动旧模块，元数据重分类，保留原载荷与来源报告 |
| 首次部署与独立旧模块迁移 | `tools/deploy_project.py`、`tools/build_deployer.py` | 配套版本与摘要随脚本发布；离线调整标准旧模块路径，复用归档合并引擎另存新 ZIP |

表中省略的 `LIB/` 均位于 `CGYRO_TGLF_scan` 下。已有 `GUIS/`、`SCRIPTS/`、`PLOTS/` 脚本是 OMFIT 入口，不应仅因文件短而删掉；原生数据类的子类也不能机械移动进 LIB，详见 [OMFIT 兼容说明](OMFIT_COMPATIBILITY.md)。

## 数据归属和失败边界

- `INPUTS`、Transfer 原始剖面和准备好的 `BATCH_INPUTS` 属于输入。转换时先建立副本，再完成校验；不能在界面刷新或预览时覆盖原文件。
- CGYRO 的 `RUN_BATCH` 保存本批计划与 token，`RUN_HISTORY[token]` 保存各案例快照；`RUN_MANIFEST` 和 `Cases` 是当前激活案例。切换案例前保存，等待和收集结束后再次保存。调度器作业结束不等于结果已完整下载。
- `RUN_DB` 是已归档结果。同一结果名、半径和离子下，不同参数扫描并存；相同有序参数轴（包含联动参数，不包含取值和 ky 网格）的完整重扫才替换该组结果。`N_THETA` 与 `N_ENERGY` 分别保存；多轴组合及仅 ky 扫描用独立分支，避免共享首轴时相互覆盖。发布先在临时树合并全部旧扫描并准备新扫描，成功后才替换案例节点。
- 每个案例的 `__SCANS__[扫描键]` 保存独立的 `info` / `tasks`，该案例的公开扫描分支保存指向 RESULT_STORE 的结果引用。`p000001` 等点编号只在各自扫描内有效。顶部 `__INFO__` / `__TASKS__` 仅作最近一次扫描的兼容视图；浏览与续算必须遍历 `case_scans`，不能以它们代表整个案例。续算只替换选定扫描的选定点，并拒绝已经重扫替换的旧 token。作业号和结果目录由运行记录持有，不能从当前 GUI 参数重新推断。
- 取消后确认 Slurm 终态再自动收集整批。collection_status 与作业状态分离；空点跳过，部分扫描使用独立结果集，原完整归档保留。未开始点只可复用带摘要的原输入 ZIP；已有样本不能在检查点失效时静默重算。续算链和各点来源跨再次取消保留，完整覆盖原计划才替换完整扫描。
- 续算验证把历史损坏与未推进分开：前缀、有限性、顺序和检查点索引不一致仍报读取错误；合法但尚未超过旧末时刻的段进入 continuation_pending 与 partial_points，保留本次结果 / 检查点到独立部分归档。各次续算通过 previous_final_time 保持原最长末时刻，不能以较短段降低完成目标。调度器失败即使有完整输出仍是部分点；Slurm 状态与待推进原因一同写入任务表供浏览，不触发未推进点自动重提。
- 续算提交 ZIP 由 RESULT_STORE/__FILES__ 唯一持有，__FILE_REF__ 叶通过 result_view / submission_file 解析。保存快照前去重；新提交不挂载展开检查点。旧展开普通文件只在与 ZIP 成员逐字节摘要相同时移除，编辑型输入和不同内容保留。原目录不删除，上传恢复原点文件名并验证最终副本。新增引用类型时必须同步快照、剪枝、迁移和全部读取入口。
- CGYRO 物理目录只归 RESULT_STORE 所有。其余树的结果叶只能持久化 __RESULT_REF__ 索引；result_view 产生的普通 Python 视图只在局部读取，不能回写归档。去重覆盖完整目录内容，不凭 UUID / 点号 / 文件大小归并；部分和未发布历史的独有结果必须保留。prune_storage 先检查全部可达索引，才从保存树中移除无引用池条目，不直接删除磁盘文件。
- 输出文件探测复用单个点检查函数，按 shell 引号转义后的 UTF-8 命令字节数分批（不超过 16 KiB）。每批返回码和点表均须完整匹配，全部探测确认后才开始读取结果；探测异常不能作为空点或求解器失败的证据。
- 网络报错后先确认原提交是否成功。无法确认时保留 `submission_uncertain`，不重复提交。重试资格按每个扫描点判定，先前的取消、超时和内存不足状态不能因切换到重试数组而丢失。
- 手动“重新收集未归档结果”只读取、重读和归档原输出，collect_current 默认禁止求解器重试；配置中的重试次数不授予提交权限。单案例明确传 False，批量仅在原“运行”动作自动收集时传 True。手动批量收集不进入等待循环：活动案例由 downsync 报告后继续其他案例；运行动作和续算动作仍可按原限制重试，取消后的既有禁重提规则继续生效。
- OMFIT Abort 继承 KeyboardInterrupt。上传阶段不调用调度器，中断可确认未提交；调度阶段保存已收到的回执并重抛，中断处理中不发远程请求。同步从原日志或唯一 WorkDir 匹配恢复身份，新协议可原子封闭尚未开始的提交；无日志、无匹配的旧协议需人工核对，不能靠空队列自动解锁。未成功提交的重试恢复上次已确认身份与点来源，失败记录另存。
- 提交窗口 Kill local 与 Abort 分开：前者记录 submission_stop_requested，找回回执后沿原身份完成取消，批量停止后自动收集；后者直接传播。状态同步要精确替换元数据，不能残留被撤销的 submission_parent。所有实际运行（含单次续算）都写 RUN_HISTORY；输入 / 配置 / 脚本全部准备成功后才替换活动记录。重复收集已完成的部分归档失败时回滚记录及 Cases，保留恢复入口。重试核对原脚本摘要与完整输入包成员，取消 / OOM 等旧点状态跨重试保存。审查细节与硬退出限制见 [WORKFLOW_AUDIT.md](WORKFLOW_AUDIT.md)。
- TGLF 批量点允许部分成功；归档和异常传播是两个步骤，后续点失败不能抹去前面已经返回的结果。
- 局部输入转换不会自动选择新的碰撞模型。CGYRO → TGLF 在指定 Zeff 时保留该值；反向旧入口仍采用 `COLLISION_MODEL=4`，没有将 TGLF 的独立 Zeff 转为指定 Zeff 模式。需要改变这一物理约定时，应单独核对模型适用条件，不能只增加一个字段。
- Transfer 等效方案只把高密度热 H/D/T 识别为主离子，快粒子和微量燃料留在辅助组；规则同时用于原始副本的电荷补偿。`equivalent_temperature` 明确区分保压与温度随热主离子，随同其他选项冻结进生成记录。后者只检查实际保留的电荷 / Zeff / 质量 / 电荷梯度约束，单独记录压力变化；不能把压力变化误报为守恒失败，也不能继续显示“压力守恒”。曲率先还原物理导数再重建，不能直接复制温度改变前的 SDLNNDR。
- 二维 / 三参数 CGYRO 比较必须使用任务的完整 values / result_path，不能用组合扫描键当作单一参数。cgyro_scan_view 的虚拟切片仅存在于绘图上下文：一个变化参数、其余固定坐标和原物理结果引用；谱 / 时间 / 本征函数 / 状态 / 跨模型 / 导出共用，缺网格用 NaN 或实际散点，不平均不同固定坐标。
- 取值列表的紧凑格式只作用于 Entry 显示和重置默认值，不能重命名原始归档键。多列图例的原曲线、代理线和文字按相同排序绑定；点击须检查横纵区域，不能只按同一行定位。说明文字优先使用短提示，完整内容放入带行距的滚动帮助窗口。
- 对比选择和半径配对属于所选数据源。切换结果集后恢复该结果集的选择，同时重新检查有效值；图例短名不能取代归档键。
- “清空全部结果”在既有确认后同时清理主结果、旧索引和派生缓存，保留输入和配置。远程文件不由此入口删除。

## 修改代码时的约定

1. 优先把计算与校验放入无执行副作用的函数，把原生任务调用和数据树替换留在动作层。注释解释数据归属、归一化、状态转换和异常处理原因，避免逐行复述代码。
2. OMFIT 的 `SortedDict.get` 需要显式默认值，`update` 接收一个映射；构造 `OMFITtree` 后再填入数据。不要把原生树假定为完全兼容普通 `dict`。
3. OMFIT 会注入 NumPy/pylab 名称。需要 Python 语义的 `all`、`any`、`min`、`max`、`sum` 等应显式从 `builtins` 导入。
4. 工程库在文件顶部导入，供 GUI 回调保留引用；不要在按钮回调内延迟导入 `OMFITlib_*`。新增库要登记在根工程和模块清单，并为实际使用它的子模块登记全部依赖。
5. 不凭目录名或 UUID 排序推断时间。使用运行时间、归档顺序和记录中的身份；列表显示名称与实际键分离。
6. 修改失败路径时同时阅读成功、取消、网络状态不明和重新收集路径。记录要先足够恢复，再执行远程动作；成功数据与失败日志都应有明确保存位置。

7. Tk 变量必须显式使用 `master=`，初值和 Tcl 名称用 `value=` / `name=`。OMFIT 将 StringVar / BooleanVar 封装为 `(name=None, **kw)`，不能按标准 Tk 把窗口作为首个位置参数。打包的 API 与保存树检查通过 AST 核对构造器及导入别名，不导入 Tk。

8. 页面 mixin 不定义构造函数，不覆盖其他页面方法。新增页通过 catalog 登记，并在 ProjectUI 顶部导入；收集动作使用 cgyro_workflow 公开接口。长参数行由 NativeLayout 根据字体和宽度把标题移到控件上方，不手动切断参数名或改动数值。缩略结果名只用于显示，完整身份通过帮助窗口查看。

## 校验与发布

日常维护执行静态和安装包校验；涉及归档与数据保留时补充隔离文件/元数据测试。测试替身只验证文件保留和索引协议，不代表 OMFIT 原生保存/重开已实测；未经用户要求不启动 GUI、绘图、求解器或集群任务。Python 3.9 AST、符号检查、原生 API 和清单依赖校验不能代替实际服务器验证；发布说明需明确这一点。

每次发布冻结源文件及包的 SHA-256，校验包内文件与源文件一致。两个代码安装包均小于 1,000,000 字节，完整字体通过独立资源包缓存，不能通过裁剪或改写字体满足大小限制。开发文档和完整历史保留在 GitHub，安装包只纳入运行所需文件及现有用户文档。

管理器的 TESTS 便利节点已从分发树移除，测试源码继续保留在仓库 `OMFITtemplates/tests`。构建时排除此开发目录，并拒绝残留的直接测试文件注册；未更改管理器运行代码或字体资源。

归档去重的完整设计、旧项目流程及 .old 风险见 [RESULT_STORAGE_DESIGN.md](RESULT_STORAGE_DESIGN.md)。
