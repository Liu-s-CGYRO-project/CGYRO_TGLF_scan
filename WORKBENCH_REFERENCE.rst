Short Description
-----------------
统一管理 CGYRO / TGLF 输入准备、计算运行、结果绘图和工程模板

Keywords
--------
CGYRO, TGLF, GACODE, scans, plotting, templates

Long Description
----------------
“检查配置”检查已填写的运行配置和 CGYRO 输入，不连接服务器或提交计算。
通过时短暂显示“配置检查通过”，3 秒后消失；有问题时保留需要修改的项目，共用问题只列一次。
运行或应用配置失败时，顶部仅短暂显示失败提示，5 秒后消失；
刷新或重开页面不会重复显示。完整错误在“2 环境配置与记录 → 操作历史”查看，
原生 OMFIT 异常报告和各模块日志继续保留。

页面切换与刷新
~~~~~~~~~~~~~~

“工作页面”和内部页签只切换相应内容，不因浏览页面而读取全部结果或连接服务器。
下拉选择、全选、清空选择和参数重置通常只更新所在区域；
提交、收集、恢复或删除任务后，当前工作页的状态和结果入口会一起更新。
顶部“刷新”用于主动重载当前工程窗口；普通切换不需要先点它。
直接打开部分旧版子模块的独立设置窗口时，仍可能更新该窗口的整个表单。

结果列表优先显示收集时记录的状态、最后模拟时间、样本数和检查点摘要。
绘图、数值表和续算才读取所选范围；旧点缺少摘要时显示待校验，不自动扫描整库。
“同步作业状态”仍需等待服务器查询返回，但不应因此重新读取已归档的科学结果。

输入与扫描
~~~~~~~~~~

输入转换页的“生成文件”用于查看、编辑各半径的 input.cgyro / input.tglf 参数。
双击数值编辑，点击“保存修改”后生效；旧输入保存在操作历史，保存只影响当前文件。
预览选择不影响计算范围，CGYRO 在扫描页自动读取完整半径集合。
TGLF 统一在“5 TGLF 扫描”使用，通过“输入与扫描”“计算参数”“结果与记录”“多个剖面对比”页签切换。
刷新后保留当前页签；“更多 TGLF 参数”直接切到计算参数，运行返回后显示结果与记录。
“输入与扫描”下面分为“输入准备”“扫描设置”“运行”三个子页签，刷新后保留当前子页签。
生成输入成功或直接导入 TGLF 文件后进入扫描设置；切换页签不会启动生成或计算。
默认选择 input.gacode，先设置 TGLF 场景和数值参数，再点击“生成输入文件”（0.01–0.99，间隔 0.01）。
参数写入生成种子和局部输入。扫描区明确选择单个半径、范围、列表或全部，默认单个半径。
生成输入集合与选择计算范围是两步；任务数只按当前选择计算。
生成使用共用队列中的 TGYRO 预处理，按配置申请节点和 CPU；99 个 MPI 进程允许超额运行，固定每进程 1 线程。
例如配置 1 节点、每节点 16 时只申请 16 核。超额运行仅用于生成输入，需要 Open MPI；正式计算保持原配置。
输入完整后再替换旧集合。复用 Transfer_tool 当前剖面时，文件框显示完整数据树地址。
Transfer_tool 半径集排在直接导入 TGLF 文件之前，也可选择已有 TGYRO 半径集或局部互转文件。
完整剖面、生成输入和日志保存在 TGLF_scan/TGYRO/RUN_DB/inputs_*，计算输入位于 TGLF_scan/input.tglf。
不扫描参数时，每个所选输入运行一次；一维、二维参数扫描与半径选择可组合。
扫描取值可用原值倍数、实际范围或列表；多半径倍数扫描分别使用每个输入的基准值。
UQ 使用各参数的独立正态分布、指定样本数及 Latin Hypercube / Hammersley 采样。
计算参数可直接修改，扫描值优先，未改的参数沿用每个源文件；运行副本开启通量模型。
更换当前 TGLF 文件会自动保留旧输入和结果，不再跳转到独立的覆盖确认页面。
旧版尚未确认的候选留在操作历史，继续保留当前输入。

新 TGLF 运行保存到 TGLF_scan/RUN_DB/运行编号/points，使用平面的 p000001 等编号。
每点保存来源、实际输入、扫描值、状态、结果或错误日志；部分失败时已完成结果仍保留。
“结果与记录”可查看数值表、各物种通量、通量趋势和单点频率 / 增长率谱。
运行记录名称只显示“时间 · 扫描参数”，例如“10-14 14:11:56 · RLTS_1”；不扫描参数时显示“时间 · 原值”。
结果页和绘图页使用相同名称，同名记录追加序号，仍分别对应原有记录。
新记录直接在“绘图与对比”中选择，自动识别一维 / 二维扫描；频率、增长率和通量均读取所选记录。
部分成功的运行只提供已完成点；旧版缓存仍可单独选择，不混用不同运行的数据。
半径与参数选项按连续两列排列。“图例排序”选择排列方式，手动指定时在“排序关键词”填写图例名称或关键词。
工程各页、按钮、输入框、下拉列表、说明窗口、结果表和模板管理器统一使用随包的 Noto Sans CJK SC。
界面字体在当前进程加载，字号沿用现有设置，表格按实际字体计算行高。
绘图内置思源宋体（Source Han Serif CN）与 Liberation Sans，分别作为宋体与 Arial 的相近替代，自动加载；可在“全局样式”中修改字体或指定其他字体文件。

