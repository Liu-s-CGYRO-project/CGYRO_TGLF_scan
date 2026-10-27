"""Concise Chinese notes checked against GACODE documentation, 2026-10-27.

The web manual and parser are not always from the same solver version. Describe
that difference instead of changing the user's input to a documentation default.
Everything here is local text; opening a help button never queries the network.
"""
from builtins import bool, int, isinstance, str
from OMFITlib_tglf_parameters import FIELDS, SPECIES_PATTERN, field_spec, scalar

DOC_URL = 'https://gacode.io/tglf/tglf_list.html'
TABLE_URL = 'https://gacode.io/tglf/tglf_table.html'
CODE_URL = 'https://github.com/gafusion/gacode/blob/master/tglf/bin/tglf_defaults.py'

# Meaning, units/normalization, activation or interpretation. Facts are written
# in our own words; species and shape families share notes, not repeated prose.
HELP = {
    'SAT_RULE': ('选择从线性模态到湍流输运通量的饱和模型。', '整数模型编号。',
        '0：SAT0；1：包含 ky 耦合的 SAT1；2：改进几何和 TEM 处理的 SAT2；3：进一步区分 ITG/TEM 饱和的 SAT3。可用版本取决于服务器 GACODE；它不是数值精度等级。'),
    'KYGRID_MODEL': ('选择输运计算的 ky 谱网格。', '整数 0–5，具体支持以所用版本为准。',
        '0：从 KY/NKY 到 KY 的 NKY 个等间距点；1：常用谱；2、3：源码保留的谱选项；4：增加低 ky 点，常用于 SAT2；5：源码中的扩展网格。非 0 模型的总点数不一定等于 NKY。'),
    'KY': ('单模计算的 kθρ_s,unit；网格模型 0 中作为最大 ky。', '无量纲波数。',
        '当前工作台使用输运模型。扫描 KY 时需结合 KYGRID_MODEL；标准谱模型并非都使用 KY 作为最大波数。'),
    'NKY': ('控制 ky 谱的离散点数。', '整数点数。',
        'KYGRID_MODEL=0 时为总点数；常用标准谱中控制高 ky 段，另有固定低 ky 段，因此输出谱点数可能更多。'),
    'NMODES': ('按增长率排序时保留的本征模数。', '正整数。', '与 IBRANCH=-1 配合；不是 ky 点数。'),
    'NBASIS_MIN': ('平行方向 Hermite 基展开的最少基函数数。', '正整数。', '与 NBASIS_MAX 共同控制模态求解。'),
    'NBASIS_MAX': ('平行方向 Hermite 基展开的最多基函数数。', '正整数。', '可做基函数收敛扫描；增加时计算成本也增加。'),
    'NXGRID': ('Gauss-Hermite 求积的节点数。', '正整数。', '是积分分辨率，不是径向空间网格。'),
    'WIDTH': ('平行 Hermite 展开的高斯权函数宽度。', 'TGLF 归一化宽度。', 'FIND_WIDTH=True 时是搜索上限；False 时直接使用此宽度。'),
    'WIDTH_MIN': ('寻找最大增长率时的宽度搜索下限。', 'TGLF 归一化宽度。', '与 WIDTH、FIND_WIDTH 配合。'),
    'NWIDTH': ('模态宽度搜索使用的最大宽度数。', '正整数。', '仅在进行宽度搜索时有意义。'),
    'FIND_WIDTH': ('是否寻找增长率最大的模态宽度。', 'True / False。', '关闭后使用 WIDTH 给定值。'),
    'USE_BISECTION': ('选择二分法搜索最不稳定模态的宽度。', 'True / False。', '用于 FIND_WIDTH 开启时的宽度搜索。'),
    'IBRANCH': ('决定如何选择和排序不稳定模态。', '整数选择器。', '−1：按增长率排序；0：分别寻找电子、离子抗磁漂移频率方向最不稳定的模态。'),
    'USE_AVE_ION_GRID': ('用平均离子尺度构造 ky 网格。', 'True / False。', '多离子输运谱选项；实际网格还取决于 KYGRID_MODEL 和物种参数。'),
    'USE_BPER': ('保留与平行矢势 δA∥ 对应的横向磁扰动。', 'True / False。', '电磁模型开关；其耦合还取决于 BETAE。'),
    'USE_BPAR': ('保留压缩磁扰动 δB∥。', 'True / False。', '官方说明提醒该分量受有限矩模型限制，某些情形与回旋动理学线性结果不一致。'),
    'BETAE': ('以 B_unit 定义的电子 beta。', '无量纲比值；不是百分数。', '控制电磁耦合；需结合 USE_BPER、USE_BPAR。'),
    'XNUE': ('电子–离子碰撞频率 ν_ei。', '以 c_s/a 归一化，即 ν_ei·a/c_s。', '与 XNU_MODEL 的碰撞模型配合，不能直接填写 Hz。'),
    'ZEFF': ('有效离子电荷数。', '无量纲，Zeff=Σ n_i Z_i²/n_e。', '应与密度和电荷组成相容；不同碰撞实现对它的使用取决于版本。'),
    'XNU_MODEL': ('选择电子碰撞模型。', '整数模型编号。', '官方常用搭配：SAT0/SAT1 用 2，SAT2 用 3；不是碰撞频率倍率。'),
    'XNU_FACTOR': ('缩放俘获/通过边界的电子–离子碰撞项。', '无量纲倍率。', '不是对所有碰撞项统一乘倍数；整体碰撞频率使用 XNUE。'),
    'DEBYE': ('Debye 长度相对声回旋半径的比值。', 'λ_D/ρ_s。', '不要直接填写米；有效值还受 DEBYE_FACTOR 影响。'),
    'DEBYE_FACTOR': ('对 DEBYE 指定的长度比乘以该系数。', '无量纲倍率。', '1 保留原值。'),
    'USE_MHD_RULE': ('是否忽略曲率漂移中的压力梯度贡献。', 'True 忽略，False 保留。', '官方对高 beta 情形建议 False；并非总的 MHD 模式开关。'),
    'ADIABATIC_ELEC': ('使用绝热电子响应代替完整动理学电子响应。', 'True / False。', '可用于识别 ITG/TEM 贡献；不适用于需要俘获电子动力学的 TEM 描述。'),
    'USE_INBOARD_DETRAPPED': ('模态向内侧鼓包时将模型中的俘获份额设为零。', 'True / False。', '只影响满足该模态条件的计算。'),
    'THETA_TRAPPED': ('调整俘获粒子份额模型的参数。', '模型的无量纲系数。', '它不是输入磁面上的极向观测角。'),
    'WDIA_TRAPPED': ('俘获粒子抗磁漂移响应的模型控制量。', '无量纲系数。', 'OMFIT 的 SAT2 场景取 1；独立输入解析器默认 0。保留实际输入或明确选定的场景值。'),
    'ALPHA_ZF': ('控制带状流混合强度。', '无量纲系数。', '用于 SAT1/2/3；官方还说明 −1 的特殊处理可避免非物理的最低 ky 主导，不能视作一般负混合率。'),
    'ETG_FACTOR': ('ETG 饱和规则中的指数参数。', '无量纲指数。', '改变它会改变饱和模型，不是增加电子温度梯度。'),
    'RLNP_CUTOFF': ('限制饱和模型使用的归一化压力梯度。', '无量纲压力逆梯度尺度。', '源码用于 SAT2/3 的压力梯度处理；正值截断上限，非正值进入固定参考分支，不等于关闭全部压力效应。'),
    'VPAR_MODEL': ('选择平行流处理模型。', '整数模型编号。', '官方文档的 0 为低 Mach 数近似。'),
    'VPAR_SHEAR_MODEL': ('旧版平行流剪切模型选择器。', '整数。', '官方文档已标为弃用；保留旧输入兼容，扫描它未必改变当前版本结果。'),
    'VEXB': ('旧接口中的公共 ExB Doppler 速度。', 'TGLF 归一化速度。', '官方标记为未使用，流速度应查看 VPAR_i；不是 VEXB_SHEAR。'),
    'VEXB_SHEAR': ('公共环向 ExB 速度的径向剪切。', '−SIGN_IT·(r/|q|)·d(V_ExB/R)/dr·a/c_s。', '是带符号的无量纲量；有效剪切还受 ALPHA_E 等模型设置影响。'),
    'ALPHA_MACH': ('对所有粒子的平行速度乘以该系数。', '无量纲倍率。', '0 移除此速度贡献，1 使用输入值；不等于设置剪切。'),
    'ALPHA_E': ('缩放谱移位模型使用的 ExB 速度剪切。', '无量纲倍率。', '与 VEXB_SHEAR 和所选饱和模型一起使用。'),
    'ALPHA_P': ('缩放所有粒子的平行速度剪切。', '无量纲倍率。', '配合 VPAR_SHEAR_i；与 ExB 剪切倍率 ALPHA_E 不同。'),
    'ALPHA_QUENCH': ('选择流剪切抑制的处理方式。', '无量纲模型控制量。', '官方说明 1 使用 quench 规则，0 使用谱移位模型。'),
    'SIGN_BT': ('环向磁场的符号约定。', '+1 或 −1。', '从装置上方看，+1 为逆时针；应与平衡输入一致。'),
    'SIGN_IT': ('环向等离子体电流的符号约定。', '+1 或 −1。', '从装置上方看，+1 为逆时针；参与流和剪切的符号定义。'),
    'RMIN_LOC': ('局部磁面的小半径。', 'r/a。', '不一定等于归一化磁通半径 rho；修改几何半径不会自动重新插值整套实验剖面。'),
    'RMAJ_LOC': ('局部磁面中心的大半径。', 'R_maj/a。', '局部几何量，不是米。'),
    'ZMAJ_LOC': ('局部磁面中心的垂直位置。', 'Z_maj/a。', '可带正负号。'),
    'DRMINDX_LOC': ('小半径对所用径向坐标 x 的导数 dr/dx。', '长度之比。', '用于 x 与 r 不相同的坐标表示。'),
    'DRMAJDX_LOC': ('磁面中心大半径的径向导数 dR_maj/dx。', '长度之比。', '反映 Shafranov 位移的径向变化。'),
    'DZMAJDX_LOC': ('磁面中心高度的径向导数 dZ_maj/dx。', '长度之比。', '不是垂直位置本身。'),
    'KAPPA_LOC': ('局部磁面的拉长比 κ。', '无量纲，圆截面为 1。', '需与局部几何模型配合。'),
    'S_KAPPA_LOC': ('拉长比的径向剪切 (r/κ)dκ/dr。', '无量纲。', '官网字母列表与参数表的默认值不一致；本目录按解析器参考 0，已有输入优先。'),
    'DELTA_LOC': ('局部磁面的三角形变 δ。', '无量纲。', 'Miller 形状参数；正、负值区分三角形变方向。'),
    'S_DELTA_LOC': ('三角形变的径向剪切 r·dδ/dr。', '无量纲。', '与 δ 本身分开设置。'),
    'ZETA_LOC': ('局部磁面的方形度 ζ。', '无量纲。', '用于支持该形状参数的局部几何。'),
    'S_ZETA_LOC': ('方形度的径向剪切 r·dζ/dr。', '无量纲。', '与 ζ 本身分开设置。'),
    'Q_LOC': ('局部安全因子的绝对值 |q|。', '无量纲。', '电流、磁场方向分别由 SIGN_IT、SIGN_BT 规定。'),
    'Q_PRIME_LOC': ('局部几何中的磁剪切组合 q²a²s/r²。', '无量纲，其中 s=(r/q)dq/dr。', '不能直接把 s 填进此项；s-alpha 模型则使用 SHAT_SA。'),
    'P_PRIME_LOC': ('局部几何的归一化压力梯度。', '(q a² / (r B_unit²))·dp/dr，按 GACODE 压力单位。', '是带符号量，不能直接填写 Pa/m；通常由局部输入生成器给出。'),
    'BETA_LOC': ('传给局部平衡几何接口的 beta。', '原生局部平衡归一化。', '与电子电磁参数 BETAE 不等价；饱和模型可用它和 P_PRIME_LOC 计算压力梯度，通常沿用生成器值。'),
    'KX0_LOC': ('鼓包模态偏移的波数比 kx0/ky。', '无量纲。', '不是 kx0 本身。'),
    'NEW_EIKONAL': ('是否重新计算几何程函。', 'True / False。', 'False 在原生连续调用接口中复用前次计算；独立文件作业不能把它当成跨作业的结果缓存。'),
    'RMIN_SA': ('s-alpha 模型的小半径。', 'r/a。', '用于 GEOMETRY_FLAG=0。'),
    'RMAJ_SA': ('s-alpha 模型的大半径。', 'R_maj/a。', '用于 GEOMETRY_FLAG=0。'),
    'Q_SA': ('s-alpha 模型的安全因子绝对值。', '无量纲。', '用于 GEOMETRY_FLAG=0。'),
    'SHAT_SA': ('s-alpha 模型的磁剪切 s=(r/q)dq/dr。', '无量纲。', '仅 GEOMETRY_FLAG=0 使用；局部 Miller 几何使用 Q_PRIME_LOC。'),
    'ALPHA_SA': ('s-alpha 模型的归一化压力梯度参数。', '无量纲。', '用于 GEOMETRY_FLAG=0；不是直接的实验压力梯度。'),
    'XWELL_SA': ('s-alpha 模型的磁阱参数。', '模型的无量纲量。', '用于 GEOMETRY_FLAG=0。'),
    'THETA0_SA': ('s-alpha 模型的鼓包角 θ0=kx/(s·ky)。', '无量纲角变量。', '用于 GEOMETRY_FLAG=0。'),
    'B_MODEL_SA': ('是否在垂直波数中包含 B(θ) 因子。', '整数 0 关闭、1 开启。', '用于 s-alpha 几何。'),
    'FT_MODEL_SA': ('选择 s-alpha 几何的俘获份额模型。', '整数选择器。', '1 使用外侧中平面的俘获份额。'),
    'GEOMETRY_FLAG': ('选择平衡几何模型。', '整数模型编号。', '官网列出 0：s-alpha；1：Miller；2：Fourier；3：ELITE。后两者需相应几何数据；仅改编号不会生成这些数据。'),
    'PARK': ('缩放平行梯度项。', '无量纲倍率。', '算法/模型研究参数，1 为原值。'),
    'GHAT': ('缩放曲率漂移的闭合项。', '无量纲倍率。', '与 GCHAT 的不可约项不同。'),
    'GCHAT': ('缩放曲率漂移的不可约项。', '无量纲倍率。', '与 GHAT 的闭合项不同。'),
    'WD_ZERO': ('防止曲率漂移本征值为零的截断参数。', 'TGLF 模型归一化量。', '数值模型控制，不是求解器收敛误差。'),
    'LINSKER_FACTOR': ('缩放 Linsker 项。', '无量纲倍率。', '用于模型项的对比研究。'),
    'GRADB_FACTOR': ('缩放磁场强度梯度项。', '无量纲倍率。', '用于模型项的对比研究。'),
    'FILTER': ('按模态频率与漂移频率的比例过滤非漂移波不稳定性。', '无量纲阈值。', '改变它可能改变保留的物理模态，不是显示过滤器。'),
    'DAMP_PSI': ('原生输入接口保留的 PSI 阻尼参数。', '官网未给出完整归一化。', '官网参数表未解释其作用范围；用于专家模型实验时请核对所装版本源码，不将它解释为时间步长。'),
    'DAMP_SIG': ('原生输入接口保留的 SIG 阻尼参数。', '官网未给出完整归一化。', '官网参数表未解释其作用范围；请核对所装版本源码，通常沿用输入值。'),
    'IFLUX': ('是否计算准线性权重及模态振幅。', 'True / False。', '工作台的通量结果依赖相应输出；关闭后不能期望得到完整通量。'),
    'WRITE_WAVEFUNCTION_FLAG': ('控制本征函数输出。', '整数输出标记，0 为默认值。', '支持的非零选项以所装版本为准；影响文件输出。'),
    'NN_MAX_ERROR': ('TGLF-NN 与完整 TGLF 之间的误差阈值控制。', '原生神经网络误差尺度。', '需要支持 NN 的构建；−1 强制完整 TGLF。NN 通量预测不提供完整本征谱，绘谱需完整求解。'),
    'NS': ('参与计算的粒子种类数，包括电子和离子。', '正整数。', '由输入物种组成管理；不能仅扫描计数而不同时准备相应物种字段。'),
    'USE_TRANSPORT_MODEL': ('启用输运谱和通量计算。', 'True / False。', '本工作台固定使用 True，由运行方式管理，不作为参数轴。'),
    'UNITS': ('选择饱和模型采用的归一化/标定约定。', '字符串 GYRO 或 CGYRO。', '官方说明 SAT0 使用 GYRO，SAT2 强制 CGYRO；SAT1 的选择也影响谱移位及几何标定，不只是图轴换单位。'),
}

