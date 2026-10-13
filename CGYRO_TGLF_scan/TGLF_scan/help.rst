Short Description
-----------------
Run the TGYRO code to get inputs for and then run TGLF at various radii

Keywords
--------
Experimental fluxes, Reduced model, Gyrokinetic fluxes

Long Description
----------------
工程总控的“TGLF 计算与扫描”统一选择当前 / 导入文件、Transfer_tool 半径输入、
已有 TGYRO 半径输入或局部互转文件。不扫参数时每个输入运行一次；一维和二维扫描
填写实际取值列表，可与多个半径组合。UQ 支持 1–5 个连续参数的独立正态分布采样。

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
