# Code Review Report

审查基线：`096c5f4c558639d33df6ddad4dc9ec1a02bc4ab5`，工程 1.24.33 / 管理器 1.10.30。本报告中的修复随工程 1.24.34 / 管理器 1.10.31 发布。

范围：CGYRO 收集、索引、续算、删除与状态探针；TGLF 原生分支与工作台缓存；Transfer 数据保留；GUI 刷新；模板预览、更新、归档路径和相关测试。采用实际调用链检查、失败用例复现和隔离回归，不以函数行数或命名偏好代替缺陷证据。

## Critical — 必须修复

### C1. 打开工程会自动删除旧 Transfer 数据 — 已修复

- 位置：`Transfer_tool/LIB/OMFITlib_transfer_workflow.py:17`，`OMFITlib_project.py`，`Transfer_tool/SCRIPTS/main.py`。
- 原因：只要 `Profiles_gen` 有当前输入，就删除旧 H/D/T 转换分支及 `History`。当前输入存在不能证明旧分支内容重复；打开工作台、初始化设置也会触发删除。
- 修复：移除这些调用；旧脚本仍可能持有的函数保留兼容入口，但不再删除数据。需要清理时由用户明确删除相应分支。不恢复或复制历史快照。
- 实现示例：

```python
def discard_legacy_outputs(node):
    # Compatibility hook for saved scripts; never delete legacy user data.
    return []
```

- 验证：向旧分支放入独有对象，打开工程、初始化转换设置、调用兼容入口后，确认引用保持不变；普通映射和原生约束映射均覆盖。已被旧版本删除并保存的数据，需要从用户已有备份恢复，本次代码修改不能还原它们。

### C2. TGLF 径向扫描覆盖单文件结果，异常时丢失部分成功点 — 已修复

- 位置：`TGLF_scan/SCRIPTS/runScanAtRho.py:18`，`TGLF_scan/TGLF/SCRIPTS/runTGLFUQscan.py`。
- 原因：径向结果先复制到子模块单文件分支，计算结束再 `pop` 回去。原单文件结果被覆盖；内层异常会跳过回存。
- 修复：直接把本半径的结果和缓存映射传给现有原生扫描脚本，只复制本次输入。成功点直接留在对应原生分支；异常继续向上传播。UQ 增加同样的可选缓存映射参数。
- 实现示例：

```python
results = root.setdefault(scanResults, OMFITtree()).setdefault(rho, OMFITtree())
root['TGLF']['SCRIPTS'][script].run(
    inputTGLF=radial_input, results=results,
    results_spectra=spectra, cache_records=cache_records)
```

- 验证：1D / 2D / UQ 成功与失败路径；单文件结果使用禁止读取和深拷贝的替身；其他半径及参数组不受影响。

### C3. CGYRO 错配输入可先覆盖有效归档，直到续算才发现 — 已修复

- 位置：`LIB/OMFITlib_cgyro_input_identity.py:64`，`CGYRO_scan/SCRIPTS/downsync.py`、`CGYROScan.py`。
- 原因：收集时只比较生成输入与坐标，没有同时验证 `input.cgyro`、`input.cgyro.gen` 和冻结输入摘要。修改显式输入但保留旧 `.gen`，仍能生成结果索引。
- 修复：收集和续算共用 `verified_parameters`；在结果替换前传入冻结 SHA，并核对两份输入及坐标。每次只读当前点的小输入文件，单文件上限 1 MiB。旧无 `.gen` 结果核对已有摘要及显式字段，不猜测省略的默认参数。
- 实现示例：

```python
actual, input_digest = read_parameters(result_file(result, 'input.cgyro'))
if expected_hash and input_digest != expected_hash:
    raise ValueError('Saved input.cgyro checksum disagrees with the frozen input')
```

- 验证：能量分辨率或离子质量错配、冻结 SHA 不符、旧无 `.gen`、省略默认参数，以及其他归档结果保持不变。既有有效结果不会因失败的新点验证而被替换。

## Warning — 建议修复

### W1. 纯显示操作仍刷新 OMFIT 主数据树 — 已修复

- 位置：`LIB/OMFITlib_project_ui.py:133`，`OMFITlib_plot_style_ui.py:12`，`OMFITlib_compare_cases.py`、`OMFITlib_compare_ui.py`、`OMFITlib_compare_widgets.py`。
- 原因：`updateGUI=False` 只控制当前窗口，原生按钮仍发送主树事件；样式控件也未使用已有的纯显示适配模式。打开管理器、帮助、样式窗口、图例编辑，以及全选/清空选择会触发无关工作。
- 修复：复用现有刷新边界，纯显示按钮明确设置 `refresh_tree=False`，样式控件采用 `view_only()`；需要更新选择的操作只重建当前局部区域。归档等实际数据写入仍保留必要通知。
- 示例：`ui.Button('清空半径', callback, updateGUI=True, refresh_tree=False)`。
- 验证：原生 Tk / OMFIT 按钮测试同时检查窗口对象保留和 `<<update_treeGUI>>` 次数。修复前可复现主树事件，修复后这些操作为零；没有把本地事件测试描述为太原实际延迟测量。

### W2. TGLF 新结果仍携带旧原生缓存摘要 — 已修复

- 位置：`LIB/OMFITlib_tglf_records.py:51`。
- 原因：工作台替换结果后未失效原生缓存。同坐标来自不同输入的新结果可能被旧摘要认作原配置缓存，原生入口从而跳过计算。
- 修复：成功发布点后，仅失效对应扫描组/半径的摘要，包括二维行缓存及 UQ。使用现有缓存结构，不解析结果数组。
- 示例：`records.pop(group, None); records.pop(group + '_rows', None)`。
- 验证：实际执行原生 1D 脚本，确认不会误用旧摘要；检查其他参数组、半径和维度的缓存保留。

