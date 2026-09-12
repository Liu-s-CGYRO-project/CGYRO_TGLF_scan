import numpy as np
import matplotlib.pyplot as plt

def triad_phasor_check(phi_cmplx, kx, ky, idx_k, idx_kp):
    """
    进行三波相位检查 (Phasor Check)
    idx_k: 目标模式 k 的索引 (kx_idx, ky_idx)
    idx_kp: 供体模式 k' 的索引 (kx_idx, ky_idx)
    """
    nx = len(kx)
    nt = phi_cmplx.shape[2]
    
    # 1. 计算理论上的 k'' (k'' = k - k')
    target_kx_pp = kx[idx_k[0]] - kx[idx_kp[0]]
    target_ky_pp = ky[idx_k[1]] - ky[idx_kp[1]]
    
    # 2. 寻找 k'' 的索引并处理厄米对称性
    # 处理 kx 的周期性 (FFT 顺序下最稳健的方法)
    idx_kx_pp = (idx_k[0] - idx_kp[0]) % nx
    
    # 处理 ky 的对称性 (因为 CGYRO 只有 ky >= 0)
    if target_ky_pp < 0:
        # 寻找模式 (-kx_pp, -ky_pp) 的共轭
        search_ky = -target_ky_pp
        # 这里的关键是：如果你反转了 ky，kx 也必须反转！
        # 找到对应于 -kx[idx_kx_pp] 的索引
        idx_kx_pp_final = np.argmin(np.abs(kx - (-kx[idx_kx_pp])))
        idx_ky_pp_final = np.argmin(np.abs(ky - search_ky))
        
        phi_k_ii = np.conj(phi_cmplx[idx_kx_pp_final, idx_ky_pp_final, :])
        mode_label = f"phi*({kx[idx_kx_pp_final]:.3f}, {ky[idx_ky_pp_final]:.3f})"
    else:
        idx_kx_pp_final = idx_kx_pp
        idx_ky_pp_final = np.argmin(np.abs(ky - target_ky_pp))
        phi_k_ii = phi_cmplx[idx_kx_pp_final, idx_ky_pp_final, :]
        mode_label = f"phi({kx[idx_kx_pp_final]:.3f}, {ky[idx_ky_pp_final]:.3f})"

    # 3. 提取三个模式的时间序列
    phi_k = phi_cmplx[idx_k[0], idx_k[1], :]
    phi_kp = phi_cmplx[idx_kp[0], idx_kp[1], :]
    
    # 4. 计算三波乘积 S = phi(k)* * phi(k') * phi(k'')
    # 注意：这里 phi_k 取共轭
    S = np.conj(phi_k) * phi_kp * phi_k_ii
    
    # 5. 计算相位角 (单位：度)
    phases = np.angle(S, deg=True)
    
    # 6. 可视化检查
    plt.figure(figsize=(10, 4))
    plt.plot(phases, 'o-', markersize=2, alpha=0.6)
    plt.axhline(np.mean(phases), color='r', linestyle='--', label=f'Mean: {np.mean(phases):.1f}°')
    plt.ylim(-180, 180)
    plt.title(f"Triad Phase Check: k({kx[idx_k[0]]:.2f},{ky[idx_k[1]]:.2f})")
    plt.xlabel("Time Step")
    plt.ylabel("Phase (Degrees)")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.show()

    print(f"--- Triad Logic Verification ---")
    print(f"Target k'' Physical: ({target_kx_pp:.4f}, {target_ky_pp:.4f})")
    print(f"Used Mode k'' in Data: {mode_label}")
    print(f"Phase Standard Deviation: {np.std(phases):.2f}°")
    
    return phases
print('Call triad_phasor_check(phi_cmplx, kx, ky, idx_k, idx_kp) with an explicit case and triad.')
