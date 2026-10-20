工程 1.22.29：接通二维及三参数 CGYRO 扫描的对比绘图。各参数轴分别筛选，任选变化参数，其余坐标固定分组；按已保存任务的完整坐标和路径读取谱、时间曲线、本征函数及导出。partial 结果缺点保留为空，三维网格不完整时用散点，不混合或补造不同组合的数据。已有归档更新后可直接绘图，无需重算；管理器仍为 1.10.20，安装包小于 1 MB。仅做静态和安装包校验，操作见 [多参数绘图说明](CGYRO_TGLF_scan/DOCS/MULTI_AXIS_PLOTS.md)。

工程 1.22.28：修复计算点 / 时间曲线 / 续算窗口的 `TypeError: name must be a string`。点说明和追加时间两个 StringVar 均显式传入 master=window，兼容 OMFIT 对 Tk 变量的封装。打包前静态检查所有已登记模块的 Tk 变量参数；更新后关闭旧工程总控和计算点弹窗，重新打开以加载新回调，结果和检查点继续保留。管理器保持 1.10.20；安装包小于 1 MB，仅完成静态和安装包校验。

工程 1.22.27：修复大扫描收集时 `/bin/bash: Argument list too long`。输出文件检查共用一份脚本，并按 UTF-8 编码与 shell 引号后的命令字节数分批，单批不超过 16 KiB；每批核对完整点表，全部探测成功后才读取结果。网络或探测失败保留运行记录，更新后可直接重新收集，无需重新提交计算。管理器保持 1.10.20；安装包小于 1 MB，仅完成静态和安装包校验。

工程 1.22.26：Kill local 取消本批 Slurm 作业后，确认终态并自动收集各案例。无结果点跳过，可读的部分结果单独归档，原完整扫描保留。结果页可选择未完成点：有效检查点从原进度继续，确认未开始的点校验原输入 ZIP 后重新计算，已完成点默认不选。再次取消仍保留续算链与输入来源。管理器保持 1.10.20；代码包小于 1 MB，仅完成静态和安装包校验，未执行 GUI、求解器或集群任务。