SPECIES_HELP = {
    'ZS': ('粒子的电荷数 Z_s。', '以基本电荷 e 为单位。', '电子通常为 −1，离子为正；与 AS_i 一起满足准中性。'),
    'MASS': ('粒子质量 m_s。', 'm_s/m_D，以氘质量归一化。', 'H、D、T 约为 0.5、1、1.5；电子约 2.723e−4。'),
    'AS': ('粒子密度相对电子密度的比例。', 'n_s/n_e。', '电子为 1；离子应满足 Σ Z_i·AS_i=1。单独扫描不会自动补偿其他粒子密度。'),
    'TAUS': ('粒子温度相对电子温度的比例。', 'T_s/T_e。', '不是 keV；同步热离子选项只联动当前输入中同温的离子。'),
    'RLNS': ('密度的归一化逆梯度长度。', '−a·d(ln n_s)/dr。', '向外递减时通常为正；不是 n_s 本身。'),
    'RLTS': ('温度的归一化逆梯度长度。', '−a·d(ln T_s)/dr。', '向外递减时通常为正；编号 1 通常为电子，其余按实际输入物种顺序。'),
    'VPAR': ('粒子的归一化平行速度。', 'SIGN_IT·R_maj·V_tor/(R·c_s)。', '带符号；还受 ALPHA_MACH 和 VPAR_MODEL 影响。'),
    'VPAR_SHEAR': ('粒子的归一化平行速度剪切。', '−SIGN_IT·R_maj·d(V_tor/R)/dr·a/c_s。', '带符号；还受 ALPHA_P 影响。'),
    'VNS_SHEAR': ('原生 put_profile_shear 接口的密度剖面剪切量。', '官网未给出完整归一化。', '保留输入中的专家参数；不能仅按名称当作 RLNS 的导数填写，需核对所用版本源码。'),
    'VTS_SHEAR': ('原生 put_profile_shear 接口的温度剖面剪切量。', '官网未给出完整归一化。', '保留输入中的专家参数；不能仅按名称当作 RLTS 的导数填写，需核对所用版本源码。'),
}

