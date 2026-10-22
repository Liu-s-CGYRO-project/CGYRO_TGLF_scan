# Command box 安装管理器与旧扫描迁移

## 安装和更新

在旧工程的 OMFIT Command box 中执行以下四行，使用默认 HTTP 代理访问 HTTPS Release，无需终端、gh、pip 或修改 OMFIT 本体：

```python
import urllib.request as u
p = u.build_opener(u.ProxyHandler({'https': 'http://47.102.120.146:18889'}))
b = p.open('https://github.com/Liu-s-CGYRO-project/CGYRO_TGLF_scan/releases/latest/download/omfit-manager-bootstrap.py', timeout=30).read(131072)
exec(compile(b, 'omfit-manager-bootstrap.py', 'exec'), {'OMFIT': OMFIT})
```

脚本固定管理器包名、大小和 SHA-256；包校验成功后只安装 OMFITtemplates，并打开管理器。下载失败重试三次，不替换当前计算工程，不自动启动计算。不需要的旧管理器窗口会在打开新版本前关闭；忙碌时先结束其操作。已有同版或更新管理器直接打开，避免降级。代理设置与模板缓存继续使用既有用户目录。脚本存放在 Release 附件中，HTTPS 下载的脚本是这条安装路径的信任入口。

选择最新工程版本，点击“拉取并使用 →”，在“更新 / 切换”页保持“保留当前案例 / 结果”和“保留当前设置”，点击“预览变更”，检查迁入与归类清单后点击“更新当前工程”。更新在当前会话生效，完成后正常保存即可；不需要打开另一份 ZIP。预览后的代码或索引发生变化会要求重新预览，事务失败回退原节点。迁移后数据或设置未继续变化时，可以撤销本次更新。

## 迁移报错包含非法斜杠键名时

若旧管理器报“Jet / nr=1 contains the / character”，先更新管理器到 1.10.19 或以上（也可重新执行上面的四行安装命令），再选工程 1.22.24 或以上重新预览、更新。只更换工程模板无法修复仍在运行的旧管理器。

待核对分支名中的 `%` 与 `/` 分别转义为 `%25` 与 `%2F`，同名目标自动增加编号，保留原结果对象。MIGRATION_LOG / unresolved 记录原路径、保留位置与无法归类的原因，无需手工改旧结果名称。键名检查在预览和应用前完成，不挂接结果对象；结果目录和文件路径仍按原值保留。键名修复不代表原先无法识别的物理身份已确定，这些分支继续保留在 LEGACY_UNCLASSIFIED 待核对。

## 旧模块自动识别

顶层独立的 CGYRO_scan、TGLF_scan、Transfer_tool 自动迁入 CGYRO_TGLF_scan 下。模块对象及原始结果对象直接迁移，数值数组不重新计算或深拷贝；代码更新，原输入、用户设置和运行历史保留。无关模块留在原位置，显式指向旧顶层模块的 OMFITexpression 改到新路径，不执行表达式来猜测其值。自定义普通 Python 字符串和动态拼接路径需自行核对。

已有总模块时更新其中的子模块。总模块与同名独立旧模块同时存在，会停止并列出冲突，避免把两套工程当作同一批结果。任意改名的模块或未支持的子模块同样需要先明确映射。旧 CGYRO 作业仍处于准备、提交、运行或待发布状态时，应用迁移会停止；先完成收集归档再操作。

## 旧扫描归档重新分类

工程 1.22.20 及更新模板支持以下扫描索引迁移；更早模板不应用新版索引。

| 原归档形式 | 新归类 |
| --- | --- |
| RUN_DB / 结果集 / nr=… / N_THETA_H、N_THETA_D、N_THETA_T | 结果集 / 半径与离子 / N_THETA；H/D/T 分开，界面先选半径再选离子 |
| 带 __run=… 后缀的独立案例；旧 __INFO__ / __TASKS__ | 从归档元数据识别半径和离子；不同扫描轴合并到独立 __SCANS__ 索引 |
| N_THETA 与 N_ENERGY；一至三维参数 / 取值 / lin / ky | 扫描参数组分别保留；重建点表并保留实际 ky 与参数取值 |
| 同一参数组多份旧版本或 __previous_… | 分开保存为 legacy revision 结果集，不凭 UUID 或目录顺序判断哪个可覆盖 |
| 只有 OUTPUTScan、没有 RUN_DB、点表或运行记录 | 从参数 / 取值 / lin / ky 树和对应结果目录的原 input.cgyro 核对；也识别直接 ky → 结果、单个原生结果。原始输入可证明身份时自动归类，完全无身份信息时单独列为“未标识旧结果” |
| TGLF 的 scanResults、scanResults_spectra、scanResults2D 及其谱 | 按一维 / 二维参数组建立 RUN_DB，保留多个半径；旧版谱与旧版通量有独立来源标识 |

