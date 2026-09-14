# CGYRO / TGLF OMFIT Project

用于 Linux 桌面的 OMFIT 工程，包含已审计、修复和整理的 CGYRO/TGLF 工具，以及项目内置的 **OMFIT GitHub 模板管理器**。

当前分发版为 **2026.09.14.1**，仅包含代码、输入模板和默认设置；计算案例、结果、缓存与旧命令记录不入库。原模块的输入示例保留在 `TEMPLATES` 中。执行计算前，需要导入自己的平衡/剖面或案例，并配置计算环境与求解器路径。

模板管理器 1.2.3 支持更新已有模块并添加缺少的顶层模块，预览显示“更新模块”和“新增模块”；同时保留 Python 3.9 字体兼容修复。

默认 GUI 现在是 **Project 总控**：输入准备、Transfer tool、CGYRO、TGLF、运行配置和记录、绘图及 GitHub 模板管理集中在同一入口。保留多 input.gacode 计算与原比较绘图页面。

## 在 OMFIT 打开

推荐从 [Releases](https://github.com/Liu-s-CGYRO-project/CGYRO_TGLF_scan/releases) 下载 `CGYRO_TGLF_scan_code_only_2026.09.14.1.zip`，在 OMFIT 中打开。

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

1. **Transfer → CGYRO**：载入或生成输入，在“传递输入”中选择 `input.cgyro` 并点击“验证并送入 CGYRO”。已有完整输入也经过此步骤，无需强制重新运行 profiles_gen。只有输入检查和执行配置均通过，CGYRO 的准备、运行按钮才启用。传递后修改源输入、上游剖面或 CGYRO 输入，会要求重新准备和传递。
2. **Transfer → TGLF**：选择 `input.tglf` 并传入。目标已有文件时先显示参数差异，由用户决定保留当前版本或使用传入版本；不自动混合参数。覆盖前保存原输入与关联结果，新的输入不会被关联到旧结果上。预览后任一输入变化，都需要重新比较。
   TGYRO 按半径生成的输入也可在“TGLF 单文件与扫描 → 参数与径向扫描”选择，然后点击“比较并传入当前 TGLF 单文件”。生成和切换半径保留已有单文件输入；径向扫描使用局部副本，不覆盖该输入或它的结果。
3. **Transfer 内部生成**：“生成与高级工具”可载入其自己的 `input.tglf` / `input.tgyro`。TGLF 种子已有值时同样先询问覆盖；改变生成输入会归档并使旧 TGYRO 结果失效。缺少上一步输入或结果时，后续按钮禁用并给出原因。
4. **计算与收集**：可以仅生成 CGYRO 扫描输入，也可以运行。只有已提交或执行过的运行才允许收集；收集后按该运行记录的实际维数归档到绘图数据中，不会重新提交作业。多剖面 TGLF 必须先生成匹配当前输入和参数的局部输入，之后才能运行。
5. **运行配置**：选择模块与 OMFIT 服务器，使用“同步 OMFIT 连接配置”填入服务器、隧道和工作目录，再设置命令。CGYRO 直接显示当前提交器读取的配置。检查仅确认本地设置和输入依赖，不代表已验证目标机器上的求解器或资源。
6. **结果与历史**：无结果时禁用相应绘图按钮；保存的旧结果仍可查看。总控操作、输入候选、覆盖选择和输入历史位于 `PROJECT_STATE`，随当前工程保存，代码模板只含空分支。打开总控页不会提交任务或自动轮询服务器。

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

在实际运行 OMFIT 的 Linux 环境安装 [GitHub CLI](https://cli.github.com/)，执行 `gh auth login --hostname github.com --web`，或使用界面的登录按钮。私有库读取和发布分别需要 Contents 读、写权限；公开库可匿名读取，但可能遇到 API 限流。

1. 连接仓库，选择开发者和版本，点击“拉取并使用”。
2. 保存当前 OMFIT 会话为 ZIP，选择保留当前案例与结果，或使用模板示例。
3. 预览变更后生成新工程。打开前可备份当前会话；原 ZIP 始终保留。
4. 开发者准备模板包，核对文件清单、仓库与账号，再发布不可覆盖的新版本。

当前模板包含 `CGYRO_TGLF_scan` 和 `OMFITtemplates` 两个模块，不带结果或计算案例。在管理器中拉取 **2026.09.14.1**，选择保留当前案例、结果和设置即可生成更新后的工程。默认 GUI 的模块信息随模板更新，用户的计算设置与结果继续保留。旧工程缺少管理模块时，1.2.3 管理器会在生成新工程时自动添加，无需先在旧工程中手动安装该模块。新版独立管理器也能处理原来的模板包。

Git 仓库保存可审查的源码；OMFIT 管理器通过 Release 附件分发模板。界面不会自动把附件内源码提交到 Git，源码改动仍通过正常的 commit / push 流程同步。

## 从源码生成工程 ZIP

```sh
python3 tools/build_project.py
```

输出到 `dist/CGYRO_TGLF_scan_code_only_2026.09.14.1.zip`（版本号来自 `PROJECT_CONTENTS.json`）。构建仅收录 `OMFITsave.txt` 引用的代码、设置与输入模板，校验所有引用，并拒绝混入非空计算数据分支。

独立模板界面可执行 `sh OMFITtemplates/start_manager.sh`；OMFIT 内使用时复用 OMFIT 自己的 Python 和 Tk。

## 验证和范围

管理器需要 Python 3.9+ 与 Tk；比较绘图还需要 OMFIT 的 NumPy / Matplotlib 等依赖。详见 [验证记录](VALIDATION.md) 和 [管理器完整说明](OMFITtemplates/help.rst)。

此版本未运行求解器，也未在完整 OMFIT 安装中完成整机验收。随附模块原有的作者、许可与依赖说明保留；本仓库不包含 OMFIT 框架本体。
