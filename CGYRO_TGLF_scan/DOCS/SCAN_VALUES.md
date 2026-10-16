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

新版 Transfer_tool 记录原生 locpargen 的 rhos/a，按 expro 的有效曲率定义还原并合并密度和压力二阶导数。旧等效杂质记录中的 rhostar 也可复用。旧输入缺少该尺度时，仅允许 N_GLOBAL=0 的局部扫描，未使用的曲率字段保留加权值；全局扫描会要求重新生成输入，不猜测尺度。

## 原剖面 Zeff 与剪切

Transfer_tool“仅保留主离子”将 Z=1 主离子的总密度补齐为 ne，保持其相对比例，因此局部输入中的主离子密度和为 1。删除杂质前保存原剖面 z_eff，缺失时按原完整组成计算。按 rmin/a 使用与 expro 一致的自然三次样条，生成每个半径的 ZEFF / Z_EFF；不将被保留的有效 Zeff 混入纯主离子剖面的电荷闭合。原始网格、实际局部 Zeff 和模型均有独立记录。

CGYRO 同时写入 `Z_EFF_METHOD=1` 和所选 `COLLISION_MODEL=1` 或 `5`（默认 1）。后续固定参数或扫描将其改为不支持的组合时，在作业提交前停止；不会把模型 4 当作支持独立 Zeff。旧版的按剩余组成重算行为保留为独立方案。HDT 的合并副本保留指定 Zeff 和碰撞模型。

CGYRO 的 `GAMMA_E` 已列入“平衡与剪切”，可直接编辑或扫描，`Z_EFF` / `Z_EFF_METHOD` 位于“场与碰撞”。GAMMA_E 的求解器作用仍遵循 CGYRO 的线性 / 非线性模型，界面不改写这些模型。

定义依据：[CGYRO 原生参数](https://github.com/gafusion/gacode/blob/27b63e321c8474a6a4bd1198dc586da9c393fd0b/cgyro/bin/cgyro_parse.py)、[有效曲率](https://github.com/gafusion/gacode/blob/27b63e321c8474a6a4bd1198dc586da9c393fd0b/f2py/expro/expro_locsim.f90)、[指定 Zeff 的模型条件](https://github.com/gafusion/gacode/blob/27b63e321c8474a6a4bd1198dc586da9c393fd0b/cgyro/src/cgyro_make_profiles.F90#L257)。
