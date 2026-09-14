# 验证记录 · 2026.09.14

本版将模板管理器更新为 **1.2.2**，修复 Python 3.9 下启动时报 `nametofont() got an unexpected keyword argument 'root'` 的兼容问题。

- 先用旧版 `nametofont(name)` 签名配合真实 Linux Tk 窗口复现报错，再改用 Python 3.9 支持的 `Font(root=window, name='TkDefaultFont', exists=True)`。
- 管理器 91 项 Linux 回归测试通过；新增覆盖旧字体接口下完整界面初始化，以及目标 Tk 解释器的字体绑定。确认不会更改另一 Tk 窗口的默认字体。
- 测试环境仍为 Python 3.10 / Tk 8.6；旧接口用与 Python 3.9 一致的签名复现，未声称完成完整 Python 3.9 环境验收。兼容接口已核对 CPython 3.9 的 `Lib/tkinter/font.py`。
- 工程总控和计算流程代码沿用上一版；以下 133 项工程测试记录为上一版验证结果。本版发布包重新检查语法、引用、模板校验及旧工程升级保留。

以下保留 2026.09.13.1 的验证背景：

本版将默认界面改为 Linux OMFIT 原生 **Project 总控**，统一 Transfer、CGYRO、TGLF、多剖面计算、运行记录、绘图和 GitHub 模板入口。

- 133 项 Linux 回归测试通过：原有 74 项绘图/工程测试、25 项多剖面测试、34 项 Project 总控与输入保护测试。环境为 Ubuntu 22.04 / Python 3.10 / NumPy 1.21.5 / Matplotlib 3.5.1。
- 覆盖空工程九个页面与运行配置绑定、Transfer 准备要求、输入改变后阻止运行、点击时重新校验、只生成输入时禁止收集、按运行维数收集归档、运行标志在异常后恢复。
- 验证 Transfer/TGYRO 输入差异、保留与覆盖选择、待确认时禁用运行、过期预览拒绝覆盖、原输入及对应结果一起归档。生成局部输入和切换半径保留当前单文件；径向和增长率扫描在成功或失败后均保留该输入与结果。
- Linux Tk 8.6 / WSLg 适配器渲染 ProjectUI 控件并检查中文布局和按钮状态；原 OMFIT CompoundGUI 子页面以占位控件代替。尚未在完整 OMFIT 桌面实例中联调，未执行真实求解器或提交服务器任务。
- 发布前检查 Python 3.9 语法、OMFITsave 引用、代码包与模板的 CRC/SHA-256，验证升级保留案例、已有 TGLF 输入/结果、PROJECT_STATE 历史和用户设置，同时更新默认 GUI。
- 新增记录存放于 PROJECT_STATE 数据分支；分发包只包含空数据容器。运行环境检查仅验证字段与输入依赖，不代表自动探测求解器、队列或硬件资源。原 TGLF 批量调度设置的统一自动化尚未实现。

以下保留 2026.09.13 的验证背景：

本版增加 OMFIT 原生 **TGLF 多 input.gacode 计算** 页面，入口位于默认比较界面和原 main 页面，也可从 `GUIS/TGLF_multi` 打开。

- 新增 23 项 Linux 回归测试：真实文件导入、同名文件区分、剖面快照、半径范围与坐标、单半径辅助点、参数覆盖、独立工作目录、分步生成/运行、失败继续与重试、中止、输入变更检测、执行命令更新、空工程 GUI、结果记录、绘图和双层 OMFITsave 注册。
- 既有绘图/工程 74 项测试全部通过；新增 23 项全部通过，合计 97 项。测试环境为 Ubuntu 22.04 / Python 3.10 / NumPy 1.21.5 / Matplotlib 3.5.1。
- 外部执行使用模拟 TGYRO localdump 和 TGLF 输出验证控制流程，未调用真实求解器。GUI 测试核对 OMFIT 控件绑定和回调；尚未在完整 OMFIT 桌面实例中联调。
- 核对官方 GACODE 的 `tgyro` 命令、`tgyro_parse.py`、`tgyro_init_profiles.f90` 与 `tgyro_tglf_map.f90`：使用 `-t` 测试模式、`DIR ... X=...` 和明确的 `TGYRO_USE_RHO`；保留原始 profile，通过 TGYRO 生成每例的局部几何、物种及梯度，再应用显式 TGLF 参数。默认同步顺序运行，不自动提交队列。
- 输入、输出、历史尝试和日志归入独立的 `TGLF_CASES` 数据分支。每次运行使用新子目录，并显式传递 `clean=False`；原有 `TGLF_scan` 的输入和扫描结果保持独立。
- 工程与模板附件在发布前检查引用、Python 3.9 语法、ZIP CRC 和 SHA-256，并验证模板更新保留历史数据及用户设置。

