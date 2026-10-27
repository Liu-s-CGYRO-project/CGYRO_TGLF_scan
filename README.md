工程 1.24.23：优化扫描、转换和对比页面的交互，标签按需创建，修改选项只重绘相关区域；普通数值编辑不重复运行整套扫描校验。修复 Kill local 后续算结果卡在“已读取，待归档”：归档使用本次冻结点表，不再依赖可能被其他归档替换的旧索引。已有工程仅更新代码，保存后重启 OMFIT，再收集原作业即可，不必重新提交整批计算。配套管理器仍为 1.10.28。

已有工程可下载本版 [仅更新代码脚本](https://github.com/Liu-s-CGYRO-project/CGYRO_TGLF_scan/releases/download/omfit/tdxy-liu/cgyro-tglf/1.24.23/omfit-update-1.24.23.py)，上传到运行 OMFIT 的服务器执行，保留输入、结果和设置。任务删除见 [任务管理说明](CGYRO_TGLF_scan/DOCS/TASK_CLEANUP.md)。按作业号恢复见 [恢复说明](CGYRO_TGLF_scan/DOCS/JOB_RECOVERY.md)。需要额外整理旧归档时，使用 [更新与整理脚本](https://github.com/Liu-s-CGYRO-project/CGYRO_TGLF_scan/releases/download/omfit/tdxy-liu/cgyro-tglf/1.24.23/omfit-maintain-1.24.23.py)，步骤见 [Command Box 整理说明](COMMAND_BOX_COMPACTION.md)。

操作与 .old 风险见 [归档去重说明](CGYRO_TGLF_scan/DOCS/RESULT_STORAGE.md)，取消与续算见 [操作说明](CGYRO_TGLF_scan/DOCS/CANCEL_RESUME.md)。历史修订见 [完整版本记录](https://github.com/Liu-s-CGYRO-project/CGYRO_TGLF_scan/blob/main/RELEASE_HISTORY.md)。

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

当前工程版本为 **1.24.23**，管理器为 **1.10.28**。分发包仅包含代码、输入模板和默认设置，计算前请导入自己的输入并配置求解器环境。项目专用支持库随工程保存，不依赖私人 Python 路径；兼容范围见 [OMFIT 兼容说明](OMFIT_COMPATIBILITY.md)。

运行与环境 → 选择服务器和队列 → **自动检测** → 核对“服务器能力”和资源草稿 → **应用到整个工程**。检测结果只用于原服务器和隧道；队列查询失败时保留资源设置并显示未知。内存值用于展示，不推算求解器需求；账户 / QOS 配额及实时空闲资源仍由调度器决定。v3 检查点验证通过后可调整 MPI / OpenMP 资源继续计算。

管理器在 OMFIT 内更新当前工程的代码，保留案例、结果和设置；常规更新不调用整个工程的加载或保存。更新后照常另存工程。历史管理器修订已保存在上述完整版本记录。

## 在 OMFIT 打开

发布后可从 [Releases](https://github.com/Liu-s-CGYRO-project/CGYRO_TGLF_scan/releases) 下载 `CGYRO_TGLF_scan_code_only_1.24.23.zip`，在 OMFIT 中打开。

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

工作页面包括概览、运行与环境、Transfer tool、CGYRO、TGLF 计算与扫描、绘图对比、模板与 GitHub。多 input.gacode 入口位于 TGLF 工作台。常用参数在总控页设置；原模块的完整设置页通过对应按钮打开。

1. **Transfer → CGYRO**：运行 Transfer_tool 后自动读取本轮全部 `input.cgyro_N`。在 CGYRO 页勾选 `nr/rho` 和“原始/H/D/T”主离子方案，再设置 1–3 个物理参数轴；它们自动组成计算案例。已有完整 `input.cgyro` 也可直接载入，作为一个输入案例使用。
2. **TGLF 输入选择**：在“TGLF 计算与扫描”选择当前文件、Transfer_tool 输入或已生成的半径输入。显式导入或传入新的单文件时，程序先把旧输入与关联结果独立保存在输入历史，再安装新输入；参数不混合，也不自动运行。内容相同的输入保留当前结果，不重复归档。工程 1.17 起已取消独立的输入差异确认页。
   生成或选择半径不会替换已有单文件输入；径向扫描使用局部副本。旧工程未处理的输入候选在打开工作台时转为“保留当前输入”，候选继续保存在历史中。
3. **Transfer 内部生成**：在“Transfer_tool 运行”载入剖面，设置 rho 或 r/a、起止半径和点数，点击“运行 Transfer_tool”。程序按原 command box 1 同步离子数量、质量与电荷，随后调用 main.py 连续完成 TGYRO 和局部输入生成。无需分别点击 TGYRO 与 profiles_gen。已有 input.tglf / input.tgyro 沿用；缺少时从内置种子复制。“高级设置”只编辑或更换 Transfer_tool 自己的种子，不再跳转到 TGLF_scan 的另一套 TGYRO 参数。显式导入不同的 TGLF 种子会保存旧种子及其 TGYRO 结果，然后清除当前旧输出，等待用户再次运行。生成结果按本次半径重建，旧输出归档，失败时恢复原输出。
   “局部输入互转”为独立页，选择 TGLF → CGYRO、CGYRO → TGLF 或 localdump → CGYRO，只载入该方向需要的源文件；目标输入自动创建。
4. **计算与收集**：可以仅生成 CGYRO 扫描输入，也可以运行。每个点使用 `p000001` 形式的任务编号；参数、半径、离子方案、任务表及实际结果统一记录在 `RUN_DB/结果名/案例`，服务器目录固定为 `runs/<运行标识>/<任务编号>`。同一结果名、输入、半径与离子下，不同参数扫描并存；相同有序参数轴（含联动参数）按全部参数坐标和 ky 合并，新增坐标追加，仅同坐标点更新。失败或未完整收集时保留旧结果，其他扫描与案例不变。只有已提交或执行过的运行才允许收集。多剖面 TGLF 必须先生成匹配当前输入和参数的局部输入，之后才能运行。
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

模板包含 CGYRO_TGLF_scan 与 OMFITtemplates，不带结果。更新时保留当前案例和设置，预览后应用；赋值或界面刷新失败会回退本次节点修改。

如果总控页因旧版本报错而无法打开，可以从工程树直接打开 `OMFITtemplates → GUIS → main`，或在 OMFIT 命令窗口执行 `OMFIT['OMFITtemplates']['GUIS']['main'].run()`。桌面无法联网时，将 Release 的 `.omfittpl.zip` 传到 Linux，在“更新 / 切换”的模板包位置选择本地文件；内置管理器直接更新当前工程，外部管理器生成新 ZIP。

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

旧管理器如无增量入口，先通过完整包升级；工程更新使用“更新 / 切换”，预览后应用到当前工程。
