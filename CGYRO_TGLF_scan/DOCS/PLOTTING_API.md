# 绘图与界面扩展

工程绘图入口使用全局样式，输出图中文字为英文，界面保持中文。全局字号、配色、线宽、图例和导出选项在“全局图形样式”设置，修改后重新绘图。默认英文字体 Liberation Sans 通过完整字体资源包下载；来源与许可见 GUI_FONTS.md / PLOT_FONTS_LICENSE.txt。

## 新绘图入口

在模块 PLOTS 登记脚本，例如：

```python
from OMFITlib_plot_style import plot_context

with plot_context(root):
    fig, ax = subplots()
    ax.plot(x, y, label='Case A')
    ax.set_xlabel('x')
    ax.set_ylabel('y')
    ax.legend()
```

plot_context 按所属工程读取 SETTINGS/PLOT_STYLE，只在本次绘图与延迟重绘 / 导出期间应用配置，不改数据、单位或别的工程。使用默认循环；有物理意义的参考线可设置 gid='reference'。新图直接填写英文文字；旧内置中文由 OMFITlib_plot_labels 映射，自定义中文需提供英文显示名，原名不改。

FigureNotebook 绘图完成、尺寸和布局设置后调用 `OMFITlib_plot_window.fit_figure_window(fig)`：窗口初始尺寸受屏幕限制，标签栏与原生工具栏先分配空间，画布随剩余区域缩放。多标签共用控制器，切换和重绘不重置用户调整的窗口；非 Tk 绘图保持原导出尺寸。对比绘图的 apply_figure_layout 已接入此接口。

## 数据与扩展边界

- CGYRO 结果用 OMFITlib_cgyro_storage.result_view / resolve_result 读取，仅存放于 RUN_DB；临时视图不得回写。
- 多轴扫描通过 OMFITlib_cgyro_scan_view 按完整坐标选择切片，一次改变一个参数、其他轴固定；不能把组合键当单参数，也不能平均不同物理组合。
- ω / γ 随时间可在 CGYRO 对比绘图类型中选择，或从结果表打开。使用所选 ky 的完整时序；末段平均比例只影响谱统计。
- 图例质量顺序为 H、D、T；短名只影响显示。点击图例会切换对应曲线，可在图例排序设置中选手动顺序。
- 相同参数组按完整坐标与 ky 合并，仅更新重算点；其他参数扫描并存。取值“重置”恢复实际归档的完整列表，不重命名原始结果键。
- TGLF 读取用 OMFITlib_plot_sources / OMFITlib_tglf_records，只展示完成点；旧缓存以 legacy 标识，不与新运行混写。
- 控件通过 OMFITlib_gui_api / gui_controls 接入，使用现有帮助窗口和默认值按钮。Tk 变量显式 master=；SortedDict.get 填默认值，update 传一个映射。新增库同时登记两个层级 OMFITsave.txt。

完整接口、代码示例和维护说明保存在 GitHub 仓库根目录 [PLOTTING_REFERENCE.md](https://github.com/Liu-s-CGYRO-project/CGYRO_TGLF_scan/blob/main/PLOTTING_REFERENCE.md)。
