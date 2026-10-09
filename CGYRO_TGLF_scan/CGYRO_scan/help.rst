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

1. 在“扫描与运行”选择 Transfer_tool 半径输入、导入文件或当前 CGYRO 输入。
   导入框显示实际选择的路径。半径可全选、清空或逐个选择。
2. 主离子方案选择“保持原始粒子”“H/D/T 对比”或“自选方案”。
   原始方案不改粒子组成；H/D/T 只修改 Z=1 主离子的质量。
3. 填写结果名称、ky 取值和扫描内容。可只扫 ky，也可增加 1–3 个物理参数。
   参数下拉菜单读取当前输入中的实际字段；取值使用列表。输入案例、离子方案、
   参数值与 ky 自动组合，页面显示计算点总数。
4. 点击唯一的“运行所选扫描”，自动准备输入、按统一环境提交、等待并收集。
   每次运行创建 ``runs/<运行标识>``，其中计算点固定命名为 ``p000001`` 等。
5. 收集后，``RUN_DB/结果名/案例`` 同时保存运行信息、``__TASKS__`` 任务坐标
   和实际 CGYRO 输出；``OUTPUTScan`` 保持原绘图入口兼容。
6. 在“结果与记录”选择记录并点击“查看当前数值表”。
   表格显示全部参数、ky、平均 omega/gamma 与相对波动；二维参数选择 ky，
   三维参数再选择第三轴切片。绘图为可选功能。

原模块的 CGYRO GUI 与工程总控使用同一套界面。修改相关字段后即时更新计划和
按钮状态，不需要“刷新批量输入”。数值输入编辑、时间缩放和重启放在折叠选项中。
新工程默认保持原始粒子、只扫描 ky，不开启时间缩放；已有工程的设置继续保留。
本页面执行线性计算，NONLINEAR_FLAG 设为 0；其余源输入物理参数不再被自动清零。
“只扫 ky”不覆盖 beta 等物理参数，运行记录保存真实的固定输入坐标以兼容旧绘图视图。
提交和收集结束或出错后，当前源 input.cgyro 与当前案例设置恢复。
运行记录用空 OMFITtree 加 update(mapping) 创建；其第一个构造参数用于路径，不能传字典。

Restart and limitations
-----------------------

``restart_mode=1`` 只允许一个输入案例，并要求每个任务存在匹配的
``bin.cgyro.restart``。只有 ``MAX_TIME`` 和 ``PRINT_STEP`` 可以变化；其他输入
变化必须新建运行。重启使用新目录，原结果不覆盖。

Quasilinear/nonlinear comparisons require an explicit
PLOTS/nl/linear_range_by_case mapping and compatible species/field input metadata.
旧 GYRO 提交后端禁用。1.13.0 仅完成静态兼容检查，未运行真实求解器、集群作业
或完整 OMFIT GUI 会话。
