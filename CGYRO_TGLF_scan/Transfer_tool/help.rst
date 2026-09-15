Transfer_tool 使用流程
---------------------

在工程总控的“输入准备与转换”中：

* Transfer_tool 运行：载入 input.gacode，设置坐标、起始半径、结束半径和点数，点击运行。
* 运行按钮执行原 command box 1 的准备逻辑：同步离子，运行 TGYRO，再生成各半径 input.cgyro / input.tglf。
* 生成结果与传递：选择本次半径输入，验证并送入 CGYRO 或 TGLF。TGLF 覆盖仍由用户决定。
* 局部输入互转：转换已有局部输入，独立于剖面生成。
* 高级设置：查看、编辑或更换 Transfer_tool 的种子输入。缺少时自动使用内置种子。

直接运行 SCRIPTS/main.py 仍可使用原命令框设置的 input.tgyro 半径及 SETUP/p_tgyro。
统一计算环境在工程总控的“环境配置与记录”中配置。