局部输入转换只选择 TGLF → CGYRO 或 CGYRO → TGLF。
TGLF 文件按 NS、KY 及完整展开几何字段自动识别 input.tglf / out.tglf.localdump；
不依赖文件名，不完整的展开几何会明确报出缺失字段。

环境配置使用窄长布局：“常用配置”集中设置服务器、程序版本、共用调度和默认资源；
“安装路径”维护安装列表；“脚本与命令”编辑共用初始化脚本和各程序命令。
“共用作业调度”中的调度方式、队列和运行时限供各模块共用；
“默认并行资源”中的节点、MPI 和线程按原规则同步，Transfer_tool 按半径分配 MPI。
“CGYRO 并发点数”用于 CGYRO 扫描。相关字段并排显示，标签在输入框上方；
窗口过窄时自动转为单列，本机模式隐藏队列和时限。
所有页签共用顶部的“应用到整个工程”，修改后点击一次即可同步。
有未应用修改时按钮高亮为蓝色；同步完成后显示灰色“配置已同步”。
配置不完整或存在未保存草稿时，补齐或保存后才能应用。
应用期间显示准备、服务器校验和模块同步阶段，完成后更新环境配置页及共用的“应用”状态。
同一服务器、隧道及全部路径在 5 分钟内的完整校验可复用；过期或变化时重新校验。
运行记录与操作历史在各自页签查看。

在“2 环境配置与记录 → 常用配置”点击“新增服务器”，填写新配置名、
用户名@主机（可带端口）、可选连接隧道及 Linux 工作根目录，再点“保存并选用”。
新增表单使用普通文本，不用加 Python 引号，也不用在每一项输入后按回车。
成功后配置写入 OMFIT 个人服务器设置并自动选中；确认统一 GACODE 环境后，
点击“应用到整个工程”同步各模块。

新增期间使用独立草稿；取消不会改动原连接，同名配置不会被覆盖。
切换已有服务器时自动读取它的地址、隧道及工作目录；“读取连接信息”
用于刷新当前连接，并保留已填写的工作根目录。个人设置保存失败时会明确提示，
此时只在当前会话生效。新增和切换配置本身不建立 SSH 连接或提交计算。

GACODE 安装与自动检测
~~~~~~~~~~~~~~~~~~~~

在“安装路径”页填写搜索目录，点击“自动检测”，读取该目录下 Gacode* 安装的实际程序。
检测不会启动求解器，也不申请计算节点；现有安装和程序选择保留。
可用“新增路径”“编辑路径”维护其他安装，路径随工程保存；移除只改变列表，不删除服务器文件。
在“常用配置”或“安装路径”选择“共用安装”，四个程序版本与脚本中的 GACODE_ROOT
立即同步，再点击“应用到整个工程”同步运行模块。
“编辑对象”仅用于路径维护，编辑或移除未使用的安装不会切换计算版本。
在“常用配置”分别选择 CGYRO、TGYRO、TGLF 和 profiles_gen 版本，然后点击“应用到整个工程”。
分别选版时“共用安装”显示“各程序分别选择”；再次选中某个共用安装会统一四个程序。
各程序共用连接、MPI 基础环境及资源设置，但使用所选安装的 GACODE_ROOT。
四个程序选择同一安装时，公共脚本中的 GACODE_ROOT 会立即同步到该路径，
已有工程中的旧路径也会修正；编译器、MPI、平台和其他初始化命令保留。
分别选择版本时，每个程序在加载平台环境和 gacode_setup 之前就绑定自己的路径，
不再先加载旧安装再覆盖根目录。“沿用环境脚本”继续使用公共脚本中的路径。
选择和脚本修改先保存在环境页，点击“应用到整个工程”后才同步到计算模块。
例如 CGYRO 使用专用版本，TGYRO 和 profiles_gen 使用完整的标准安装。
应用时校验安装，可复用近期完整结果；执行时在实际节点再次检查二进制文件，缺失时直接报告路径。
检测只检查文件和执行权限，不代表二进制依赖或计算正确性已验证。

The default panel is ``GUIS/main``. It organizes Transfer tool, CGYRO, TGLF,
multi-profile calculations, execution settings, result collection, plotting,
input differences and GitHub templates. Advanced module GUIs remain available.

Prepare and validate CGYRO input through Transfer tool before running from
the workbench. Changing the transferred input or its upstream profiles invalidates
the handoff. Only a submitted/executed run can be collected. Collection archives
the loaded results without resubmitting the scan.

