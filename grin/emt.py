"""
等效介质：Maxwell Garnett（球形 inclusion 于基体）及反演。
空气 inclusion ε≈1，基体 ε_m 由配置给出。
"""

from __future__ import annotations

import numpy as np


def epsilon_eff_maxwell_garnett(epsilon_m: float, epsilon_i: float, vf_inclusion: float) -> float:
    """
    Maxwell Garnett：基体 ε_m 为连续相，inclusion ε_i，f = vf_inclusion 为 inclusion 体积分数。

    ε_eff = ε_m * (ε_i + 2ε_m + 2f(ε_i - ε_m)) / (ε_i + 2ε_m - f(ε_i - ε_m))
    """
    f = float(np.clip(vf_inclusion, 0.0, 1.0))
    em, ei = float(epsilon_m), float(epsilon_i)
    num = ei + 2.0 * em + 2.0 * f * (ei - em)
    den = ei + 2.0 * em - f * (ei - em)
    if abs(den) < 1e-15:
        return em
    return em * num / den


def epsilon_eff_from_solid_vf(epsilon_m: float, epsilon_air: float, vf_solid: float) -> float:
    """vf_solid 为实体（基体）体积分数；孔隙为 inclusion。"""
    vf_inc = 1.0 - float(np.clip(vf_solid, 0.0, 1.0))
    return epsilon_eff_maxwell_garnett(epsilon_m, epsilon_air, vf_inc)


def invert_vf_solid_for_epsilon(
    epsilon_target: float,
    epsilon_m: float,
    epsilon_air: float = 1.0,
    tol: float = 1e-6,
    max_iter: int = 80,
) -> float:
    """给定目标 ε_eff，反求 vf_solid ∈ [0,1]（二分）。"""
    et = float(epsilon_target)
    lo, hi = 0.0, 1.0
    e_lo = epsilon_eff_from_solid_vf(epsilon_m, epsilon_air, lo)
    e_hi = epsilon_eff_from_solid_vf(epsilon_m, epsilon_air, hi)
    if not (min(e_lo, e_hi) - tol <= et <= max(e_lo, e_hi) + tol):
        return float(np.clip((et - epsilon_air) / (epsilon_m - epsilon_air + 1e-30), 0.0, 1.0))

    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        e_mid = epsilon_eff_from_solid_vf(epsilon_m, epsilon_air, mid)
        if abs(e_mid - et) < tol:
            return mid
        if e_mid < et:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)
