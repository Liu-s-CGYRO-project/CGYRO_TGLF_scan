# 字体与独立资源包

主程序和管理器只携带字体名称、文件摘要与加载代码。完整字体分成独立的界面包和绘图包；首次使用时下载到用户缓存目录，之后跨版本共用。程序更新不会再次携带几十兆字库。旧版已经生成且通过 SHA-256 校验的缓存直接复用。

- 界面：完整 Noto Sans CJK SC Regular。
- 绘图中文：完整思源宋体 Source Han Serif CN，常规和粗体。
- 绘图英文：完整 Liberation Sans，常规、斜体、粗体和粗斜体，作为 Arial 的可分发相近替代。

字体保留原始字节与完整 SIL OFL 1.1 许可。没有裁剪字形或降低显示质量。字体名称和文件配置继续在“全局样式”修改；自定义字体覆盖默认值。

## 下载和离线使用

首次缺少字体时显示下载进度，可取消。网络连接或读取中断最多尝试三次，大小或 SHA-256 校验失败时不会安装。下载走普通 HTTPS 文件直链，不调用 GitHub REST API，也不需要账号令牌。网络沿用模板管理器的代理设置；管理员也可以在启动环境配置系统代理。

缓存位置为 XDG_CACHE_HOME 或 LOCALAPPDATA 下的 omfit-cgyro/fonts；两者均未设置时使用 ~/.cache/omfit-cgyro/fonts。文件路径保持旧版的 SHA-256 命名。只有通过整包和逐文件校验后才原子写入缓存，不修改系统字体配置。缓存目录不可写时使用当前进程的临时目录，字体管理窗口显示实际位置。

离线环境先在能联网的机器下载资源包，然后在“全局样式 → 字体管理”或管理器“设置与记录 → 字体管理”导入 ZIP。界面包和绘图包可以分别导入；完成后离线使用。首次下载窗口采用英文启动提示，避免字体尚未就绪时显示乱码。取消首次下载后页面使用系统字体；可稍后通过字体管理重新下载或导入。

## 接口

| 文件 / 接口 | 用途 |
| --- | --- |
| OMFITlib_font_manifest | 固定资源包直链、大小、摘要及文件清单，不含字体字节 |
| OMFITlib_font_cache.ensure_cached_fonts(kind, progress=None, cancel=None) | 界面无关的下载和缓存，kind 为 gui 或 plot |
| OMFITlib_font_cache.import_font_pack(path, progress=None, cancel=None) | 校验并导入离线包 |
| OMFITlib_font_ui.ensure_fonts(kind, parent=None) | 缓存命中直接返回；需要下载时在工作线程处理，Tk 显示进度 |
| OMFITlib_font_ui.open_font_manager(parent=None) | 重试下载、离线导入和缓存状态 |
| OMFITlib_gui_fonts.configure_window_fonts(window) | 只设置项目窗口的字体，不更改 Tk 全局命名字体 |
| OMFITlib_gui_fonts.gui_font(widget, base='TkDefaultFont', **overrides) | 沿用字号、字重和斜体属性 |
| OMFITlib_gui_fonts.refresh_window_fonts(parent) | 离线导入后刷新已登记的项目窗口 |
| OMFITlib_plot_fonts.font_rc(style) | 保留同一幅图延迟重绘与导出时的字体配置 |

新子模块接入 GUI 字体时，登记 gui_fonts、gui_font_data、font_ui、font_cache、font_manifest 五个 LIB；绘图另登记 plot_fonts、plot_font_assets、plot_font_data。顶层工程和各子模块的 OMFITsave.txt 都已登记。Matplotlib 中英文混排仍需 3.6 或以上版本。

## 重建

```sh
python -B tools/build_font_resources.py --gui-source /path/to/NotoSansCJKsc-Regular.otf --gui-license /path/to/Noto-OFL.txt --plot-source /path/to/original_plot_fonts --output-dir /path/to/font_resources
```

输入字体与许可必须匹配固定摘要。输出是两个可复现 ZIP 和两份小清单；不把字体编码回 Python 文件。添加或更换字体时使用新的资源包版本与下载标签，不覆盖已有资源包。绘图来源固定于 tools/plot_fonts_sources.json；许可分别见 FONT_LICENSE.txt 与 PLOT_FONTS_LICENSE.txt。

主程序构建检查字库标识、共享加载器、所有模块的 LIB 依赖及整包小于 1,000,000 字节；字体资源包独立于主程序构建和代码更新。
