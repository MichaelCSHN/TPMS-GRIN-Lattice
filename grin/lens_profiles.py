"""
透镜剖面与径向分层：龙伯理想 n(0)=√2、ε(0)=2、ε(R)=1（相对）；
目标等效 ε_eff(r) 取该理想剖面，再由 Maxwell Garnett（ε_m、ε_air）反演实体体积分数 Vf。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np

from grin import emt


class LensProduct(str, Enum):
    LUNEBURG = "luneburg"
    EATON = "eaton"


class LayeringMode(str, Enum):
    EQUAL_THICKNESS = "equal_thickness"
    EQUAL_DELTA_N = "equal_delta_n"
    EQUAL_DELTA_EPS = "equal_delta_eps"


def luneburg_epsilon_ideal(r_mm: np.ndarray, R_mm: float) -> np.ndarray:
    """相对理想介电常数 ε_id(r)=2-(r/R)^2，故 ε(0)=2，ε(R)=1。"""
    R = float(R_mm)
    t = np.clip(np.asarray(r_mm, dtype=np.float64) / R, 0.0, 1.0)
    return 2.0 - t**2


def luneburg_n_ideal(r_mm: np.ndarray, R_mm: float) -> np.ndarray:
    """n_id(r)=sqrt(2-(r/R)^2)，故 n(0)=sqrt(2)，n(R)=1。"""
    return np.sqrt(np.maximum(luneburg_epsilon_ideal(r_mm, R_mm), 1e-15))


def luneburg_epsilon_physical(r_mm: np.ndarray, R_mm: float, eps_air: float, eps_m: float) -> np.ndarray:
    """
    龙伯目标「等效介电常数」ε_eff(r)，用于 EMT 反演实体体积分数。

    与旧版不同：不再把 ε_id 线性映射到 [ε_air, ε_m]（那样会把 r=0 映成 ε_m，
    反演 Vf 恒为 1，与「材料 ε_m、目标 ε_id(0)=2 → Vf<1」矛盾）。

    此处取 ε_eff(r)=ε_id(r)=2-(r/R)²（相对介电常数，球面为 1）；
    ε_air、ε_m 仅作为 Maxwell Garnett 两相参数参与 emt.invert_vf_solid_for_epsilon，
    不用于拉伸 ε_eff 曲线。
    """
    _ = (eps_air, eps_m)  # 签名保留，与 epsilon_at_r 等调用一致
    return luneburg_epsilon_ideal(r_mm, R_mm)


def _inverse_r_from_eps_luneburg_physical(eps: float, R: float, eps_air: float, eps_m: float) -> float:
    """龙伯：ε_eff(r)=ε_id=2-(r/R)²，由目标 ε∈[1,2] 反解 r = R·√(2-ε)。"""
    _ = (eps_air, eps_m)
    eid = float(np.clip(float(eps), 1.0, 2.0))
    r = float(R) * np.sqrt(max(0.0, 2.0 - eid))
    return float(np.clip(r, 0.0, float(R)))


def _inverse_r_from_eps_eaton_linear(eps: float, R: float, eps_air: float, eps_m: float) -> float:
    de = eps_air - eps_m
    if abs(de) < 1e-15:
        return 0.0
    t = (float(eps) - eps_m) / de
    return float(np.clip(t, 0.0, 1.0)) * R


def epsilon_at_r(
    r_mm: np.ndarray,
    R: float,
    eps_air: float,
    eps_m: float,
    product: LensProduct,
) -> np.ndarray:
    """壳层目标：物理有效 ε(r)，供 EMT 反演与 MC 分层。"""
    r_mm = np.asarray(r_mm, dtype=np.float64)
    if product == LensProduct.LUNEBURG:
        return luneburg_epsilon_physical(r_mm, R, eps_air, eps_m)
    if product == LensProduct.EATON:
        t = np.clip(r_mm / float(R), 0.0, 1.0)
        return eps_m + (eps_air - eps_m) * t
    return luneburg_epsilon_physical(r_mm, R, eps_air, eps_m)


def build_radial_edges(
    radius_mm: float,
    n_layers: int,
    eps_air: float,
    eps_m: float,
    product: LensProduct,
    mode: LayeringMode,
) -> tuple[np.ndarray, np.ndarray]:
    R = float(radius_mm)
    n_layers = int(max(3, min(20, n_layers)))

    if mode == LayeringMode.EQUAL_THICKNESS:
        r_edges = np.linspace(0.0, R, n_layers + 1)
        r_centers = 0.5 * (r_edges[:-1] + r_edges[1:])
        return r_edges, r_centers

    if product == LensProduct.LUNEBURG and mode == LayeringMode.EQUAL_DELTA_N:
        n_edges = np.linspace(np.sqrt(2.0), 1.0, n_layers + 1)
        eid_edges = n_edges**2
        r_edges = R * np.sqrt(np.clip(2.0 - eid_edges, 0.0, None))
        r_edges[0] = 0.0
        r_edges[-1] = R
        r_centers = 0.5 * (r_edges[:-1] + r_edges[1:])
        return r_edges, r_centers

    if product == LensProduct.LUNEBURG and mode == LayeringMode.EQUAL_DELTA_EPS:
        eid_edges = np.linspace(2.0, 1.0, n_layers + 1)
        r_edges = R * np.sqrt(np.clip(2.0 - eid_edges, 0.0, None))
        r_edges[0] = 0.0
        r_edges[-1] = R
        r_centers = 0.5 * (r_edges[:-1] + r_edges[1:])
        return r_edges, r_centers

    eps0 = float(epsilon_at_r(np.array([0.0]), R, eps_air, eps_m, product)[0])
    epsR = float(epsilon_at_r(np.array([R]), R, eps_air, eps_m, product)[0])

    if mode == LayeringMode.EQUAL_DELTA_EPS:
        eps_edges = np.linspace(eps0, epsR, n_layers + 1)
        inv = _inverse_r_from_eps_luneburg_physical if product == LensProduct.LUNEBURG else _inverse_r_from_eps_eaton_linear
        if product == LensProduct.EATON:
            inv = _inverse_r_from_eps_eaton_linear
        r_edges = np.array([inv(e, R, eps_air, eps_m) for e in eps_edges])
        r_edges[0] = 0.0
        r_edges[-1] = R
        r_centers = 0.5 * (r_edges[:-1] + r_edges[1:])
        return r_edges, r_centers

    if mode == LayeringMode.EQUAL_DELTA_N:
        n0 = np.sqrt(max(eps0, 1e-9))
        nR = np.sqrt(max(epsR, 1e-9))
        n_edges = np.linspace(n0, nR, n_layers + 1)
        eps_edges = n_edges**2
        inv = _inverse_r_from_eps_eaton_linear if product == LensProduct.EATON else _inverse_r_from_eps_luneburg_physical
        r_edges = np.array([inv(e, R, eps_air, eps_m) for e in eps_edges])
        r_edges[0] = 0.0
        r_edges[-1] = R
        r_centers = 0.5 * (r_edges[:-1] + r_edges[1:])
        return r_edges, r_centers

    r_edges = np.linspace(0.0, R, n_layers + 1)
    r_centers = 0.5 * (r_edges[:-1] + r_edges[1:])
    return r_edges, r_centers


@dataclass
class ShellRow:
    index: int
    r_inner: float
    r_outer: float
    r_center: float
    epsilon_target: float


def build_shell_table(
    radius_mm: float,
    n_layers: int,
    eps_air: float,
    eps_m: float,
    product: LensProduct,
    mode: LayeringMode,
) -> tuple[list[ShellRow], np.ndarray]:
    r_edges, r_centers = build_radial_edges(radius_mm, n_layers, eps_air, eps_m, product, mode)
    R = float(radius_mm)
    rows: list[ShellRow] = []
    for k in range(n_layers):
        rc = float(r_centers[k])
        eps = float(epsilon_at_r(np.array([rc]), R, eps_air, eps_m, product)[0])
        rows.append(
            ShellRow(
                index=k,
                r_inner=float(r_edges[k]),
                r_outer=float(r_edges[k + 1]),
                r_center=rc,
                epsilon_target=eps,
            )
        )
    return rows, r_edges


def shell_stair_targets(
    rows: list[ShellRow],
    r_edges: np.ndarray,
    radius_mm: float,
    eps_air: float,
    eps_m: float,
    product: LensProduct,
) -> dict[str, np.ndarray]:
    """
    各径向壳层上的目标量（分段常数），用于在 n/ε/Vf 图上叠加阶梯曲线。
    物理量由壳心处 epsilon_target 与 MG 反演得到；龙伯另给出壳心处的理想 n、ε。
    """
    R = float(radius_mm)
    r_e = np.asarray(r_edges, dtype=np.float64)
    eps_s = np.array([row.epsilon_target for row in rows], dtype=np.float64)
    n_phys_s = np.sqrt(np.maximum(eps_s, 1e-15))
    vf_s = np.array(
        [emt.invert_vf_solid_for_epsilon(float(e), eps_m, eps_air) for e in eps_s],
        dtype=np.float64,
    )
    if product == LensProduct.LUNEBURG:
        rc = np.array([row.r_center for row in rows], dtype=np.float64)
        n_id_s = luneburg_n_ideal(rc, R)
        e_id_s = luneburg_epsilon_ideal(rc, R)
    else:
        n_id_s = n_phys_s.copy()
        e_id_s = eps_s.copy()
    return {
        "r_edges": r_e,
        "n_phys_shell": n_phys_s,
        "epsilon_shell": eps_s,
        "vf_shell": vf_s,
        "n_ideal_shell": n_id_s,
        "epsilon_ideal_shell": e_id_s,
    }


def design_curves_sampled(
    radius_mm: float,
    eps_air: float,
    eps_m: float,
    product: LensProduct,
    n_samples: int = 128,
) -> dict:
    """
    返回理想 n、理想 ε；物理 ε；Vf solid = MG^{-1}(ε_phys|ε_m,ε_i)。
    Vf 为实体体积分数（0–1 为物理量纲，由 EMT 唯一确定，非任意归一化）。
    """
    R = float(radius_mm)
    r = np.linspace(0.0, R, n_samples)
    if product == LensProduct.LUNEBURG:
        epsilon_ideal = luneburg_epsilon_ideal(r, R)
        n_ideal = luneburg_n_ideal(r, R)
        epsilon_phys = luneburg_epsilon_physical(r, R, eps_air, eps_m)
    else:
        epsilon_phys = epsilon_at_r(r, R, eps_air, eps_m, product)
        epsilon_ideal = np.asarray(epsilon_phys, dtype=np.float64)
        n_ideal = np.sqrt(np.maximum(epsilon_ideal, 1e-15))

    n_phys = np.sqrt(np.maximum(epsilon_phys, 1e-15))
    vf_solid = np.array(
        [emt.invert_vf_solid_for_epsilon(float(e), eps_m, eps_air) for e in epsilon_phys],
        dtype=np.float64,
    )

    return {
        "r_mm": r,
        "n_ideal": n_ideal,
        "epsilon_ideal": epsilon_ideal,
        "epsilon_phys": epsilon_phys,
        "n_phys": n_phys,
        "vf_solid_emt": vf_solid,
    }


def wavelength_mm_vacuum(frequency_ghz: float) -> float:
    c = 299.792458
    return c / float(frequency_ghz)