只读取归档树结构、已有元数据及原结果附带的 input.cgyro 标量文本；不加载 CGYRO 数值数组来推测身份，也不使用当前 GUI 设置替历史结果补半径、离子、作业号或结果目录。旧记录只有 nr、没有 rho 时保留为 rho=unknown，界面按 nr 选择。裸 OUTPUTScan 无 rho 时，原输入含固定 RMIN 就明确显示 RMIN，不能把它冒充为原始 rho；质量扫描、混合氢同位素和无法判断的离子组成不强行贴 H/D/T 标签。扫描键和原输入坐标不一致时，完整原分支进入待核对区。

没有足够输入信息的裸结果仍保留原数值载荷，按参数和 ky 建立“未标识旧结果”供选择绘图，不伪造半径或离子。识别不了的树结构、缺失 ky 的单结果和有身份冲突的原分支保留在 LEGACY_UNCLASSIFIED；未识别的 TGLF 分支留在原位置。预览列出原因和路径，可以导出完整变更报告。原始输入的路径与 SHA-256 随任务行保存，应用前再次核对输入未改变。

没有 CGYRO_scan 模块、结果直接放在工程顶层 OUTPUTScan 的旧工程也可首次部署：管理器创建总模块与 CGYRO_scan，把结果迁入新归档。顶层旧 OUTPUTScan 在事务完成后移除，原始路径保存在报告；自定义脚本中直接访问顶层 OUTPUTScan 的路径需改用新归档。已有总模块和另一套独立旧模块同时存在的情况仍先停止，避免合并两套身份不明的工程。

CGYRO 和 TGLF 原有 RUN_HISTORY、Cases、运行清单及重启文件继续保留。只有能对应原 token 和目录的记录才具备续算来源；不会为仅有数组的旧结果伪造可续算作业。重新归类也无法恢复在旧版本中已经被覆盖、且不再存在于工程或服务器的结果。

CGYRO_TGLF_scan / MIGRATION_LOG 保存原模块、原归档路径、新路径、点数与待核对项，随工程保存。迁移索引不改变数值结果、物理输入、求解器或已完成任务的状态。

## 校验范围

本功能仅完成 Python 3.9 AST / 符号、OMFIT 原生 API、LIB 登记、事务与原生父节点机制的源码检查，以及安装包内容、CRC、SHA-256、大小和发布附件校验。按照维护约定未执行测试、实际迁移、GUI 或服务器任务，尚未在用户旧工程中验证；首次迁移请先正常保存原工程，便于独立回退。

以下保留已保存 ZIP 的终端方案。ZIP 脚本负责模块路径迁移和代码更新；需要按上述规则重新索引旧归档时，在 OMFIT 打开后再通过管理器预览 / 更新当前工程。

# 首次部署与旧工程迁移

先在 OMFIT 中把旧工程保存成自包含 ZIP。以下命令在运行 OMFIT 的 Linux 终端执行，使用 Python 3.9 或以上版本；可以直接使用 OMFIT conda 环境中的 Python。

```sh
curl -fL --retry 3 --proxy http://47.102.120.146:18889 https://github.com/Liu-s-CGYRO-project/CGYRO_TGLF_scan/releases/latest/download/omfit-deploy.py -o omfit-deploy.py
python3 omfit-deploy.py '/路径/旧工程.zip'
```

执行成功会打印 DEPLOYED 和新 ZIP 的完整路径。在 OMFIT 打开这个新 ZIP，然后打开 CGYRO_TGLF_scan → GUIS → main。后续可直接使用工程里的模板管理器更新。

## 自动识别的结构

已有 CGYRO_TGLF_scan 总模块时，更新其中的代码和默认结构。已有总模块与其他独立旧模块并存时，总模块优先，其他顶层模块保留原位置，不猜测两份案例该如何合并。

没有总模块、但存在以下标准顶层 OMFITmodule 时，自动调整工程树路径：

| 旧模块 | 新模块位置 |
| --- | --- |
| CGYRO_scan | CGYRO_TGLF_scan / CGYRO_scan |
| TGLF_scan | CGYRO_TGLF_scan / TGLF_scan |
| Transfer_tool | CGYRO_TGLF_scan / Transfer_tool |

