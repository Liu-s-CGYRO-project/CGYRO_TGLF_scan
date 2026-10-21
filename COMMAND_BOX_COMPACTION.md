# 在 OMFIT Command Box 整理当前工程

先更新模板管理器到 1.10.23、工程到 1.24.1，关闭旧结果窗口。在 Command Box 执行下面完整的一行：

```python
OMFIT['CGYRO_TGLF_scan']['SCRIPTS']['compact_cgyro_storage'].run()
```

它把旧的 `Jet [partial ...]`、`Jet [recovered ...]` 和 `Jet [legacy revision ...]` 合并回 `Jet`，实际目录变为 `RUN_DB/Jet/nr=1_rho=0.33/H`（或 D、T），各离子下保存扫描结果。状态只记在内部。旧结果和冻结输入都留在 `CGYRO_scan/RUN_DB`，按文件名称、长度和 SHA-256 去重，核对后恢复旧扫描索引。`N_THETA`、`N_ENERGY` 及多轴扫描独立保存；相同参数组按全部坐标和 ky 合并。不同 ky 追加，完全相同坐标的新结果更新对应点。

可核实的未分类记录按其原 runid、case_id、scan_axes 和 result_path 恢复。无法核实或缺少数据的记录保留在 `RUN_DB/__UNCLASSIFIED__`，不会根据当前界面设置猜测其身份。整理报告在 `RUN_DB/__STORAGE__/recovery`。这不是重新提交或补算操作。

整理完成后使用 OMFIT“另存为”保存新的工程 ZIP，保存后体积才会变化。原 ZIP、来源目录和服务器文件不删除。哈希与复制可能需要数分钟和临时磁盘空间。关闭旧窗口后重新打开结果浏览，确保回调使用新版代码。

如果旧工程缺少脚本或出现 `KeyError: OMFITlib_cgyro_storage`，从 1.24.1 Release 下载 `omfit-cgyro-compact.py`，在 Command Box 执行文件内容。工具 1.3.1 会检查父、子模块完整依赖和读取接口；需要时下载固定版本代码包，核对大小、SHA-256 和 ZIP CRC，使用管理器的事务接口更新代码，再整理数据。输入和设置采用 keep 策略；独立旧模块由迁移器识别。工具不调用 OMFIT.load()。

完整文件可用单行命令执行（路径改为下载位置）：

```python
exec(compile(open('/absolute/path/omfit-cgyro-compact.py', 'rb').read(), 'omfit-cgyro-compact.py', 'exec'), {'OMFIT': OMFIT})
```

下载工具默认沿用现有代理；直连可在执行字典中加入 `'COMPACT_PROXY': ''`。结果格式更新后不会保留仅撤销读取代码的入口，以免新索引交给旧读取器。

检查点规则及删除 .old 的实际代价见 [归档设计](RESULT_STORAGE_DESIGN.md)。本版完成隔离文件与元数据回归检查，未在用户的 OMFIT 会话执行整理、保存重开或求解器续算。

## /tmp 100 GiB 限制

每批运行开始准备输入时，仅检查一次已有临时占用是否不超过 100 GiB；H/D/T 后续案例不重复遍历。标准 `/tmp/<user>/OMFIT/...` 按 `/tmp/<user>` 汇总会话。运行中的临时峰值允许超过 100 GiB，不把另有的 100 GiB 余量设成新硬上限。每次准备、打包、复制、下载及归档仍检查目标文件系统的真实剩余空间。手动收集和整理不因已超过启动阈值而拒绝执行；空间不足时停止新增复制，保留 RUN_DB、原 ZIP 和远端身份。不持久化“已经检查”的开关；每次新的运行或续算重新执行启动检查。

输入打包后核对 ZIP 成员及 SHA-256，只清理本轮 `runs/<UUID>/staging/pNNNNNN` 展开目录。显式整理也会检查已保存运行的这类目录。含软链接、校验不一致、仍被结果读取器引用的目录保留并报告；不按日期扫描删除整个 /tmp，也不清理其他项目或 OMFIT 的物理所有者。关闭或另存工程后，框架自身目录的回收仍由 OMFIT 管理。
