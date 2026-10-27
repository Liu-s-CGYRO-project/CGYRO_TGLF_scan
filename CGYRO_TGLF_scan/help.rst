Short Description
-----------------
统一管理 CGYRO / TGLF 输入准备、计算运行、结果绘图和工程模板

Keywords
--------
CGYRO, TGLF, GACODE, scans, plotting, templates

Long Description
----------------
在“工程总控”按输入准备、环境配置、扫描、结果和绘图的顺序操作。
勾选、切换下拉框或修改参数只更新选择；计算由“运行”按钮启动。
更新后关闭旧工程窗口再打开。

页面切换与刷新
~~~~~~~~~~~~~~
工作页面和页签只切换相应内容；参数选择通常只更新所在区域。
提交、收集、恢复或删除后更新当前工作页，顶部“刷新”才主动重载当前工程窗口。
直接打开部分旧子模块设置窗口时，仍使用该窗口的整个表单作为刷新范围。
结果列表只读索引摘要；缺少摘要的旧点显示待校验，不为了显示列表而读取全部结果。
绘图、数值表和续算按所选范围读取；同步状态等待服务器返回，不解析全部已归档结果。

输入与扫描
~~~~~~~~~~
Transfer_tool 生成或转换 input.gacode、input.cgyro、input.tglf；在“生成文件”中双击数值编辑，点击“保存修改”后生效。
CGYRO 可选择生成的半径输入、导入 input.cgyro 或使用当前输入，再选择半径与原始/H/D/T 离子方案。
每组输入可只扫描 ky，或同时扫描一至三个物理参数。物理轴支持实际列表、范围和基准倍数。
更改剖面、粒子方案或半径配置后需重新生成输入；“检查配置”可检查交接和参数问题。
预检查不提交任务；真正运行时生成独立输入，记录各点参数、服务器和作业身份。

TGLF 在“输入与扫描”“计算参数”“结果与记录”“多个剖面对比”页签中使用。
可选择当前输入、Transfer_tool/TGYRO 半径输入、局部转换文件或 input.gacode 生成输入。
生成输入集合与选择计算范围分开：选择单半径、范围、列表或全部，再设一维/二维扫描或 UQ。
输入生成使用 TGYRO 预处理；99 个单线程进程的超额运行仅用于 Open MPI 输入生成，正式计算按申请资源执行。
新 TGLF 结果在 TGLF_scan/RUN_DB 中保存；更换当前输入时保留旧输入和对应结果。

运行环境
~~~~~~~~
先选择服务器、GACODE 安装、队列、时限及 MPI/线程资源，再点“应用到整个工程”。
各程序可共用安装或分别选版；未保存的草稿不会应用到计算。新增服务器不自动连接或提交。
“自动检测”只读检查安装、执行权限和服务器能力；检测可见不代表计算正确性已经验证。
应用时显示校验进度，执行时再次检查程序。短时重复应用可复用同一连接、路径的完整校验。
错误详情在“环境配置与记录 → 操作历史”及原生 OMFIT 错误报告中查看。

收集、归档与续算
~~~~~~~~~~~~~~~~
“同步作业状态”查询原作业；“重新收集未归档结果”只收集已有输出，不补算。
CGYRO 结果、部分输出、检查点和冻结输入仅保存在 RUN_DB，绘图从这里读取。
普通参数扫描直接放在运行/半径下；H/D/T 各自分支，BASE 只保存原始参数基准结果。
新 ky 追加，重算只更新相同完整坐标，其他扫描和未重算点保留。
在“时间曲线 / 选择点续算”中选择点、核对状态并续算；使用原冻结输入和检查点。
续算只校验所选点自己的输入、检查点及配套文件，不要求父作业或历史链存在。
旧点的坐标或文件无法确定时单独报告并保留，不猜测匹配，也不阻止其他完整点续算。
“优化 CGYRO 归档（去重）”用于整理旧工程，完成后另存。它不删除远程文件。
结果树中展开 ky 下的 data 可查看详细数据。已被当前结果完整替代的失败快照仅保留作业记录。
“清空全部结果”需确认，且存在活动任务时不可执行；输入、配置和远程文件保留。

