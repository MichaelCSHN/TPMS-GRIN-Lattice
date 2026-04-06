"""
基于 TPMS 隐式场，按球壳分层设置 iso（分位数），与 TPMS_Mixer 逻辑一致但 iso 随半径变化。
不修改 TPMS_Mixer_v1.1.0.py；复用 get_field、weld_vertices。
"""

from __future__ import annotations

import math
from typing import Literal, Sequence

import numpy as np
from skimage.measure import marching_cubes

from grin.tpms_mixer_bridge import get_mixer


def compute_tpms_radial_shell_quantiles(
    state,
    res: int,
    r_edges_mm: Sequence[float],
    quantile_per_shell: Sequence[float],
    max_voxels: int = 20_000_000,
    *,
    mesh_domain: Literal["full", "octant"] = "full",
):
    """
    r_edges_mm: 长度 N+1，从球心向外，0 = r0 < r1 < ... < r_N = R（与立方体 inscribed sphere 一致）。
    quantile_per_shell: 长度 N，每层传给 np.quantile(absPhi, q) 的 q，对应 Mixer 中 RD 含义。

    球心位于 (Sx/2, Sy/2, Sz/2)。仅在 dist <= r_N 的体素上赋壳；外侧体素用常数负 sdf 避免杂散面（可选）。

    mesh_domain:
      - full：全球体素（与历史行为一致）。
      - octant：仅 +X+Y+Z 卦限（物理坐标 x,y,z ≥ 球心），体素量约 1/8，显著减负。
        TPMS 在壳层内 |Phi| 并非球对称，壳上分位统计仅用卦限子集会与「全球」略有差异；
        若需与全球严格一致的分位/等值面，请使用 full。

    返回 (vertices, faces, voxel_info)。体素总量超限时仅将每轴采样限制在 rx_cap，不降低 K（周期数由 cli 中 a→K 决定）。
    """
    mod = get_mixer()
    get_field = mod.get_field
    weld_vertices = mod.weld_vertices

    # 理想采样：K·res（与 Mixer 一致）。体素总量有上限时只压缩网格分辨率，不降低 K（否则 a 与界面显示失效）。
    rx_raw = max(int(round(state.Kx * res)), 8)
    ry_raw = max(int(round(state.Ky * res)), 8)
    rz_raw = max(int(round(state.Kz * res)), 8)
    rx_cap = max(8, int((float(max_voxels) ** (1.0 / 3.0)) * 0.985))
    rx = min(rx_raw, rx_cap)
    ry = min(ry_raw, rx_cap)
    rz = min(rz_raw, rx_cap)
    grid_capped = (rx_raw > rx_cap) or (ry_raw > rx_cap) or (rz_raw > rx_cap)
    vox = rx * ry * rz

    sx = state.Sx / max(rx - 1, 1)
    sy = state.Sy / max(ry - 1, 1)
    sz = state.Sz / max(rz - 1, 1)
    xc_full = np.linspace(0.0, float(state.Sx), rx, dtype=np.float64)
    yc_full = np.linspace(0.0, float(state.Sy), ry, dtype=np.float64)
    zc_full = np.linspace(0.0, float(state.Sz), rz, dtype=np.float64)
    cx = 0.5 * float(state.Sx)
    cy = 0.5 * float(state.Sy)
    cz = 0.5 * float(state.Sz)
    origin_xyz: tuple[float, float, float] = (0.0, 0.0, 0.0)

    if mesh_domain == "octant":

        def _first_ge(arr: np.ndarray, t: float) -> int:
            m = np.nonzero(arr >= t - 1e-12)[0]
            return int(m[0]) if m.size else len(arr) - 1

        i0, j0, k0 = _first_ge(xc_full, cx), _first_ge(yc_full, cy), _first_ge(zc_full, cz)
        xc = xc_full[i0:]
        yc = yc_full[j0:]
        zc = zc_full[k0:]
        rx_o, ry_o, rz_o = len(xc), len(yc), len(zc)
        if min(rx_o, ry_o, rz_o) < 4:
            mesh_domain = "full"
        else:
            vox = rx_o * ry_o * rz_o
            gx = (xc / float(state.Sx) * (state.Kx * 2 * math.pi)).astype(np.float32)
            gy = (yc / float(state.Sy) * (state.Ky * 2 * math.pi)).astype(np.float32)
            gz = (zc / float(state.Sz) * (state.Kz * 2 * math.pi)).astype(np.float32)
            X, Y, Z = np.meshgrid(gx, gy, gz, indexing="ij")
            origin_xyz = (float(xc[0]), float(yc[0]), float(zc[0]))
    if mesh_domain == "full":
        gx = np.linspace(0.0, state.Kx * 2 * math.pi, rx, dtype=np.float32)
        gy = np.linspace(0.0, state.Ky * 2 * math.pi, ry, dtype=np.float32)
        gz = np.linspace(0.0, state.Kz * 2 * math.pi, rz, dtype=np.float32)
        X, Y, Z = np.meshgrid(gx, gy, gz, indexing="ij")
        xc = xc_full
        yc = yc_full
        zc = zc_full
        origin_xyz = (0.0, 0.0, 0.0)

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

    XM, YM, ZM = np.meshgrid(xc, yc, zc, indexing="ij")
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

    # 球外：须为强负（与孔隙同号）。误用正值会把角区标成「实体」，与 pad 负值在立方体
    # 网格外表面形成整面虚假零等值面，3D 中呈实心立方体外壳。
    outside_strength = float(np.max(absPhi) + 1.0)
    outside = dist_mm > r_max + 1e-3
    iso_field[outside] = 0.0
    sdf = (iso_field - absPhi).astype(np.float32)
    sdf[outside] = -outside_strength

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
    ox, oy, oz = origin_xyz
    if ox != 0.0 or oy != 0.0 or oz != 0.0:
        verts_xyz[:, 0] += np.float32(ox)
        verts_xyz[:, 1] += np.float32(oy)
        verts_xyz[:, 2] += np.float32(oz)
    faces = np.asarray(faces, dtype=np.int32)

    v_out, f_out = weld_vertices(verts_xyz, faces, decimals=5)
    vox_info: dict = {
        "mesh_domain": mesh_domain,
        "rx_requested": rx_raw,
        "ry_requested": ry_raw,
        "rz_requested": rz_raw,
        "rx_used": rx,
        "ry_used": ry,
        "rz_used": rz,
        "rx_cap": rx_cap,
        "grid_capped": grid_capped,
        "voxel_count": int(vox),
    }
    if mesh_domain == "octant":
        vox_info["rx_used"] = len(xc)
        vox_info["ry_used"] = len(yc)
        vox_info["rz_used"] = len(zc)
    notes: list[str] = []
    if mesh_domain == "octant":
        notes.append(
            "mesh_domain=octant：仅 +X+Y+Z 卦限体素，计算量约 1/8；"
            "壳层内 |Phi| 非球对称，分位 iso 与全球体素略有差异，验证请用 full。"
        )
    if grid_capped:
        notes.append(
            f"体素每轴已限制为 ≤{rx_cap}（理想 K·res={rx_raw}）。"
            f"周期数 K 仍由目标 a 决定；单胞边长 d/K 不变。高 K 时可能欠采样，可提高 Res 改善（体素总量仍受上限）。"
        )
    vox_info["note"] = " ".join(notes)
    return v_out, f_out, vox_info
