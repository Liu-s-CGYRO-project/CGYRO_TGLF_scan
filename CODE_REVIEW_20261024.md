# Code Review Report

审查基线：`0dc400134f87744a92379fd3f4dc9929754863e5`，工程 1.24.11、管理器 1.10.26。修复归入工程 1.24.12、管理器 1.10.27。本报告按根因分组，文件位置指修复后的源码；测试中的人工故障和合成数据不代表真实计算结果。

重点审查 RUN_DB 迁移/归档/回滚、提交/取消/续算/收集、运行参数、GUI 后台任务、模板验证与更新入口。补充复核已有绘图选择、刷新范围及构建检查。没有修改用户工程 ZIP、服务器环境或远端作业。

## Critical — 必须修复

### C1 离线部署会执行模板自带的未可信引擎（已修复）

- 位置：`tools/deploy_project.py:_capture_template/_stage_runtime_sources/runtime`。
- 原因：旧 `--template` 路径将 ZIP 中三个更新引擎解包后直接导入；author/id 和内部 SHA-256 由同一个 ZIP 自述，不是独立信任。即使只是预览，也能执行被替换模块的顶层代码。
- 证据：对基线源码使用仅创建临时标记的合成模板，确认导入阶段执行了该代码，随后才因接口缺失报错。
- 修复：发布安装器先核验内嵌的整包长度与摘要；源码运行只执行仓库内引擎。后续预览和写入绑定同一私有快照，避免验证后源文件被换掉；退出时恢复原模块缓存。
- 回归：`test_tool_entrypoints.DeploymentTrustTests` 的自签摘要模板、错误整包摘要、缓存隔离、Abort 和源路径替换用例。

### C2 同运行编号的旧快照覆盖 RUN_DB 独有点（已修复）

- 位置：`CGYRO_TGLF_scan/LIB/OMFITlib_cgyro_db.py:_set_migrated_cases/ensure_layout`。
- 原因：旧 `RUN_HISTORY.cases` 和顶层 `Cases` 对同 token 直接赋值；若 RUN_DB 中已有不同内容，会丢失被替换分支独有的点。
- 修复：在写活树前核对已有与传入快照。无法证明一致便明确报冲突、保留所有来源；等价摘要引用正常迁移。不同原生文件对象不能仅凭路径判等，不加载数组，也不增加新的结果存储层。
- 回归：`test_cgyro_storage` 覆盖历史冲突、顶层 Cases 冲突与等价引用；旧实现重放可确认覆盖。

### C3 冻结提交脚本时先删除唯一引用（已修复）

- 位置：`CGYRO_TGLF_scan/LIB/OMFITlib_cgyro_db.py:freeze_run_inputs`。
- 原因：`inputs[key] = cases.pop(key)` 先执行 pop；目标赋值失败或 Abort 时脚本已经从来源移除。
- 修复：非空 token 预检；先保存目标引用再移除来源。覆盖原生赋值“修改后再抛错”的行为，成功路径仍只有一个冻结引用。
- 回归：`test_cgyro_storage` 注入目标赋值前/后中断、来源解除后中断；空 token 不再产生 `RUNS['']` 半成品。

```python
# Transfer ownership only after the destination assignment has succeeded.
inputs[key] = cases[key]
cases.pop(key)
```

### C4 归档恢复的二次异常可能删除最后一个结果索引（已修复）

- 位置：`CGYRO_TGLF_scan/LIB/OMFITlib_cgyro_recover.py:recover_archives`。
- 原因：旧名称归并成干净名称后遇到 Abort；若恢复旧分支再次失败，却仍删除新分支，就会让结果 owner 变成无人引用，后续剪枝可能移除它。
- 修复：逐项尝试恢复原分支；有恢复错误时保留新分支。对未分类来源的恢复也先于新分支清理，不能因回滚清理失去唯一可达引用。
- 回归：跨名称恢复故障注入，复核后续 `prune_storage` 仍保留 owner。这项是在补丁交叉审查中追加验证的路径。

## Warning — 建议修复

### W1 中断恢复被第二次异常打断或替换（已修复）

