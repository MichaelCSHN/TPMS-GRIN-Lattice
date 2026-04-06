"""
GRIN / 龙伯：从 YAML 配置生成径向分层 TPMS STL（不修改 TPMS_Mixer_v1.1.0.py）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import yaml

from grin import emt
from grin.lens_profiles import LensProduct, LayeringMode, build_shell_table
from grin import metrics_geo
from grin.tpms_mixer_bridge import get_mixer
from grin.tpms_radial_shells import compute_tpms_radial_shell_quantiles
from grin.design_audit import get_spec_audit_report
from grin import vf_measurement


def load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def merge_dict(base: dict, override: dict | None) -> dict:
    if not override:
        return base
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merge_dict(out[k], v)
        else:
            out[k] = v
    return out


def compute_grin_mesh(
    radius_mm: float,
    n_layers: int,
    epsilon_matrix: float,
    epsilon_air: float,
    res: int,
    type_tpms: str = "G",
    *,
    type_b: str | None = None,
    mix_enabled: bool = False,
    mix_dir: str = "Z",
    trans_center: float = 0.5,
    trans_k: float = 6.0,
    lens_product: str = "luneburg",
    layering_mode: str = "equal_thickness",
    geometry_shape: str = "sphere_in_cube",
    frequency_ghz: float = 10.0,
    target_efficiency_pct: float | None = None,
    d_c_mm: float = 0.4,
    a_cell_mm: float | None = None,
    envelope_margin_mm: float = 0.0,
    quantile_override: list[float] | None = None,
    measure_vf: bool = True,
    mesh_domain: str = "full",
) -> tuple:
    """
    计算 GRIN 分层 TPMS 网格，不写文件。
    返回 (verts, faces, meta_layers, report_extra)

    a_cell_mm：目标单胞边长（mm）。用于确定立方体域内沿各轴的周期数 K（Kx=Ky=Kz），
    使物理周期长度 ≈ box_mm/K；径向局部 Vf 仍由分层 iso 控制。

    envelope_margin_mm：立方体包络在直径 2R 基础上的半宽余量（每侧），使 box_mm=2R+2*margin ≥ 2R。
    quantile_override：若给定，覆盖各壳层由 EMT 得到的分位 q（用于迭代优化）。
    measure_vf：是否做蒙特卡洛距离带 Vf 代理与角向 Vf 统计（略增耗时）。
    mesh_domain："full" 全球体素；"octant" 仅 +X+Y+Z 卦限（约 1/8 体素，快；壳层分位与 full 略有差异）。
    """
    try:
        product = LensProduct(lens_product)
    except ValueError:
        product = LensProduct.LUNEBURG
    try:
        mode = LayeringMode(layering_mode)
    except ValueError:
        mode = LayeringMode.EQUAL_THICKNESS

    rows, r_edges = build_shell_table(radius_mm, n_layers, epsilon_air, epsilon_matrix, product, mode)

    margin = float(max(0.0, envelope_margin_mm))
    R = float(radius_mm)
    d = 2.0 * R + 2.0 * margin
    K, k_meta = metrics_geo.resolve_tpms_periods_K(d, res, r_edges, a_cell_mm)

    quantiles: list[float] = []
    meta_layers: list[dict] = []
    for row in rows:
        vf_s = emt.invert_vf_solid_for_epsilon(row.epsilon_target, epsilon_matrix, epsilon_air)
        q = float(max(0.001, min(0.999, vf_s)))
        if quantile_override is not None and row.index < len(quantile_override):
            q = float(max(0.001, min(0.999, quantile_override[row.index])))
        quantiles.append(q)
        meta_layers.append(
            {
                "index": row.index,
                "r_mm": [row.r_inner, row.r_outer],
                "epsilon_target": row.epsilon_target,
                "vf_solid_emt": vf_s,
                "quantile_q": q,
            }
        )

    mod = get_mixer()
    st = mod.AppState()
    st.typeA = type_tpms
    st.typeB = (type_b if mix_enabled and type_b else type_tpms)
    st.dir = mix_dir if mix_dir in ("Z", "X", "XZ") else "Z"
    st.trans_center = float(trans_center)
    st.trans_k = float(trans_k)
    st.Kx = st.Ky = st.Kz = int(K)
    st.Sx = st.Sy = st.Sz = d
    st.RD = 0.3

    md = mesh_domain if mesh_domain in ("full", "octant") else "full"
    verts, faces, vox_info = compute_tpms_radial_shell_quantiles(
        st, res, list(r_edges), quantiles, mesh_domain=md
    )

    lattice_parts = [s for s in k_meta.get("notes", []) if s]
    if vox_info.get("note"):
        lattice_parts.append(vox_info["note"])
    shell_th = np.diff(np.asarray(r_edges, dtype=np.float64)).tolist()
    report_extra: dict = {
        "lens_product": product.value,
        "layering_mode": mode.value,
        "geometry_shape": geometry_shape,
        "mesh_domain": md,
        "frequency_ghz": frequency_ghz,
        "target_efficiency_pct": target_efficiency_pct,
        "d_c_mm": d_c_mm,
        "mix_enabled": mix_enabled,
        "box_mm": float(d),
        "envelope_margin_mm": float(margin),
        "per_shell_thickness_mm": shell_th,
        "tpms_periods_K": int(K),
        "a_cell_requested_mm": k_meta.get("a_requested_mm"),
        "a_cell_effective_mm": float(k_meta["a_effective_mm"]),
        "min_layer_thickness_mm": float(k_meta["min_layer_thickness_mm"]),
        "lattice_note": " ".join(lattice_parts),
        "voxel_grid": vox_info,
    }
    est = metrics_geo.estimate_a_dc_from_res_and_box(res, d, k_periods=K)
    report_extra["a_voxel_step_mm"] = est["a_est_mm"]
    report_extra["a_est_mm"] = float(k_meta["a_effective_mm"])
    report_extra["a_est_note"] = est.get("note", "")
    report_extra["spec_audit"] = get_spec_audit_report(geometry_shape)

    try:
        import trimesh

        mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=False)
        vol = float(mesh.volume)
        v_ball = (4.0 / 3.0) * 3.14159265 * (radius_mm**3)
        report_extra["volume_mm3"] = vol
        vf_ball = vol / v_ball if v_ball > 0 else None
        report_extra["volume_fraction_in_ball_approx"] = vf_ball
        if vf_ball is not None and vf_ball > 1.0:
            report_extra["volume_note"] = (
                "立方体域内周期结构，实体可超出内接球；体积/球体积仅供参考，非严格球内 Vf。"
            )
    except Exception as e:
        report_extra["volume_note"] = f"trimesh 体积未计算: {e}"

    center = np.array([d / 2, d / 2, d / 2], dtype=np.float64)
    ri, ro = 0.25 * float(radius_mm), 0.85 * float(radius_mm)
    au = metrics_geo.angular_uniformity_cv(verts, center, ri, ro)
    report_extra["angular_uniformity"] = au

    if measure_vf:
        try:
            vf_bl = np.array([m["vf_solid_emt"] for m in meta_layers], dtype=np.float64)
            r_e_m = metrics_geo.r_edges_from_meta_layers(meta_layers)
            measured_vf, mf_info = vf_measurement.measure_vf_band_proxy(
                verts, faces, center, r_e_m, float(d_c_mm), n_samples_total=40000
            )
            report_extra["vf_measurement"] = {
                "per_shell_proxy": measured_vf.tolist(),
                "target_vf_emt": vf_bl.tolist(),
                "compare": vf_measurement.compare_vf_to_target(measured_vf, vf_bl),
                **mf_info,
            }
            report_extra["angular_vf_phi"] = metrics_geo.angular_vf_by_phi(
                verts, center, r_e_m, vf_bl
            )
        except Exception as e:
            report_extra["vf_measurement"] = {"error": str(e)}

    return verts, faces, meta_layers, report_extra


def run_grin_export(
    radius_mm: float,
    n_layers: int,
    epsilon_matrix: float,
    epsilon_air: float,
    res: int,
    out_stl: Path,
    type_tpms: str = "G",
    report_json: Path | None = None,
    **kwargs,
) -> dict:
    verts, faces, meta_layers, report_extra = compute_grin_mesh(
        radius_mm, n_layers, epsilon_matrix, epsilon_air, res, type_tpms, **kwargs
    )

    mod = get_mixer()
    out_stl.parent.mkdir(parents=True, exist_ok=True)
    mod.write_stl_binary_with_progress(str(out_stl), faces, verts)

    report = {
        "radius_mm": radius_mm,
        "n_layers": n_layers,
        "epsilon_matrix": epsilon_matrix,
        "epsilon_air": epsilon_air,
        "res": res,
        "layers": meta_layers,
        "stl": str(out_stl.resolve()),
        **report_extra,
    }

    if report_json:
        report_json.parent.mkdir(parents=True, exist_ok=True)
        with open(report_json, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

    return report


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="GRIN 龙伯径向分层 TPMS → STL")
    p.add_argument("--config", type=Path, default=Path("config/grin_defaults.yaml"))
    p.add_argument("--override", type=Path, help="覆盖默认的 YAML 片段")
    p.add_argument("--out", type=Path, default=Path("output/luneburg_tpms.stl"))
    p.add_argument("--report", type=Path, default=Path("output/luneburg_report.json"))
    p.add_argument("--res", type=int, default=None, help="体素分辨率（覆盖配置）")
    p.add_argument("--type", type=str, default="G", choices=["P", "G", "D", "I", "N"])
    args = p.parse_args(argv)

    cfg = load_yaml(args.config)
    if args.override and args.override.is_file():
        cfg = merge_dict(cfg, load_yaml(args.override))

    g = cfg.get("geometry", {})
    m = cfg.get("material", {})
    rm = g.get("radius_mm", 100.0)
    radius = float(rm["default"]) if isinstance(rm, dict) else float(rm)
    n_layers = int(g.get("radial_layers", 6))
    em = m.get("epsilon_matrix", 2.8)
    eps_m = float(em["default"]) if isinstance(em, dict) else float(em)

    res = int(args.res) if args.res is not None else 36

    kwargs: dict = {}
    if isinstance(g.get("envelope_margin_mm"), (int, float)):
        kwargs["envelope_margin_mm"] = float(g["envelope_margin_mm"])
    mesh_cfg = cfg.get("mesh")
    if isinstance(mesh_cfg, dict):
        md = mesh_cfg.get("mesh_domain")
        if md in ("full", "octant"):
            kwargs["mesh_domain"] = md
        if "measure_vf" in mesh_cfg:
            kwargs["measure_vf"] = bool(mesh_cfg["measure_vf"])

    report = run_grin_export(
        radius_mm=radius,
        n_layers=n_layers,
        epsilon_matrix=eps_m,
        epsilon_air=1.0,
        res=res,
        out_stl=args.out,
        type_tpms=args.type,
        report_json=args.report,
        **kwargs,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