只识别这些确切模块名。没有识别到标准模块、目标名被非模块节点占用、旧工程含模板未支持的子模块或文件引用冲突时，会给出原因并停止。其他无关顶层模块继续保留；任意改名的模块、独立 TGLF / TGYRO 根或自定义模块布局需先明确映射，不能凭名称相似自动合并。

独立模块在内存中调整树路径，数据文件从原 ZIP 流式复制一次到最终 ZIP；不额外写一份完整中间工程。输入、结果、运行历史和当前设置使用既有 keep 策略；补充新版本缺少的默认值，模块和依赖元数据使用新版。既有 TEMPLATES 分支属于代码分发范围，按新版更新；实际输入文件由数据树分类保留。

保存的 OMFITexpression 中，明确的 OMFIT['CGYRO_scan'] 等顶层模块访问会同步修改为新路径；root[...] 形式继续相对于其模块工作。表达式通过 AST 定位文字，只改路径，不执行表达式。普通用户字符串、动态拼接的代码和任意自定义跨模块 Python 脚本不自动重写，需要在迁移后检查自己的扩展。

## 输出和保留规则

默认在旧 ZIP 旁生成“旧文件名-deployed-版本.zip”。同名文件已存在时自动使用新的后缀；可通过 --output 指定一个尚不存在的 ZIP：

```sh
python3 omfit-deploy.py old.zip --output new.zip
```

原 ZIP 保留。新 ZIP 旁的 .deploy.json 记录版本、识别结构、模块映射、表达式路径变更、保留文件数、文件 / 树变更和空间估计。输出路径或报告路径已有文件时，不覆盖它。归档引擎检查源文件在处理期间是否改变，并核对保留文件的 ZIP 大小 / CRC、生成文件摘要及模板载荷。

迁移对象是磁盘上已保存的工程快照，不包括 OMFIT 会话尚未保存的修改。新工程包含原有计算结果，因此通常会大于 1 MB；小于 1 MB 的限制针对分发的代码安装包。处理大型结果工程需要为最终 ZIP 留出磁盘空间，原引擎会在写入前检查。

## 其他用法

只生成迁移报告，暂不创建新工程：

```sh
python3 omfit-deploy.py old.zip --dry-run
```

全新部署，不携带旧数据：

```sh
python3 omfit-deploy.py --new
```

离线迁移：把发布页的 omfit-deploy.py 与 tdxy-liu__cgyro-tglf__版本.omfittpl.zip 传到 Linux，然后执行：

```sh
python3 omfit-deploy.py old.zip --template tdxy-liu__cgyro-tglf__1.22.23.omfittpl.zip
```

首次下载脚本的 curl 使用上例显式代理。脚本内部默认使用相同的 HTTP 代理，可选 --network system 读取环境代理，或 --network direct 直连；--proxy URL 可另设 HTTP / HTTPS 代理。

发布的脚本内固定配套的版本、包名、大小和 SHA-256，直接从 GitHub Release 附件下载并验证，无需 GitHub API 查询、gh 登录、pip 或 Tk。下载失败会重试三次。文件和部署报告确认成功后，再由用户在 OMFIT 打开新工程；脚本不启动 GUI、求解器或服务器作业。

## 部署后检测服务器

打开工程总控的“运行与环境”，选好服务器与队列，点击“自动检测”。同一次连接检查安装权限、队列 CPU / 内存 / 时限、可见工具及登录会话软硬限制。合法资源保持；超出队列上限的 MPI × 线程数和时限修正到草稿，核对后点击“应用到整个工程”再运行。

检测不提交计算。队列信息读取失败时保留资源设置并显示未知；登录环境没有 MPI 命令不等于程序未安装，作业会在加载所选环境后核对启动器。内存只展示，账户配额和实时调度仍由服务器决定。批处理启动时重新读取实际上限，仅调整允许修改的软限制；v3 检查点与原网格校验通过后可更改 MPI / OpenMP 资源续算。

## 维护与校验

源码入口为 tools/deploy_project.py。tools/build_deployer.py 将两个已审查代码包的版本、大小和摘要嵌入脚本，输出独立的 omfit-deploy.py。每次工程发布都应把这份脚本和两个代码包一同附加到 Release，并把脚本纳入 SHA256SUMS，才能继续使用稳定的 latest/download 链接。

本次仅做 Python 3.9 AST / 符号、归档引擎接口、源码与安装包、CRC / SHA-256 和发布附件校验；按现有约定未执行迁移、安装、测试、GUI 或服务器任务，尚未用实际旧工程验证迁移结果。
