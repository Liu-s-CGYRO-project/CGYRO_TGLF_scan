# OMFIT 兼容审计与内部支持代码 · 1.1.0

## 1.1.0 / 管理器 1.3.0：GitHub 代理

新增注册库 `OMFITlib_template_proxy`，同时注册在完整工程及 OMFITtemplates 模块保存树。管理器默认使用已有的 47.102.120.146 SSH 中继配置，读取脚本导出的动态本地端口及 HTTP 代理认证；提供显式加载脚本、连接测试、系统代理、手动 HTTP 代理和直连选项。

HTTP CONNECT 保留 GitHub 端到端 TLS 证书验证。显式代理不受继承的 NO_PROXY 绕过；GitHub Authorization 只发送给 GitHub，Proxy-Authorization 只用于代理隧道，跨下载主机重定向移除 GitHub 凭据。偏好设置只保存非密码配置，不修改 OMFIT 全局环境或 opener。新增库在页面加载时导入，按钮回调保留函数引用。

本版验证 119 项 Linux 管理器测试，其中新增 9 项代理/脚本测试与 5 项 GUI 测试；包含实际本地 HTTP CONNECT、认证、经校验证书的 TLS、下载重定向、上传字节、认证失败、脚本文件名转义和密码不落盘。17 项原生执行测试覆盖 40 个注册库及清理后的代理回调；原生 Tk 封装另验证新代理对话框、变量绑定、密码隔离和生成新工程。记录见 `validation/proxy_1_1_0/`。

没有 tyadmin06 的现有连接脚本和运行会话，本地隔离代理验证不等同于已连通其真实 SSH 中继；也未运行完整服务器 OMFIT 或真实求解器。CGYRO/TGLF 代码与科学设置沿用 1.0.1，199 项工程回归、66 项原生映射回归和 32 组比较布局记录沿用该版。以下保留 1.0.1 兼容与支持代码记录。

本版把项目专用的 Python 支持代码随 OMFIT 工程保存。CGYRO 绘图和扫描入口不再添加个人目录到 `sys.path`，无需为这些辅助文件配置 `PYTHONPATH`。

## 1.0.1：页面加载后的按钮回调

1.0.0 中，CGYRO 对比页面可以打开，但点击绘图、检查或导出时可能报 `No module named 'OMFITlib_compare_cgyro_selection'`。库文件及注册均存在；实际原因是 `execGlobLoc` 在 GUI 脚本结束后移除 OMFIT 导入钩子并清理库缓存，按钮回调中的延迟导入失效。

选项解析与校验现放在不依赖其他工程库的 `OMFITlib_compare_options` 中，由页面加载时导入并保留函数引用。新库已同时注册在工程和模块的 `OMFITsave.txt` 中，原有函数导入入口继续兼容。TGLF 多输入页面的通量摘要也改为加载时导入。无需安装额外包或恢复私人 Python 路径。

新增独立回调回归：先执行实际 GUI 入口，再确认导入钩子和缓存已被原生代码清理，最后触发保存的按钮。覆盖四种比较模式的检查/绘图、无效选项阻止绘图、谱文件导出、取消导出和完成记录的通量摘要。修复前复现同一异常，修复后通过。测试加载器不再提前导入普通 Python 测试套件，避免文件系统导入缓存掩盖 OMFIT 的生命周期问题。源码审计新增函数内工程库延迟导入检查。

## 1.0.1：比较页面的原生布局

对照本地 OMFIT 源码中的 `modules/TGLF_GACODE/GUIS/TGLF_GUI.py`、`modules/EFIT/GUIS/EFITgui.py` 和 `modules/TUTORIAL/GUIS/basic.py`、`nested_tabs.py`，采用原生 `Tab`、`Separator`、`same_row` 和参数控件组织界面。与 EFIT 的公共操作区相同，用 `Tab('')` 返回标签页之外放置常用动作。

- 四种比较模式统一使用“案例选择 / 绘图设置 / 图形样式 / 导出与检查”标签页；公共区仅保留选择状态、“检查选择”和“绘制所选数据”。
- 工程总控、TGLF 多输入、模板 / GitHub 移到第四页的“其他工具”，避免与绘图按钮混排。
- 参数按用途分组，统一标签宽度，缩短主界面说明；详细说明放入原生帮助按钮。半径和扫描参数每行最多三项，长名称缩略显示并提供完整帮助文本。
- 显示文案和控件排列调整不改变设置键、已保存参数值或科学计算逻辑；绘图点击时仍重新校验选择。
- “过滤未收敛点”旁始终显示可编辑的 `error 上限`，0.01 表示 1%；启用过滤后，ω 或 γ 的相对时间波动超过该阈值的点被排除。CGYRO 谱峰值标记改为每条曲线当前显示的最大 γ，随原始 γ、γ/ky、γ/ky²、归一化与过滤设置变化；无效值和对数坐标下不可见的点不参与定位。

Linux 预览直接使用 12 个未修改的 OMFIT 控件/布局函数体，在较大字体（Helvetica 11，Tk scaling 1.5）下验证四种模式、四个标签页和两种窗口尺寸（860×640、1080×800），共 32 组。检查可见控件不越界、不重叠、公共操作按钮可见，并在原生导入清理后实际触发 Tk 绘图按钮。预览的宿主、主题及帮助/位置查询接口使用适配器，不是完整 OMFIT 服务器会话；布局覆盖代表性案例。

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

## 1.0.0 已纳入的修复

