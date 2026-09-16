Short Description
-----------------
处理粒子剖面和准中性约束并生成各半径的 CGYRO / TGLF 输入

Keywords
--------
GACODE, Transfer_tool, profiles, quasineutrality, CGYRO, TGLF

Long Description
----------------
在工程总控“输入准备与转换 → Transfer_tool 运行”中，载入剖面，
设置计算半径，确认自动识别的主离子，选择粒子处理方案，点击唯一的“运行 Transfer_tool”按钮。
程序依次准备粒子、运行 TGYRO、生成各半径 input.cgyro / input.tglf。

页面仅显示剖面状态、半径、主离子摘要和粒子方案。完整路径可点“剖面文件”旁的“?”；
粒子规则、处理说明及上次结果可点“处理方案”旁的“?”查看。

运行资源
~~~~~~~~

沿用原 command box 1：每个半径 1 个 MPI 进程，3 个半径对应
``tgyro -e . -n 3``，input.tgyro 的每个 DIR 也分配 1 个进程。
进程数由半径点数决定，不使用 CGYRO 扫描的核数，也不按核数取整或超额分配。

已应用统一环境时，Slurm / PBS 使用 OMFIT 原生 submit_job 申请一节点、
每半径一进程、每进程一线程，队列和时限沿用统一设置。
GACODE 环境初始化在作业内执行。等待作业结束并读取退出状态后才解析 TGYRO 结果；
提交成功不等于生成成功。本机模式及未配置调度器的旧独立设置保留直接执行。
不改变其他计算程序的资源设置。更新后重新运行 Transfer_tool 即使用这一规则。

主离子识别
~~~~~~~~~~

对原始剖面中每个离子分别计算本轮半径区间内 ni/ne 的平均值，
严格大于 30% 的全部列为主离子，恰好 30% 不入选。通常是 1–2 种，
不硬限制数量，不再手工指定一个主离子。热离子和快离子均按密度规则判断，
不按电荷、质量或在输入文件中的顺序判断，也不把同名的不同粒子群预先相加。

平均值在所选 rho 或 r/a 坐标上计算：对原始网格的 ni/ne 作分段线性插值，
包含所选区间的两个端点，积分后除以区间长度；不按体积加权，
不依赖输出半径点数。识别在准中性调整、合并、删减之前进行，本轮处理期间不重新分类。
无粒子达标、径向网格无效或区间超出剖面时停止，并给出原因。

主离子按平均占比从高到低排列在输出前部，同占比按原编号排列；
界面简要显示名称和平均占比；“?”帮助、日志及 OUTPUTS/Particle_processing/main_ions 保留原始编号。
更换半径区间后界面重新识别；“仅保留主离子”等方案始终保留全部达标粒子。

粒子方案
~~~~~~~~

* 保留所有粒子：保留各离子的热 / 快类型，所有主离子按原密度比例共同承担准中性校正。
* 慢化快离子（热化处理）：以电荷和质量识别同种粒子。对应热杂质时将快离子密度并入该热离子；对应任一主离子时保留为独立粒子，其密度不合并，温度、环向流速与极向流速改用所选热杂质的值。自身达标的快离子也保留为独立主离子。需要合并时若缺少同种热离子，或需要独立热化时缺少参考热杂质，均停止；不计算真实慢化分布。
* 仅保留主离子和等效杂质：保留电子及全部主离子；把全部非主离子（包括未达主离子阈值的快离子）合成一种等效杂质。每个计算半径分别计算 Z、密度 N、MASS、温度和梯度，保持原杂质的总电荷、Zeff 贡献、总质量和压力。没有非主离子或其密度全部为零时不新增杂质。
* 仅保留主离子：保留电子和全部主离子，各半径按原主离子密度比例补齐电荷，分别保留各自温度和流速。

所有方案均保留电子。等效杂质不选择代表粒子，也不把电荷取整；旧的代表粒子设置自动移除。
其他来源在生成 input.gacode 后自动识别；可切到该 input.gacode 再指定热化参考。

“温度 / 流速来源”用于对应任一主离子、独立保留的快离子，候选为
不属于任何主离子种类（电荷与质量）的热离子。默认取原剖面中的首个热杂质；存在多个
热杂质时可在下拉框明确指定。参数在粒子重排和合并前保存副本，
随后复制其 Ti、vtor、vpol 径向数组，不改变独立粒子的密度、质量和电荷。
缺少参考热杂质时停止。OUTPUTS/Particle_processing/thermal_reference
保存实际参考粒子的原始编号、名称、电荷和质量，界面与运行日志也显示该来源。

准中性约束
~~~~~~~~~~

所有方案都强制满足密度和密度梯度准中性，没有关闭此处理的选项。
固定 ne 及其梯度，主离子集合记为 M。各半径对所有主离子乘以同一系数，
因此保留 D/T 等多个主离子之间的密度比例：

.. math::

   \alpha = \frac{n_e - \sum_{j\notin M} Z_j n_j}{\sum_{m\in M} Z_m n_m},
   \qquad n'_m = \alpha n_m

派生梯度更新后，主离子的对数梯度加上同一个修正量：

.. math::

   \Delta g = \frac{n_e g_e - \sum_i Z_i n'_i g_i}{\sum_{m\in M} Z_m n'_m},
   \qquad g'_m = g_m + \Delta g

