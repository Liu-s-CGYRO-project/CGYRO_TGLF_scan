Short Description
-----------------
准备 CGYRO 扫描输入、运行计算、收集和对比结果

Keywords
--------
CGYRO, linear, nonlinear, scans, gyrokinetics

Long Description
----------------
本模块准备、提交、收集和浏览 CGYRO 线性扫描。求解器与集群环境必须在
实际运行的 Linux/OMFIT 环境中配置。

Workflow
--------

1. 在工程总控的 CGYRO 页选择一个或多个 ``nr/rho`` 输入案例。
2. 选择“原始、H、D、T”中的一个或多个主离子方案。原始方案不改粒子组成；
   H/D/T 只修改 Z=1 主离子的质量。
3. 设置 1、2 或 3 个参数轴及 ``kyarr``。所有输入案例、离子方案、参数值与 ky
   自动作笛卡尔组合；页面显示实际计算点总数。
4. “刷新批量输入”只准备输入；“运行所选组合”按统一环境提交并收集。
   每次运行创建 ``runs/<运行标识>``，其中计算点固定命名为 ``p000001`` 等。
5. 收集后，``RUN_DB/结果名/案例`` 同时保存运行信息、``__TASKS__`` 任务坐标
   和实际 CGYRO 输出；``OUTPUTScan`` 保持原绘图入口兼容。
6. 在工程总控的“绘图与对比”打开“CGYRO 扫描结果浏览”，点击“查看当前数值表”。
   表格显示全部参数、ky、平均 omega/gamma 与相对波动；二维参数选择 ky，
   三维参数再选择第三轴切片。绘图为可选功能。

Restart and limitations
-----------------------

``restart_mode=1`` 只允许一个输入案例，并要求每个任务存在匹配的
``bin.cgyro.restart``。只有 ``MAX_TIME`` 和 ``PRINT_STEP`` 可以变化；其他输入
变化必须新建运行。重启使用新目录，原结果不覆盖。

Quasilinear/nonlinear comparisons require an explicit
PLOTS/nl/linear_range_by_case mapping and compatible species/field input metadata.
旧 GYRO 提交后端禁用。1.13.0 仅完成静态兼容检查，未运行真实求解器、集群作业
或完整 OMFIT GUI 会话。
