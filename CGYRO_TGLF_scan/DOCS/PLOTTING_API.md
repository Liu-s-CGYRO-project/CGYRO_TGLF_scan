# 绘图与界面扩展接口

从工程 1.20.0 起，数据读取、样式和 GUI 控件分成独立文件。添加绘图时优先复用这些接口。

| 文件 | 职责 |
| --- | --- |
| `LIB/OMFITlib_plot_sources.py` | 把 TGLF 运行记录转换为只读绘图视图，兼容旧扫描缓存；统一谱数组维度 |
| `LIB/OMFITlib_plot_style.py` | 全局外观设置、配色和绘图上下文 |
| `LIB/OMFITlib_plot_style_ui.py` | 全局样式编辑页 |
| `LIB/OMFITlib_tglf_records.py` | 运行记录摘要，供扫描页和对比页共同使用 |
| `LIB/OMFITlib_gui_api.py` | 本工程的帮助窗口、默认值按钮和复选框适配 |
| `LIB/OMFITlib_result_cleanup.py` | 明确列出的结果清理范围和运行状态检查 |

## 添加一个绘图入口

在模块的 `PLOTS` 中保存脚本：

```python
from OMFITlib_plot_style import plot_context

with plot_context(root):
    fig, ax = subplots()
    ax.plot(x, y, label='案例 A')
    ax.set_xlabel('x')
    ax.set_ylabel('y')
    ax.legend()
```

`plot_context` 根据 `_OMFITparent` 找到所属工程，从唯一的 `SETTINGS/PLOT_STYLE` 读取样式。仅在本次绘图期间设置 matplotlib 默认值，并整理本次新建的图。离开上下文时恢复原来的 rcParams。不会改写数据、单位、坐标范围、扫描设置或其他工程的样式。

主要工程入口已接入：CGYRO 结果浏览、四种模型对比、TGLF 运行记录谱图及通量趋势、多剖面 TGLF、Transfer_tool 的绘图入口和 TGYRO 绘图页。数据树中直接执行的历史脚本可用同样的上下文接入；它们保留原生实现。

曲线优先使用默认颜色循环和线宽，避免在新脚本里写死 `color`、`linewidth` 和 `fontsize`。用 `ax.axhline` / `ax.axvline` 表示参考线；需要保留特殊宽度的数据线可以设置 `gid='reference'`。原生图中有物理含义的特殊颜色、热图色标及参考线不强制重染。默认字号、线宽、标记、轴线、画布尺寸和 DPI 由全局页控制。

`apply_figure_style(figure, validated(root))` 可用于不经过 pyplot 注册的自建 Figure。更改全局样式后重新绘图；已打开的图不会被其他窗口的设置修改。

## 读取 TGLF 结果

`run_choices(project_root)` 返回“摘要 → 原始记录编号”的有序字典。只包含至少一个完成点的记录；部分成功记录只提供成功点。旧版缓存以 `legacy:1D` / `legacy:2D` 明确标识，不覆盖或混入新运行。

`tglf_results(project_root, state, target='Spectra')` 返回：

```text
半径或输入标识 → 参数名 → 实际扫描值 → ResultView
二维：半径 → 参数1+参数2 → 实际值1 → 实际值2 → ResultView
```

`state['result_source']` 保存选中的记录编号；`source_dimension` 自动给出维度。无参数扫描使用 `原值/0`，UQ 使用样本编号。`ResultView` 是只读、延迟读取的映射，提供原始结果及本次实际 `input.tglf`，不会向工程树写入额外副本。

`spectrum_arrays(spectrum)` 返回 `ky, omega, gamma`，后两者为“模态 × ky”；识别 xarray 的 `mode_num` / `ky` 维度，也支持旧版 `freq(1)`、`gamma(1)` 字段，形状不一致时报错。

同一张图会多次取曲线时使用 `context_results(project_root, ctx, target)`；视图缓存仅存在于此次绘图上下文，不跨运行、不跨刷新保存。

## 添加控件和登记文件

GUI 开头使用 `from OMFITlib_gui_api import adapt` 和 `OMFITx = adapt(OMFITx)`。原生 `help=` 原文会放入可缩放、可滚动的说明窗口。`D` / `d` 按钮显示为“重置”，保留原回调；鼠标停留提示分别为模块默认值 / 模块载入时的值。提示仅绑定此按钮，离开、点击或销毁时关闭。取消参数覆盖的按钮应命名“沿用输入”，不要混为默认值重置。

新入口和新库同时登记到工程根 `OMFITsave.txt` 与模块 `CGYRO_TGLF_scan/OMFITsave.txt`。OMFIT 按当前模块查找 `LIB`；子模块若使用共用库，也要登记对应的 LIB 别名及其传递依赖。回调所需的 OMFITlib 导入放在文件顶层，避免 GUI 返回后才导入导致 `ModuleNotFoundError`。

结果清理仅处理 `OMFITlib_result_cleanup.BRANCHES` 与明确的运行记录。新后端应在该文件补充结果分支和活动状态检查。不要用遍历全树或按目录名猜测的方式删除数据；不要把 `INPUTS`、生成的半径输入、剖面或共享环境设置列入清理范围。

## OMFIT 字典兼容约定

OMFIT 的 `SortedDict` 与 Python `dict` 的可选参数不同。读工程、设置和运行记录时使用 `node.get(key, None)`，创建缺省项时使用 `node.setdefault(key, default)`，批量写入时使用 `node.update(dict(...))`。不要省略 `get` 的默认值，也不要向树的 `update` 直接传关键字参数。

从 1.20.1 起，`tools/build_project.py` 在打包前调用 `tools/check_omfit_api.py`，静态检查这三种调用。它不执行 GUI、绘图或求解器。Tk 的 `Listbox.get(index)` 和 `os.environ.get(key)` 按各自的原生接口保留。
