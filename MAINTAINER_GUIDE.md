# 维护与扩展接口

适用于工程 1.24.23。这是 OMFIT 数据树工程；`root` 在总控页面指工程，在 CGYRO 子脚本中指 `CGYRO_scan`。普通 Python 包的导入、字典和对象生命周期不能直接套用。先读 [架构](ARCHITECTURE.md) 和 [兼容要求](OMFIT_COMPATIBILITY.md)。



## 页面构建与续算归档边界（1.24.23）

`gui_deferred.TabPages` 统一 CGYRO、TGLF、转换、运行配置与对比页面的标签生命周期。真实 Tk 只构建当前页；切页保留已构建控件及未提交文字。无 Tk 的结构检查仍遍历全部标签。不得再次为每个页面复制 Notebook 事件处理，也不要用窗口重建模拟切页。

页面内编辑通过 `_cgyro_local_refresh` 定位最近的局部区域；原生回调先提交值，再合并一次重绘。普通数值编辑使用 `updateGUI=False`，只让其他已缓存页失效；打开“运行”或“检查配置”、真正提交时仍执行完整校验。结构、预览会随之改变的下拉项保留局部重绘。按钮改变任务/结果或顶层提示时刷新所属窗口；运行配置页使用 `local=False`，保证“应用”状态与表头同步，不因追求局部刷新而显示旧状态。

`gui._cgyro_view_revision` 是窗口内瞬态失效代数，只缓存控件，不缓存科学结果或验证结论。修改参数后其他页在下次选中时重建；当前区域及其祖先标为最新，避免切回父页又整体重绘。`DeferredSection` 保留原生 `_aux`/`pythonFile` 上下文，保存锁期间延后，关闭时撤销回调；构造失败保留旧区域。销毁旧区域后须剔除 `gui.notebooks` 和布局记录中的失效 Tk 对象，否则下一次原生 GUI.update 会访问已不存在的 Tcl 路径。适配器缓存构造函数，不得长期持有旧 Entry 或已关闭页面。

`CGYROScan.publish_loaded_run` 区分“选择一个旧结果发起新续算”和“归档已提交续算”两个阶段。前者的 `archived_case` 仍拒绝过期窗口；后者直接使用冻结的 manifest/point_table，不能再要求来源 token 仍是公开索引头。另一次归档合并可能已替换该头并退休旧快照，但这不使已提交任务的输入身份失效。按完整参数与带符号 ky 合并，保留未选坐标，较短部分结果不覆盖完整结果；下载/解析错误依旧阻止完成归档。

正常续算历史从相同 `scan_key` 的索引读取，当前 run_token 只追加一次。`stopped_run` 恢复原批次时仍尝试继承其已完成点，来源缺失不能据此认证整批完成，但本次可读部分可以归档。调度终态与 collection_status 分开报告：cancelled/failed 不代表已归档，不能清空清单或直接放行下一次提交来掩盖收集失败。

已迁移的 `case_layout=radius-scans` 在普通发布中仅处理当前运行；`recover_archives` 的全库兼容恢复只用于旧布局首次迁移或显式维护。手工导入未迁移的旧分支后应使用整理入口，不能让每次提交/收集都遍历物理结果。布局标志不替代所选点的输入、检查点与结果保留校验。

回归入口：`test_gui_tab_pages` 覆盖真实 Tk 局部刷新、未提交文字、预览失效、原生 CompoundGUI、多窗口上下文、保存锁、失败重试及旧控件释放；`test_cgyro_storage` 覆盖来源头被替换后的部分/完整归档、重复收集、读错误及已迁移无关结果零读取。验证记录和本地基准范围见 [VALIDATION.md](VALIDATION.md)。

## 已应用配置的持久化身份（1.24.22）

PROJECT_STATE 下普通 dict 会保存为 pickle，重开时由 OMFITlazyLoad 代理；SETTINGS 下同样数据通过 JSON/SettingsName 保存。不要对代理与字典直接做 ==/!=，也不要用“不是 dict”判断配置丢失。server_capabilities.matching_profile 只对指定的小型能力报告调用 items 并返回实际映射；gacode_installations.same_endpoint 只读取 server/tunnel 字段。绝不能通过全工程递归加载解决身份比较。

