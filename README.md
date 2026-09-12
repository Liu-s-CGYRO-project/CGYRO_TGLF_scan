# CGYRO / TGLF OMFIT Project

用于 Linux 桌面的 OMFIT 工程，包含已审计、修复和整理的 CGYRO/TGLF 工具，以及项目内置的 **OMFIT GitHub 模板管理器**。

当前分发版为 **2026.09.12**，仅包含代码、输入模板和默认设置；计算案例、结果、缓存与旧命令记录不入库。原模块的输入示例保留在 `TEMPLATES` 中。执行计算前，需要导入自己的平衡/剖面或案例，并在 OMFIT 配置计算服务器与求解器路径。

## 在 OMFIT 打开

推荐从 [Releases](https://github.com/Liu-s-CGYRO-project/CGYRO_TGLF_scan/releases) 下载 `CGYRO_TGLF_scan_code_only_2026.09.12.zip`，在 OMFIT 中打开。

也可直接加载本仓库的工程入口：

```python
OMFIT.load('/absolute/path/CGYRO_TGLF_scan/OMFITsave.txt')
```

`OMFIT.load` 会切换当前工程，请先保存已有工作。工程提供两个顶层模块：

- `CGYRO_TGLF_scan`：扫描、转换及 CGYRO/TGLF 对比绘图。
- `OMFITtemplates`：GitHub 模板版本管理。

打开 CGYRO/TGLF 默认 GUI，点击 **Templates / GitHub** 即可进入管理器；也可以打开 `OMFITtemplates → GUIS → main`。管理器已预填本仓库地址。

如果只想把管理器加入已有计算工程，在该工程的 OMFIT 命令框执行：

```python
OMFIT['OMFITtemplates'] = OMFITmodule('/absolute/path/CGYRO_TGLF_scan/OMFITtemplates/OMFITsave.txt')
OMFIT['OMFITtemplates']['GUIS']['main'].run()
```

这两条命令只添加管理模块，不替换已有 CGYRO/TGLF 数据。添加后保存自己的工程即可长期使用。

## GitHub 模板管理

在实际运行 OMFIT 的 Linux 环境安装 [GitHub CLI](https://cli.github.com/)，执行 `gh auth login --hostname github.com --web`，或使用界面的登录按钮。私有库读取和发布分别需要 Contents 读、写权限；公开库可匿名读取，但可能遇到 API 限流。

1. 连接仓库，选择开发者和版本，点击“拉取并使用”。
2. 保存当前 OMFIT 会话为 ZIP，选择保留当前案例与结果，或使用模板示例。
3. 预览变更后生成新工程。打开前可备份当前会话；原 ZIP 始终保留。
4. 开发者准备模板包，核对文件清单、仓库与账号，再发布不可覆盖的新版本。

当前初始模板包含 `CGYRO_TGLF_scan` 和 `OMFITtemplates` 两个模块，不带结果或计算案例。旧工程如缺管理模块，可先按上面的两条命令添加，再另存为 ZIP 并进行版本更新。

Git 仓库保存可审查的源码；OMFIT 管理器通过 Release 附件分发模板。界面不会自动把附件内源码提交到 Git，源码改动仍通过正常的 commit / push 流程同步。

## 从源码生成工程 ZIP

```sh
python3 tools/build_project.py
```

输出到 `dist/CGYRO_TGLF_scan_code_only_2026.09.12.zip`。构建仅收录 `OMFITsave.txt` 引用的代码、设置与输入模板，校验所有引用，并拒绝混入非空计算数据分支。

独立模板界面可执行 `sh OMFITtemplates/start_manager.sh`；OMFIT 内使用时复用 OMFIT 自己的 Python 和 Tk。

## 验证和范围

管理器需要 Python 3.9+ 与 Tk；比较绘图还需要 OMFIT 的 NumPy / Matplotlib 等依赖。详见 [验证记录](VALIDATION.md) 和 [管理器完整说明](OMFITtemplates/help.rst)。

此版本未运行求解器，也未在完整 OMFIT 安装中完成整机验收。随附模块原有的作者、许可与依赖说明保留；本仓库不包含 OMFIT 框架本体。
