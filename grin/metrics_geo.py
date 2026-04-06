"""
几何/拓扑简易指标：角向均匀性（占位算法）、胞元尺度与线径估计（由工艺参数传入）。
"""

from __future__ import annotations

import numpy as np


def angular_uniformity_cv(verts: np.ndarray, center_mm: np.ndarray, r_inner: float, r_outer: float, n_phi_bins: int = 36) -> dict:
    """
    在球壳 r_inner≤r≤r_outer 内，按方位角 φ 分箱统计顶点数，返回变异系数 CV=std/mean。
    仅为工程占位，不等同于严格孔隙角向均匀。
    """
    if verts.size == 0:
        return {"cv": None, "note": "空网格"}
    p = verts - center_mm.reshape(1, 3)
    r = np.linalg.norm(p, axis=1)
    mask = (r >= r_inner) & (r <= r_outer)
    if np.count_nonzero(mask) < n_phi_bins:
        return {"cv": None, "note": "too_few_vertices_in_shell"}
    p = p[mask]
    phi = np.arctan2(p[:, 1], p[:, 0])
    hist, _ = np.histogram(phi, bins=n_phi_bins, range=(-np.pi, np.pi))
    mu = float(np.mean(hist))
    if mu < 1e-9:
        return {"cv": None, "note": "均值过小"}
    cv = float(np.std(hist) / mu)
    return {"cv": cv, "note": "phi_bin_count_CV_placeholder"}


def estimate_a_dc_from_res_and_box(res: int, box_mm: float, k_periods: int = 2) -> dict:
    """
    粗估：周期长度尺度 ~ box/(k*某常数)，胞元特征尺度 a ~ box/(k*res)；线径下界由工艺 d_c 约束。
    """
    # 与 TPMS 采样一致：每周期 res 细分
    a_est = float(box_mm / max(k_periods * res, 1))
    return {"a_est_mm": a_est, "note": "由 box 与 Res 粗估，非精确壁厚"}