shared_issues 比较 runtime_capability_contract，并继续调用 resource_issues。契约包括检测格式、服务器/隧道、Slurm 检测状态、所选队列的可用性、CPU 上限、按规格分组的节点数量/内存与数值化时限；其他队列、checked、hostname、登录限制、tools 和 draft_changes 不影响已应用配置。节点组排序后比较；同一时限的不同 Slurm 写法视为相同。新增会影响运行的能力字段时，同时更新契约与 resource_issues 的测试。缺失报告、过期格式和端点变化不能当作“没变化”。

安装自动检测的时间戳继续用于显式应用时的短期安装文件复核，不代表队列能力的有效期；普通切页不触发网络检测。scan=False 复核必须保留同一端点的能力报告。apply_runtime 保持配置事务与回滚，不悄悄改写用户选择或已提交作业。

test_runtime_persistence 使用未修改的原生 OMFITlazyLoad、SortedDict 与 SettingsName，宿主路径解析和 pickle/JSON I/O 是隔离适配；覆盖首次读取、重复重开、安装状态、复核保留、真实变化拦截与结果文件零读取。它不是完整服务器 OMFIT 会话的保存验收。测试仅恢复注入的注册表模块，不可通过恢复整个 sys.modules 快照反复移除/导入 C 扩展；结束时解除原生节点的宿主引用。

## 历史结果按需读取（1.24.20）

`CgyroPage.render_cgyro` 从 1.24.23 起通过 `gui_deferred.TabPages` 管理全部标签，其局部构造由 `DeferredSection` 完成。内层扫描标签和外层结果标签不是同一个 Notebook；回调必须核对所属 Notebook，保存各自的标签选择，不得用 UpdateGUI 实现切页。首次选中结果页只补建该区域，未失效时复用；参数编辑只刷新所需区域，任务操作和手动刷新仍可重建所属窗口。失效的其他页到下次选中才构建。

延后构造时，必须恢复捕获的 `_aux` 和所属 GUI 的 `pythonFile`，使相对位置、锁和控件回调仍指向原工程；`finally` 恢复此前其他窗口的构造上下文。不能在事件回调中借用进程最后一次渲染的全局状态。只对新子树应用布局和按钮绑定，保留其他控件与尚未提交的文字。保存锁未释放时延后；已经切走则取消这次加载，关闭 Frame 时取消定时器。构造失败销毁未完成子树，下一次选择可重试。运行时 Frame/回调只属于当前窗口，不写入 SETTINGS。

不可让隐藏结果页在每次扫描参数刷新时重建未完成任务的 ancestry。结果页的公开索引和未归档任务切片入口仍保留。

`cgyro_payload.resolve_browser` 调用 `resolve_owner(..., defer_native=True)`，让旧原生目录及文件清单两种所有者都先返回 DeferredResult。原生 OMFIT 加载工程时会求值全部保存的表达式，并调用 iter(value) 判断类型；因此 `DeferredResult.__iter__` 必须是生成器，不能直接返回 iter(self._payload_reader())。前者直到 next/实际遍历才触发读者，后者在分类时已经完整加载。不要通过静音 pygacode 日志掩盖实际 I/O，也不要把此运行时类型或数组缓存存进 RUN_DB。

`_payload_file` 对旧原生所有者只返回指定小文件路径，对文件清单验证并读取对应文件；小文件检查不必复制整个检查点目录。普通 resolve_owner 的旧目录兼容行为不变，明确的数据动作仍使用原生读者。

主树的 `_update_treeGUI` / `itemTagsValues` 会对折叠结果检查 `dynaLoad`、`modifyOriginal`、`readOnly` 和 `__tree_repr__`。这些属性必须在适配器本地回答；不要通过通用 `__getattribute__` 转发而创建读者。已打开读者仅用弱引用跟踪，目录缓存仍有容量上限。不要用 `__getattr__` 回退到原生 SortedDict 的自动加载。