- 位置：`cgyro_db.ensure_layout`、`cgyro_storage.compact_storage`、`cgyro_retry._restore_collection_failure`、`OMFITlib_template_session.OMFITSession.backup_and_open`、`tools/bootstrap_manager.py:install`。
- 原因：部分路径只捕获 Exception，漏掉 OMFIT Abort；部分恢复直接串行赋值，第二次失败会掩盖原始中断、跳过其他恢复，或继续不应进行的读取重试。
- 修复：CGYRO 统一 `rollback_actions(original_error, actions)`；各恢复独立尝试，二次诊断附在原异常。回滚未完整完成则停止重试并保留可能被引用的 owner/backing。项目切换保留会话备份路径；bootstrap 在首次写活树前持有暂存目录。
- 回归：存储、收集、项目切换、首次安装/替换管理器的 Abort 和二次异常用例。仍不承诺 kill -9/掉电能执行 Python 回滚。

### W2 NaN/Inf 进度绕过旧结果保护（已修复）

- 位置：`CGYRO_TGLF_scan/LIB/OMFITlib_cgyro_archive.py:_finite_final_time/store_scan`。
- 原因：NaN 的大小比较均为 False，未完成新点可能绕过时间检查替换正常旧点。
- 修复：发布前检查双方 final_time 必须有限；`None` 表示未知，零值有效。错误元数据不改变已有扫描。
- 回归：NaN、正负 Inf、零和未知时间；旧版可重现替换。

### W3 复合 shell 命令让 MPI 参数加到错误程序（已修复）

- 位置：`CGYRO_TGLF_scan/LIB/OMFITlib_cgyro_launch.py:_has_inline_control/_invocation`。
- 原因：只检查独立分词的操作符，`cgyro -e .; echo finished` 中相邻分号绕过校验，变成 `echo finished -n 32 -nomp 1`。
- 修复：按原始引用/转义识别同一行的 shell 控制操作符；拒绝复合调用，保留引用路径、转义字符和合法重定向。这是启动调用约束，不宣称构成任意 shell 的安全沙箱。
- 回归：相邻/分隔的分号、管道、后台符、引号路径、注释和 `2>&1`。

### W4 本地混合并行线程数被重置（已修复）

- 位置：`cgyro_launch.launch_spec`、`CGYRO_scan/SCRIPTS/subscan_lin.py` 的资源解析/脚本生成。
- 原因：本地 `-n 8 -nomp 4` 解析后又取默认单线程，启动参数与 OMP 环境不能可靠对应。
- 修复：无显式覆盖时保留命令实际线程数；命令参数、OMP_NUM_THREADS、OMP_THREAD_LIMIT 和 manifest 使用同一解析结果。明确的资源配置仍优先。
- 回归：解析本地混合并行并执行真实脚本生成代码片段，核对最终脚本及清单；不以真实 MPI 执行代替本地验证。

### W5 新批次挤出失败作业的常规收集入口（已修复）

- 位置：`cgyro_run_state.uncollected_job`、`cgyro_queue.pending_runs`、`subscan_lin.py` 提交前置条件。
- 原因：failed/cancelled 被当作不再待处理，即使已有 job_id、尚未收集。新批次替换 RUN_BATCH 后无法从常规入口找到旧批次；历史和远端输出仍在，不能描述成直接删除数据。
- 修复：已分配作业须完成收集才能替换批次，包括失败/取消；明确提交拒绝且没有作业号允许重试，提交不确定仍阻止重复提交。
- 回归：失败、取消、partial 已收集、无作业号拒绝和不确定提交；原生单作业/批次前置检查。

### W6 空或不完整 TGLF 输出被标记成功（已修复）

- 位置：`CGYRO_TGLF_scan/LIB/OMFITlib_tglf_multi_run.py:validate_result`。
- 原因：零模态谱、频率/增长率模态数不一致、仅有物种名的通量行通过旧校验，后续汇总或绘图才失败。
- 修复：校验 ky 维度、非空模态、谱形状一致及有限数值、通量必要字段；保留有效零值。失败尝试保留失败状态，修正后可重试。
- 回归：`test_execution_audit.TglfOutputContractTests` 覆盖边界以及失败后成功的完整控制流程。

### W7 旧窗口回滚覆盖另一窗口成功激活的版本（已修复）

