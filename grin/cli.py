"""
GRIN / 龙伯：从 YAML 配置生成径向分层 TPMS STL（不修改 TPMS_Mixer_v1.1.0.py）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from grin import emt, luneburg
from grin.tpms_mixer_bridge import get_mixer
from grin.tpms_radial_shells import compute_tpms_radial_shell_quantiles


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


def run_grin_export(
    radius_mm: float,
    n_layers: int,
    epsilon_matrix: float,
    epsilon_air: float,
    res: int,
    out_stl: Path,
    type_tpms: str = "G",
    report_json: Path | None = None,
) -> dict:
    layers = luneburg.luneburg_layers_table(radius_mm, n_layers, epsilon_air, epsilon_matrix)
    r_edges, _ = luneburg.build_radial_layers(radius_mm, n_layers)

    quantiles = []
    meta_layers = []
    for lay in layers:
        vf_s = emt.invert_vf_solid_for_epsilon(lay.epsilon_target, epsilon_matrix, epsilon_air)
        q = float(max(0.001, min(0.999, vf_s)))
        quantiles.append(q)
        meta_layers.append(
            {
                "index": lay.index,
                "r_mm": [lay.r_inner_mm, lay.r_outer_mm],
                "epsilon_target": lay.epsilon_target,
                "vf_solid_emt": vf_s,
                "quantile_q": q,
            }
        )

    mod = get_mixer()
    st = mod.AppState()
    st.typeA = st.typeB = type_tpms
    st.Kx = st.Ky = st.Kz = 2
    d = 2.0 * float(radius_mm)
    st.Sx = st.Sy = st.Sz = d
    st.RD = 0.3

    verts, faces = compute_tpms_radial_shell_quantiles(st, res, list(r_edges), quantiles)

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
    }

    try:
        import trimesh

        mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=False)
        vol = float(mesh.volume)
        v_ball = (4.0 / 3.0) * 3.14159265 * (radius_mm**3)
        report["volume_mm3"] = vol
        vf_ball = vol / v_ball if v_ball > 0 else None
        report["volume_fraction_in_ball_approx"] = vf_ball
        if vf_ball is not None and vf_ball > 1.0:
            report["volume_note"] = (
                "立方体域内周期结构，实体可超出内接球；体积/球体积仅供参考，非严格球内 Vf。"
            )
    except Exception as e:
        report["volume_note"] = f"trimesh 体积未计算: {e}"

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

    report = run_grin_export(
        radius_mm=radius,
        n_layers=n_layers,
        epsilon_matrix=eps_m,
        epsilon_air=1.0,
        res=res,
        out_stl=args.out,
        type_tpms=args.type,
        report_json=args.report,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
