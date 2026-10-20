# 代码结构与维护入口

本工程是保存在 OMFIT 数据树中的模块集合，不是普通的 Python 安装包。界面和脚本由 OMFIT 执行，支持库通过当前模块的 `LIB` 加载。修改库时需要同时考虑调用代码、数据树路径和两个层级的 `OMFITsave.txt`。

## 按职责找代码

| 要修改的功能 | 主要入口 | 职责边界 |
| --- | --- | --- |
| 工程导航、操作历史、输入交接 | `CGYRO_TGLF_scan/LIB/OMFITlib_project.py` | `ProjectActions` 执行用户动作、保存结果和恢复临时设置；保留旧导入入口 |
| 输入校验、摘要、差异比较 | `LIB/OMFITlib_project_inputs.py` | 读取与校验数据；不提交任务、不写文件、不替换输入 |
| CGYRO 半径、H/D/T 和扫描计划 | `LIB/OMFITlib_cgyro_plan.py` | 选择迁移、输入副本转换、运行前校验；不提交作业 |
| CGYRO 参数与取值 | `LIB/OMFITlib_cgyro_parameters.py`、`OMFITlib_cgyro_scan_values.py`、`OMFITlib_cgyro_parameter_help.py` | 参数定义、取值解析、离线帮助；预览和提交共用 |
| CGYRO 批量队列 | `LIB/OMFITlib_cgyro_queue.py` | 切换当前案例、保存整批进度、等待和整批取消 |
| CGYRO 重试 | `LIB/OMFITlib_cgyro_retry.py` | 确认提交结果、筛选可重试点、复用核对过的输入 |
| CGYRO 调度器状态 | `LIB/OMFITlib_cgyro_run_state.py` | 解析状态、核对作业身份、取消与已有 Kill local 接口 |
| CGYRO 准备、下载、归档 | `CGYRO_scan/SCRIPTS/subscan_lin.py`、`downsync.py`、`CGYROScan.py`、`LIB/OMFITlib_cgyro_archive.py` | 原生 OMFIT 任务适配；完整结果仅替换相同扫描参数组 |
| TGLF 工作台和多剖面 | `LIB/OMFITlib_tglf_workbench.py`、`OMFITlib_tglf_multi_run.py` | 准备计划和持久运行记录；底层执行在 `TGLF_scan/TGLF/SCRIPTS` |
| Transfer 粒子处理 | `Transfer_tool/LIB/OMFITlib_transfer_particles.py`、`OMFITlib_transfer_equivalent.py`、`OMFITlib_transfer_zeff.py` | 原始副本准中性 → 完整组成 Zeff → 粒子方案 → 局部输入复查 |
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
- 每个案例的 `__SCANS__[扫描键]` 保存独立的 `info` / `tasks`，物理结果仍只有一份、保存在该案例的公开扫描分支。`p000001` 等点编号只在各自扫描内有效。顶部 `__INFO__` / `__TASKS__` 仅作最近一次扫描的兼容视图；浏览与续算必须遍历 `case_scans`，不能以它们代表整个案例。续算只替换选定扫描的选定点，并拒绝已经重扫替换的旧 token。作业号和结果目录由运行记录持有，不能从当前 GUI 参数重新推断。
- 取消后确认 Slurm 终态再自动收集整批。collection_status 与作业状态分离；空点跳过，部分扫描使用独立结果集，原完整归档保留。未开始点只可复用带摘要的原输入 ZIP；已有样本不能在检查点失效时静默重算。续算链和各点来源跨再次取消保留，完整覆盖原计划才替换完整扫描。
- 网络报错后先确认原提交是否成功。无法确认时保留 `submission_uncertain`，不重复提交。重试资格按每个扫描点判定，先前的取消、超时和内存不足状态不能因切换到重试数组而丢失。
- TGLF 批量点允许部分成功；归档和异常传播是两个步骤，后续点失败不能抹去前面已经返回的结果。
- 局部输入转换不会自动选择新的碰撞模型。CGYRO → TGLF 在指定 Zeff 时保留该值；反向旧入口仍采用 `COLLISION_MODEL=4`，没有将 TGLF 的独立 Zeff 转为指定 Zeff 模式。需要改变这一物理约定时，应单独核对模型适用条件，不能只增加一个字段。
- Transfer 等效方案只把高密度热 H/D/T 识别为主离子，快粒子和微量燃料留在辅助组；规则同时用于原始副本的电荷补偿。`equivalent_temperature` 明确区分保压与温度随热主离子，随同其他选项冻结进生成记录。后者只检查实际保留的电荷 / Zeff / 质量 / 电荷梯度约束，单独记录压力变化；不能把压力变化误报为守恒失败，也不能继续显示“压力守恒”。曲率先还原物理导数再重建，不能直接复制温度改变前的 SDLNNDR。
- 对比选择和半径配对属于所选数据源。切换结果集后恢复该结果集的选择，同时重新检查有效值；图例短名不能取代归档键。
- “清空全部结果”在既有确认后同时清理主结果、旧索引和派生缓存，保留输入和配置。远程文件不由此入口删除。

## 修改代码时的约定

1. 优先把计算与校验放入无执行副作用的函数，把原生任务调用和数据树替换留在动作层。注释解释数据归属、归一化、状态转换和异常处理原因，避免逐行复述代码。
2. OMFIT 的 `SortedDict.get` 需要显式默认值，`update` 接收一个映射；构造 `OMFITtree` 后再填入数据。不要把原生树假定为完全兼容普通 `dict`。
3. OMFIT 会注入 NumPy/pylab 名称。需要 Python 语义的 `all`、`any`、`min`、`max`、`sum` 等应显式从 `builtins` 导入。
4. 工程库在文件顶部导入，供 GUI 回调保留引用；不要在按钮回调内延迟导入 `OMFITlib_*`。新增库要登记在根工程和模块清单，并为实际使用它的子模块登记全部依赖。
5. 不凭目录名或 UUID 排序推断时间。使用运行时间、归档顺序和记录中的身份；列表显示名称与实际键分离。
6. 修改失败路径时同时阅读成功、取消、网络状态不明和重新收集路径。记录要先足够恢复，再执行远程动作；成功数据与失败日志都应有明确保存位置。

## 校验与发布

当前维护约定只执行静态和安装包校验，未经用户要求不启动测试、GUI、绘图、求解器或集群任务。Python 3.9 AST、符号检查、原生 API 和清单依赖校验不能代替实际服务器验证；发布说明需明确这一点。

每次发布冻结源文件及包的 SHA-256，校验包内文件与源文件一致。两个代码安装包均小于 1,000,000 字节，完整字体通过独立资源包缓存，不能通过裁剪或改写字体满足大小限制。开发文档和完整历史保留在 GitHub，安装包只纳入运行所需文件及现有用户文档。