`OMFITcgyro` 本身是 dict 子类；判断 `__CGYRO_FILES__`、`__FILE_REF__` 或 `zip` 等标记之前必须先排除 `is_native_file`。成员检查、`get`、`len`、`items` 都可能加载全部科学数组。删除/引用回收只遍历元数据。提交和 `save_current` 调用 `compact_storage(..., run_token=token)`，只转换当前记录；`None` 才代表显式全工程维护，空 token 也不扩大范围。局部整理不提升全局 checkpoint_policy，事务回滚恢复原目标分支及物理所有者。

`selected_linear_keys` 在调用原生数据映射前根据持久 ky 索引筛选。时间曲线保留带符号原始 ky，显示绝对值及主离子归一化仍遵守原绘图语义；归一化预选只读 input.cgyro.gen。指定 ky 模式只读所选结果；谱图和最大 γ 需要当前选中半径/参数的候选谱，不能扩大到其他案例。TGLF/cross-model 沿用 `plot_sources` 的按项读取。

`point_status(..., verify_checkpoint=False)` 仅用于时间曲线列表，读取日志尾、tag 与末采样时间，显示待校验。它不能作为提交安全条件。真正续算的 `resume_source` / `continuation_plan` / staging 仍完整校验选中点；不能因列表显示时间而跳过二进制尺寸、SHA、有限值和物理输入检查。未开始点先按原输入溯源显示候选，不在列出全部点时解压或哈希每份 ZIP。

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
- 任务窗口使用独立 Tk Toplevel，筛选只处理当前内存行，清除隐形选择；两次确认间处理事件后，必须再次检查选择和后台数据。第一次确认可滚动且按钮固定，1.24.16 起第二次使用按钮确认，默认取消；GUI 在确认后传递预览绑定的内部凭据，不让用户输入。工作台刷新只请求所属 GUI，不能广播 UpdateGUI。
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

`cgyro_retention.retention_plan(module, resolve, reference)` 只计划，不改树。`retire_superseded` 在发布或显式整理时提交：要求旧作业每个完整坐标都被公开 loaded 点覆盖，时间不回退且不损失已验证检查点；缺少索引、未知输入字段、当前/未收集记录、公开扫描 info.run_token 锚点以及仍被保留续算依赖的祖先都保留。`payload_retired` 只保存替代来源和原点号，原 manifest 不变。禁止仅按 failed 状态、运行名或 p000001 进行清理。

退休、可达性剪枝各自带 BaseException 回滚；外层事务还保留物理池的浅引用日志，覆盖 prune 返回之后的 Abort。这里仅解除保存树的引用，源目录和原工程 ZIP 不删除。`require_retained_run` 是旧窗口续算、激活、手动收集的统一保护入口。批量收集跳过退休记录，不能重新下载它的旧数据。

普通状态保存只检查当前运行记录中新插入的数据，没有转换时不再复制整个 __STORAGE__；其他历史只由显式整理处理。不要用长期 bool 缓存跳过当前记录检查；用户可能在两次保存之间导入旧原生结果。性能测试应分别报告目录 I/O、解析、元数据复制和真实界面延迟，不能把合成本机基准说成集群实测。

`archived_case(..., allow_inherited=True)` 只供停止续算的祖先重建使用：扫描头可能已指向子运行，祖先仅剩部分公开坐标。匹配必须同时核对原 token、运行/案例/参数组及完整坐标，再映回原冻结点号；禁止只靠同名 p000001，也不能让过期窗口使用此回退。数值表和绘图传入选定 token，不为列出选择项展开其他运行的祖先链。

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

CaseSelection._catalog_scope 仅在一次同步渲染中共享 catalog_runs 视图，finally 释放；独立子页刷新必须建立新目录。latest_cases 可接收该目录。不要以运行名、点数或对象 id 作为跨刷新有效性依据，不把目录或结果缓存写入 SETTINGS。

ResultBrowser.render 以 resolve_stopped=False 读取选择项；有公开索引的停止任务只读索引，数据动作仍用 selected_record 的默认完整解析。没有公开索引的当前 partial/续算任务保留完整回退，以维持未归档结果的切片与操作入口。

