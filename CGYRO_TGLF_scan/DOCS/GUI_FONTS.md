# 字体与独立资源包

主程序和管理器只携带字体名称、文件摘要与加载代码。完整字体分成独立的界面包和绘图包；首次使用时下载到用户缓存目录，之后跨版本共用。程序更新不会再次携带几十兆字库。旧版已经生成且通过 SHA-256 校验的缓存直接复用。

- 界面：完整 Noto Sans CJK SC Regular。
- 绘图：完整 Liberation Sans，常规、斜体、粗体和粗斜体，作为 Arial 的可分发相近替代；输出文字统一英文。
- 保留资源：完整思源宋体 Source Han Serif CN，常规和粗体，继续保存在既有独立资源包和缓存中，当前绘图不再使用。

字体保留原始字节与完整 SIL OFL 1.1 许可。没有裁剪字形或降低显示质量。字体名称和文件配置继续在“全局样式”修改；自定义字体覆盖默认值。

## 下载和离线使用

首次缺少字体时显示下载进度，可取消。网络连接或读取中断最多尝试三次，大小或 SHA-256 校验失败时不会安装。下载走普通 HTTPS 文件直链，不调用 GitHub REST API，也不需要账号令牌。网络沿用模板管理器的代理设置；管理员也可以在启动环境配置系统代理。

缓存位置为 XDG_CACHE_HOME 或 LOCALAPPDATA 下的 omfit-cgyro/fonts；两者均未设置时使用 ~/.cache/omfit-cgyro/fonts。文件路径保持旧版的 SHA-256 命名。只有通过整包和逐文件校验后才原子写入缓存，不修改系统字体配置。缓存目录不可写时使用当前进程的临时目录，字体管理窗口显示实际位置。

离线环境先在能联网的机器下载资源包，然后在“全局样式 → 界面字体与字号”或管理器“设置与记录 → 字体管理”导入 ZIP。界面包和绘图包可以分别导入；完成后离线使用。首次下载窗口采用英文启动提示，避免字体尚未就绪时显示乱码。取消首次下载后页面使用系统字体；可稍后通过字体管理重新下载或导入。

## 界面字号与实际生效状态

正文、输入框、按钮、页签和数值使用统一的 11 pt；分组标题为 12 pt 粗体。点数随 Tk 的显示缩放换算，不继承 OMFIT 各控件混杂的原始字号。“GUI size / pt”可选择 9–18 pt，点击“Apply GUI font”立即应用到已登记的窗口和隐藏页签，并保存在字体缓存目录的 gui_preferences.json。绘图字号单独保留在全局绘图样式中。

控件内边距、表格行高和文本行距按实际字体度量计算。字体变更会更新保留的 Tk 命名字体，重新测量表单标签和页签内容，避免仍使用旧字号的尺寸。原生 OMFIT 新建字段后再次应用字体；已打开的窗口在加载器更新后也会重新绑定本模块的字体处理函数，不替换原生回调。

“GUI file: ready”仅说明文件通过校验；“GUI active”以及 CJK、Latin、digits 三项显示 Tk 实际选中的字体，并显示 Tk 后端和失败原因。旧版缓存的加载失败不会阻止更新或导入后重新应用。Linux 优先通过 Tk 自己加载的依赖定位 Fontconfig，避免 Conda Tk 与系统 Fontconfig 不一致。Tk 若只支持 X11 位图字体，窗口会明确说明需要支持 Xft 的 Tk；缓存完整不代表渲染后端已经支持字体。

## 接口

