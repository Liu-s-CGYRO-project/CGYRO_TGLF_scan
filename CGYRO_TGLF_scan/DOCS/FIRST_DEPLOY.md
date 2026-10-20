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
python3 omfit-deploy.py old.zip --template tdxy-liu__cgyro-tglf__1.22.22.omfittpl.zip
```

首次下载脚本的 curl 使用上例显式代理。脚本内部默认使用相同的 HTTP 代理，可选 --network system 读取环境代理，或 --network direct 直连；--proxy URL 可另设 HTTP / HTTPS 代理。

发布的脚本内固定配套的版本、包名、大小和 SHA-256，直接从 GitHub Release 附件下载并验证，无需 GitHub API 查询、gh 登录、pip 或 Tk。下载失败会重试三次。文件和部署报告确认成功后，再由用户在 OMFIT 打开新工程；脚本不启动 GUI、求解器或服务器作业。

## 维护与校验

源码入口为 tools/deploy_project.py。tools/build_deployer.py 将两个已审查代码包的版本、大小和摘要嵌入脚本，输出独立的 omfit-deploy.py。每次工程发布都应把这份脚本和两个代码包一同附加到 Release，并把脚本纳入 SHA256SUMS，才能继续使用稳定的 latest/download 链接。

本次仅做 Python 3.9 AST / 符号、归档引擎接口、源码与安装包、CRC / SHA-256 和发布附件校验；按现有约定未执行迁移、安装、测试、GUI 或服务器任务，尚未用实际旧工程验证迁移结果。