### W3. 删除结果后完成条件仍包含被删坐标 — 已修复

- 位置：`LIB/OMFITlib_cgyro_task_cleanup.py:65`，`OMFITlib_cgyro_result_index.py:382`。
- 原因：只删除结果引用，未更新 `planned_coordinates` 和 `scan_complete`，后续归档仍要求已明确删除的点。
- 修复：只移除本次删除的坐标；如果该坐标仍有保留点则不移除。未收集及身份未知的点继续影响覆盖完整性，再从元数据计算状态。
- 示例：`saved['scan_complete'] = scan_completion(info, tasks, scope)`。
- 验证：正负 ky、未选点和未收集点保留；删除操作不读取物理结果文件。

### W4. 线性输出存在且退出码为零，被误报完整 — 已修复

- 位置：`CGYRO_scan/SCRIPTS/downsync.py:125`。
- 原因：探针没有要求求解器正常结束标志；仅有初始化日志与零退出码也能通过。
- 修复：线性计算必须有收敛或达到最大模拟时间标志。无标志的可读输出保留为部分结果，不丢弃文件；非线性流程不套用线性标志。
- 示例：`grep -q -E 'Linear (converged|terminated at max time)' "$point/out.cgyro.info"`。
- 验证：真实本地 Bash 探针覆盖初始化假完成、正常收敛、最大时间退出和非线性边界。

### W5. 保留当前数据的模板预览仍读取全部示例载荷 — 已修复

- 位置：`OMFITtemplates/LIB/OMFITlib_template_live.py:159`。
- 原因：先校验整个模板，再复制选中文件。未采用的大示例结果也被解压、哈希；采用的文件重复读取。
- 修复：完整成员索引、路径、树结构检查保持；实际采用的成员在私有暂存复制时流式校验一次大小和 SHA。选择示例模式仍验证示例，失败清理暂存。
- 示例：`_stage_member(source, name, destination, cancel)`，在一次复制中累积 `digest.update(block)` 和字节数。
- 验证：未采用数据禁止打开、采用文件只读一次、缺文件/损坏代码/树摘要不符拒绝、示例模式仍拒绝损坏示例。

### W6. Windows 更新 Linux ZIP 时改写合法文件名 — 已修复

- 位置：`OMFITtemplates/LIB/OMFITlib_template_service.py:73`。
- 原因：Windows 的 `ZipInfo` 将 Linux 文件名中的反斜杠改为路径分隔符，更新保留校验出现 `KeyError`，两个不同成员也可能被归一为同一路径。
- 修复：复制 ZIP 成员时保持精确归档名；文件系统解压的路径限制不变。
- 示例：`target.filename = target.orig_filename = dest_name`。
- 验证：同时包含 `literal\name` 和 `literal/name` 的归档经更新后，两者名称及内容分别保留。

## Info — 可选改进

### I1. 架构文档仍描述旧历史链和快照行为 — 已修正

- 位置：`ARCHITECTURE.md`、`Transfer_tool/help.rst`。
- 更新为当前 RUN_DB 直接定位、所选点续算、TGLF 原生维度分支、轻量摘要和显式清理边界。增加 section / 窗口 / 主数据树三种刷新区别。
- 后续遵循的接口示例：`select_result(...)` / `selected_result(...)`，不以 `source_token` 递归拼接祖先结果。

### I2. 绘图测试依赖宿主窗口管理器定位 — 已修正

- 位置：`tests/test_plot_window.py:31`。
- 首轮失败中窗口尺寸未变，仅屏幕坐标被移动；生产代码重复布局路径未调用窗口定位。测试 fixture 改为自行持有窗口几何，排除宿主 WM 自动定位。
- 示例：`self.master.overrideredirect(True)`。保留完整窗口坐标、尺寸及工具栏断言，没有放宽业务检查；不把这次测试环境失败描述成已证实的应用故障。

## 验证与审查边界

最终完整回归与构建结果见 `VALIDATION.md` 的本次审查记录。首轮失败日志保留，不把失败轮次和定向重跑重复计入最终测试总数。

- 测试包括原生 OMFIT 控件回调、真实 Tk 画布、本地 Bash 探针、文件及元数据协议；求解器和部分 OMFIT 数据类使用明确的替身。
- 安全检查覆盖远程命令参数转义、准确作业身份、ZIP 路径/符号链接/重复成员、HTTPS 重定向凭据边界、摘要校验、失败回滚。未发现其他有证据支持的新漏洞；未进行在线依赖 CVE 审计。
- 没有执行真实求解器、连接太原或修改用户工程；未验证完整 OMFIT 会话的现场保存重开，也未测量修复后的远程 VNC 延迟。
- 保留已有模块结构和索引机制。仅抽取收集/续算共享校验，去掉径向结果复制、删除隐式清理、明确刷新边界，未做全量重构。

## 旧工程使用方式

本次尚未发布 GitHub。发布后采用“仅更新代码，保留现有输入、结果和设置”，关闭旧工作台、绘图和管理器窗口后重新打开；现有活动回调不会自动换成新实现。

不需要整理全库、复制历史快照或迁移 TGLF 结果。后续收集和续算按当前点核验输入；对无法证实一致性的点明确报错并保留原结果。已经发生的数据删除不能由代码更新自动撤销。

## Summary

- Critical：3 项，已修复。
- Warning：6 项，已修复。
- Info：2 项，已处理。
- 总体评价：主要风险集中在结果所有权、缓存失效和刷新事件边界。针对失败路径补验证比整体重构更合适；本次保留现有结构，修复确认的问题，不承诺未验证环境不存在缺陷。