- 位置：`OMFITtemplates/LIB/OMFITlib_template_incremental.py:_activation_lock/activate_installation/restore_activation`、`OMFITlib_template_manager_ui.py`。
- 原因：激活与回滚只有原子写文件，没有事务归属校验；A 激活后 B 激活，A 启动失败恢复旧文件会撤销 B。
- 修复：短事务使用非阻塞跨进程锁，UI 请求激活回执。回滚仅在 active.json 仍等于本事务写入的字节/唯一激活标识时执行。兼容旧 previous-bytes API，不将等待锁放在 Tk 主线程。
- 回归：旧回执不能覆盖新激活、跨进程竞争立即报错；Windows 与 WSL 本地文件系统通过。集群共享文件系统锁语义仍需现场验证。

### W8 Windows 空目录解包未检查主机路径边界（已修复）

- 位置：`OMFITtemplates/LIB/OMFITlib_template_live.py:_staging_path/Prepared`。
- 原因：文件有边界检查，空目录直接 mkdir；Linux ZIP 中的反斜杠在 Windows 可变成路径分隔，造成暂存根以外目录创建。
- 修复：文件与空目录统一解析并验证目标处于暂存根；保留 Linux 合法的反斜杠文件名。
- 回归：使用原始 ZIP 成员名构造跨平台样本；Windows 旧版重放确实越界，新版拒绝；Linux 仍可正常读取合法名称。

## Info — 可选改进

### I1 Windows 回归报告漏计 failures/errors/skips（已修复）

- 位置：`tools/run_regressions.py:run_suite`。
- 原因：输出保留 CRLF，行尾正则不能匹配 FAILED 统计。失败退出码正确，但分项数量错误显示零。
- 修复：解析前统一换行，包括超时输出；添加混合 failure/error/skip 计数测试。

## 可读性、架构与性能复核

- 将部署引擎加载拆为捕获快照、清单校验、代码来源选择、导入隔离四个职责；变量明确区分原模板和已验证快照。
- CGYRO 多处恢复循环统一到 `rollback_actions`，待收集作业使用统一状态谓词；注释说明原生赋值、中断、未知数据与引用所有权的原因。
- 更新维护指南，说明事务调用约定、结果完整性、启动参数、CLI 信任边界、激活回执、扩展与测试入口。
- 没有为消除 50 行警告而大幅重排已覆盖的界面/事务编排函数，也未把公共持久字段 `info/data` 改名。它们属于已有工程协议，机械重命名会破坏旧数据兼容。
- 继续使用集中资源上限、等待策略和字段定义；新快照检查复用包大小策略。迁移快照比较仅访问索引/元数据，文件对象保持不透明；GUI 渲染没有新增磁盘扫描、网络请求或数组读取。
- 已有字体性能、局部刷新、绘图选择、后台任务和收集默认只读权限回归均纳入本轮。没有以本机用例推断神马/太原服务器的实际加速比。

## 验证与边界

最终 Linux 回归为 **37 个套件、734 项全部通过，0 失败、0 跳过、0 超时**；相对基线新增 40 项。另有 Windows 95 项定向回归通过。代码包 410 个源文件逐字节和 SHA-256 核验一致，生成的离线安装器完成本地预览，并在导入前拒绝错误模板摘要。详见仓库 `VALIDATION.md` 的本轮记录。用例覆盖普通字典及 OMFIT 映射适配器、真实 Tk 控件与故障注入；外部调度器和求解器使用隔离适配器，未提交真实任务。

静态原生 API 审查保留 6 条 `missing_script_target`：2 条位于开头明确禁用的旧 GYRO 脚本中，3 条为高级 OMFIT QLGYRO 模式的可选外部模块（入口已先检查依赖），1 条为传入 CGYRO 子根的 downsync 动态上下文。它们不代表标准 CGYRO/TGLF 主流程新增缺失入口，也不能机械重定向为不同求解器。报告未隐藏这些告警。

此工程不是 Web 服务，SQL/XSS/CSRF 不作为适用攻击面；本轮安全重点是本地代码信任、ZIP 写入和并发更新。没有两台服务器的完整依赖清单，不能给出运行环境已无组件漏洞的结论。真实工程保存重开、完整服务器 GUI、集群锁和真实求解器仍需现场验收。

## Summary

- Critical：4 类，已修复。
- Warning：8 类，已修复。
- Info：1 类，已修复。
- 以上按独立根因计数；同类中断恢复横跨多个入口，没有按文件重复累计。
- 总体评价：已修复本轮证实的高风险路径，并增加可复现回归及维护约定；不能将测试通过解释为所有宿主环境和物理计算均已验证。
