# 绘图与界面扩展接口

从工程 1.20.0 起，数据读取、样式和 GUI 控件分成独立文件。添加绘图时优先复用这些接口。

| 文件 | 职责 |
| --- | --- |
| `LIB/OMFITlib_plot_sources.py` | 把 TGLF 运行记录转换为只读绘图视图，兼容旧扫描缓存；统一谱数组维度 |
| `LIB/OMFITlib_plot_style.py` | 全局外观设置、配色和绘图上下文 |
| `LIB/OMFITlib_plot_window.py` | FigureNotebook 初始尺寸、工具栏空间与画布自适应；不修改 OMFIT 全局实现 |
| `LIB/OMFITlib_plot_fonts.py` | 英文字体文件加载、旧版兼容、公式字体及延迟绘制 / 导出上下文 |
| `LIB/OMFITlib_plot_labels.py` | 输出图英文词条、未知自定义标签映射及重绘 / 导出时的文字处理 |
| `LIB/OMFITlib_plot_font_assets.py` | 随包思源宋体与 Liberation Sans 的校验、缓存及进程内注册 |
| `LIB/OMFITlib_plot_style_ui.py` | 全局样式编辑页 |
| `LIB/OMFITlib_tglf_records.py` | 运行记录摘要，供扫描页和对比页共同使用 |
| `LIB/OMFITlib_gui_api.py` | 本工程的帮助窗口、默认值按钮和复选框适配 |
| `LIB/OMFITlib_gui_fonts.py` | 随包字体加载、窗口字体与表格行高；接入方法见 `DOCS/GUI_FONTS.md` |
| `LIB/OMFITlib_result_cleanup.py` | 明确列出的结果清理范围和运行状态检查 |

## 添加一个绘图入口

在模块的 `PLOTS` 中保存脚本：

```python
from OMFITlib_plot_style import plot_context

with plot_context(root):
    fig, ax = subplots()
    ax.plot(x, y, label='Case A')
    ax.set_xlabel('x')
    ax.set_ylabel('y')
    ax.legend()
```

`plot_context` 根据 `_OMFITparent` 找到所属工程，从唯一的 `SETTINGS/PLOT_STYLE` 读取样式。仅在本次绘图期间设置 matplotlib 默认值，并整理本次新建的图。离开上下文时恢复原来的 rcParams。不会改写数据、单位、坐标范围、扫描设置或其他工程的样式。

主要工程入口已接入：CGYRO 结果浏览、四种模型对比、TGLF 运行记录谱图及通量趋势、多剖面 TGLF、Transfer_tool 的绘图入口和 TGYRO 绘图页。数据树中直接执行的历史脚本可用同样的上下文接入；它们保留原生实现。

曲线优先使用默认颜色循环和线宽，避免在新脚本里写死 `color`、`linewidth` 和 `fontsize`。用 `ax.axhline` / `ax.axvline` 表示参考线；需要保留特殊宽度的数据线可以设置 `gid='reference'`。原生图中有物理含义的特殊颜色、热图色标及参考线不强制重染。默认字号、线宽、标记、轴线、画布尺寸和 DPI 由全局页控制。

`apply_figure_style(figure, validated(root))` 可用于不经过 pyplot 注册的自建 Figure。更改全局样式后重新绘图；已打开的图不会被其他窗口的设置修改。

FigureNotebook 的渲染器在最后一次尺寸和布局设置后调用 `fit_figure_window(fig)`（从 `OMFITlib_plot_window` 顶层导入）。对比图的 `apply_figure_layout` 已执行此步骤。窗口初始大小限制在屏幕内；Tk 先为原生工具栏分配空间，再将剩余区域交给画布。切换标签或增加新页不重置手动调整的窗口，原 Matplotlib 缩放、保存和 OMFIT 按钮回调继续使用。布局控制器只附着于当前 Tk Notebook，不进入工程数据树；非 Tk 画布不改变尺寸。新增消费模块需登记此库的 LIB 依赖。

