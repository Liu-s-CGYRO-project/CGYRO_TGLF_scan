# CGYRO 扫描取值

GUI 位于“CGYRO 扫描 → 输入与扫描 → 扫描设置”。列表输入沿用 OMFIT 原生数值表达式：填入 `np.linspace(0.1, 1.0, 10)` 并回车后，保存并显示实际数值。也可使用 `np.arange`、`np.logspace` 或实际列表。

ky 可选列表、线性范围、对数范围。参数轴可选列表、实际值范围、原值倍数、沿用输入。范围以起点、终点、点数定义，包含端点；点数为 1 时只取起点。原值倍数按各半径和主离子方案的输入分别计算。整数参数要求每个结果为整数，不自动取整。

## 程序接口

`LIB/OMFITlib_cgyro_scan_values.py` 提供无 GUI、无作业提交的接口：

```python
from OMFITlib_cgyro_scan_values import ky_values, scan_axes

physics = root['CGYRO_scan']['SETTINGS']['PHYSICS']
ky = ky_values(physics)
axes = scan_axes(physics, dimensions=1, source=input_cgyro)
```

预检查与实际提交共用此接口。返回的轴保留 `name`、实际 `values` 和 `linked`；不改写原始输入或计算数据。旧工程未设置新定义时，继续读取 `kyarr` 和 `1d/Range`、`2d/Range_x` 等原有列表。

新定义存储在同一个 PHYSICS 分支：

```python
physics['ky_spec'] = {'mode': 'range', 'start': 0.1, 'end': 1.0, 'count': 10}
physics['1d']['value_specs'] = {
    'Range': {'mode': 'range', 'start': 16, 'end': 64, 'count': 4}
}
```

`mode='list'` 使用原有实际列表，也接受单值；`mode='original'` 使用输入原值。倍数定义使用独立的 `factor` 范围，切换方式时分别保留实际范围和倍数范围：

```python
physics['1d']['value_specs']['Range'] = {
    'mode': 'factor',
    'factor': {'start': 1.0, 'end': 3.0, 'count': 3}
}
```

ky 的对数范围用 `mode='log'`，起止值直接填写实际正数。点数限制为 1–10000；非有限值、重复值、非正 ky、非整数的整数参数和联动长度不匹配会在提交前报错。任务与结果清单保存实际使用的值。

## H / D / T 主离子合并

H/D/T 案例先合并已识别的全部 Z=1 主离子，再将合并后的质量设为 0.5、1.0、1.5（氘质量归一化）。未被识别为主离子的粒子不参与此合并。BASE 保留原组成，源输入始终保留。

合并密度为 `sum(n_i)`，温度为 `sum(n_i*T_i)/sum(n_i)`。密度梯度按密度加权，温度梯度由总压力梯度减去合并密度梯度得到，不直接平均各温度梯度。杂质、电子及原 Zeff 设置保留，N_SPECIES 和十种原生粒子字段同步重新编号。粒子扫描轴和启用的固定参数按原编号映射；同时指向合并主离子的多个轴或不一致固定值会报错，避免静默覆盖。原值倍数以合并后的实际输入为基准。

`LIB/OMFITlib_cgyro_isotopes.py` 提供 `isotope_input(source, mass, main_indices, rhostar=None, global_curvature=False)` 和 `remap_physics(physics, dimensions, mapping)`。返回独立输入和包含原编号、新编号、参数与规则的记录；案例准备、预检查及提交使用同一接口。局部输入要求 PROFILE_MODEL=1；非 1 的粒子梯度倍率需要先折算进源输入。

新版 Transfer_tool 记录原生 locpargen 的 rhos/a，按 expro 的有效曲率定义还原并合并密度和压力二阶导数。旧等效杂质记录中的 rhostar 也可复用。旧输入缺少该尺度时，仅允许 GLOBAL_FLAG=0 的局部扫描，未使用的曲率字段保留加权值；全局扫描会要求重新生成输入，不猜测尺度。N_GLOBAL 只控制全局输出分辨率，不能据此判断是否启用全局剖面变化。

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
