Short Description
-----------------
在 OMFIT 或 Linux 桌面通过 GitHub 管理工程模板与管理器更新

Keywords
--------
OMFIT, GitHub, templates, versions, incremental updates

Long Description
----------------
面向带桌面的 Linux，在 OMFIT 内浏览、拉取和发布不同开发者的模板版本。

启动后自动连接上次仓库并检查管理器更新。检查结果显示在界面，安装由用户选择；
网络失败时保留手动重试和本地模板使用入口。选择本地或共享模板库后，下次仍使用该来源。

1.2.2 修复 Python 3.9 的字体初始化兼容问题，保留对当前 OMFIT Tk 窗口的显式绑定。
1.2.3 支持更新已有模块并添加缺少的顶层模块，预览分别列出两类操作。
1.2.4 在生成新工程时自动写入正确的 ZIP 入口顺序，兼容原生 OMFIT 加载器。
1.2.5 修复 OMFIT 拦截 StringVar/BooleanVar 后的初始化参数冲突；全部变量使用显式 master、value 参数。
1.3.0 新增 GitHub 代理设置、SSH 中继脚本环境读取、手动 HTTP 代理与 HTTPS 连接测试。
1.3.1 修复桌面 PATH 中没有 python3 时的脚本加载，并区分退出状态、启动失败与超时。
1.4.0 默认按实际发布时间排序，可切换版本号排序；修正旧日期版本与语义版本混排。
右上角“检查管理器更新”独立检查管理器稳定版，使用当前代理，提供经过 SHA-256 校验的 Linux／OMFIT 模块包。
管理器更新源固定为官方仓库，修改计算模板仓库不会改变软件更新源；检查与下载不会自动替换正在运行的工程。
1.5.0 移除 SSH 隧道入口，旧配置自动迁移到公共 HTTP 代理。登录时自动安装缺少的 gh。
1.6.0 修复大字体下文字遮挡，控件按实际文字尺寸布局；窗口标题使用不带版本号的英文。
发布页在未登录时整体禁用；完成授权后自动读取 GitHub 登录名作为只读作者 ID。
账号切换或凭据失效时清除旧发布计划；已下载模板的查看和使用不受影响。
1.7.0 新增文件级增量更新，复用本地未变文件，只下载有变化的文件并在界面内安装。
默认仓库为 Liu-s-CGYRO-project/CGYRO_TGLF_scan，可在界面更改。
通过 GitHub Releases 分发版本；默认只包含代码和设置，案例、结果可选择作为示例。

在 OMFIT 中使用
---------------

将 OMFITtemplates 放入 OMFIT 的 modules 目录，加载模块并打开默认 GUI。
也可在 OMFIT 命令框执行，再打开模块默认 GUI：

::

    OMFIT['OMFITtemplates'] = OMFITmodule('/absolute/path/OMFITtemplates/OMFITsave.txt')

窗口复用 OMFIT 的 Tk 会话，关闭窗口不会退出 OMFIT。
1.9.0 内置模式默认直接更新内存中的工程并刷新现有窗口；不生成工程 ZIP，不重载工程。
外部独立管理器仍然生成新工程 ZIP。两种模式按打开入口自动区分。
“保存当前 OMFIT 会话”调用 OMFIT.saveas，完整保存内存中的当前工程，并将
当前工程和发布来源指向新 ZIP。这是另存为操作，OMFIT 当前项目名称也随之改变。

GitHub 代理
-----------

默认“手动 HTTP 代理”使用 47.102.120.146:18889，用户名与密码留空。
还可选择“系统代理”或“不使用代理”，手动模式也支持其他 HTTP 代理和可选认证。
旧 SSH 模式自动迁移并清除旧用户名与脚本路径；已有手动、系统和直连配置保留。
点击“测试连接”检查 HTTPS；版本、下载、发布、更新与 gh 安装沿用当前代理。
密码只留在当前窗口，不写入偏好或工程；外部浏览器使用自身的网络设置。

命令行诊断（Python 3.9+）：

::

    python3 OMFITtemplates/launch.py github-probe
    python3 OMFITtemplates/launch.py github-probe --network manual --proxy-host 47.102.120.146 --proxy-port 18889
    python3 OMFITtemplates/launch.py github-check --network system --anonymous
    python3 OMFITtemplates/launch.py github-list --network direct --anonymous

GitHub 连接与首次建库
--------------------