桌面回归为 `python3 -m unittest discover -s tests -p test_plot_window.py -v`。用完整源代码中的原生 FigureNotebook 类复核布局可执行 `python3 tools/validate_plot_window.py /path/to/OMFIT-source/omfit --output /path/to/report`；后者保留原生类方法，OMFIT 会话和应用工具栏动作为适配器，不能代表整机联调。

输出图统一使用英文，默认 `Liberation Sans`，作为 Arial 的相近替代。首次使用下载或导入完整字体包，无需安装字体或填写路径；英文包含常规 / 斜体 / 粗体 / 粗斜体。既有思源宋体资源与完整 SIL OFL 1.1 许可保留在独立资源包，绘图不再需要登记中文字体，代码安装包保持小于 1 MB。来源、摘要及重建方法见 `DOCS/GUI_FONTS.md`、`DOCS/PLOT_FONTS_LICENSE.txt` 和 `tools/plot_fonts_sources.json`。

`font_family` / `font_file` 分别选择字体名称或文件，文件配置优先并自动读取字体名称。旧 `chinese_font_family` / `chinese_font_file` 保存在已有设置中但不再参与绘图。Matplotlib 3.6 才引入[同一文本内逐字形回退](https://matplotlib.org/stable/users/explain/fonts.html#font-fallback)，英文图无需这项能力，不再据此拒绝旧版本。尚无 `addfont` 的版本沿用原生字体列表登记接口，公式回退参数及逐文本公式字体接口按实际能力选用。字体诊断使用 ASCII 固定说明并保留实际文件路径，避免错误报告变成问号。

新增绘图应直接使用英文标题、坐标轴、图例和注释。共享入口还通过 `OMFITlib_plot_labels` 转换旧记录中的内置中文显示词条；后续添加词条集中修改 `ENGLISH_TERMS`。任意自定义中文不能可靠自动翻译，未收录片段使用图内可区分的 `Label N`，可将案例显示名预先填为英文以保留原命名；对应原文存于本图的 `figure._project_label_aliases`。这只处理输出文字，不改写数据树、案例编号、参数键、计算值或单位。普通 GUI 和数值表文案保留中文。文本对象在延迟重绘、布局测量和导出时继续执行相同转换，防止新刻度文字回到中文。

普通数学字符使用英文配置的正体、斜体及粗体；显式的等宽 / 花体命令保留其数学字体语义，未覆盖的数学符号使用 STIX 回退。每幅图在自身 `draw` / `savefig` 操作期间恢复保存的字体上下文，确保 Tk 延迟绘制和导出时仍使用相同字体。PDF / PS 设置字体嵌入，SVG 使用字形路径；实际嵌入格式由 Matplotlib 后端及字体格式决定，其他图及进程外的设置不受影响。

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

## 图例排序与案例短名

“按质量 H → D → T”先按同位素分组，同组自然排序，其他图例排在后面；明确 ion 标记优先，兼容旧独立 H / D / T 参数后缀。质量排序使用与跨面板颜色相同的曲线身份，误差图的参考项不改变本曲线顺序。

CGYRO 图例由 `cgyro_case_caption` 生成案例部分，例如 `H · N_THETA=32`。多个半径时补 rho，同半径同离子的不同输入补 nr。保留 CGYRO / TGLF 混合比较中的模型区分，去掉运行 UUID 和数值末尾多余的零；归档键仍用于实际数据查找和分组。自定义名称不猜测同位素。图内文字继续使用英文。

## CGYRO 扫描对比中的时间曲线

在“CGYRO 对比 → 绘图设置 → 绘图类型”选择“频率 / 增长率随时间”。沿用案例页选择的半径、原始 / H / D / T、扫描参数及取值；ky 列表留空使用全部已保存 ky，也可填入多个数值，按各扫描取值的实际网格匹配最近的 ky，重复目标只选择一次。每个实际 ky 独立分页，默认各案例分开；“合并所选半径”把所选案例叠加在同一 ky 页，便于比较 H / D / T。

每页并排绘制完整 ω(t) 和 γ(t)，分别保留各点自己的采样网格、终止时间及续算后的累计时间。横轴为 Time (a/c_s)，纵轴分别为 omega / gamma (c_s/a)。使用保存的原生归一化，不做末段平均、/ky 缩放、主离子重归一化或收敛过滤；切换模式前的这些选项不会作用于时间图。负频率与负增长率保留；非有限频率样本显示为曲线断点。时间非有限、非单调或数组长度不一致的计算点会跳过并报告；单采样点使用标记显示。

时间序列读取共用 `OMFITlib_compare_core.cgyro_frequency_history(data)`，原结果浏览器中的“绘制 omega & gamma vs time”也调用此接口。新入口的数据选择、曲线收集、按 ky 分页和渲染仍在各自的 compare 库中。只读取所选值及匹配 ky 的频率历史，不生成新的计算任务或结果分支。全局字体、颜色、线宽、图例排序、对数坐标及图片保存继续使用既有接口；图内文字为英文。时间图的“保存图片”区域不显示谱平均值 CSV 导出按钮。

## CGYRO 案例替换与绘图取值重置

同一结果名下，输入 nr、rho 与离子共同标识一个 CGYRO 案例。不同参数组扫描并存；完整重扫在全部点收集并构造成功后只替换相同有序扫描轴（含联动参数）的结果。失败、中断及部分结果不替换旧完整结果。各组索引保存在案例的 `__SCANS__`，服务器工作目录仍按每次运行的唯一标识隔离。

`OMFITlib_cgyro_archive.latest_cases` 返回最新实际案例键及旧键别名，仅为已有修订记录提供只读视图。识别旧发布器的 `__run=<8位十六进制>` 后缀后，按已发布元数据和原生插入顺序选最新记录，不用随机 UUID 排序；原勾选与配对可迁入最新键。显示仍先选 rho，再选该半径下的原始 / H / D / T。归档时合并仍存在的旧扫描分支，完整重扫仅清除被替换参数组的旧取值，其他参数组和案例保留。

绘图取值框的当前筛选与默认值分开传递。默认值每次从当前结果的完整扫描坐标生成，重置恢复全部可用值；共同参数、各案例独立参数及 TGLF 一维 / 二维轴均遵守此约定。

## 添加控件和登记文件

GUI 开头使用 `from OMFITlib_gui_api import adapt` 和 `OMFITx = adapt(OMFITx)`。原生 `help=` 原文会放入可缩放、可滚动的说明窗口。`D` / `d` 按钮显示为“重置”，保留原回调；鼠标停留提示分别为模块默认值 / 模块载入时的值。提示仅绑定此按钮，离开、点击或销毁时关闭。取消参数覆盖的按钮应命名“沿用输入”，不要混为默认值重置。

新入口和新库同时登记到工程根 `OMFITsave.txt` 与模块 `CGYRO_TGLF_scan/OMFITsave.txt`。OMFIT 按当前模块查找 `LIB`；子模块若使用共用库，也要登记对应的 LIB 别名及其传递依赖。回调所需的 OMFITlib 导入放在文件顶层，避免 GUI 返回后才导入导致 `ModuleNotFoundError`。

结果清理仅处理 `OMFITlib_result_cleanup.BRANCHES` 与明确的运行记录。新后端应在该文件补充结果分支和活动状态检查。不要用遍历全树或按目录名猜测的方式删除数据；不要把 `INPUTS`、生成的半径输入、剖面或共享环境设置列入清理范围。

## OMFIT 字典兼容约定

OMFIT 的 `SortedDict` 与 Python `dict` 的可选参数不同。读工程、设置和运行记录时使用 `node.get(key, None)`，创建缺省项时使用 `node.setdefault(key, default)`，批量写入时使用 `node.update(dict(...))`。不要省略 `get` 的默认值，也不要向树的 `update` 直接传关键字参数。

从 1.20.1 起，`tools/build_project.py` 在打包前调用 `tools/check_omfit_api.py`，静态检查这三种调用。它不执行 GUI、绘图或求解器。Tk 的 `Listbox.get(index)` 和 `os.environ.get(key)` 按各自的原生接口保留。
