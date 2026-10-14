Short Description
-----------------
Run the TGYRO code to get inputs for and then run TGLF at various radii

Keywords
--------
Experimental fluxes, Reduced model, Gyrokinetic fluxes

Long Description
----------------
“TGLF 计算与扫描”通过“输入与扫描”“计算参数”“结果与记录”“多个剖面对比”页签切换。
刷新后保留当前页签；“更多 TGLF 参数”直接切到计算参数，运行返回后显示结果与记录。
“输入与扫描”再分为“输入准备”“扫描设置”“运行”三个子页签，分别选择文件、设置半径与参数、提交计算。
生成输入成功后自动进入扫描设置；直接导入 TGLF 文件后也进入扫描设置。
上层页签和子页签分别记住选择，切换页签不会自动生成文件或提交计算。
工程总控的“TGLF 计算与扫描”默认从 input.gacode 开始。选择剖面，点击“生成输入文件”，
在 0.01–0.99、间隔 0.01 的网格上生成 input.tglf。径向坐标可选 rho 或 r/a。
生成前可选择 OMFIT 原生 TGLF 场景，并直接设置 SAT_RULE、KYGRID_MODEL、NKY、NMODES、
USE_BPER、USE_BPAR 和 UNITS。“更多 TGLF 参数”提供常用及输入中全部数值参数，修改后回车。
显式设置会写入生成种子和每个生成输入，生成记录保存实际参数；成功后沿用这份种子。
生成使用 TGYRO 预处理命令、环境页选择的程序版本及共用队列。
申请环境页设置的节点数和每节点 CPU 数，每个生成进程固定 1 线程；99 个 MPI 进程允许超额运行。
例如 1 节点、每节点 16 时，申请 16 个 CPU，在作业内启动 99 个生成进程，不再要求单节点有 99 核。
超额运行仅用于输入生成，使用 Open MPI；正式 CGYRO / TGLF 计算的资源和绑核保持原配置。
页面只显示输入选择与生成操作，半径范围在文件框的“?”帮助中查看。
选择 Transfer_tool 当前剖面后，文件框显示完整的 OMFIT 数据树地址。
生成用 TGYRO_PED_MODEL=1（固定边界），与该版本的 TGYRO 参数要求一致。
生成后，在“扫描设置”的“计算半径”选择单个半径、范围、列表或全部半径，默认单个半径。
生成的是可供选择的输入集合，运行只使用选中的半径；查看 / 编辑列表也对应所选输入。
旧版自动全选迁移为单个半径，已有范围和列表保留；明确选择全部后会保存该选择。
再选择原始参数、1D、2D 或 UQ。原始参数方式在每个所选半径只计算一次。
准备剖面与运行 TGLF 是两个明确的按钮；载入文件或打开页面不自动提交任务。
也可直接复用 Transfer_tool 已生成的半径输入，或导入 input.tglf / out.tglf.localdump。
Transfer_tool 输入排在直接导入 TGLF 文件之前。已有工程保留当前来源选择。

99 个输入保存在 TGLF_scan/input.tglf；生成记录、原剖面和日志在 TGLF_scan/TGYRO/RUN_DB/inputs_*。
生成记录还保存实际 batch.sh、申请资源、生成脚本、MPI 退出码及任务专用的 TGYRO 启动器副本。
失败报告直接附上 TGYRO 的具体错误、失败阶段、日志摘要和记录地址；完整日志仍保存在 diagnostics。
剖面变化后需要重新生成。失败保留当前输入和结果；完整成功后归档并替换旧半径集合及旧扫描缓存。
一维和二维扫描可选原值倍数、实际值范围或数值列表。范围设置起点、终点和点数，包含端点。
原值倍数沿用 OMFIT 原生扫描逻辑，多半径分别采用各输入的原值；实际范围和列表使用所列绝对值。
整数参数仍需整数取值，原值为零时使用实际范围或列表。UQ 支持 1–5 个连续参数的独立正态分布采样。

“计算参数”直接修改数值并回车，恢复后沿用每个文件原值。扫描值优先。
新运行的每个点在 RUN_DB 中保存实际输入、参数、状态、结果或错误日志。
“结果与记录”提供数值表和可选绘图，不需要先使用旧扫描 GUI。
更换当前输入自动归档旧输入和结果；页面不再要求单独确认覆盖。
队列、时限、环境来自工程共用配置，并发任务数在 TGLF 页面设置。

This module orchestrates the running of various GACODE pieces: profiles_gen, TGYRO, TGLF, to start from an experimental power balance calculation, and then perform a sensitivity analysis of TGLF at various radii either to investigate straight sensitivity or to calculate particle D and V from TGLF.

Typical workflows
-----------------
This module is used to:

* calculate radial profiles of TGLF growth rates and fluxes
* calculate radial profiles of TGLF particle D and V
* calculate TGLF sensitivity to input parameters at various radii

Supported devices
-----------------
* Any device for which profiles_gen processing of power balance is available, which includes TRANSP, ONETWO, ASTRA, etc.

Tutorials
---------
* `Google docs <https://docs.google.com/document/d/1ggFvm3IfqqTRs1EqJiXS7mGbfOAmUPnd1MrZTOhh8xM>`_
* `PDF <https://docs.google.com/document/d/1ggFvm3IfqqTRs1EqJiXS7mGbfOAmUPnd1MrZTOhh8xM/export?format=pdf>`_
* `YouTube Video <https://www.youtube.com/watch?v=rjGLHIN8cwI&index=3&list=PLdksEfhRAD67q1fGDlZMAYcWSO8BlhbK5>`_

Relevant publications
---------------------
* See the TGLF module publications

External resources
------------------
* `TGLF on the GA GACODE website <https://fusion.gat.com/theory/Tglfoverview>`_ (needs GA account)
* `TGLF on the GitHub GACODE website <http://gafusion.github.io/doc/tglf.html>`_