结果与绘图
~~~~~~~~~~
结果记录可打开数值表、当前图或时间曲线。二维扫描选 ky，三维再选第三轴切片。
末段平均比例 0.02 表示使用最后 2% 时间样本，按原有最小尾段约定处理。
对比页先选记录、半径、离子和扫描值，再设置图型，最后检查选择、绘图或导出。
“全局样式”统一字号、线宽、配色、图例和图尺寸；修改后重新绘图。
图窗按屏幕限制初始尺寸，缩放时为原生工具栏保留空间。
“?” 打开可滚动的完整说明；“重置”恢复原生默认值，“沿用输入”取消该参数覆盖。
界面和绘图字体使用独立资源包，首次下载后缓存。字号设置可在字体管理中调整。

更新与维护
~~~~~~~~~~
模板管理器可从 GitHub 或本地模板更新当前工程，选择保留数据与设置。
详细工作流参见仓库 WORKBENCH_REFERENCE.rst；开发接口见 MAINTAINER_GUIDE.md 与 DOCS/绘图接口。
本版经过针对性自动回归和真实 Tk 检查，完整用户 OMFIT 会话及服务器性能仍需实测。

Selection and data behavior
---------------------------

* Radial and parameter checkboxes follow the underlying keys, not their
  position in a changing list. Selections are retained separately per run
  and TGLF source; a new source starts with an explicit selection.
* The averaging fraction is between 0 and 1: 0.02 requests the final 2% of
  the saved frequency samples (with the existing minimum-tail convention).
* Raw, /ky and /ky-squared display scalings are mutually exclusive.
  Gamma ratios always use gamma itself. Scaling at ky=0 is undefined and
  is displayed as missing, not infinity or zero.
* Model-difference panels require one reference curve in at least one model
  on each page. The difference is normalized to abs(CGYRO), retaining the
  existing 1e-6 denominator floor. CGYRO relative time fluctuation is the
  population standard deviation divided by the absolute mean. It is not
  a standard error or a model-difference estimate.
* Negative gamma and signed omega are retained. Log axes cannot show
  nonpositive values. TGLF has no CGYRO time-fluctuation estimate; no zero
  error curve is invented for it.
* TGLF labels include radius, parameter and mode. In 2D views, para1/para2
  selects the varying scan parameter; the other parameter is held fixed.
* Export creates a new folder and records the normalization and averaging
  settings. Exported omega/gamma values precede display /ky scaling.
  Opening the GUI does not read frequency arrays or launch any solver.

CGYRO self-comparison details
----------------------------

* A blank growth-rate reference uses the first valid selected scan value.
  Explicit references and ky requests snap to the nearest saved value;
  duplicate ky matches count once. Invalid ky input produces an error.
* Spectra-only uses two panels. The optional fluctuation panels share case
  colors with the frequency/growth-rate panels. Legends are finalized once
  per page, using two columns for long lists and automatic height when needed.
* The peak marker selects the maximum currently displayed gamma quantity,
  including the selected /ky scaling and filtering.
  Signed spectra, population standard deviations and main-ion scaling retain
  the existing conventions. Saved sample counts must match frequency arrays.
* Single-ky scans preserve missing grid points as gaps. 3D scans use surfaces
  only for complete rectangular grids; incomplete or one-point scans show
  saved points. All 3D pages belong to the OMFIT figure notebook.
* Eigenfunction selection reads balloon data only for the selected ky. Saved
  complex fields are interpolated onto a common theta grid without amplitude
  renormalization. Missing E-parallel data is explicitly labelled; no
  second-derivative reconstruction or extra inductive term is added.
* Raw spectrum export is independent of the selected plot view and writes
  spectrum tables plus metadata.json in a new directory. Existing exports
  remain intact. Missing/filtered samples are recorded in the metadata.