取消与续算步骤见 [操作说明](CGYRO_TGLF_scan/DOCS/CANCEL_RESUME.md)。旧版本修订说明移到 [完整版本记录](https://github.com/Liu-s-CGYRO-project/CGYRO_TGLF_scan/blob/main/RELEASE_HISTORY.md)，安装包保留当前使用说明。

## 在 OMFIT Command box 首次部署

在旧工程的 Command box 中执行以下四行，先下载、校验并打开模板管理器：

```python
import urllib.request as u
p = u.build_opener(u.ProxyHandler({'https': 'http://47.102.120.146:18889'}))
b = p.open('https://github.com/Liu-s-CGYRO-project/CGYRO_TGLF_scan/releases/latest/download/omfit-manager-bootstrap.py', timeout=30).read(131072)
exec(compile(b, 'omfit-manager-bootstrap.py', 'exec'), {'OMFIT': OMFIT})
```

选择最新 CGYRO / TGLF 工程版本 → 拉取并使用 → 保留当前案例和设置 → 预览变更 → 更新当前工程。预览会列出模块迁入、归档重新分类及待核对的节点；完成后照常保存 OMFIT 工程。管理器脚本只安装管理模块，工程替换在预览后由用户执行。

完整说明见 [首次部署与迁移](CGYRO_TGLF_scan/DOCS/FIRST_DEPLOY.md)。正在运行或尚未收集的旧 CGYRO 作业需要先完成收集，之后再迁移模块。下面保留已保存 ZIP 的终端部署方式。

## 两条命令首次部署

先在 OMFIT 把旧工程保存成自包含 ZIP。在运行 OMFIT 的 Linux 终端中，用其 Python 3.9+ 环境执行：

```sh
curl -fL --retry 3 --proxy http://47.102.120.146:18889 https://github.com/Liu-s-CGYRO-project/CGYRO_TGLF_scan/releases/latest/download/omfit-deploy.py -o omfit-deploy.py
python3 omfit-deploy.py '/路径/旧工程.zip'
```

自动识别已有 CGYRO_TGLF_scan，或独立的 CGYRO_scan、TGLF_scan、Transfer_tool。原 ZIP 保留，生成新工程与 .deploy.json 报告；在 OMFIT 打开打印出的新 ZIP 即可。输入 / 结果 / 设置保留，代码与依赖使用新版。若只想全新部署，第二行改为 `python3 omfit-deploy.py --new`。预览、离线模式、网络选择和范围见 [首次部署与迁移](CGYRO_TGLF_scan/DOCS/FIRST_DEPLOY.md)。

# CGYRO / TGLF OMFIT Project

用于 Linux 桌面的 OMFIT 工程，包含已审计、修复和整理的 CGYRO/TGLF 工具，以及项目内置的 **OMFIT GitHub 模板管理器**。

管理器 **1.10.6** 在 OMFIT 中直接打开完整管理器，移除带“打开 GitHub 模板管理”按钮的中间面板。再次打开切换到已有窗口；更新时清理旧入口的空面板。通过“检查管理器更新”增量安装，独立版本继续不进入模板选择列表。

管理器 **1.10.5** 在模板校验成功后显示“模板校验完成 · 版本 · 可点击预览变更”，进度条为 100%，提示保留到下一步操作。GitHub 下载、缓存和本地模板均适用；可通过“检查管理器更新”增量安装。

管理器 **1.10.4** 从 GitHub、本地和共享模板选择列表排除独立管理器包及下载缓存，管理器升级统一使用“检查管理器更新”。完整工程模板正常显示。

管理器 **1.10.3** 独立修复 GitHub 响应读取中途的连接重置：只读请求最多尝试三次，等待可取消；发布与上传不自动重复。支持界面内增量更新、完整安装与管理器离线模板。

当前分发版为 **1.19.0**，仅包含代码、输入模板和默认设置；计算案例、结果、缓存与旧命令记录不入库。原模块的输入示例保留在 `TEMPLATES` 中。执行计算前，需要导入自己的平衡/剖面或案例，并配置计算环境与求解器路径。

本版将项目专用 Python 支持全部保存到 OMFIT 工程，移除私人 `sys.path` 和 `PYTHONPATH` 依赖。已对照提供的 GACODE_module.zip 中 9 个源文件，补齐缺少的方法，并修正旧辅助加载、绘图缓存与 NumPy 注入语义等兼容问题。此前 get/default、update 和 Tk 变量修复继续保留。详见 [OMFIT 兼容审计与内部支持代码](OMFIT_COMPATIBILITY.md)。

本次没有运行测试或 GUI 实测，只有静态代码审阅、Python 3.9 语法和分发包完整性检查；不将这些检查视为桌面显示验证。

按用户要求，本次未运行回归测试或其他运行测试；仅对修改文件做静态语法检查、代码审阅和分发包完整性校验。

工作页面固定按“概览 → 环境配置 → 输入准备 → 输入确认 → CGYRO → TGLF 单文件 → TGLF 多剖面 → 绘图 → 模板”排列。输入转换、TGLF、TGYRO、PROFILES_GEN 等页面补齐中文操作文字；物理参数名、文件名和设置取值保持原意。

原生“…”多行编辑及文件选择按钮按实际所属窗口执行，修复另一个窗口关闭后 `_absLocation` 找不到 `topGUI` 的异常；从总控打开的原生子模块窗口也继承此处理。补丁只作用于工程控件，不修改 OMFIT 源码或全局 Tk 接口。

模板管理器 **1.9.0** 在 OMFIT 内默认直接更新当前内存工程，替换代码并刷新原来的 GUI 窗口，保留所选的案例、结果和设置，不调用 OMFIT.load，也不生成中间工程 ZIP。提供本次更新的撤销入口；照常保存工程即可持久保存。外部独立管理器继续预览并生成新工程 ZIP。

管理器还支持“作者”下拉筛选，可与关键词搜索、版本排序组合使用，适用于 GitHub、本地和共享模板库。修复列表空状态两行文字重叠，使用中文实际字体计算布局，并增加更新说明和日志的行距。继续支持界面内增量更新、GitHub 登录与公共代理。

默认 GUI 现在是 **Project 总控**：输入准备、Transfer tool、CGYRO、TGLF、运行配置和记录、绘图及 GitHub 模板管理集中在同一入口。保留多 input.gacode 计算与原比较绘图页面。

工程模板从 **1.0.0** 起使用语义版本：修复问题递增修订号（例如 1.0.1），兼容的新功能递增次版本号（例如 1.1.0），不兼容的变更递增主版本号（例如 2.0.0）。管理器版本独立维护，目前为 **1.10.2**。历史日期版保留供回溯。

1.0.1 修复 OMFIT 页面加载结束后点击 CGYRO 绘图、检查或导出时的库导入异常，并按 OMFIT 自带 TGLF、EFIT 和 TUTORIAL 的原生控件用法重排四种比较页面。页面分为“案例选择 / 绘图设置 / 图形样式 / 导出与检查”；标签页下方统一放置“检查选择”和“绘制所选数据”，其他工具入口移入第四页。升级后请关闭旧比较页面，在新生成工程中重新打开；本次新增库已随模板注册。

“过滤未收敛点”旁的 `error 上限` 始终可编辑；0.01 表示相对波动 1%，勾选过滤后生效。“标记当前曲线最大 γ”跟随当前显示量（原始 γ、γ/ky 或 γ/ky²），在过滤后的有效曲线上定位。

## 在 OMFIT 打开

推荐从 [Releases](https://github.com/Liu-s-CGYRO-project/CGYRO_TGLF_scan/releases) 下载 `CGYRO_TGLF_scan_code_only_1.16.8.zip`，在 OMFIT 中打开。

也可直接加载本仓库的工程入口：

```python
OMFIT.load('/absolute/path/CGYRO_TGLF_scan/OMFITsave.txt')
```

`OMFIT.load` 会切换当前工程，请先保存已有工作。工程提供两个顶层模块：

- `CGYRO_TGLF_scan`：扫描、转换及 CGYRO/TGLF 对比绘图。
- `OMFITtemplates`：GitHub 模板版本管理。

打开默认总控页，选择 **模板与 GitHub** 即可进入管理器；也可以打开 `OMFITtemplates → GUIS → main`。管理器已预填本仓库地址。

如果只想把管理器加入已有计算工程，在该工程的 OMFIT 命令框执行：

```python
OMFIT['OMFITtemplates'] = OMFITmodule('/absolute/path/CGYRO_TGLF_scan/OMFITtemplates/OMFITsave.txt')
OMFIT['OMFITtemplates']['GUIS']['main'].run()
```

这两条命令只添加管理模块，不替换已有 CGYRO/TGLF 数据。添加后保存自己的工程即可长期使用。

## Project 总控与流程依赖

默认入口为 `CGYRO_TGLF_scan → GUIS → main`，也可以执行：

```python
OMFIT['CGYRO_TGLF_scan']['GUIS']['main'].run()
```

工作页面包括概览、Transfer tool、输入差异确认、CGYRO、TGLF 单文件与扫描、多 input.gacode、运行与环境、绘图对比、模板与 GitHub。常用参数在总控页设置；原模块的完整设置页通过对应按钮打开。

1. **Transfer → CGYRO**：运行 Transfer_tool 后自动读取本轮全部 `input.cgyro_N`。在 CGYRO 页勾选 `nr/rho` 和“原始/H/D/T”主离子方案，再设置 1–3 个物理参数轴；它们自动组成计算案例。已有完整 `input.cgyro` 也可直接载入，作为一个输入案例使用。
2. **Transfer → TGLF**：选择 `input.tglf` 并传入。目标已有文件时先显示参数差异，由用户决定保留当前版本或使用传入版本；不自动混合参数。覆盖前保存原输入与关联结果，新的输入不会被关联到旧结果上。预览后任一输入变化，都需要重新比较。
   TGYRO 按半径生成的输入也可在“TGLF 单文件与扫描 → 参数与径向扫描”选择，然后点击“比较并传入当前 TGLF 单文件”。生成和切换半径保留已有单文件输入；径向扫描使用局部副本，不覆盖该输入或它的结果。
3. **Transfer 内部生成**：在“Transfer_tool 运行”载入剖面，设置 rho 或 r/a、起止半径和点数，点击“运行 Transfer_tool”。程序按原 command box 1 同步离子数量、质量与电荷，随后调用 main.py 连续完成 TGYRO 和局部输入生成。无需分别点击 TGYRO 与 profiles_gen。已有 input.tglf / input.tgyro 沿用；缺少时从内置种子复制。“高级设置”只编辑或更换 Transfer_tool 自己的种子，不再跳转到 TGLF_scan 的另一套 TGYRO 参数。替换 TGLF 种子仍显示差异并由用户确认。生成结果按本次半径重建，旧输出归档，失败时恢复原输出。
   “局部输入互转”为独立页，选择 TGLF → CGYRO、CGYRO → TGLF 或 localdump → CGYRO，只载入该方向需要的源文件；目标输入自动创建。
4. **计算与收集**：可以仅生成 CGYRO 扫描输入，也可以运行。每个点使用 `p000001` 形式的任务编号；参数、半径、离子方案、任务表及实际结果统一记录在 `RUN_DB/结果名/案例`，服务器目录固定为 `runs/<运行标识>/<任务编号>`。同一结果名、输入、半径与离子下，不同参数扫描并存；完整重扫只替换相同有序参数轴（含联动参数）的旧结果。失败或未完整收集时保留旧结果，其他扫描与案例不变。只有已提交或执行过的运行才允许收集。多剖面 TGLF 必须先生成匹配当前输入和参数的局部输入，之后才能运行。
5. **运行配置**：选择模块与 OMFIT 服务器，使用“同步 OMFIT 连接配置”填入服务器、隧道和工作目录，再设置命令。CGYRO 直接显示当前提交器读取的配置。检查仅确认本地设置和输入依赖，不代表已验证目标机器上的求解器或资源。
6. **结果与历史**：在“绘图与对比 → CGYRO 扫描结果浏览”选择结果记录并点击“查看当前数值表”。表格列出任务、全部扫描参数、ky、末段平均 omega/gamma、相对波动，并标记当前筛选范围的最大 gamma；二维参数先选择 ky，三维参数再选择第三轴切片。也可直接在数据树展开 `RUN_DB/结果名/案例/__SCANS__/扫描键/tasks` 查看各组坐标，实际输出保存在同一案例的公开扫描分支；顶部 `__TASKS__` 仅是最近扫描的兼容视图。跨案例或 CGYRO/TGLF 对比继续使用原对比页。

上述流程约束由总控入口及其点击回调执行；直接在 OMFIT 命令行运行旧脚本仍属于高级用法。旧 TGLF 批处理的并行数、时限和通用运行设置自动化仍待后续统一，本次未改动其科学模型和求解算法。

## 多份 input.gacode 的 TGLF 计算

在总控页选择 **TGLF 多 input.gacode**，也可运行 `CGYRO_TGLF_scan → GUIS → TGLF_multi`。原比较页仍保留快捷按钮。

1. **文件与案例**：多选 `input.gacode`，或选目录递归导入。不同文件夹中的同名文件按独立案例保存。填写共用半径（例如 `0.3, 0.5, 0.7`）；单个案例的半径可覆盖共用值。坐标明确选择 `rho` 或 `r/a`。
2. **计算设置**：设定 SAT_RULE、NKY、NMODES、电磁开关及离子选择。案例的“此案例参数”支持 `SAT_RULE=2; NKY=24`，优先于共用设置。“复制为新案例”可对同一份剖面运行不同模型参数，不复制历史结果。
3. **执行环境**：默认本机 Linux。环境初始化中可填写 `source /path/to/gacode/shared/bin/gacode_setup` 等命令；需要能运行已安装的 TGYRO 和 TGLF。远程模式复用嵌套 TGYRO / TGLF 模块的服务器配置，顺序、同步执行；本页不自动提交排队任务，应使用已分配的计算节点。TGYRO / TGLF 命令支持按本地安装修改。
4. **运行与结果**：可以先“生成输入”，查看 `TGLF_CASES` 中的 localdump 和实际 `input.tglf`，再“运行已生成输入”；也可“生成并运行”。更改半径或物理参数后需要重新生成输入。失败项可重试，完成项会跳过；准备阶段失败则重新生成。
5. **比较**：每个案例选择一条运行记录，勾选参与对比，叠加显示各自 ky 网格上的频率和增长率。界面同时显示逐物种粒子/热通量。数值为各案例原始 TGLF 归一化单位；不同剖面的归一化参考量可能不同，物理单位比较需另行转换。

输入转换使用 TGYRO 的 `-t` 测试模式和 `out.tglf.localdump`，指定半径使用 `DIR ... X=...`；`TGYRO_USE_RHO` 与所选坐标对应。单半径时会加入一个范围内的辅助转换点，最终 TGLF 计算只覆盖请求半径。参考 [TGYRO 命令源码](https://github.com/gafusion/gacode/blob/master/tgyro/bin/tgyro) 和 [TGYRO 参数说明](https://gafusion.github.io/doc/tgyro/tgyro_list.html)。

案例保存于 `CGYRO_TGLF_scan['TGLF_CASES']`，包含导入文件副本、SHA-256、实际输入、转换/运行命令与日志、各次尝试及结果。每次生成创建新记录，每次重试使用新目录；不会替换现有扫描的 `FILES` / `scanResults`。保存当前 OMFIT 工程即可保存这些案例。更新模板时选择保留当前案例与结果；发布包不包含此数据分支的内容。

## GitHub 模板管理

默认使用“手动 HTTP 代理”：主机 `47.102.120.146`，端口 `18889`，用户名和密码留空。也可选择“系统代理”读取环境代理，或“不使用代理”。旧版 SSH 模式自动迁移到公共 HTTP 代理，并清除旧代理认证与脚本路径；已保存的手动、系统和直连配置保留。

在“GitHub 版本 → 代理设置”编辑网络配置，点击“测试连接”验证 HTTPS。版本检查、拉取、发布、管理器更新及 gh 安装使用当前代理。手动代理密码仅留在当前窗口，不写入偏好或工程；外部浏览器使用自身网络设置。

点击“登录 GitHub”会自动检测 gh：已有命令直接使用，缺少时按当前 Linux 架构下载 [GitHub CLI 官方稳定版](https://github.com/cli/cli/releases/latest)，核对大小和 SHA-256，安装到 `${XDG_DATA_HOME:-$HOME/.local/share}/omfit-template-manager/tools/bin/gh`。无需 sudo、pip 或更改 PATH。界面显示进度，可取消；失败时清理临时文件，重新点击登录即可重试。安装后自动打开官方 gh 登录流程，用户完成浏览器授权后，管理器自动读取 GitHub 当前账号并启用发布页；已有登录时点击“连接仓库”也会同步账号。授权流程见 [gh auth login](https://cli.github.com/manual/gh_auth_login)。公开模板的浏览和下载无需安装 gh 或登录。发布页（包括准备本地模板包）在未登录时禁用，作者 ID 使用 GitHub 验证返回的登录名并设为只读；账号变化或凭据失效后清除原发布计划。

终端诊断可运行 `python3 OMFITtemplates/launch.py github-probe`，默认使用公共代理且不读取 GitHub 凭据。可用 `--network system` / `--network direct` 切换网络方式，或 `--network manual --proxy-host HOST --proxy-port PORT` 指定 HTTP 代理。


私有库读取和发布分别需要 Contents 读、写权限；公开库可匿名读取，但可能遇到 API 限流。

1. 连接仓库，选择开发者和版本，点击“拉取并使用”。
2. 选择保留当前案例、结果和设置，或切换到模板示例与模板设置。
3. 在 OMFIT 内预览后点击“更新当前工程”，直接更新内存中的模块并刷新界面；外部管理器继续选择当前 ZIP 并生成新工程。
4. 开发者准备模板包，核对文件清单、仓库与账号，再发布不可覆盖的新版本。

当前模板包含 `CGYRO_TGLF_scan` 和 `OMFITtemplates` 两个模块，不带结果或计算案例。内置管理器 **1.10.2** 拉取工程 **1.13.0** 后，选择保留当前案例、结果和设置，点击“预览变更 → 更新当前工程”即可在当前会话生效。未保存的案例和结果也保留原对象，窗口自动刷新。更新时不保存或重载工程，不改变当前项目文件名；照常使用 OMFIT 保存即可。代码或设置在预览后发生变化时要求重新预览；赋值或 GUI 刷新失败会回退本次节点修改。外部独立管理器保持原有的生成新 ZIP 流程。

如果总控页因旧版本报错而无法打开，可以从工程树直接打开 `OMFITtemplates → GUIS → main`，或在 OMFIT 命令窗口执行 `OMFIT['OMFITtemplates']['GUIS']['main'].run()`。桌面无法联网时，将 Release 的 `.omfittpl.zip` 传到 Linux，在“更新 / 切换”的模板包位置选择本地文件；内置管理器直接更新当前工程，外部管理器生成新 ZIP。

如果已经生成的 ZIP 打不开，在 **1.6.0 管理器**中将该 ZIP 选为当前工程，选择所需模板，保留当前案例、结果和设置，预览后点击“生成新工程”。入口顺序会自动正确写入，无需单独修复或重新计算。原 ZIP 保留，需要一份完整工程的额外磁盘空间。

Git 仓库保存可审查的源码；OMFIT 管理器通过 Release 附件分发模板。界面不会自动把附件内源码提交到 Git，源码改动仍通过正常的 commit / push 流程同步。

## 从源码生成工程 ZIP

```sh
python3 tools/build_project.py
```

输出到 `dist/CGYRO_TGLF_scan_code_only_1.13.0.zip`（版本号来自 `PROJECT_CONTENTS.json`）。构建仅收录 `OMFITsave.txt` 引用的代码、设置与输入模板，校验所有引用，并拒绝混入非空计算数据分支。`OMFITsave.txt` 固定为 ZIP 第一个条目，兼容原生 OMFIT 的入口定位规则。

独立模板界面可执行 `sh OMFITtemplates/start_manager.sh`；OMFIT 内使用时复用 OMFIT 自己的 Python 和 Tk。

## 验证和范围

管理器需要 Python 3.9+ 与 Tk；比较绘图还需要 OMFIT 的 NumPy / Matplotlib 等依赖。详见 [验证记录](VALIDATION.md) 和 [管理器完整说明](OMFITtemplates/help.rst)。

此版本未运行求解器，也未在完整 OMFIT 安装中完成整机验收。随附模块原有的作者、许可与依赖说明保留；本仓库不包含 OMFIT 框架本体。

## 管理器增量更新

右上角“检查管理器更新”会显示需下载的文件、压缩后体积和复用文件数。点击“安装增量更新并重新打开”即可，无需手动解压或 Import module。公开更新无需 GitHub 登录，使用当前代理。

文件清单和每个压缩附件都校验 GitHub 提供的 SHA-256，解压后再校验文件内容。未改变的文件按校验值复用，支持跨版本更新。所有文件在独立版本目录组装，校验完成后才切换；取消、校验失败或本地文件在预览后变化时保留当前版本。

在 OMFIT 内只替换 OMFITtemplates，保留原设置并补全新增项，然后重新打开管理器。其他模块和内存中的计算结果不动，不调用整个工程的保存或加载。请正常保存 OMFIT 工程以持久保留更新；新版界面打开失败会恢复原管理模块。

独立 Linux 版在用户 XDG 数据目录保存完整的新版本与启动指针，原安装目录保留。切换前使用当前 Python 隔离检查完整 GUI；启动失败恢复原指针。原启动脚本会自动打开新版本。需要回到原目录版本时，可执行 `bash start_manager.sh --no-update-redirect`。

1.6.0 及更早管理器需先通过原来的完整安装包升级一次到 1.7.0；之后更新可使用增量。完整包下载继续保留作兼容入口。计算工程仍通过“更新 / 切换”生成新工程 ZIP。
