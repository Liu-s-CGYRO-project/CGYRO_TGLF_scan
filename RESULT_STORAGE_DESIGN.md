# RUN_DB 单一结果存储设计（1.24.6）

## 持久化布局

所有 CGYRO 结果、部分输出、重启文件和冻结提交 ZIP 仅归 `CGYRO_scan/RUN_DB` 所有。绘图不得从顶层 Cases、OUTPUTScan、OUTPUTS、RESULT_STORE、RUN_INDEX 或 RUN_HISTORY 回退读取。TGLF 和剖面转换的输入输出不属于这次 CGYRO 归档格式变更。

```text
RUN_DB/
  Jet/
    nr=1_rho=0.33/
      N_THETA | N_ENERGY | N_ENERGY__N_XI | ...  # 普通原物种参数扫描
      __SCANS__/<scan>/{info,tasks}
      BASE/KY_ONLY/                    # 原始参数固定的基准结果，存在才创建
      H | D | T/
        N_THETA | N_ENERGY | N_ENERGY__N_XI | ...
        __SCANS__/<scan>/{info,tasks}
  __STORE__/<sha256>                 # 唯一原生 OMFITcgyro 所有者
           __FILES__/<sha256>        # 唯一冻结输入 ZIP 所有者
  __RUNS__/<token>/{manifest,cases,inputs}
  __UNCLASSIFIED__/...               # 未核实旧结果
  __LEGACY__/...                     # 未适配旧结构、非线性输出
  __STORAGE__/{bytes,file_bytes,checkpoints,recovery}
```

外部 RUN_MANIFEST、RUN_HISTORY、RUN_BATCH 是作业元数据。正式提交前冻结点表、输入摘要、目录及身份。下载替换一个点之前保留其原 ZIP 引用；取消、下载失败或 Abort 后输入和已取得部分输出仍可从 __RUNS__ 找回。完整归档后移除冗余运行点/输入索引，保留来源 manifest。

## 逐点合并

有序扫描轴及联动参数定义扫描组；完整参数路径与带符号 ky 定义点身份。新增 ky 或参数坐标追加，只有同坐标点更新。`8`、`8.00000` 等数值拼写不会拆成两个谱。各轴取值并集只用于选择器，不构造虚假的笛卡尔积；实际数据始终由 tasks 的完整坐标决定。

不同运行的 p000001 不是同一个点。新运行保留自己的点号，冲突的保留点分配独立归档点号，记录 source_point_id 及原 run_token。新续算使用选中归档点的原输入和检查点，在新运行目录中执行。旧窗口的过期 token 不会凭短名匹配别的运行。

归档先在树外合并，核对其他扫描及同扫描未重算坐标仍存在，才安装结果并清理不可达所有者。完整和部分输出统一显示在原结果名下，状态只进入元数据；较短或未知进度的部分输出不替换已有完整点；手动“重新收集未归档结果”没有补算权限。

## 迁移与去重

`OMFITlib_cgyro_db.ensure_layout` 将旧已知分支移入 RUN_DB，带事务回滚，不删除不确定来源。`compact_storage` 核对名称、长度与完整 SHA-256 后生成唯一所有者及普通索引。原生延迟元数据必须先加载才能遍历引用，原生文件读取器保持延迟；未打开的扫描也必须保留可达性。映射、列表、元组均纳入引用检查。

`recover_archives` 验证原 runid、case_id、轴、每一点路径及输出引用；可核实后再删除未分类来源。partial、recovered、legacy revision 后缀归回原结果名，再按半径 / 离子合并完整坐标。同坐标优先采用有明确发布时间的新记录；没有可靠时间顺序时比较实际末时刻并保护完整结果，不生成可见修订目录。无法验证的内容留在 __UNCLASSIFIED__。`prune_storage` 先检查全部引用再移除不可达所有者的树条目，不删除磁盘源文件。

`store_result`、`resolve_result`、`run_cases`、`freeze_run_inputs` 是写入、读取、运行点和冻结输入接口。`grouped_case_path(case_id, info)` 按扫描元数据确定实际路径，原物种普通扫描为半径，固定参数基准为半径/BASE，同位素扫描为半径/H、D、T。`install_case` 在树外分配普通扫描与基准，再一次安装半径节点，保留其他离子分支。

`case_sources` 独立枚举迁移来源；`catalog_runs` 为比较接口提供不保存的扁平逻辑视图，只合并元数据和现有结果索引，不能写回保存树。原物种逻辑 case_id 仍含 `ion=BASE`，但目录 BASE 仅表示基准；`case_destination` 必须使用当前扫描 info 解析物理位置。旧 BASE 与新直接扫描均兼容，冲突来源先整理后读取。停止作业的续算按 __RUNS__ 中原点表取源；合并时预留未开始的原点号，防止其他结果占用。普通元数据映射可用完整路径作为键，不强制转换成禁止斜杠的 OMFITtree。

旧工程推荐 [Command Box 脚本](COMMAND_BOX_COMPACTION.md) 并另存。离线工具只读 ZIP 与字面 OMFITsave 行，不执行 pickle；不具备原生元数据读取能力时拒绝处理旧分散结果，要求先用应用内入口迁移。

## 检查点边界

[操作说明](CGYRO_TGLF_scan/DOCS/RESULT_STORAGE.md) 解释 .old 的选择及风险。当前文件通过结构与配套时间核对后，归档副本可省略 .old，但不保证未来不损坏或求解器一定读取成功。当前损坏而备份可辨时只保留备份；配套标签不明时不自动用于续算。未知格式保守保留。

原工程 ZIP、原运行目录和服务器文件均不删除。另存后的 ZIP 减少重复文件，不等于当前 OMFIT 工作目录已释放对应空间。哈希和复制需要额外临时空间。原生 GUI、保存重开及集群任务的验收与隔离回归检查分开记录。

## /tmp 100 GiB 限制

每批运行开始准备输入时，仅检查一次已有临时占用是否不超过 100 GiB；H/D/T 后续案例不重复遍历。标准 `/tmp/<user>/OMFIT/...` 按 `/tmp/<user>` 汇总会话。运行中的临时峰值允许超过 100 GiB，不把另有的 100 GiB 余量设成新硬上限。每次准备、打包、复制、下载及归档仍检查目标文件系统的真实剩余空间。手动收集和整理不因已超过启动阈值而拒绝执行；空间不足时停止新增复制，保留 RUN_DB、原 ZIP 和远端身份。不持久化“已经检查”的开关；每次新的运行或续算重新执行启动检查。

输入打包后核对 ZIP 成员及 SHA-256，只清理本轮 `runs/<UUID>/staging/pNNNNNN` 展开目录。显式整理也会检查已保存运行的这类目录。含软链接、校验不一致、仍被结果读取器引用的目录保留并报告；不按日期扫描删除整个 /tmp，也不清理其他项目或 OMFIT 的物理所有者。关闭或另存工程后，框架自身目录的回收仍由 OMFIT 管理。