configure_window_fonts 在同一字体配置下只注册一次；显式导入字体或调整字号使用 refresh=True。Map 处理新增控件；FONT_PROFILE 变化及主题变化重扫现有控件。缓存只挂 Tk 对象，既不改变全局命名字体，也不保存到工程。字体查询必须观察原命名字体的实时变化。

## 控件刷新范围（1.24.9）

通过 OMFITlib_gui_api.adapt 构造本工程控件。普通 updateGUI=True 被替换为 _DeferredGUIRefresh 策略对象：原生代码在提交后测试其布尔值时，请求所属窗口并返回 False，阻止全局 <<update_GUI>>。不要提前 bool()、序列化或复制该对象到工程树。绑定按控件祖先查找 _GUIs，不能依赖全局最后绘制的 topGUI。每次 GUI 脚本渲染构造新的适配器，不跨渲染缓存构造函数快照。

定时器用 after 而非 after_idle，避免原生 update_idletasks 在当前回调内删除控件；合并同一窗口的请求，save lock 期间重排定时器，Destroy 取消。更新仍在 Tk 主线程执行，范围是整个所属原生 GUI，不是局部控件重绘。

原生 Button 的非全局分支仍会安排 250 ms 后重新启用。仅跟踪该按钮实例的 after 回调，Destroy 时取消；按钮已因任务内部刷新被删除时不再安排回调。不能扫描或清理全局定时器，否则会影响其他窗口。测试必须捕获 Tcl bgerror，单看 Python report_callback_exception 会漏报此类失效命令。

保持原生参数校验、postcommand 和 reset 语义。不要用统一 postcommand 包装器代替原生刷新判断：norm 会覆盖它，delete_if_default 可能在构造时调用它，Entry 的重置只暂填文字而不提交。Entry 原生 showText 硬编码 True，必须通过仅替换 _Text 的本次构造函数副本转发请求；副本沿用原生代码与默认值，不重写输入编辑逻辑。ObjectPicker/ModulePicker 同样将内部控件导向适配器。

适配器 UpdateGUI() 默认刷新捕获的所有者；top 指定一个目标，all_windows=True 显式请求原生全局行为。确有跨窗口依赖时应单独描述：ShotTimeDevice 每次写 MainSettings、模板 apply/undo 的事务校验、实际任务结束以及模块载入保留原生刷新。不得为缩小范围而改变计算、归档或事务验证行为。

## 重跑隔离回归

在仓库根目录使用有 NumPy、Matplotlib 和 Tk 的 Python 环境运行；`--omfit-source` 指向原生 OMFIT 的 `omfit/` 源码目录（含 `omfit_classes/OMFITx.py` 和 `utils_tk.py`）。Linux 的真实 Tk 测试需要可用 `DISPLAY`，可在桌面终端或 Xvfb 中执行。缺少显示或原生源码时，相关套件明确失败，不计作通过。

```bash
python -B tools/run_regressions.py \
  --omfit-source /path/to/omfit \
  --font-file /path/to/NotoSansCJKsc-Regular.otf \
  --adapters --log-dir /path/to/regression-logs --workers 3 --timeout 300
```

字体文件必须提前离线准备；运行器不会下载字体，并根据本仓库 `OMFITlib_gui_font_data.py` 中的 SHA-256 校验后复制到本次日志的独立缓存。可另传 `--font-sha256` 核对已知摘要，它仍须与仓库固定身份一致。每个测试文件使用独立子进程，避免原生模块替身互相污染。`--adapters` 复用存储测试的原生读取器替身，并把管理器自动启动发现限定到本地测试库；显式安装、更新、取消等操作仍调用生产处理函数。它不能代替真实 OMFIT 工程保存重开或集群作业验证。

日志包含 `environment.json`、每套测试输出及执行命令、`summary.json` 和 `totals.json`；超时、环境不满足及零测试都导致非零退出码。可重复指定 `--suite` 只跑相关套件，管理器套件可用 `manager_test_ui` 等带前缀名称消除歧义。无 GUI 的构建冒烟不需要字体或 OMFIT 源码：

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
