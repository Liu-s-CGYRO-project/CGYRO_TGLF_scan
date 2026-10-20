# CGYRO 扫描取值

GUI 位于“CGYRO 扫描 → 输入与扫描 → 扫描设置”。列表输入沿用 OMFIT 原生数值表达式：填入 `np.linspace(0.1, 1.0, 10)` 并回车后，保存并显示实际数值。也可使用 `np.arange`、`np.logspace` 或实际列表。

ky 可选列表、线性范围、对数范围。参数轴可选列表、实际值范围、原值倍数、沿用输入。范围以起点、终点、点数定义，包含端点；点数为 1 时只取起点。原值倍数按各半径和主离子方案的输入分别计算。整数参数要求每个结果为整数，不自动取整。

## 远程批量排队

“运行所选扫描”对 Slurm / PBS 的多个案例先全部提交，再等待并分别收集。例如选择一个半径的 H / D / T，会先得到三个作业号，不等待 H 结束才提交 D 和 T。队列决定实际开跑顺序和并行程度；Slurm 并发点数是每个案例数组的上限，多案例总并发可能更高。

RUN_BATCH 关联本批计划与 token，RUN_HISTORY 保存各例的独立目录、点表、作业号和未归档数据。“同步作业状态”同步整批 Slurm 作业，“重新收集未归档结果”继续等待与收集未归档例。Slurm 等待窗口的 Kill local 请求取消本批未结束作业，并停止本地等待；失败可重试。部分失败保留其他任务与成功结果，完整收集后才覆盖同一案例、相同扫描参数组的旧结果。

本地计算继续同步运行，重启只允许一个案例。该排队方式不会更改已提交的旧任务。

### 不同参数追加，同一参数重扫覆盖

同一结果名（如 Jet）、半径和 H / D / T 案例下，先扫描 N_THETA、再扫描 N_ENERGY，会并列保存两个分支。绘图仍先选半径、再选离子，然后选择 N_THETA 或 N_ENERGY。完整重扫 N_THETA 只替换 N_THETA 的旧取值及 ky 结果，不删除 N_ENERGY；新的取值列表不与同参数旧列表拼接。

扫描身份按有序参数轴及联动参数确定，不包含取值、ky 网格和运行 UUID。二维 / 三维组合单独保存（例如 N_THETA__N_ENERGY），不会覆盖一维 N_THETA；仅 ky 扫描使用 KY_ONLY。背景固定参数变化仍视为该扫描组的重扫；若需要并列对比不同背景设置，请使用不同结果名。

每个扫描的任务表和运行记录位于 RUN_DB/结果名/案例/__SCANS__/扫描键/tasks 和 info。结果浏览器按参数组列出记录，ky 续算仅修改所选记录的点；另一参数组的 p000001 不与它混用。旧单记录案例在下次归档时迁移，仍存在的旧 UUID 案例按扫描组合合并。

更新不会凭空恢复旧版本已覆盖的数据。RUN_HISTORY 中归档后的记录通常只有目录和运行信息，重复结果副本及点表已移除；恢复需要仍存在的原结果目录及对应 manifest.json（含点表），或覆盖前保存的工程。不要把“重新收集未归档结果”当作所有已归档历史扫描的恢复入口，也不要用当前 GUI 参数重建旧运行的坐标。

### 偶发失败重试

运行页“失败点重试次数”可填 0–3，默认 2，0 关闭自动补算。服务器确认作业已结束后，仅对可重试的失败点用原始输入补跑，使用新目录；成功点仍从原目录读取，全部点完整后才归档。手动取消、超时、内存不足、明确输入 / 积分错误不反复提交；参数和资源不自动修改。读取或网络错误最多重读两次，先核实提交日志取得作业号，不能确认时保留状态并阻止盲目重复提交。

