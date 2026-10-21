# 维护与扩展接口

适用于工程 1.22.37。这是 OMFIT 数据树工程；`root` 在总控页面指工程，在 CGYRO 子脚本中指 `CGYRO_scan`。普通 Python 包的导入、字典和对象生命周期不能直接套用。先读 [架构](ARCHITECTURE.md) 和 [兼容要求](OMFIT_COMPATIBILITY.md)。

## 先找到修改层

| 目标 | 修改位置 | 边界 |
| --- | --- | --- |
| 新页面、模块路径、状态文案 | `LIB/OMFITlib_workbench_catalog.py` | 纯数据定义，保存键保持稳定 |
| 总控导航、通用按钮与说明 | `LIB/OMFITlib_project_ui.py` | `ProjectUI` 保留公共入口与界面上下文 |
| CGYRO 页面 | `LIB/OMFITlib_workbench_cgyro_ui.py` | 输入、参数、运行入口、结果概览 |
| 运行配置页面 | `LIB/OMFITlib_workbench_runtime_ui.py` | 编辑草稿，显式点击后才探测或应用 |
| 转换页面和输入编辑器 | `LIB/OMFITlib_workbench_transfer_ui.py` | 编辑副本，摘要复核通过后才保存 |
| CGYRO / TGLF 共用扫描字段 | `LIB/OMFITlib_workbench_scan_ui.py` | 取值列表、区间、倍率；不提交作业 |
| CGYRO 收集编排 | `LIB/OMFITlib_cgyro_workflow.py` | 原生脚本执行由调用方注入 |
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

## 参数、绘图和数据归属

- 新 CGYRO 参数进入 `OMFITlib_cgyro_parameters.FIELDS` 和 `OMFITlib_cgyro_parameter_help.PARAMETER_HELP`，同时核对扫描取值解析与物理限制。UI 文案不能隐式改变物理默认值。
- 新绘图类型从 `OMFITlib_compare_state` 的选项、对应 `compare_*` 调度入口和渲染函数接入。多轴扫描使用完整任务坐标，不将组合键当作单个参数。详见 [绘图接口](CGYRO_TGLF_scan/DOCS/PLOTTING_API.md)。
- 仅读取结果元数据的页面使用 `cgyro_present`；需要数值时才调用 `resolve_result/result_view`。后者返回的临时视图不能写回保存树。`RESULT_STORE` 仍是物理结果唯一拥有者。
- `record_options(records)` 返回“显示文字 → 原 token”；同名和缩略重名会加标识区分。完整身份由 `record_details(record, token)` 提供，不可用短名反查目录或构造归档键。
- `collection_status` 与作业状态独立。`COMPLETED` 只说明调度器执行返回，不能用它推断已收集、完整结果或物理收敛。

## 排版约定

采用原生 `same_row`、`Tab` 和已适配的控件，不为单个页面修改全局主题。普通行由 `NativeLayout` 根据可用宽度调整列数；参数行标记 `frame._cgyro_inline = True`，不足一行时把名称放到输入框上方。行内控件顺序、绑定和帮助按钮都保持不变。

正文保持短句，完整说明使用 `help=` 或 `view.note()`。不要为了缩短显示而改动选项值、输入值或归档键。宽度以实际字体测量为准；字体变更会重新测量并排版。绘图中的文字继续采用英文，界面使用中文。

Tk 变量使用 `master=`，布尔框走 `gui_controls.checkbox`。不要在 `Configure` 回调中运行计算、读取大结果、重新渲染整个页面或更改用户选择。

## 静态检查与发布

当前约定只执行静态和安装包检查；下面三条命令不会导入应用界面或运行求解器：

```bash
python tools/check_workbench.py
python tools/audit_omfit_compatibility.py /path/to/omfit --output audit.json
python tools/build_project.py --output /path/to/review/project.zip
```

构建时会自动检查页面登记、mixin 方法冲突、回调导入位置、收集默认权限、原生 API 和每个模块的依赖注册。提交前还需检查 Python 3.9 AST/符号、ZIP 成员、CRC、源文件与包摘要、完整字体许可，并记录哪些分支未做真实服务器验证。

管理器测试源码保留在 `OMFITtemplates/tests`，不再登记到运行树或打入工程安装包；它们仍可由后续显式授权的开发验证使用。不能通过删除字体许可、检查点保护或恢复信息缩减安装包。所有 GUI 实机验证、测试套件与集群任务都需要另外获得执行授权，静态检查不能声称它们已通过。

## 续算输入归档接口

OMFITlib_cgyro_storage_files.SubmissionFiles 只计划新所有者与索引，不直接修改工程；compact_storage 负责提交与回滚。ZIP 所有者放在 RESULT_STORE/__FILES__，外部叶用 __FILE_REF__。需要文件时使用 result_view / submission_file，不复制解析后的视图回树。prune_storage 同时检查结果引用和文件引用。迁移器独立理解 __RESULT_REF__，不能依赖更新完成后才可导入的工程库。

已读结果、未开始点 ZIP、部分历史和本次提交的输入是不同职责；不能通过删除整个 Cases / RUN_HISTORY 或删旧结果达到去重。保留旧 ZIP 的原始成员摘要，重试只从本次运行的冻结记录取文件，并恢复上传文件名。
