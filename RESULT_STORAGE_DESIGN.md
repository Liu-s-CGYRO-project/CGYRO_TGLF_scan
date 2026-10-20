# CGYRO 归档与检查点

在“项目概览 → 结果管理”点击“优化 CGYRO 归档（去重）”，完成后另存工程。新收集也自动整理。原 ZIP、服务器文件和临时运行目录不删除；磁盘空间要在另存后再检查。

每份结果只归 CGYRO_scan/RESULT_STORE 所有。Cases、RUN_HISTORY、OUTPUTScan、RUN_DB 和旧 RUN_INDEX 保存 __RESULT_REF__ 小索引。按实际保留文件的名称、长度、SHA-256 去重，不按点号或文件大小合并。部分扫描、独有历史、原输入 ZIP、场与时间数据保留。缺文件、内容变化、软链接或悬空索引会中止。

## 检查点只保留一份

1. 当前 bin.cgyro.restart 通过检查，并有与时间历史匹配的 out.cgyro.tag：归档副本只保留当前文件。
2. 当前文件缺失或检查失败、.old 通过格式与数据检查：副本只保留 bin.cgyro.restart.old，记录为备用文件。
3. 格式无法识别、元数据不足或两份都不可靠：保留现有文件并告警，不强行删到一份。

已核对 v3 文件头、端序、六个网格尺寸、速度空间排序、完整文件长度，以及全部载荷中的 NaN/Inf。当前时间标签还需匹配保存的时间序列。检测与复制使用摘要核对，检查过程不改文件；报告位于 RESULT_STORAGE/checkpoints。

这些检查不能证明物理收敛，也不能发现所有数值仍有限的位翻转。删除 .old 后，当前文件日后损坏时将失去上一检查点的回退机会；仍可从保留的原工程或服务器目录寻找备份。

.old 二进制中没有保存时间，不能借用当前 out.cgyro.tag。备用文件保留原名，一键续算会要求先找回匹配的历史标签；不会自动改名或假定恢复时刻。真实回退还需匹配输入、执行布局和输出历史，通常要重算两个检查点之间的进度。

工程不修改 RESTART_PRESERVATION_MODE；服务器计算期间仍由求解器管理检查点。代码读取索引用 resolve_result / result_view，临时视图不能写回保存树。

依据：[CGYRO 检查点源码](https://github.com/gafusion/gacode/blob/master/cgyro/src/cgyro_restart.F90)。本版只完成静态、文件和安装包校验，GUI 与求解器续算尚未实测。完整设计及离线工具见 GitHub 的 RESULT_STORAGE_DESIGN.md。

## 原生保存边界

结果池使用原生 OMFITcgyro；索引是普通 OMFITtree / str，不使用动态表达式、软链接或自定义类。重新打开时不因索引提前加载所有场历史。绘图、表格、导出和续算仅在读取时建立不保存的视图。覆盖旧扫描后，只从保存树中清理无引用池条目，不直接删除磁盘目录。

旧工程先准备所有新索引和独立物理副本，再事务替换分支。原生 deepcopy 可能与源对象共用目录，因此保留文件由新的原生对象拥有，并逐文件核对复制摘要；从不在来源目录 unlink .old。保留未发布 / 部分历史的独有数据，不能删除整个 RUN_HISTORY。

## 离线整理已有 ZIP

在仓库根目录执行，代码 ZIP 应与本工具属于同一发布：

```powershell
python -B -X utf8 tools/compact_cgyro_project.py OMFIT_updated.zip --output OMFIT_compact.zip --code-project CGYRO_TGLF_scan_code_only_1.22.31.zip --report compaction.json
```

只读取 ZIP、二进制和字面保存清单，不运行项目脚本、表达式或 pickle。普通输入 / 设置 / 自定义代码和其他文件逐字节保留，安装同版读取库；新 ZIP 的首个成员为 OMFITsave.txt。写完逐文件验证 SHA-256 与 CRC，确认原文件大小和修改时间未变后才将 .partial 改为最终名称。需要源工程加新副本的磁盘空间。工具处理已统一的 CGYRO_TGLF_scan/CGYRO_scan；独立旧模块先通过管理器迁入。

## 验证能力与限制

v3 的头部和载荷长度来自上游 MPI_COMPLEX16 格式；旧版 v2 或非标准整数 ABI 不凭猜测处理。当前 tag 与时间序列相符是必要条件，但二进制不含时刻，不能从它证明与 tag 的原子配对。检查是文件结构和有限值检查，尚未用求解器实际读取验证；未来 bit rot 或有限值的静默损坏也不在保证范围内。源目录仍由 OMFIT / 用户原有流程管理，本优化没有远程删除或在线修改求解器检查点的入口。
