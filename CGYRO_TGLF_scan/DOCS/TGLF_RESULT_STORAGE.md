# TGLF 原生结果保存

TGLF 使用原生扫描结构；CGYRO 的结果仍保存在 `CGYRO_scan/RUN_DB`。

| TGLF 方式 | 通量 | 完整结果 / 谱 |
| --- | --- | --- |
| 一维 | `scanResults` | `scanResults_spectra` |
| 二维 | `scanResults2D` | `scanResults2D_spectra` |
| 三维 | `scanResults3D` | `scanResults3D_spectra` |
| 不确定度 | `UQResults` | `UQResults_spectra` |
| 径向原值计算 | `Experimental_fluxes` | `Experimental_spectra` |
| 单文件原值计算 | — | `TGLF/FILES` |

由完整剖面生成的径向扫描保存在 `TGLF_scan` 下，先按半径索引。当前单文件扫描保存在 `TGLF_scan/TGLF` 下，不额外套半径。二维沿用原生的 `参数2+参数1 / 值2 / 值1`；三维按同样规则扩展为 `参数3+参数2+参数1 / 值3 / 值2 / 值1`。三维不写入二维分支。

Transfer_tool 的各个输入、局部互转文件保存在 `TGLF_scan/sourceResults/<输入键>` 内，内部仍使用上表的原生结构。不同输入即使半径相同也不会串用结果。原生的 `TGLF_scan/TGYRO/RUN_DB` 是 TGYRO 输入生成及计算记录，不属于 TGLF 扫描结果库。

工作台的 `_workbench_runs` 保存本次状态、扫描坐标、通量摘要及结果路径；成功点的完整输入和输出仅由原生分支持有。`_workbench_index` 记录该路径当前属于哪个提交，防止旧运行记录显示成后一次计算。重置、原生重算和替换输入会失效相应引用。直接选择原生结果不依赖工作台运行记录。

新点先检查通量是否完整、有限，再更新对应通量和谱分支。下载失败的点保留诊断及原有可用结果；已成功的其他点照常保存。未选择的参数坐标和其他维度保留。

“结果与记录”可查看表格及单点谱。对比绘图提供原生一维、二维和三维来源；三维使用标明第三轴取值的二维分片，不丢弃第三轴。切换页面和结果筛选不解析结果数组，绘图只读取选择的点。

更新时保留工程数据与设置。模板管理器不再把 TGLF 原生结果迁入 `RUN_DB`。旧版本已经写入 `TGLF_scan/RUN_DB` 的结果继续通过兼容入口读取，保留原文件和选择，不在打开页面时全库搬迁或复制；新提交按上表保存。更新后关闭并重开工作台和绘图窗口即可。
