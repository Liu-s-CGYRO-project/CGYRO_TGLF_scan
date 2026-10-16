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