1. 在“GitHub 版本”填写 所有者/仓库 或 https://github.com/所有者/仓库.git。
2. 点击“登录 GitHub”。已有 gh 时直接使用；缺少时自动通过当前代理下载官方 Linux
   稳定版，按机器架构选择安装包，核对大小和 SHA-256 后装入用户目录。
   默认位置为 ~/.local/share/omfit-template-manager/tools/bin/gh，支持 XDG_DATA_HOME。
   无需 sudo、pip 或配置 PATH，进度在窗口底部显示，可点击“取消操作”。
   安装完成后自动打开登录终端，按提示完成浏览器授权，管理器自动读取账号并启用发布页。
   登录和读取凭据共用这个 gh；公开版本的浏览下载不要求安装。

3. 公开仓库可匿名浏览和拉取。私有仓库需要 Contents 读取权限；发布及初始化需要
   Contents 写权限，组织可能要求 SSO。连接栏显示仓库可见性和实际登录账号。
4. 空仓库可在“设置与记录”中初始化。界面先显示目标和完整 README，确认后
   创建 README.md 与首次提交。已有提交的仓库不会被初始化。

凭据按 GH_TOKEN、GITHUB_TOKEN、gh 当前 github.com 账号的顺序读取；环境变量
必须在启动 OMFIT 时已存在。凭据不保存在本工具配置或日志中。
匿名限流时可以登录后重试。当前支持 github.com，不包含自建 Enterprise 主机。

拉取、更新和切换
----------------

1. 选择作者和版本，点击“拉取并使用”。连接和校验阶段显示活动进度；
   下载阶段显示真实百分比及已下载 / 总大小。下载与模板载荷均通过 SHA-256 校验。
   使用已缓存模板时显示缓存校验提示；可取消，失败或取消时进度动画停止。
2. 在 OMFIT 内打开时，“当前工程”指当前内存中的模块；无需先保存 ZIP。
   外部独立管理器继续选择已保存的工程 ZIP 和输出路径。
3. 默认保留当前案例与结果，也保留未保存的结果对象；可选择用模板示例替换
   所选模块的数据。不含示例的模板不能切换到示例结果。
4. 设置默认保留现有值和动态表达式并补全新增项；MODULE 和 DEPENDENCIES 随模板更新。
   也可选择使用模板设置。切换示例后可能需要重新选择绘图案例。
5. 预览新增、更新和删除，完整清单可导出 JSON。受管理代码分支中的自建脚本也可能
   被删除，应检查清单或先发布自己的版本。预览会构造独立的模板节点，不修改当前工程。
6. 内置模式点击“更新当前工程”：在主线程修改现有模块的代码和设置节点，保留模块根
   与所选结果对象，重新绑定原生 GUI 控制器并在原窗口重绘。不调用 OMFIT.load/saveas，
   不改变当前项目文件名。通过 OMFIT 正常保存工程即可将更新持久保存。
7. “撤销本次更新”恢复上一版代码和设置，保留期间新增的计算结果（保留结果策略）。
   后续代码或被更新设置发生修改时，撤销会停止以免覆盖新编辑。节点赋值或界面刷新
   失败会回退本次节点修改；在“设置与记录”可查看当前会话的更新记录。
8. 外部模式仍点击“生成新工程”，写入独立 ZIP，原 ZIP 保留；之后在 OMFIT 中打开。

升级、降级和跨作者切换使用相同流程。模板文件暂存在会话专用目录，为代码节点与撤销
提供文件支持；不会复制现有计算结果。关闭管理器窗口不影响已更新的工程节点。


发布模板
--------

1. 先登录 GitHub 以启用发布页。保存完整工程 ZIP，读取模块范围，填写显示名、模板 ID、版本和说明。
   作者 ID 自动读取当前 GitHub 登录名，不可编辑。按顶层模块选择；作者 ID + 模板 ID + 版本号不可重复。
2. 默认只打包代码、模板输入、帮助/许可和设置。代码分支包括 SCRIPTS、PLOTS、GUIS、LIB、
   TEMPLATES、WORKFLOWS、SOURCE、DOCS、TESTS，以及模块直属 Python 对象。
   其他分支和未被树引用的文件作为数据。MainSettings、命令历史和未选模块不进入模板。
3. “包含案例与结果”会打包所选模块的全部数据，应使用专门准备的小型示例工程。
   GitHub 单个附件必须小于 2 GiB。发布前可以查看完整文件清单，包括设置文件。
