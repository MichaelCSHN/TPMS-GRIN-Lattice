"""
基于 TPMS 隐式场，按球壳分层设置 iso（分位数），与 TPMS_Mixer 逻辑一致但 iso 随半径变化。
不修改 TPMS_Mixer_v1.1.0.py；复用 get_field、weld_vertices。
"""

from __future__ import annotations

import math
from typing import Sequence

import numpy as np
from skimage.measure import marching_cubes

from grin.tpms_mixer_bridge import get_mixer


def compute_tpms_radial_shell_quantiles(
    state,
    res: int,
    r_edges_mm: Sequence[float],
    quantile_per_shell: Sequence[float],
    max_voxels: int = 20_000_000,
):
    """
    r_edges_mm: 长度 N+1，从球心向外，0 = r0 < r1 < ... < r_N = R（与立方体 inscribed sphere 一致）。
    quantile_per_shell: 长度 N，每层传给 np.quantile(absPhi, q) 的 q，对应 Mixer 中 RD 含义。

    球心位于 (Sx/2, Sy/2, Sz/2)。仅在 dist <= r_N 的体素上赋壳；外侧体素用常数负 sdf 避免杂散面（可选）。
    """
    mod = get_mixer()
    get_field = mod.get_field
    weld_vertices = mod.weld_vertices

    rx = max(int(round(state.Kx * res)), 8)
    ry = max(int(round(state.Ky * res)), 8)
    rz = max(int(round(state.Kz * res)), 8)
    vox = rx * ry * rz
    if vox > max_voxels:
        raise ValueError(f"网格规模过大：{vox/1e6:.2f}M 体素，请降低 res 或 K。")

    gx = np.linspace(0.0, state.Kx * 2 * math.pi, rx, dtype=np.float32)
    gy = np.linspace(0.0, state.Ky * 2 * math.pi, ry, dtype=np.float32)
    gz = np.linspace(0.0, state.Kz * 2 * math.pi, rz, dtype=np.float32)
    X, Y, Z = np.meshgrid(gx, gy, gz, indexing="ij")

    PhiA = get_field(state.typeA, X, Y, Z)
    if state.typeA == state.typeB:
        PhiFinal = PhiA
    else:
        PhiB = get_field(state.typeB, X, Y, Z)
        xn = X / float(gx.max())
        zn = Z / float(gz.max())
        if state.dir == "Z":
            dist = Z / float(gz.max())
        elif state.dir == "X":
            dist = X / float(gx.max())
        else:
            dist = (xn - zn + 1.0) / 2.0
        w = 1.0 / (1.0 + np.exp(-state.trans_k * (dist - state.trans_center) * 10.0)).astype(np.float32)
        PhiFinal = (1.0 - w) * PhiA + w * PhiB

    absPhi = np.abs(PhiFinal).astype(np.float32)
    sx = state.Sx / max(rx - 1, 1)
    sy = state.Sy / max(ry - 1, 1)
    sz = state.Sz / max(rz - 1, 1)

    xc = np.linspace(0.0, float(state.Sx), rx, dtype=np.float64)
    yc = np.linspace(0.0, float(state.Sy), ry, dtype=np.float64)
    zc = np.linspace(0.0, float(state.Sz), rz, dtype=np.float64)
    XM, YM, ZM = np.meshgrid(xc, yc, zc, indexing="ij")
    cx, cy, cz = 0.5 * float(state.Sx), 0.5 * float(state.Sy), 0.5 * float(state.Sz)
    dist_mm = np.sqrt((XM - cx) ** 2 + (YM - cy) ** 2 + (ZM - cz) ** 2).astype(np.float32)

    r_edges = np.asarray(r_edges_mm, dtype=np.float64)
    qs = np.asarray(quantile_per_shell, dtype=np.float64)
    n_layers = len(qs)
    if r_edges.shape[0] != n_layers + 1:
        raise ValueError("r_edges_mm 长度须为 len(quantile_per_shell)+1")

    r_max = float(r_edges[-1])
    layer_id = -np.ones_like(dist_mm, dtype=np.int32)
    for k in range(n_layers):
        r0, r1 = float(r_edges[k]), float(r_edges[k + 1])
        if k < n_layers - 1:
            mask = (dist_mm >= r0) & (dist_mm < r1)
        else:
            mask = (dist_mm >= r0) & (dist_mm <= r1 + 1e-6)
        layer_id[mask] = k

    iso_field = np.full_like(absPhi, np.nan, dtype=np.float32)
    for k in range(n_layers):
        mask = layer_id == k
        q = float(np.clip(qs[k], 1e-6, 1.0 - 1e-6))
        if not np.any(mask):
            continue
        iso_k = float(np.quantile(absPhi[mask], q))
        iso_field[mask] = iso_k

    bad = np.isnan(iso_field) & (dist_mm <= r_max + 1e-6)
    if np.any(bad):
        q0 = float(np.clip(qs[0], 1e-6, 1.0 - 1e-6))
        iso_field[bad] = float(np.quantile(absPhi, q0))

    # 球外：强负 sdf，避免在周期盒角上生成杂散实体
    neg = float(np.max(absPhi) + 1.0)
    outside = dist_mm > r_max + 1e-3
    iso_field[outside] = 0.0
    sdf = (iso_field - absPhi).astype(np.float32)
    sdf[outside] = neg

    vol = np.transpose(sdf, (2, 1, 0))
    pad = 1
    neg_const = -float(np.max(np.abs(vol)) + 1.0)
    vol_pad = np.pad(vol, pad_width=pad, mode="constant", constant_values=neg_const)

    verts, faces, _, _ = marching_cubes(vol_pad, level=0.0, spacing=(sz, sy, sx))
    verts = np.asarray(verts, dtype=np.float32)
    verts[:, 0] -= pad * sz
    verts[:, 1] -= pad * sy
    verts[:, 2] -= pad * sx
    verts_xyz = np.column_stack([verts[:, 2], verts[:, 1], verts[:, 0]]).astype(np.float32)
    faces = np.asarray(faces, dtype=np.int32)

    return weld_vertices(verts_xyz, faces, decimals=5)
