"""
几何/拓扑简易指标：角向均匀性、胞元尺度与 TPMS 周期数 K。
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


def angular_vf_by_phi(
    verts: np.ndarray,
    center_mm: np.ndarray,
    r_edges: np.ndarray,
    vf_by_layer: np.ndarray,
    n_bins: int = 36,
) -> dict:
    """
    将顶点按半径归入径向壳层，赋予该层目标实体体积分数 Vf，再按方位角 φ 分箱取平均，
    得到角向 Vf(φ)（工程近似：等值面顶点代理，非体积分割）。
    """
    if verts.size == 0:
        return {"phi_deg": None, "vf_mean": None, "vf_global_mean": None, "cv_vf": None, "note": "空网格"}
    center_mm = np.asarray(center_mm, dtype=np.float64).reshape(3)
    r_edges = np.asarray(r_edges, dtype=np.float64)
    vf_by_layer = np.asarray(vf_by_layer, dtype=np.float64)
    n_layers = vf_by_layer.size
    if r_edges.size != n_layers + 1:
        return {"phi_deg": None, "vf_mean": None, "vf_global_mean": None, "cv_vf": None, "note": "r_edges 与层数不一致"}

    p = verts - center_mm.reshape(1, 3)
    r = np.linalg.norm(p, axis=1)
    rmx = float(r_edges[-1])
    r = np.clip(r, 0.0, max(rmx - 1e-9, 0.0))
    k = np.searchsorted(r_edges, r, side="right") - 1
    k = np.clip(k, 0, n_layers - 1)
    vf_vert = vf_by_layer[k]

    phi = np.arctan2(p[:, 1], p[:, 0])
    pb = (phi + np.pi) / (2.0 * np.pi) * float(n_bins)
    bid = np.floor(pb).astype(np.int32)
    bid = np.clip(bid, 0, n_bins - 1)

    sum_w = np.bincount(bid, weights=vf_vert, minlength=n_bins)
    cnt = np.bincount(bid, minlength=n_bins)
    mean_vf = sum_w / np.maximum(cnt.astype(np.float64), 1.0)
    phi_c = -np.pi + (np.arange(n_bins) + 0.5) * (2.0 * np.pi / n_bins)
    phi_deg = np.degrees(phi_c)

    mu = float(np.mean(mean_vf))
    cv_vf = float(np.std(mean_vf) / mu) if mu > 1e-12 else None
    return {
        "phi_deg": phi_deg,
        "vf_mean": mean_vf,
        "vf_global_mean": float(np.mean(vf_vert)),
        "cv_vf": cv_vf,
        "note": "壳层目标 Vf + 顶点 φ 分箱平均",
    }


def r_edges_from_meta_layers(meta_layers: list) -> np.ndarray:
    """由 meta_layers 重建 r_edges（长度 N+1）。"""
    if not meta_layers:
        return np.array([], dtype=np.float64)
    e = [float(meta_layers[0]["r_mm"][0])]
    for m in meta_layers:
        e.append(float(m["r_mm"][1]))
    return np.array(e, dtype=np.float64)


def min_shell_thickness_mm(r_edges: np.ndarray) -> float:
    """径向相邻壳边界的最小间距（mm）。"""
    r_edges = np.asarray(r_edges, dtype=np.float64)
    if r_edges.size < 2:
        return float("inf")
    return float(np.min(np.diff(r_edges)))


def resolve_tpms_periods_K(
    box_mm: float,
    res: int,
    r_edges: np.ndarray,
    a_cell_mm: float | None,
) -> tuple[int, dict]:
    """
    确定 Mixer 状态量 Kx=Ky=Kz=K：立方体边长 d=box_mm 上每轴放置 K 个 TPMS 周期，
    物理周期长度 ≈ d/K，目标上接近用户指定的单胞尺度 a。

    未指定 a 时保持历史默认 K=2。指定 a 时要求 a≤最薄壳层厚度，否则用最小层厚参与计算并记录说明。
    体素预算在 tpms_radial_shells 内通过限制每轴采样数处理，不修改 K。
    """
    d = float(box_mm)
    min_layer = min_shell_thickness_mm(r_edges)
    notes: list[str] = []

    if a_cell_mm is None or float(a_cell_mm) <= 0:
        K = 2
        a_phys = d / K
        return K, {
            "a_requested_mm": None,
            "a_effective_mm": a_phys,
            "min_layer_thickness_mm": min_layer,
            "notes": notes
            + [
                "未指定目标胞元尺度 a，使用默认 K=2（每轴 2 个周期；改变 a 可加密/稀疏周期阵列）。"
            ],
        }

    a_req = float(a_cell_mm)
    if a_req > min_layer + 1e-9:
        a_eff = min_layer
        notes.append(
            f"目标 a={a_req:.4f} mm 大于最小层厚 {min_layer:.4f} mm，已按层厚上限计算 K（设计约束：a≤最小层厚）。"
        )
    else:
        a_eff = a_req

    K = max(2, int(round(d / max(a_eff, 1e-12))))

    a_phys = d / K
    return K, {
        "a_requested_mm": a_req,
        "a_effective_mm": a_phys,
        "min_layer_thickness_mm": min_layer,
        "notes": notes,
    }


def estimate_a_dc_from_res_and_box(res: int, box_mm: float, k_periods: int = 2) -> dict:
    """
    体素方向特征尺度（与周期长度 d/K 不同）：box/(K*res) 近似沿轴每 res 采样一步的物理步长。
    """
    a_est = float(box_mm / max(k_periods * res, 1))
    return {"a_est_mm": a_est, "note": "体素步长粗估 box/(K·res)，非周期边长；周期边长见 a_cell_effective_mm=d/K。"}