下拉列表在首次展开时由 Tk 创建；字体处理接入各控件的 postcommand，在原命令执行后、原生列表布局前同步字体。每个选项上下留白为 max(3, linespace // 5) 像素，使用 Listbox 的 selectborderwidth 参与行高度量。Tk 的行高为 linespace + 1 + 2 * selectborderwidth，鼠标与键盘继续使用原生索引和绑定。参见 [Tk 8.6 Combobox 实现](https://github.com/tcltk/tk/blob/core-8-6-branch/library/ttk/combobox.tcl)和 [Listbox 行高度量](https://github.com/tcltk/tk/blob/core-8-6-branch/generic/tkListbox.c)。

postcommand 的原始 Tcl 脚本通过 Tcl 列表引用保留，并先执行一次；字体处理复用一个控件回调，刷新不重复包裹。仅在弹出前创建 Listbox，仍使用 Tk 的显示、滚动条、选择和关闭流程。已经创建的列表在界面字体刷新时也同步更新。

Entry 与收起状态的 ComboBox 共用 fit_field_height(widget, style_name, font)，统一实际 textarea 高度、边框与垂直留白。原生 Tk 的文字绘制在 textarea 内裁切，外层 padding 只改变控件外部请求尺寸。函数在窗口私有样式的原生 padding 子布局内加入透明高度约束元素，与 textarea 同层，其余 field、箭头和文字节点保留。高度随实际字体度量变化，并用中文字宽提供后备字形的保守字面估计。文字区域已含上下留白，外层垂直 padding 为 0，避免重复加高；边框为 1。透明元素在 Tk 根窗口保留和缓存，不生成或替换字形；NativeLayout 应用私有样式后也调用此函数。参见 [Tk Entry 绘制与 textarea 布局实现](https://github.com/tcltk/tk/blob/core-8-6-branch/generic/ttk/ttkEntry.c)。

OMFIT 原生校验会切换 valid / error 等样式。控件局部事件监听在原生校验之后恢复私有几何样式，保留原生状态颜色和回调。监听与计时器复用，尺寸改变但样式未变时跳过，控件销毁时取消计时器。旧 fit_combobox_text 接口作为兼容入口保留。

| 文件 / 接口 | 用途 |
| --- | --- |
| OMFITlib_font_manifest | 固定资源包直链、大小、摘要及文件清单，不含字体字节 |
| OMFITlib_font_cache.ensure_cached_fonts(kind, progress=None, cancel=None) | 界面无关的下载和缓存，kind 为 gui 或 plot |
| OMFITlib_font_cache.import_font_pack(path, progress=None, cancel=None) | 校验并导入离线包 |
| OMFITlib_font_download_ui.ensure_fonts(kind, parent=None)（font_ui 保留兼容导出） | 缓存命中直接返回；需要下载时在工作线程处理，Tk 显示进度 |
| OMFITlib_font_ui.open_font_manager(parent=None) | 重试下载、离线导入、GUI 字号和实际渲染状态 |
| OMFITlib_gui_fonts.configure_window_fonts(window) | 只设置项目窗口的字体，不更改 Tk 全局命名字体 |
| OMFITlib_gui_fonts.gui_font(widget, base='TkDefaultFont', **overrides) | 统一界面字号，沿用字重和斜体；显式 size 可用于标题 |
| OMFITlib_gui_fonts.font_size(widget) / set_font_size(widget, value) | 读取或保存界面字号，自动刷新项目窗口 |
| OMFITlib_gui_fonts.font_status(widget) | 实际字体、渲染后端、生效状态和错误信息 |
| OMFITlib_gui_fonts.fit_field_height(widget, style_name, font) | 统一输入框与收起下拉框的文字区域高度、边框和留白，仅用于窗口私有样式 |
| OMFITlib_gui_fonts.fit_combobox_text(widget, style_name, font) | 兼容旧调用，转调 fit_field_height |
| OMFITlib_gui_fonts.refresh_window_fonts(parent) | 离线导入后刷新已登记的项目窗口 |
| OMFITlib_plot_fonts.font_rc(style) | 保留同一幅图延迟重绘与导出时的字体配置 |

新子模块接入 GUI 字体时，登记 gui_fonts、gui_font_data、font_download_ui、font_ui、font_cache、font_manifest 六个 LIB；绘图另登记 plot_fonts、plot_font_assets、plot_font_data 和 plot_labels。顶层工程和各子模块的 OMFITsave.txt 都已登记。输出图全部采用英文及 Liberation Sans，不再读取中文绘图字体设置或要求 Matplotlib 3.6；GUI 的中文字体设置保持原有用途。

## OMFIT 回调加载

字体下载进度和 ensure_fonts 位于 font_download_ui，依赖字体缓存，不依赖 gui_fonts 或字体设置窗口。gui_fonts 直接使用这层下载接口；font_ui 在文件顶部导入 gui_fonts，构建“字体管理”的界面和字号动作，保留 ensure_fonts、set_proxy 的旧导出。

OMFIT 在脚本结束后移除其 LIB 导入器和模块缓存，Tk 回调不能再临时导入 OMFITlib_*。下载、离线导入、状态刷新和字号应用均使用加载时保留的函数引用。构建时检查共享字体库一致、依赖无循环、没有延迟导入，并验证各消费模块的 LIB 登记。此检查不启动 GUI 或实际下载字体。

## 重建

```sh
python -B tools/build_font_resources.py --gui-source /path/to/NotoSansCJKsc-Regular.otf --gui-license /path/to/Noto-OFL.txt --plot-source /path/to/original_plot_fonts --output-dir /path/to/font_resources
```

输入字体与许可必须匹配固定摘要。输出是两个可复现 ZIP 和两份小清单；不把字体编码回 Python 文件。添加或更换字体时使用新的资源包版本与下载标签，不覆盖已有资源包。绘图来源固定于 tools/plot_fonts_sources.json；许可分别见 FONT_LICENSE.txt 与 PLOT_FONTS_LICENSE.txt。

主程序构建检查字库标识、共享加载器、所有模块的 LIB 依赖及整包小于 1,000,000 字节；字体资源包独立于主程序构建和代码更新。