- 清除 CGYRO 源码中 40 行个人导入路径及注释，替换额外的动态 reader 路径注入。28 个读取器导入改用注册的 `OMFITlib_cgyro_read`；移除不再使用的 `cgyro_ball`、`cgyro_ball_class` 导入。
- 34 处辅助脚本改为按完整源码执行，保留原文件名与当前脚本命名空间；支持多行函数和控制块。
- 修正 OMFIT 注入 NumPy 后 `any/all(generator)` 的语义变化，覆盖通量检查、Rice 参数检查与 QLGYRO 离子检查。
- 旧线性绘图使用 collector 写入的 `_PLOT_CACHE`，不再读取错误的 `OUTPUTS/Linear` 分支；线性通量估算复用已加载的对象。
- 修正旧 `classes.omfit_*` 导入、缺少的 SciPy 插值导入、过时 NumPy 标量别名和积分函数名。修正非线性 GYRO Miller 方法引用了另一个类的错误。
- 旧线性图的 GYRO 归一化读取当前案例的生成输入，区分第一离子和后续离子键名，避免未定义变量并排除动理学电子；CGYRO 半径同样取自当前案例。
- Transfer 的 `view12` 用明确的 SciPy `CubicSpline` 替代未定义的 `spline`，采用默认 not-a-knot 三次插值；这明确了旧脚本未声明的插值边界约定。OMAS 导出明确从 `omas.omas_physics` 导入搜索函数。

## 验证范围

检查 262 个生产 Python 文件、9 个 OMFIT 模块、全部已保存表达式与设置 JSON。检查 Python 3.9 语法、脚本引用、每个模块的库注册，以及 873 处固定 OMFITx 调用的参数签名。本次文件清单和 SHA-256 见仓库 `validation/omfit_callbacks_1_0_1/`；原支持文件对照记录保留在 `validation/omfit_compatibility_1_0_0/`。

Linux 验证：

- 199 项工程回归，涵盖运行保护、输入覆盖选择、多 input.gacode、历史和绘图；扩展峰值标记回归以验证三种显示量、无效 ky 与对数坐标，验证不同 error 阈值实际改变保留点。
- 66 项回归另用未修改的 OMFIT SortedDict 类及其惰性加载装饰器执行。
- 16 项原生执行检查，使用 OMFIT `execGlobLoc` 和 `_defaultVars` 函数体；覆盖全部 39 个注册库、4 个 collector 类、34 个多行辅助加载位置、缓存读取、有效与损坏的通量、频率统计、Miller 方法、Rice 参数和旧归一化/插值入口。本次在无预加载工程库的环境中重新执行。
- 5 项独立回调回归，包含四种比较模式和多组非法选项子测试；实际生成 Matplotlib 图和原始谱导出文件。
- 32 组原生 Tk 控件布局检查，包含四种模式、四页及两种窗口尺寸；记录见 `layout_validation.json`。
- 管理器代码未改动，105 项测试及原生 Tk 封装检查沿用 1.0.0 的记录。新模板另验证“生成新工程”保留输入、结果和设置，以及离线包校验与预览。

原生执行检查仅省略外层 Matplotlib 偏好锁定装饰器；宿主会话、文件节点和求解器读取边界使用测试适配器。测试环境为 Ubuntu 22.04、Python 3.10.12、NumPy 1.21.5、Matplotlib 3.5.1、Tk 8.6.12。**未启动完整服务器 OMFIT 会话、真实 CGYRO/TGLF 求解器，也未完成真实结果文件解析和所有科学算法的验收。** 873 处 API 签名检查不能等同于全部数据分支的 GUI 实机运行。

仍有 5 处静态缺失引用，均属于已限制的旧路线：两个 GYRO 提交入口原已禁用；QLGYRO 需要未包含的 `TGLF_GACODE` 和 `GYRO_scan` 伴随模块，本版在读取/修改输入和提交前明确检查并拒绝缺失的配置。常用的 CGYRO、TGLF、Transfer 与多剖面流程不依赖这些伴随模块。

常规 OMFIT 环境及其第三方依赖仍需正常安装。特别是 OMFIT 的 `OMFITcgyro/OMFITgyro/OMFITtgyro` 由标准 `pygacode` 支持，本版没有复制或替换 OMFIT 框架本身。可选 UQ/OMAS 功能仍需其对应的公开 Python 包。

## 使用新版

模板版本 **1.0.1**，模板管理器仍为 **1.2.5**。先保存当前工程，在管理器中选择本版 `.omfittpl.zip`，保留当前案例/结果及设置，点击正常的“生成新工程”，关闭旧比较页面，然后打开生成的 ZIP 并重新打开比较页面。不要只替换单个库文件；本次新增库需要更新 OMFIT 树注册。首次新建工程可直接打开本版 `code_only.zip`。

不需要把 `GACODE_module.zip` 再解压到个人 Python 路径。更新工程不会修改 Linux 的 `.bashrc`、Conda 环境或删除服务器上的个人文件。计算案例和结果不进入代码模板。

开发者复现命令：

```sh
python3 tools/audit_omfit_compatibility.py /path/to/omfit --output audit.json
python3 tools/audit_private_support.py /path/to/GACODE_module.zip --output support.json
python3 tools/validate_native_execution.py /path/to/omfit --output native_execution.json
python3 tools/validate_native_callbacks.py /path/to/omfit --output native_callbacks.json
python3 tools/validate_compare_layout.py /path/to/omfit --output gui_preview
python3 tools/validate_project_mapping.py /path/to/omfit/omfit_classes/sortedDict.py
python3 tools/validate_template_tk.py /path/to/omfit/utils_tk.py
python3 -m unittest discover -s tests
python3 -m unittest discover -s OMFITtemplates/tests
```
