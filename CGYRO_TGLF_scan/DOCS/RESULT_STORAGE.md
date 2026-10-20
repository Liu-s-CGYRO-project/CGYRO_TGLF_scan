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