Slurm 补跑保持原数组索引，并用 `--array=失败索引列表%并发上限` 选择失败点，参见 [sbatch](https://slurm.schedmd.com/sbatch.html)；PBS 生成只含失败点的列表。各轮作业号、目录和状态进入 attempts，point_workdirs 标记每个点的实际结果来源，原目录和日志均保留。

程序接口与扩展示例见 GitHub 仓库根目录 [SCAN_VALUES_REFERENCE.md](https://github.com/Liu-s-CGYRO-project/CGYRO_TGLF_scan/blob/main/SCAN_VALUES_REFERENCE.md)。预检查与实际提交共用 cgyro_scan_values，返回实际轴取值，不改原始输入。

## H / D / T 主离子合并

H/D/T 案例先合并已识别的全部 Z=1 主离子，再将合并后的质量设为 0.5、1.0、1.5（氘质量归一化）。未被识别为主离子的粒子不参与此合并。BASE 保留所选局部输入的组成；如果 Transfer_tool 已使用分离快粒子的合并方案，BASE 也使用合并后的主离子。源输入始终保留。

合并密度为 `sum(n_i)`，温度为 `sum(n_i*T_i)/sum(n_i)`。密度梯度按密度加权，温度梯度由总压力梯度减去合并密度梯度得到，不直接平均各温度梯度。杂质、电子及原 Zeff 设置保留，N_SPECIES 和十种原生粒子字段同步重新编号。粒子扫描轴和启用的固定参数按原编号映射；同时指向合并主离子的多个轴或不一致固定值会报错，避免静默覆盖。原值倍数以合并后的实际输入为基准。

`LIB/OMFITlib_cgyro_isotopes.py` 提供 `isotope_input(source, mass, main_indices, rhostar=None, global_curvature=False)` 和 `remap_physics(physics, dimensions, mapping)`。返回独立输入和包含原编号、新编号、参数与规则的记录；案例准备、预检查及提交使用同一接口。局部输入要求 PROFILE_MODEL=1；非 1 的粒子梯度倍率需要先折算进源输入。

新版 Transfer_tool 记录原生 locpargen 的 rhos/a，按 expro 的有效曲率定义还原并合并密度和压力二阶导数。旧等效杂质记录中的 rhostar 也可复用。旧输入缺少该尺度时，仅允许 GLOBAL_FLAG=0 的局部扫描，未使用的曲率字段保留加权值；全局扫描会要求重新生成输入，不猜测尺度。N_GLOBAL 只控制全局输出分辨率，不能据此判断是否启用全局剖面变化。

## 热主离子与等效辅助物种

在“输入准备与转换 → Transfer_tool 运行”选择“仅保留主离子和等效杂质”，再选择“辅助温度 → 温度随热主离子”，即使用热燃料稀释模型。重新生成半径输入后，在 CGYRO 扫描中选择 H / D / T，得到“电子 + 一种热主离子 + 一种等效辅助物种”。Transfer 生成阶段仍保留热 D / T 各自的参数，BASE 也保留这些热主离子；它们在 H/D/T 案例准备时合并。

等效方案的主离子需同时满足：源 `input.gacode` 中类型为 `therm`、电荷为 1、质量接近 H/D/T（原子质量单位 1/2/3，允许与整数相差小于 0.05），且所选半径区间平均 `ni/ne > 30%`。不按名称或温度猜测快离子。原始副本的准中性补偿也使用这一候选规则；所有粒子先保留，校正后再识别最终主离子。因此快 D/T、少量 H/D/T、Be、Ni、He 等都进入辅助组，不会加入热主离子密度。没有符合条件的热主离子时停止，不能把高密度快离子当作回退。下述分离快粒子方案也使用这一热主离子识别规则；保留全部、热化和仅主离子方案继续使用各自的原有规则。

每个局部半径按辅助组计算 `C1=sum(Zj*nj)`、`C2=sum(Zj**2*nj)`，设 `Zz=C2/C1`、`nz=C1**2/C2`、`mz=sum(nj*mj)/nz`。辅助密度梯度为 `gnz=sum(Zj*nj*gnj)/C1`；这些 Z、质量在每次局部计算内视为常数。热主离子保留校正后的稀释份额，**不补成 ni/ne=1**。Zeff 由完整组成计算，不使用源文件的独立 z_eff 字段。

辅助温度有两种约定：

| 界面选项 | 温度与温度梯度 | 压力处理 |
| --- | --- | --- |
| 保留原总压力（默认） | `Tz=sum(nj*Tj)/nz`；`gTz=sum(nj*Tj*(gnj+gTj))/sum(nj*Tj)-gnz` | 保留辅助组压力及其梯度 |
| 温度随热主离子 | `Tz=Tm=sum(ni*Ti)/sum(ni)`；`gTz=gTm` | 保留电荷、Zeff 贡献、质量和电荷密度梯度；总压力随新温度改变 |

热主离子温度不同时，`gnm=sum(ni*gni)/sum(ni)`、`gTm=sum(ni*Ti*(gni+gTi))/sum(ni*Ti)-gnm`。该定义与 H/D/T 合并共用同一物理约定；不能简单平均温度梯度。CGYRO 还原原生有效曲率后保留辅助组电荷密度二阶导数，温度随热主离子时采用合并热主离子的温度二阶导数，随后恢复有效曲率。最后复查密度、密度梯度与二阶密度准中性，同步已存在的 SBETA / P_PRIME_LOC；电子量、原平衡几何和碰撞模型沿用输入。此为局部等效模型，不是对热化后平衡的重新求解。

H/D/T 扫描只改变合并热主离子的质量 0.5/1/1.5，辅助组采用同一套参数；显式设置其他扫描轴或固定参数时仍按用户设置执行。快粒子原来的高温及其完整动力学响应不保留，辅助物种仍有普通热压力。

设置保存在 `PHYSICS/generation/equivalent_temperature`（`pressure` / `main_ion`），生成时冻结进 `OUTPUTS/Particle_processing/options`。局部记录 `local_inputs/input.cgyro_N/equivalent`（TGLF 同理）包含 `sources`、`thermal_main_reference`、最终 `parameters`、守恒项及残差、辅助组前后矩和 `total_pressure_change`。完整剖面图仍表示局部合成前的组成，最终等效物种以局部输入和这些记录为准。切换约定或从旧等效规则升级后需要重新运行 Transfer_tool，不改写历史结果。

程序接口为 `equivalent_local_input(value, kind, main_count, expected_ions, rhostar=None, temperature_mode='pressure')`。`expected_ions` 使用本轮完整的粒子来源记录，不能仅传入电荷列表；温度选项从冻结记录传入，不从运行中的 GUI 重读。上述合并公式是模型约定；字段归一化遵循 [GACODE 参数定义](https://gacode.io/cgyro/cgyro_list.html#cgyro-dlnndr)，曲率遵循下述 expro 源码约定。

## 主离子、等效杂质与等效快粒子

在“输入准备与转换 → Transfer_tool 运行 → 处理方案”选择 **“主离子 / 等效杂质 / 等效快粒子”**，重新运行 Transfer_tool。程序先对完整源剖面的副本做准中性处理，再在每个半径生成“电子 + 一种热主离子 + 一种等效热杂质 + 一种等效快粒子”。从 1.22.19 起，此方案假设热杂质与主离子近似热平衡，采用同温处理；快粒子独立保留压力。原先把所有非主离子合成一个辅助物种的方案仍可选。

| 组别 | 来源 | 处理 |
| --- | --- | --- |
| 电子 | 原电子 | 密度、温度及梯度保留 |
| 主离子 | 按上述规则识别的热 H/D/T | 全部合为一个，保留校正后的总密度份额和总热压力 |
| 等效热杂质 | 其余 `therm` 离子，包括低于主离子阈值的少量 H/D/T | 保留电荷、Zeff 贡献和质量密度，温度及温度梯度随主离子 |
| 等效快粒子 | 全部 `fast` 离子，包括快 D/T | 单独合成一个等效物种，保留本组压力 |

按源文件的 `therm` / `fast` 标记分组，不根据名字或温度猜测。没有杂质或快粒子，或某个半径对应组的密度全部为零时，省略该辅助组；不添加零密度占位物种。主离子必须存在。空组可能使不同半径的物种总数不同，实际编号以该半径的记录为准。

三组离子各自计算 `C1=sum(nj*Zj)`、`C2=sum(nj*Zj**2)`，先确定：

```text
Zeq = C2 / C1
neq = C1**2 / C2
Meq = sum(nj*Mj) / neq
gne = sum(nj*Zj*gnj) / C1
```

因此各组分别保持电荷密度、Zeff 贡献、质量密度和电荷密度梯度。温度采用不同约定：

| 组别 | 温度 | 温度梯度 |
| --- | --- | --- |
| 主离子 | `Ti=sum(nj*Tj)/sum(nj)`，只使用热主离子 | `gTi=sum(nj*Tj*(gnj+gTj))/sum(nj*Tj)-gni` |
| 等效热杂质 | `TZ=Ti` | `gTZ=gTi`；密度梯度仍使用杂质组自己的 `gne` |
| 等效快粒子 | `Tf=sum(nj*Tj)/nf`，只使用快粒子组 | `gTf=sum(nj*Tj*(gnj+gTj))/sum(nj*Tj)-gnf` |

主离子均为 Z=1，合并密度就是密度之和；不把主离子补成 `ni/ne=1`。温度梯度由合并温度的乘积 / 商求导规则确定，不直接平均各物种的温度梯度。BASE 使用密度加权的主离子质量。H/D/T 扫描只把该主离子的质量改为 0.5/1/1.5（氘质量归一化），等效杂质和等效快粒子保持一致；用户显式设置的其他扫描轴或固定参数照常生效。快粒子不并入热主离子，也不设为热主离子温度。

热主离子和快粒子分别保持本组压力及压力梯度。热杂质同温后 `PZ_new=nZ*Ti`，`delta_PZ=nZ*Ti-sum(nj*Tj)`，压力梯度也一般改变，**不再要求热杂质或总压力矩守恒**。电子参数、电子 BETAE_UNIT / BETAE、热主离子温度和快粒子压力不用于补偿差额。Zeff 由准中性校正后的完整粒子组成计算，不使用源文件独立的 `z_eff` 值。

CGYRO 还原有效曲率后，三组均保持自身电荷密度二阶导数；主离子和快粒子还保持压力二阶导数。热杂质温度二阶导数随合并主离子，但不保留原杂质压力二阶导数。恢复有效曲率时使用新的温度梯度，不能直接复用旧有效 SDLNNDR。TGLF 的平行流速及流速剪切仍按质量密度加权。最后从实际写入字段复核各组相应守恒项及温度约束，检查密度、密度梯度和 CGYRO 密度曲率准中性；已有 SBETA / P_PRIME_LOC 按改变后的粒子参数同步。这是更新派生压力导数，不是恢复旧压力或重新求解平衡。

生成后控制台和“处理方案”旁的帮助逐半径列出 `P=sum(n*T)`、`G=sum(n*T*(gn+gT))` 的前后值、带符号差值与变化比例。比较基准是已经完成准中性校正、尚未合并的完整局部组成；P 和 G 使用该输入的原生归一化，G 表示相应长度归一化下的负压力径向导数。比例为 `(after-before)/abs(before)`；原值为零或比例无法有限表示时记为 `None`，仍保留实际差值，不伪造零变化。所有总变化必须等于热杂质组贡献的变化，否则停止生成。程序不设任意物理可接受阈值，也不自动补偿；若偏差不可忽略，应分别保留轻 / 重杂质（可用“保留所有粒子”），而不是强求单个杂质满足所有压力约束。

CGYRO 的顺序为主离子、等效杂质（若有）、等效快粒子（若有）、电子；TGLF 为电子、主离子、等效杂质、等效快粒子。分数电荷和质量在 locpargen 完成后写入局部输入，避免原生完整剖面文件的整数电荷写出限制。原始完整剖面和已归档计算结果保留。

设置为 `PHYSICS/generation/particle_mode='separate_fast'`，规则更新为 `merged_thermal_main_thermal_impurity_fast_pressure_v2`；1.22.18 的旧生成结果需重新运行 Transfer_tool，不改写历史归档。来源及最终参数保存在 `OUTPUTS/Particle_processing/local_inputs/input.cgyro_N/equivalent/groups`（TGLF 同理），三个键为 `main`、`impurity`、`fast`；每组有 `sources`、`before`、`after`、`parameters`、`conserved_moments`、`residuals`、`temperature_residuals`、`pressure_change`、`pressure_gradient_change`、`omitted` 和最终 `solver_index`。热杂质守恒清单不包含压力及其导数。上层 `equivalent` 保存 `thermal_main_reference`、`total_pressure_change`、`total_pressure_gradient_change`、`pressure_budget_residuals` 和 `electron_beta`。局部输入自身的 `main_count=1` 用于 H/D/T 扫描，不能使用完整剖面阶段原有的主离子数量。程序接口仍为 `separate_fast_local_input(value, kind, main_count, expected_ions, rhostar=None)`。

完整剖面图仍显示局部合成前的源粒子，局部快粒子压力和 KBM / BAE 热快驱动分组使用记录中的最终编号。原 ITG / ETG 解析估算依赖单个源热离子的剖面，不适用于此合并方案，界面会提示使用保留粒子的生成结果。等效物种仍是由温度描述的近似，保留上述矩不等于保留完整的慢化能谱、各向异性或各源物种独立响应。局部 Z、MASS 视为常量，不对相邻半径的等效 Z、MASS 作剖面求导。字段单位遵循 [input.gacode 定义](https://gacode.io/input_gacode.html)、[CGYRO 参数](https://gacode.io/cgyro/cgyro_list.html)及 [TGLF 参数](https://www.gacode.io/tglf/tglf_list.html)。

热杂质同温是使用者选定的热平衡近似，不适用于所有原始剖面。[Brioschi 等，2025，§3.1](https://iris.cnr.it/retrieve/d03da7f0-3d8d-4167-a48c-6cffec546ace/Brioschi_2025_Nucl._Fusion_65_026054.pdf)对其分组的低 Z 和中高 Z 杂质也采用与主离子热化的假设；该文只支持此建模约定，不证明本程序单个等效杂质没有误差，也不作为本程序快粒子保压公式的数值验证。

## 完整粒子组成的 Zeff 与剪切

Transfer_tool 先在原始完整剖面的副本上做准中性校正，固定 ne 和非主离子密度，由初步识别的主离子按原比例承担电荷补偿，同时闭合密度梯度。此时不删除、合并、重排或热化任何粒子；原始载入文件不覆盖。然后在校正后的完整剖面上识别方案主离子，GUI 预览使用同一路径。“仅保留主离子和 Zeff”由此完整组成按 `sum(ni*Zi**2)/ne` 计算并保存 Zeff，不读取输入文件现成的 `z_eff`。再删除非主离子，将 Z=1 主离子的总密度补齐为 ne，并保持其相对比例，因此局部输入中的主离子密度和为 1。保留的 Zeff 按 rmin/a 使用与 expro 一致的自然三次样条，生成每个半径的 ZEFF / Z_EFF；不将其混入纯主离子剖面的电荷闭合。原始完整剖面的准中性记录、网格、计算公式、实际局部 Zeff 和模型均有独立记录。

CGYRO 同时写入 `Z_EFF_METHOD=1` 和所选 `COLLISION_MODEL=1` 或 `5`（默认 1）。后续固定参数或扫描将其改为不支持的组合时，在作业提交前停止；不会把模型 4 当作支持独立 Zeff。旧的 `main_only_recomputed` 设置和脚本参数自动迁移为 `main_only`，不再保留单独的重算 Zeff 分支。Zeff 规则升级为 `source_neutral_composition_zeff_v3`，所有旧顺序结果需重新生成。HDT 的合并副本保留指定 Zeff 和碰撞模型。

所有粒子方案均先校正完整源剖面，再执行方案，并在各半径插值后再次校正。CGYRO 用原生 rhos/a 还原 SDLNNDR 的有效梯度项，按共同主离子密度倍率的乘积求导规则闭合二阶密度导数，然后恢复有效曲率；SBETA 和 TGLF 的 P_PRIME_LOC 同步压力导数。生成局部输入的全部变换完成后，再独立读取字段检查密度、梯度和 CGYRO 原生密度曲率，Zeff 不参与电荷求和。新 neutrality_rule 使旧生成记录失效；不改写已保存的历史计算结果。

CGYRO 的 `GAMMA_E` 已列入“平衡与剪切”，可直接编辑或扫描，`Z_EFF` / `Z_EFF_METHOD` 位于“场与碰撞”。GAMMA_E 的求解器作用仍遵循 CGYRO 的线性 / 非线性模型，界面不改写这些模型。

定义依据：[CGYRO 原生参数](https://github.com/gafusion/gacode/blob/27b63e321c8474a6a4bd1198dc586da9c393fd0b/cgyro/bin/cgyro_parse.py)、[有效曲率](https://github.com/gafusion/gacode/blob/27b63e321c8474a6a4bd1198dc586da9c393fd0b/f2py/expro/expro_locsim.f90)、[指定 Zeff 的模型条件](https://github.com/gafusion/gacode/blob/27b63e321c8474a6a4bd1198dc586da9c393fd0b/cgyro/src/cgyro_make_profiles.F90#L257)。

## 参数帮助接口

“计算参数”旁的“?”及扫描轴参数的帮助共用 `LIB/OMFITlib_cgyro_parameter_help.py`。常用参数逐项列出可输入的数值 / 枚举值、含义、单位 / 归一化和生效条件；粒子编号字段共用 `SPECIES_HELP`，形状谐波按前缀识别。新增说明在 `PARAMETER_HELP` 追加 `(可输入值, 含义, 单位, 条件)` 元组即可，不需修改 GUI 或求解器。未核对的扩展参数明确标注未收录含义，不按名称编造。

```python
from OMFITlib_cgyro_parameter_help import parameter_help
text = parameter_help('EQUILIBRIUM_MODEL')
```

说明为随包提供的中文数据，离线可用；“?”使用可滚动窗口，较长的说明不会被截断。输入框继续只接受参数值，物理解释不混入数值字段。Z_EFF_METHOD 采用普通数值输入框，填 1 或 2，回车生效。

来源为 [官网字母索引](https://gacode.io/cgyro/cgyro_list.html)、[归一化与分类表](https://gacode.io/cgyro.html)、[旋转定义](https://gacode.io/rotation.html)，并核对上述固定源码版本。官网部分默认值与新版源码不同，界面不据网页强行修改源输入或 GUI 参考值；输入值和参考值在帮助末尾单独显示。EQUILIBRIUM_MODEL 的官网旧项 3 与新版仅接受 1 / 2 的差异已标注；新版模型 2 为 Miller Extended Harmonic（MXH）。COLLISION_MODEL 的 6 / 7 也注明版本限制。

重要生效条件包括：线性计算不使用 GAMMA_E；独立指定 Zeff 需要 Z_EFF_METHOD=1 和碰撞模型 1 / 5；多数实验剖面倍率只对 PROFILE_MODEL=2 生效，局部输入应直接调整对应物理量。帮助说明输入约定，不替代服务器自身的版本检查与数值收敛检查。
