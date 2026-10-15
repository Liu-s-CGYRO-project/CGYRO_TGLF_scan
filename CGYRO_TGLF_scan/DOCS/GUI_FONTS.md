# 统一字体与页面接入

界面使用随包的完整 **Noto Sans CJK SC Regular**，原始文件和许可固定于 [Noto CJK](https://github.com/notofonts/noto-cjk/tree/f8d157532fbfaeda587e826d4cd5b21a49186f7c/Sans)。资源未修改；压缩编码用于 OMFIT 工程携带。许可见 `DOCS/FONT_LICENSE.txt`。

`LIB/OMFITlib_gui_fonts.py` 提供公共接口：

| 接口 | 用途 |
| --- | --- |
| `configure_window_fonts(window)` | 为新建的项目窗口设置字体选项，并添加此窗口自己的 Map 绑定，覆盖后续创建的控件 |
| `gui_font(widget, base='TkDefaultFont', **overrides)` | 获取解释器内保留的字体对象，沿用原字号、粗体等属性；可传 `weight='bold'` |
| `style_widget(widget)` | 设置单个原生 / ttk 控件的字体；表格同时设置行高、表头，下拉框同时设置弹出列表 |
| `style_widgets(parent)` | 设置已创建的子控件，适合在计算弹窗初始大小之前调用 |
| `font_path()` | 返回经校验的本地字体文件；用于需要字体文件路径的绘图库 |

新弹窗在创建控件前调用 `configure_window_fonts`。表格创建后调用 `style_widget(table)`，窗口尺寸使用 `gui_font(...).metrics('linespace')` 计算。保留各入口的颜色、字号、控件命令和排版规则。

```python
from OMFITlib_gui_fonts import configure_window_fonts, gui_font, style_widget

window = tk.Toplevel(parent)
configure_window_fonts(window)
table = ttk.Treeview(window, columns=columns, show='headings')
style_widget(table)
body = tk.Text(window, font=gui_font(window))
```

字体缓存位于用户缓存目录 `omfit-cgyro/fonts`，写入采用临时文件和原子替换。Linux/Xft 通过 `FcConfigAppFontAddFile` 注册应用字体，Windows 通过 `AddFontResourceExW(..., FR_PRIVATE, ...)` 加载；进程结束后系统字体配置不变。Tk 实际字体加载失败时提示原因一次，页面继续使用可用字体。窗口装饰标题由桌面环境绘制。

绘图通过既有 `plot_context(root)` 入口使用独立的中英文字体配置。默认中文为思源宋体（Source Han Serif CN），英文、数字和常用数学符号为 Liberation Sans，作为宋体与 Arial 的可分发相近替代。安装包包含中文常规 / 粗体、英文常规 / 斜体 / 粗体 / 粗斜体的上游原始文件及许可；在当前 Matplotlib 进程内注册，默认无需系统安装或手填路径。全局样式可修改字体名称，或指定 `.ttf` / `.otf` / `.ttc` 文件；文件配置优先，自动读取实际名称。

`LIB/OMFITlib_plot_fonts.py` 提供绘图字体默认值、名称 / 文件解析和绘制上下文；`OMFITlib_plot_font_assets.py` 负责校验、缓存及注册随包资源。中英文同一行先选英文字体，再按字形回退到中文字体，需 Matplotlib 3.6 或以上版本。每幅图保存字体上下文，窗口延迟重绘和后续导出继续沿用该图的字体设置；标题、坐标轴、刻度和图例的普通文字均使用同一组合。完整绘图字体来源及许可见 `DOCS/PLOT_FONTS_LICENSE.txt`。

构建资源：

```sh
python -B tools/build_gui_fonts.py --source /path/to/NotoSansCJKsc-Regular.otf --license /path/to/LICENSE.txt
python -B tools/build_plot_fonts.py --source /path/to/original_plot_fonts
```

构建脚本校验原始文件的 SHA-256，并同步两份自包含 GUI 资源。绘图输入清单固定于 `tools/plot_fonts_sources.json`，可据其中的来源、文件名和摘要重建资源；保留字体原始字节。`tools/build_project.py` 在打包时检查字体库和数据副本一致、字体字节完整、许可及各模块的 LIB 依赖。新子模块导入 GUI 字体库时，同时登记 `OMFITlib_gui_fonts` 和 `OMFITlib_gui_font_data`；使用 `plot_context` 时，同时登记样式库、`OMFITlib_plot_fonts`、`OMFITlib_plot_font_assets` 和 `OMFITlib_plot_font_data`。

GUI 字体的编码资源由 `OMFITlib_gui_font_part1`、`part2`、`part3` 三个库依次组合，原始字体 SHA-256 保持不变；每个库小于旧管理器增量更新的 8 MiB 上限。登记 `OMFITlib_gui_font_data` 时也要登记这三个依赖。

更新时先安装 1.10.9 的下载修复小补丁，再安装 1.10.10 字体版。后续管理器字体版使用 `omfit-manager/v2/<版本>` 标签；`omfit-manager/v1.10.9` 保留为旧更新器可识别的小补丁入口，避免旧下载器直接跳到大字库。
