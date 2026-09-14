OMFIT GitHub 模板管理器 1.2.5
============================

面向带桌面的 Linux，在 OMFIT 内浏览、拉取和发布不同开发者的模板版本。

1.2.2 修复 Python 3.9 的字体初始化兼容问题，保留对当前 OMFIT Tk 窗口的显式绑定。
1.2.3 支持更新已有模块并添加缺少的顶层模块，预览分别列出两类操作。
1.2.4 在生成新工程时自动写入正确的 ZIP 入口顺序，兼容原生 OMFIT 加载器。
1.2.5 修复 OMFIT 拦截 StringVar/BooleanVar 后的初始化参数冲突；全部变量使用显式 master、value 参数。
默认仓库为 Liu-s-CGYRO-project/CGYRO_TGLF_scan，可在界面更改。
通过 GitHub Releases 分发版本；默认只包含代码和设置，案例、结果可选择作为示例。

在 OMFIT 中使用
---------------

将 OMFITtemplates 放入 OMFIT 的 modules 目录，加载模块并打开默认 GUI。
也可在 OMFIT 命令框执行，再打开模块默认 GUI：

::

    OMFIT['OMFITtemplates'] = OMFITmodule('/absolute/path/OMFITtemplates/OMFITsave.txt')

窗口复用 OMFIT 的 Tk 会话，关闭窗口不会退出 OMFIT。
“保存当前 OMFIT 会话”调用 OMFIT.saveas，完整保存内存中的当前工程，并将
当前工程和发布来源指向新 ZIP。这是另存为操作，OMFIT 当前项目名称也随之改变。

GitHub 连接与首次建库
--------------------

1. 在“GitHub 版本”填写 所有者/仓库 或 https://github.com/所有者/仓库.git。
2. 安装 GitHub CLI（gh）。点击“登录 GitHub”会在 Linux 桌面终端打开浏览器登录流程。
   完成后返回并点击“连接仓库”。也可提前执行：

   ::

       gh auth login --hostname github.com --web

3. 公开仓库可匿名浏览和拉取。私有仓库需要 Contents 读取权限；发布及初始化需要
   Contents 写权限，组织可能要求 SSO。连接栏显示仓库可见性和实际登录账号。
4. 空仓库可在“设置与记录”中初始化。界面先显示目标和完整 README，确认后
   创建 README.md 与首次提交。已有提交的仓库不会被初始化。

凭据按 GH_TOKEN、GITHUB_TOKEN、gh 当前 github.com 账号的顺序读取；环境变量
必须在启动 OMFIT 时已存在。凭据不保存在本工具配置或日志中。
匿名限流时可以登录后重试。当前支持 github.com，不包含自建 Enterprise 主机。

拉取、更新和切换
----------------

1. 选择开发者和版本，点击“拉取并使用”。下载与模板载荷均通过 SHA-256 校验。
   浏览、下载、校验和预览不执行模板代码，不反序列化计算结果。
2. 在更新页保存当前 OMFIT 会话，或选择完整工程 ZIP。未保存的修改不在磁盘
   工程中，需先保存才能参与本次更新。
3. 默认保留案例与结果，也可用模板中的全部示例替换所选模块的数据；不含示例的
   模板不能选择示例切换。
4. 设置默认保留现有值并补全新增项，也可全部采用模板设置。MODULE 和 DEPENDENCIES
   随模板更新。JSON 设置与动态表达式同步处理。使用示例而保留当前设置时，可能
   需要重新选择绘图案例。
5. 预览新增、更新和删除；完整清单可导出 JSON。代码分支整体更新，自己增加在
   受管理代码分支中的脚本也可能被删除，因此应检查清单并发布自己的版本。
6. “生成新工程”写入新的 ZIP，原 ZIP 完整保留。
7. “备份并在 OMFIT 打开”先将当前内存会话另存到目标旁的
   __before_open_时间_随机值.zip，再调用 OMFIT.load。备份失败会停止切换，
   打开失败会尝试从备份恢复。此步骤按 OMFIT 接口在主线程运行。

新工程包含更新记录，可在“设置与记录”读取。升级、降级和跨开发者切换使用同一流程。
当前工程、目标工程和会话备份都需要磁盘空间；大型结果仍保留在本地完整工程中。

重新生成以前打不开的 ZIP
------------------------

旧管理器生成的 ZIP 可能使 OMFIT 到 Cases、GUIS 等子目录寻找 OMFITsave.txt。
请使用 1.2.4 管理器，将该 ZIP 作为“当前工程”，选择所需模板，保留当前案例、
结果和设置，预览后点击“生成新工程”，另存为新的 ZIP 即可。
管理器能读取旧 ZIP 的实际根入口；生成的新 ZIP 自动将 OMFITsave.txt 放在首位。
不需要单独修复操作，也无需重新计算。原 ZIP 保留，输出需要一份完整工程的磁盘空间。

发布模板
--------

1. 保存完整工程 ZIP，读取模块范围，填写显示名、模板 ID、作者 ID、版本和说明。
   按顶层模块选择；作者 ID + 模板 ID + 版本号不可重复。
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
实际发布账号与自行填写的作者 ID 分别显示。Git 标签固定仓库当时的提交；
模板版本内容以附件为准，不会自动把附件内源码提交到 Git。
源码分支和合并沿用团队的 Git 流程。Releases 是当前界面采用的分发方式。

已准备的本地包可在列表选择后点击“上传本地包”。网络恢复或空仓库初始化后
可从这里继续，不需重做同一版本。选择本地发布时不连接 GitHub。

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
