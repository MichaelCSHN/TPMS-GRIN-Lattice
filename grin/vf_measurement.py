"""
基于网格表面的 Vf 工程实测代理（蒙特卡洛采样）。

等值面为薄壳时，严格体积分需要体素化或体数据；此处用「到表面距离 < d_c/2」判为落入
材料带，得到各壳层内 material fraction 代理，可与 EMT 目标 Vf 做趋势与迭代对照。
"""

from __future__ import annotations

import numpy as np


def sample_spherical_shell_uniform(n: int, r0: float, r1: float, center: np.ndarray) -> np.ndarray:
    """球壳 r0≤r≤r1 内体积均匀随机点（r0、r1 为到 center 的距离）。"""
    center = np.asarray(center, dtype=np.float64).reshape(3)
    u = np.random.rand(max(n, 1))
    r = np.cbrt(float(r0) ** 3 + u * (float(r1) ** 3 - float(r0) ** 3))
    dirs = np.random.randn(len(u), 3)
    dirs /= np.linalg.norm(dirs, axis=1, keepdims=True) + 1e-15
    return center + r[:, np.newaxis] * dirs


def measure_vf_band_proxy(
    vertices: np.ndarray,
    faces: np.ndarray,
    center: np.ndarray,
    r_edges: np.ndarray,
    d_c_mm: float,
    n_samples_total: int = 48000,
) -> tuple[np.ndarray, dict]:
    """
    各球壳内均匀采样，到三角网格最近距离 < band（默认 d_c/2）判为材料带内，得到每层比例向量。
    """
    import trimesh

    mesh = trimesh.Trimesh(vertices=np.asarray(vertices, dtype=np.float64), faces=np.asarray(faces, dtype=np.int64), process=False)
    pq = trimesh.proximity.ProximityQuery(mesh)
    r_edges = np.asarray(r_edges, dtype=np.float64)
    n_layers = int(r_edges.size - 1)
    if n_layers < 1:
        return np.array([]), {"error": "无壳层"}

    n_per = max(120, int(n_samples_total // max(n_layers, 1)))
    band = max(0.05 * float(d_c_mm), 0.5 * float(d_c_mm))
    center = np.asarray(center, dtype=np.float64).reshape(3)
    per_shell = np.zeros(n_layers, dtype=np.float64)

    for k in range(n_layers):
        r0, r1 = float(r_edges[k]), float(r_edges[k + 1])
        pts = sample_spherical_shell_uniform(n_per, r0, r1, center)
        dist, _ = pq.distance(pts)
        per_shell[k] = float(np.mean((dist < band).astype(np.float64)))

    info = {
        "method": "monte_carlo_distance_band",
        "band_half_mm": float(band),
        "samples_per_shell": n_per,
        "note": "薄壳近似：dist<band 视为材料带内；与 EMT 体积分数量级可能偏差，宜作相对迭代与趋势。",
    }
    return per_shell, info


def compare_vf_to_target(vf_measured: np.ndarray, vf_target: np.ndarray) -> dict:
    """简单标量误差，供迭代与报告。"""
    vm = np.asarray(vf_measured, dtype=np.float64).ravel()
    vt = np.asarray(vf_target, dtype=np.float64).ravel()
    if vm.size != vt.size or vm.size == 0:
        return {"rmse": None, "max_abs": None, "mean_rel": None}
    err = vm - vt
    return {
        "rmse": float(np.sqrt(np.mean(err**2))),
        "max_abs": float(np.max(np.abs(err))),
        "mean_rel": float(np.mean(np.abs(err)) / (np.mean(np.abs(vt)) + 1e-12)),
    }
