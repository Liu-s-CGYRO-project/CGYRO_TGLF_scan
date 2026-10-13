Short Description
-----------------
Run the TGYRO code to get inputs for and then run TGLF at various radii

Keywords
--------
Experimental fluxes, Reduced model, Gyrokinetic fluxes

Long Description
----------------
工程总控的“TGLF 计算与扫描”默认从 input.gacode 开始。选择剖面，点击“生成 99 个半径输入”，
在 0.01–0.99、间隔 0.01 的网格上生成 input.tglf。径向坐标可选 rho 或 r/a。
生成使用 TGYRO 预处理命令、环境页选择的程序版本及共用队列。
申请环境页设置的节点数和每节点 CPU 数，每个生成进程固定 1 线程；99 个 MPI 进程允许超额运行。
例如 1 节点、每节点 16 时，申请 16 个 CPU，在作业内启动 99 个生成进程，不再要求单节点有 99 核。
超额运行仅用于输入生成，使用 Open MPI；正式 CGYRO / TGLF 计算的资源和绑核保持原配置。
界面显示申请资源与生成进程数。选择 Transfer_tool 当前剖面后，文件框显示完整的 OMFIT 数据树地址。
完整生成后，按全部、范围或列表选择计算半径，再设置不扫参数、1D、2D 或 UQ。
准备剖面与运行 TGLF 是两个明确的按钮；载入文件或打开页面不自动提交任务。
也可直接复用 Transfer_tool 已生成的半径输入，或导入 input.tglf / out.tglf.localdump。
Transfer_tool 输入排在直接导入 TGLF 文件之前。已有工程保留当前来源选择。

99 个输入保存在 TGLF_scan/input.tglf；生成记录、原剖面和日志在 TGLF_scan/TGYRO/RUN_DB/inputs_*。
生成记录还保存实际 batch.sh、申请资源、生成脚本、MPI 退出码及任务专用的 TGYRO 启动器副本。
剖面变化后需要重新生成。失败保留当前输入和结果；完整成功后归档并替换旧半径集合及旧扫描缓存。
一维和二维扫描填写实际取值列表，可与多个半径组合。UQ 支持 1–5 个连续参数的独立正态分布采样。

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
