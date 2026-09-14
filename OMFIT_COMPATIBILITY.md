# OMFIT 兼容审计与内部支持代码 · 1.0.0

本版把项目专用的 Python 支持代码随 OMFIT 工程保存。CGYRO 绘图和扫描入口不再添加个人目录到 `sys.path`，无需为这些辅助文件配置 `PYTHONPATH`。

## 支持代码的去向

用户提供的 `GACODE_module.zip` 含 9 个 Python 源文件。逐文件和类/方法对照后，全部已有对应实现；补回了此前工程缺少的 `OMFITcgyro_nonlin.miller_wd_s`。保留已经修正的频率统计、谱宽和通量处理，没有用旧包整体覆盖新版代码。旧包中的 `.pyc` 和旧 `OMFITsave.txt` 不作为新工程入口。

下表的 OMFIT 位置均在 `CGYRO_TGLF_scan → CGYRO_scan` 内：

| 原支持文件 | 工程中的位置 |
| --- | --- |
| CGYROscan/cgyro_read_xj.py | LIB → OMFITlib_cgyro_read；旧 assist → cgyro_read_xj 保留转发入口 |
| CGYROscan/collect.py | PLOTS → CGYROscan → assist → collect.py |
| CGYROscan/collect_gyro.py | PLOTS → CGYROscan → assist → collect_gyro.py |
| CGYROscan/getglobal.py | PLOTS → CGYROscan → assist → getglobal.py |
| CGYROscan/starter.py | PLOTS → CGYROscan → assist → starter.py |
| CGYROscan/changeOMFITcgyrogacode.py | PLOTS → CGYROscan → assist → changeOMFITcgyrogacode.py |
| CGYROalone/collect.py | PLOTS → CGYROalone → assist → collect.py，实际文件为 collect_99949.py |
| CGYROalone/collect_gyro.py | PLOTS → CGYROalone → assist → collect_gyro.py |
| CGYROalone/getglobal.py | PLOTS → CGYROalone → assist → getglobal.py |

纯函数由当前模块的 `LIB` 注册并导入。4 个继承 OMFIT 原生数据类的自定义类留在注册的 collector 脚本中：OMFIT 的库加载器会移除在 `OMFITlib_*` 中新增的 OMFITobject/SortedDict 子类，不能把所有代码机械地塞进 LIB。见 [OMFIT 原生加载器源码](https://omfit.io/_modules/omfit_classes/omfit_python.html)。

`OMFITtemplates/launch.py` 作为独立 Linux 管理器启动器，会加载它自身目录中的 LIB。该目录随离线包分发；在 OMFIT 内打开管理器使用注册库，不依赖这个启动器或个人 Python 目录。

## 本版修复

- 清除 CGYRO 源码中 40 行个人导入路径及注释，替换额外的动态 reader 路径注入。28 个读取器导入改用注册的 `OMFITlib_cgyro_read`；移除不再使用的 `cgyro_ball`、`cgyro_ball_class` 导入。
- 34 处辅助脚本改为按完整源码执行，保留原文件名与当前脚本命名空间；支持多行函数和控制块。
- 修正 OMFIT 注入 NumPy 后 `any/all(generator)` 的语义变化，覆盖通量检查、Rice 参数检查与 QLGYRO 离子检查。
- 旧线性绘图使用 collector 写入的 `_PLOT_CACHE`，不再读取错误的 `OUTPUTS/Linear` 分支；线性通量估算复用已加载的对象。
- 修正旧 `classes.omfit_*` 导入、缺少的 SciPy 插值导入、过时 NumPy 标量别名和积分函数名。修正非线性 GYRO Miller 方法引用了另一个类的错误。
- 旧线性图的 GYRO 归一化读取当前案例的生成输入，区分第一离子和后续离子键名，避免未定义变量并排除动理学电子；CGYRO 半径同样取自当前案例。
- Transfer 的 `view12` 用明确的 SciPy `CubicSpline` 替代未定义的 `spline`，采用默认 not-a-knot 三次插值；这明确了旧脚本未声明的插值边界约定。OMAS 导出明确从 `omas.omas_physics` 导入搜索函数。

## 验证范围

检查 261 个生产 Python 文件、9 个 OMFIT 模块、全部已保存表达式与设置 JSON。检查 Python 3.9 语法、脚本引用、每个模块的库注册，以及 864 处固定 OMFITx 调用的参数签名。文件清单和 SHA-256 见仓库 `validation/omfit_compatibility_1_0_0/`。

Linux 验证：

- 199 项工程回归，涵盖运行保护、输入覆盖选择、多 input.gacode、历史和绘图。
- 66 项回归另用未修改的 OMFIT SortedDict 类及其惰性加载装饰器执行。
- 16 项原生执行检查，使用 OMFIT `execGlobLoc` 和 `_defaultVars` 函数体；覆盖全部 38 个注册库、4 个 collector 类、34 个多行辅助加载位置、缓存读取、有效与损坏的通量、频率统计、Miller 方法、Rice 参数和旧归一化/插值入口。
- 管理器 105 项测试，以及 OMFIT 原生 Tk 变量/Toplevel/Text 封装下的实际 `main.py` 入口、预览和生成新工程检查。

原生执行检查仅省略外层 Matplotlib 偏好锁定装饰器；宿主会话、文件节点和求解器读取边界使用测试适配器。测试环境为 Ubuntu 22.04、Python 3.10.12、NumPy 1.21.5、Matplotlib 3.5.1、Tk 8.6.12。**未启动完整服务器 OMFIT 会话、真实 CGYRO/TGLF 求解器，也未完成真实结果文件解析和所有科学算法的验收。** 864 处 API 签名检查不能等同于全部数据分支的 GUI 实机运行。

仍有 5 处静态缺失引用，均属于已限制的旧路线：两个 GYRO 提交入口原已禁用；QLGYRO 需要未包含的 `TGLF_GACODE` 和 `GYRO_scan` 伴随模块，本版在读取/修改输入和提交前明确检查并拒绝缺失的配置。常用的 CGYRO、TGLF、Transfer 与多剖面流程不依赖这些伴随模块。

常规 OMFIT 环境及其第三方依赖仍需正常安装。特别是 OMFIT 的 `OMFITcgyro/OMFITgyro/OMFITtgyro` 由标准 `pygacode` 支持，本版没有复制或替换 OMFIT 框架本身。可选 UQ/OMAS 功能仍需其对应的公开 Python 包。

## 使用新版

模板版本 **1.0.0**，模板管理器仍为 **1.2.5**。先保存当前工程，在管理器中选择本版 `.omfittpl.zip`，保留当前案例/结果及设置，点击正常的“生成新工程”，然后打开生成的 ZIP。新工程包含所需的专用辅助源码。首次新建工程可直接打开本版 `code_only.zip`。

不需要把 `GACODE_module.zip` 再解压到个人 Python 路径。更新工程不会修改 Linux 的 `.bashrc`、Conda 环境或删除服务器上的个人文件。计算案例和结果不进入代码模板。

开发者复现命令：

```sh
python3 tools/audit_omfit_compatibility.py /path/to/omfit --output audit.json
python3 tools/audit_private_support.py /path/to/GACODE_module.zip --output support.json
python3 tools/validate_native_execution.py /path/to/omfit --output native_execution.json
python3 tools/validate_project_mapping.py /path/to/omfit/omfit_classes/sortedDict.py
python3 tools/validate_template_tk.py /path/to/omfit/utils_tk.py
python3 -m unittest discover -s tests
python3 -m unittest discover -s OMFITtemplates/tests
```