4. 点击“准备模板包”，先在本地生成并验证。界面显示目标仓库、公开/私有、登录账号、
   模板标识、范围和大小。检查清单后点击“发布到 GitHub”并确认目标。
5. 发布依次创建草稿、上传附件、检查哈希与大小，再公开该 Release。
   网络错误或取消可能留下草稿；管理器提示仓库地址，不自动重试远端写入。
   已有 Release、草稿或同名标签均不覆盖，先检查 GitHub 状态再决定后续操作。

附件名为 作者__模板ID__版本.omfittpl.zip，标签为 omfit/作者/模板ID/版本。
新建模板的作者 ID 使用验证过的 GitHub 登录名；导入既有模板包保留原作者信息。Git 标签固定仓库当时的提交；
模板版本内容以附件为准，不会自动把附件内源码提交到 Git。
源码分支和合并沿用团队的 Git 流程。Releases 是当前界面采用的分发方式。

已准备的本地包可在列表选择后点击“上传本地包”。网络恢复或空仓库初始化后
可从这里继续，不需重做同一版本。准备本地包也需先登录以读取作者 ID，打包过程不上传 GitHub。

本地库和辅助启动
----------------

默认库 ~/.local/share/omfit-template-manager/templates，配置
~/.config/omfit-template-manager/settings.json。支持 XDG_DATA_HOME 和 XDG_CONFIG_HOME。
旧版路径会继续读取。GitHub 缓存按仓库和附件 ID 隔离；离线时选择“本地模板库”。
共享目录可作额外来源；导入、导出使用 .omfittpl.zip 文件。
写入要求同目录硬链接，以保证原子提交且不覆盖。采用 Linux 大小写语义和权限元数据。

独立运行：``./start_manager.sh`` 或 ``python3 launch.py``，需要 Python 3.9+ 与该解释器的 Tk。
Tk 8.6 在 Wayland 桌面通过 XWayland 显示。``./start_manager.sh --check`` 检查显示环境。
OMFIT_TEMPLATE_PYTHON 可指定解释器。解压包中的 ``./install_desktop.sh`` 创建用户菜单入口，
无需 sudo；移动软件目录后重新安装。``./install_desktop.sh --uninstall`` 只删除菜单入口。
独立界面不能保存或打开另一个 OMFIT 进程的内存工程。

边界与参考
----------

支持自包含、未加密的完整 OMFIT 工程 ZIP。按名称更新已有模块，缺少的顶层模块按新增处理。
新增模块采用模板设置；保留数据时只创建模板提供的空数据容器，示例仍需明确选择。
同名的非模块节点、保留文件冲突和文件/目录冲突会停止更新，不自动重命名或覆盖。
原生模块导出包应先在 OMFIT 加载并保存为完整工程。保留结果时不自动删除旧子模块。
遇到外部引用、路径冲突或不兼容结构会停止。SHA-256 表示完整性，不代表作者认证或物理正确性。

GitHub Releases 与附件限制：https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases
GitHub API：https://docs.github.com/en/rest/releases/releases
GitHub 附件 API：https://docs.github.com/en/rest/releases/assets
GitHub CLI 安装：https://cli.github.com/
GitHub CLI 凭据：https://cli.github.com/manual/gh_auth_token
Linux 用户目录：https://specifications.freedesktop.org/basedir/latest/

管理器增量更新
--------------

点击右上角“检查管理器更新”，核对变更文件与下载量，再点击“安装增量更新并重新打开”。
公开更新无需登录 GitHub，使用当前代理；旧版本未提供增量时仍可下载完整安装包。
1.6.0 及更早版本需先手动安装一次 1.7.0，之后才能使用新的增量流程。

本地文件按 SHA-256 复用，不依赖连续的版本链。清单、压缩附件和解压文件逐层校验。
在独立的新目录中组装完整版本，校验完成后才启用；取消或失败保留当前版本。
OMFIT 内直接替换管理器模块并重新打开，原设置保留，其他模块和计算结果不动。
正常保存工程即可保留更新；新版界面打不开会恢复旧模块。

独立 Linux 版从原启动脚本自动进入已安装的新版本，原目录仍保留。
需要回退时，从原目录执行 bash start_manager.sh --no-update-redirect。

作者筛选与文字显示
------------------

版本页的“作者”下拉框默认显示全部作者。选择作者后可继续搜索关键词或切换排序；更换模板库后若原作者不存在，会恢复全部作者。
空列表提示分行排版并增加行距。Linux 中文回退字体用于实际布局度量，说明和日志也保留额外行间距。