这里 g = -d ln(n)/dr，因而同时满足 sum(Z_i n_i)=ne 和
sum(Z_i n_i g_i)=ne ge。局部输入使用各程序一致的归一化梯度：
CGYRO 的 DLNNDR，TGLF 的 RLNS。主离子总密度为零而仍需补齐电荷或梯度时停止。
删除其他离子后恢复主离子的原密度比例，再统一校正，避免原生 del_ion 把全部电荷加给第一个离子。

全部杂质的等效参数
~~~~~~~~~~~~~~~~~~

在各半径完成局部输入的准中性校正后，对全部非主离子求和：

.. math::

   C_1 = \sum_{i\notin M} n_i Z_i,\qquad
   C_2 = \sum_{i\notin M} n_i Z_i^2,\qquad
   M_1 = \sum_{i\notin M} n_i m_i

.. math::

   Z_q = C_2/C_1,\qquad n_q = C_1^2/C_2,\qquad m_q = M_1/n_q

因此同时保持 Zq*nq、Zq^2*nq、mq*nq；主离子无需因合并而重新分配密度。
这是一种有效粒子近似，不保证杂质总粒子数不变，也不保证完整多粒子输运响应等价。
MASS、密度及温度沿用各局部文件的原生归一化；不会把原子质量单位直接填入归一化 MASS。

等效温度保持杂质总压力，密度梯度保持杂质电荷梯度，温度梯度保持压力梯度：

.. math::

   P = \sum_{i\notin M} n_i T_i,\qquad T_q=P/n_q,
   \qquad g_{nq}=\frac{\sum_{i\notin M} n_i Z_i g_{ni}}{C_1}

   g_{Tq}=\frac{\sum_{i\notin M} n_i T_i(g_{ni}+g_{Ti})}{P}-g_{nq}

每个局部计算内 Zq、mq 视为常数，gnq 由电荷梯度定义；不能对不同半径的 nq
直接求导来替代它，否则径向变化的 Zq 会破坏局部密度梯度准中性。
写入 CGYRO 的 Z / DENS / MASS / TEMP / DLNNDR / DLNTDR，
以及 TGLF 的 ZS / AS / MASS / TAUS / RLNS / RLTS，最后再次校正密度和梯度准中性。
CGYRO 的 SDLNNDR / SDLNTDR 按原生 expro 的曲率定义合并，保持电荷和压力二阶导数；
rhos/a 从本次 out.locpargen 读取。TGLF 的流速及剪切按杂质质量密度加权。
电子和主离子参数保留，删除多余粒子字段，并同步粒子数和 Zeff。

input.gacode 对每种粒子只保存一套固定 Z、MASS，而等效结果可以随半径变化。
因此 TGYRO 和原生 profiles_gen 使用完整粒子剖面，等效合并在生成局部输入后执行，
避免原生 add_ion 和 locpargen 的整数电荷写入截断小数。等效处理不扩展 TGYRO 的源剖面粒子数上限。
原生字段与曲率定义参见：

* https://gafusion.github.io/doc/cgyro/cgyro_list.html
* https://github.com/gafusion/gacode/blob/master/f2py/expro/expro_locsim.f90
* https://github.com/gafusion/gacode/blob/master/f2py/expro/expro_util.f90

全部密度须非负；仅容许浮点抵消产生的机器精度负数归零，不裁剪实际负密度。

完整剖面由 OMFIT 的 consistent_derived 更新派生量，再校正梯度；
远端生成每个半径输入后，仍由全部主离子共同校正密度、梯度及有效电荷。
TGYRO 接口保留 DEN_METHOD1=-1，以平均占比最高的主离子作为其内部参考，
电子和其他离子不演化密度；这不改变多主离子识别或最终局部输入的共同校正规则。
CALC_FLAG / THERM_FLAG 按当前粒子组成同步。
参数定义参见 https://gafusion.github.io/doc/tgyro/tgyro_list.html 。

生成结果与传递
~~~~~~~~~~~~~~

原始 INPUTS/input.gacode 保留以便切换方案；处理后的剖面保存在
OUTPUTS/Profiles_gen/input.gacode 和 Transfer_file/input.gacode。
等效方案下，这两个 input.gacode 保留生成所用的完整粒子组成；实际合并结果在各半径的
input.cgyro / input.tglf 中，而不在这两个剖面文件中。
OUTPUTS/Particle_processing 记录识别规则、半径区间、全部主离子及平均 ni/ne、
前后粒子组成、合并与独立热化的处理记录、密度及梯度残差、
Zeff 变化、压力最大相对变化及每个局部输入的校正残差。
等效方案的 local_inputs/input.<程序>_<半径序号>/equivalent 还记录所有来源粒子、
该半径 Z / N / MASS 等实际参数，以及合并前后的电荷、Zeff 分子、质量、压力和梯度残差。
热化与粒子简化一般改变压力、碰撞性或热输运模型；几何和径向网格不做更换。

“生成结果与传递”选择本次半径输入送入 CGYRO / TGLF；TGLF 覆盖由用户选择。
切换粒子方案或主离子识别半径后必须重新生成，旧版单主离子或选择代表杂质的结果也须重新生成后才能传递。
流程异常时恢复旧输出及本次改变的输入，成功时将上一轮输出归档。

“局部输入互转”是转换已有局部输入的独立页；上述粒子预设用于剖面生成。
“高级设置”编辑 Transfer_tool 的种子输入，缺少时自动使用内置种子。
统一计算环境仍在工程总控“环境配置与记录”中配置。