以下保留 2026.09.12.1 的验证背景：

- 来源：此前审计、修复和重构后的 `CGYRO_99949_compare_refactored.zip` 的已校验代码/设置模板。
- 新工程包含 CGYRO_TGLF_scan、OMFITtemplates 两个顶层模块；计算数据文件数为 0，仅保留空数据容器。所有 OMFITsave 文件引用可解析。
- 清空旧案例选择、结果缓存、个人运行路径、部署设置及相应动态表达式；MainSettings 使用中性默认值，不包含旧命令历史、个人邮箱和服务器配置。
- 增加 CGYRO/TGLF 主界面的 Templates / GitHub 按钮；通过相邻模块的 GUI.run 进入管理器，使 OMFITlib 导入在正确的模块命名空间执行。
- 修复 OMFITsave 的树输出顺序，按深度优先遍历保存模块及其 SETTINGS；验证 OMFIT 原生工程信息读取器的关联规则。
- GitHub 版本说明兼容 LF、CRLF 和 CR 换行，避免元数据被忽略。
- 管理器 89 项测试在 Ubuntu 22.04 / Python 3.10 / Tk 8.6 / WSLg 中通过，包括真实 Tk 操作、本机 HTTP GitHub 模拟、数据保留、失败恢复、模块元数据顺序和版本说明换行格式。
- 对比绘图及工程集成 74 项测试在 Ubuntu 22.04 / Python 3.10.12 / NumPy 1.21.5 / Matplotlib 3.5.1 中通过：包含之前的 40 项测试及新增的 34 项 CGYRO 回归测试；覆盖五种图形、空工程、合并半径、保存字段读取、原始数据导出和界面选项。测试使用合成数据，不运行求解器。
- CGYRO 自对比从单个约 1,800 行库拆分为调度入口及五个职责模块。数据准备完成后创建图页；图例/颜色每页统一处理；3D 坐标点一次分组累加，缺失格点不补造数据。
- 修复空参考值不出比值图、错误 ky 被当作全部 ky、重复 ky 在比值统计中重复计数、缺失数据生成空白图、过滤器/半径选择失配、3D 图重复绘制累积坐标轴以及 Matplotlib 3.5 颜色条造成双图重叠的问题。
- 本征函数直接显示保存的 E∥；原代码中缺失字段的二阶导数估计和对已有 E∥ 再加感应项的路径已移除。此为明确的行为修正，不对旧推算公式作物理正确性背书。
- 已检查 Linux 生成的五种图形和 24 曲线图例。相同合成数据（24 曲线 × 4 ky × 4 面板，包含 Agg 画布绘制）三次对比：旧版耗时中位数 1.155 秒，新版 0.473 秒，约减少 59%；旧版布局告警 3 次，新版 0 次。该基准不包含真实结果文件读取，不能外推为所有计算案例的加速比。
- 发布包通过所有 Python 源码编译、Python 3.9 语法兼容性、ZIP CRC 和模板 SHA-256 校验；源计算工程未修改。
- 旧绘图脚本中的部分 LaTeX 字符串在 Python 3.12 下仍有无效转义 SyntaxWarning；此次均可编译，未在本次上传中扩大修改这些脚本。

GitHub 上传后另行校验提交树和 Release 附件。本测试未启动 CGYRO/TGLF 求解器，未在完整 OMFIT 安装中做整机联调。

复现：

```sh
python3 -m unittest discover -s OMFITtemplates/tests -v
python3 -m unittest discover -s tests -v
python3 tools/build_project.py
```