# These newer/expert inputs exist in the parser but have no section in the web
# alphabetical list. Link to the list itself, not an invented fragment target.
UNLISTED = {'USE_AVE_ION_GRID', 'WDIA_TRAPPED', 'RLNP_CUTOFF', 'BETA_LOC',
            'DAMP_PSI', 'DAMP_SIG', 'NN_MAX_ERROR'}


def parameter_help(name, source=None):
    """Build help from a scalar input reference, without resolving any results."""
    reference, label, _ = field_spec(name)
    entry, anchor = HELP.get(name, None), name.lower().replace('_', '-')
    species = SPECIES_PATTERN.fullmatch(name)
    if species:
        entry = SPECIES_HELP[species[1]]
        anchor = species[1].lower().replace('_', '-') + '-1'
        if species[1] in ('VNS_SHEAR', 'VTS_SHEAR'):
            anchor = ''
    elif name.startswith('SHAPE_') and name in FIELDS:
        anchor = ''
        entry = ('局部磁面形状的谐波' + ('径向剪切系数。' if name.startswith('SHAPE_S_') else '系数。'),
                 '无量纲几何系数。', '仅支持相应形状扩展的版本生效；需与所选几何模型和其他形状字段匹配。')
    if entry is None:
        anchor = ''
        entry = ('当前输入中的扩展参数，本目录未核对其物理含义。', '以所用 TGLF 版本为准。',
                 '保留原始参数名称和值，不根据名称猜测归一化或枚举含义。')
    present = source is not None and name in source
    if present:
        reference = scalar(source[name])
    kind = ('True / False' if isinstance(reference, bool) else '整数' if name in FIELDS
            and isinstance(FIELDS[name][0], int) and not isinstance(FIELDS[name][0], bool) else '有限实数')
    if name == 'UNITS':
        label = '归一化约定'
        kind, reference = 'GYRO / CGYRO', source.get(name, 'GYRO') if source is not None else 'GYRO'
    value_note = ('当前输入值：' if present else '官方解析器默认参考值：') + str(reference)
    if name not in FIELDS and not species and name != 'UNITS' and not present:
        value_note = '当前输入未提供该参数。'
    manual = DOC_URL + ('#' + anchor if anchor and name not in UNLISTED else '')
    return '\n'.join((name + ' · ' + label, '类型：' + kind, value_note,
        '含义：' + entry[0], '单位 / 归一化：' + entry[1], '适用条件：' + entry[2], '',
        '未修改的字段沿用输入/求解器默认；参考值不会自动写入输入。扫描值优先于手动覆盖值。',
        '常用归一化：a 为参考小半径，c_s=√(T_e/m_D)。本地说明核对日期：2026-10-27。',
        'GACODE 官方说明：' + manual, '参数表：' + TABLE_URL,
        '版本与默认值核对：' + CODE_URL))
