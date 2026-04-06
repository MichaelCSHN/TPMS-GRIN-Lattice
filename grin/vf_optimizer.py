"""
根据实测（代理）Vf 与目标 Vf 的偏差，迭代调整各壳层 quantile_q。
实验性：代理与 EMT 量纲不完全一致，用均值对齐后做比例修正。
"""

from __future__ import annotations

from typing import Any

import numpy as np

from grin import vf_measurement


def optimize_quantiles_iterative(
    compute_grin_mesh_fn,
    base_params: dict[str, Any],
    *,
    max_iter: int = 5,
    beta: float = 0.35,
    tol_rmse: float = 0.12,
    mc_samples: int = 24000,
) -> tuple[Any, Any, list, list[dict], np.ndarray]:
    """
    反复调用 compute_grin_mesh_fn(**params, quantile_override=...)，
    使 vf_measurement 代理逐壳逼近 meta 中的 vf_solid_emt。

    返回 (verts, faces, meta_layers, report_extra_last, history)
    """
    history: list[dict] = []
    verts = faces = None
    meta = None
    extra: dict = {}
    q_last: np.ndarray | None = None

    for it in range(max_iter):
        p = dict(base_params)
        if q_last is not None:
            p["quantile_override"] = [float(x) for x in q_last]

        verts, faces, meta, extra = compute_grin_mesh_fn(**p)

        tgt = np.array([m["vf_solid_emt"] for m in meta], dtype=np.float64)
        r_edges = np.array([meta[0]["r_mm"][0]] + [m["r_mm"][1] for m in meta], dtype=np.float64)
        d = float(extra.get("box_mm", 2.0 * float(base_params["radius_mm"])))
        center = np.array([d / 2, d / 2, d / 2], dtype=np.float64)
        d_c = float(base_params.get("d_c_mm", 0.4))

        measured, mf_info = vf_measurement.measure_vf_band_proxy(
            verts, faces, center, r_edges, d_c, n_samples_total=mc_samples
        )
        cmp = vf_measurement.compare_vf_to_target(measured, tgt)
        history.append(
            {
                "iter": it,
                "rmse": cmp["rmse"],
                "max_abs": cmp["max_abs"],
                "vf_measured": measured.tolist(),
                "vf_target": tgt.tolist(),
                "measurement": mf_info,
            }
        )

        if cmp["rmse"] is not None and cmp["rmse"] < tol_rmse:
            break

        q = np.array([m["quantile_q"] for m in meta], dtype=np.float64)
        if measured.mean() > 1e-9:
            m_scaled = measured * (float(tgt.mean()) / float(measured.mean()))
        else:
            m_scaled = measured
        err = tgt - m_scaled
        q_new = np.clip(q + beta * err, 0.02, 0.98)
        q_last = q_new

    if isinstance(extra, dict):
        extra["vf_optimization_history"] = history
    return verts, faces, meta, extra, history