CGYRO radius inputs and original/H/D/T ion variants are combined as input cases.
The rebuilt CGYRO page selects the source, cases, ky and optional physical axes,
then prepares, submits and collects with one Run action. The Results & records tab shows
records and numerical results. Each case can scan ky alone, or add one to three
physical parameters. The original CGYRO module GUI uses the same interface.
Calculation directories use flat point IDs. ``RUN_DB`` stores the task coordinates,
run metadata and actual results together. Use ``GUIS/CGYRO_results`` to open a
numeric table of all parameters, ky, mean omega/gamma and relative fluctuations;
two-axis scans select ky, and three-axis scans also select the third-axis slice.
Plotting remains optional, and existing comparison GUIs use the same result tree.

TGLF inputs are selected directly. Importing a new current file archives the old
input and its associated results together under PROJECT_STATE/activity. The
standalone keep/replace page has been removed. Radial sources are copied only for
execution, so each saved input and older result remains independent.

TGLF parameter scans write to native ``scanResults``, ``scanResults2D`` and
``scanResults3D`` with matching ``_spectra`` branches. Radial scans add the
radius key in TGLF_scan; current-file scans live in its TGLF child. UQ uses
``UQResults``. Three-dimensional comparisons expose labelled third-axis slices.
The workbench keeps summaries and direct native paths, not a second result
archive. Existing TGLF RUN_DB records remain readable for compatibility; new
runs and template updates never move native TGLF results there.

TGLF batch jobs use the applied scheduler, queue, wall time, program environment
and threads. Submission is bounded by the TGLF concurrency setting. Each job
writes an exit marker and log, and its flux output is validated before loading.
Slurm/PBS runs allocate compute resources; explicit local mode runs locally.
The existing scientific conversion formulas are unchanged.

Compare saved CGYRO linear scans and TGLF spectra or integrated flux scans in
the workbench's plotting page or ``GUIS/CGYRO_vs_TGLF``. The legacy
``GUIS/CGYRO_vs_CGYRO`` shortcut opens the same panel in CGYRO mode.

Panel order
-----------

1. **Cases**: choose the run, radii, pairings, and scan values. The selected
   TGLF run determines the source dimension automatically.
2. **Plot**: choose spectra, a growth-rate ratio, CGYRO eigenfunctions, or a
   TGLF flux view. Only applicable controls are shown.
   Log axes and legend ordering are also configured here.
3. **Export & checks**: inspect selection messages, export spectra, or show
   the CGYRO status map. Figures can be saved through the figure toolbar.

A shared **Global style** tab sets font/line sizes, colors, figure dimensions,
grid and legend placement for the project's main plotting entry points.

The Plot and Check selection buttons are below the tabs. In TGLF-only mode,
choose Linear spectra or Integrated flux before choosing the source data.

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

Code organization
-----------------

``GUIS`` and ``PLOTS`` contain short OMFIT entry scripts. The
``LIB/OMFITlib_compare_*`` libraries separate settings, widgets, cases,
data access, numerical helpers, figure styling, spectra, TGLF flux plots,
CGYRO self-comparison, status checks and dispatch/export. Libraries use
explicit imports and are registered in the project save manifest.

The CGYRO self-comparison implementation uses these files:

* ``OMFITlib_compare_cgyro.py``: OMFIT entry, data preparation and page grouping.
* ``OMFITlib_compare_cgyro_selection.py``: settings, parsing and legacy selections.
* ``OMFITlib_compare_cgyro_data.py``: spectra, statistics, scan grids and ratios.
* ``OMFITlib_compare_cgyro_eigen.py``: saved balloon-field extraction and selection.
* ``OMFITlib_compare_cgyro_render.py``: five views, shared colors and page layout.
* ``OMFITlib_compare_cgyro_export.py``: raw spectrum tables and export metadata.

Only the entry depends on OMFIT's FigureNotebook global; the other libraries
can be tested with ordinary Python, NumPy and Matplotlib. New files must be
registered in both the full project and standalone module OMFITsave.txt files.

Validation limits
-----------------

This file retains the full workbench reference outside the runtime package.
See VALIDATION.md for the checks performed on each release and their limits.
Full OMFIT desktop integration, site-specific solver versions and physical
convergence require verification in the target environment.

全局样式与结果清理
~~~~~~~~~~~~~~~~~~
“绘图与对比 → 全局样式”统一修改主要绘图入口的字体、字号、线宽、标记、配色、网格、图例和画布。
改后重新绘图生效；归一化、对数轴和扫描参数仍在各图的设置中调整。
项目概览和运行记录页提供“清空全部结果”，确认后清空 CGYRO / TGLF / TGYRO 的计算结果与运行记录。
输入文件、生成的半径输入、剖面和配置保留；远程目录、导出的图片和旧工程文件不受影响。
存在已提交或运行中的任务时不能清空，需要先结束任务并收集结果。
“?” 在独立说明窗口显示完整文字，可滚动、复制和调整窗口大小；按 Esc 或关闭按钮退出。
参数旁的“重置”恢复控件的原生默认值；鼠标停留可查看是模块默认值还是模块载入时的值。
“沿用输入”取消参数覆盖，使用各输入文件自己的值。
开发者可在 DOCS / 绘图接口 中查看共用接口与新入口的登记方法。
