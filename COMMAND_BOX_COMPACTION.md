# 在 OMFIT Command box 整理当前工程

`KeyError: 'OMFITlib_cgyro_storage'` 表示当前数据树中未登记归档库；管理器的版本与当前工程的代码版本不是一回事。也可能父模块已经更新、子模块 LIB 仍不完整。不要只下载这一个库再修改结果结构：绘图、表格和续算需要同版读取代码。

`tools/compact_commandbox.py` 是可下载后直接在 Command box 执行的完整入口。它先检查父、子模块所需 LIB；缺失时从已发布的工程 1.22.38 下载两个固定代码包，核对长度、SHA-256、ZIP 路径和 CRC，使用管理器现有的事务更新接口安装完整项目代码，然后整理当前工程。

更新使用 `data_policy='keep'` / `settings_policy='keep'`，保留原输入、设置、案例、结果和自定义代码。独立旧模块与顶层 OUTPUTScan 由现有迁移引擎识别。原管理器不由这个工具更新，也不执行 `OMFIT.load()` 或替换整个用户项目；新代码通过明确的原生 `_relLoc` 在自己的 LIB 上下文导入。

整理结果使用 RESULT_STORE/<摘要>，提交 ZIP 使用 RESULT_STORE/__FILES__/<摘要>，其余位置保存普通树引用。旧版 LEGACY_UNCLASSIFIED 与 OUTPUTS 同样检查；验证一致的展开普通文件从保存树中移除，内容不同的文件及编辑型输入继续保留。检查点按检测结果择一保留，未知情况保守保留，具体检查点规则见 [归档设计](RESULT_STORAGE_DESIGN.md)。当前检查点通过检测后，归档副本省略 .old；只保留 .old 时不能借用当前时间标签续算。

工具不会保存或覆盖现有工程 ZIP，也不会删除服务器 / 来源目录。完成后使用 OMFIT 的“另存为”生成新 ZIP，体积才会缩小。来源 ZIP 继续保留。哈希与复制需要时间和新结果副本的临时磁盘空间。

更新完代码后会清除本次代码更新的撤销入口，避免在结果已改为索引后撤回读取代码；归档整理失败时保留已安装的新读取代码和原始文件，不把新索引交给旧版读取器。检查报告在 `CGYRO_scan/RESULT_STORAGE/checkpoints`。

工具使用固定包摘要，不自动降级具备全部所需入口的新工程。GUI 刷新复用管理器现有 OMFITSession 接口。仅完成 Python 3.9 AST、符号、原生 API 及包内容校验，没有在用户服务器运行更新、GUI、绘图或续算。

从工程 1.22.38 的 GitHub Release 下载 `omfit-cgyro-compact.py`（工具 1.1.0），校验其发布摘要，然后执行：

```python
exec(compile(downloaded_script, 'omfit-cgyro-compact.py', 'exec'), {'OMFIT': OMFIT})
```

脚本默认使用现有 HTTP 代理；直连时传入 `{'OMFIT': OMFIT, 'COMPACT_PROXY': ''}`。已具备必要 LIB 的工程直接执行整理，不下载代码包。
