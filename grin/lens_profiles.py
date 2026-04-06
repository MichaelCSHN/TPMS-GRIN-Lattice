"""
透镜剖面与径向分层方式：龙伯、伊顿（占位线性）、等厚 / Δn / Δε 分层。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable

import numpy as np

from grin import luneburg


class LensProduct(str, Enum):
    LUNEBURG = "luneburg"
    EATON = "eaton"


class LayeringMode(str, Enum):
    EQUAL_THICKNESS = "equal_thickness"
    EQUAL_DELTA_N = "equal_delta_n"
    EQUAL_DELTA_EPS = "equal_delta_eps"


def _inverse_r_from_eps_luneburg(eps: float, R: float, eps_air: float, eps_m: float) -> float:
    """ε(r)=ε_air+(ε_m-ε_air)(1-(r/R)^2) 的反函数，返回 r∈[0,R]。"""
    A = eps_m - eps_air
    if abs(A) < 1e-15:
        return 0.0
    u = 1.0 - (float(eps) - eps_air) / A
    u = float(np.clip(u, 0.0, 1.0))
    return R * np.sqrt(u)


def _inverse_r_from_eps_eaton_linear(eps: float, R: float, eps_air: float, eps_m: float) -> float:
    """ε(r)=ε_m+(ε_air-ε_m)(r/R)。"""
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
    r_mm = np.asarray(r_mm, dtype=np.float64)
    if product == LensProduct.LUNEBURG:
        return luneburg.epsilon_luneburg_mapped(r_mm, R, eps_air, eps_m)
    if product == LensProduct.EATON:
        t = np.clip(r_mm / R, 0.0, 1.0)
        return eps_m + (eps_air - eps_m) * t
    return luneburg.epsilon_luneburg_mapped(r_mm, R, eps_air, eps_m)


def build_radial_edges(
    radius_mm: float,
    n_layers: int,
    eps_air: float,
    eps_m: float,
    product: LensProduct,
    mode: LayeringMode,
) -> tuple[np.ndarray, np.ndarray]:
    """
    返回 (r_edges, r_centers)，r_edges 单调 0→R。
    """
    R = float(radius_mm)
    n_layers = int(max(3, min(20, n_layers)))

    if mode == LayeringMode.EQUAL_THICKNESS:
        r_edges = np.linspace(0.0, R, n_layers + 1)
        r_centers = 0.5 * (r_edges[:-1] + r_edges[1:])
        return r_edges, r_centers

    if product == LensProduct.LUNEBURG:
        eps0 = float(epsilon_at_r(np.array([0.0]), R, eps_air, eps_m, product)[0])
        epsR = float(epsilon_at_r(np.array([R]), R, eps_air, eps_m, product)[0])
    else:
        eps0 = float(epsilon_at_r(np.array([0.0]), R, eps_air, eps_m, product)[0])
        epsR = float(epsilon_at_r(np.array([R]), R, eps_air, eps_m, product)[0])

    if mode == LayeringMode.EQUAL_DELTA_EPS:
        eps_edges = np.linspace(eps0, epsR, n_layers + 1)
        inv = _inverse_r_from_eps_luneburg if product == LensProduct.LUNEBURG else _inverse_r_from_eps_eaton_linear
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
        inv = _inverse_r_from_eps_luneburg if product == LensProduct.LUNEBURG else _inverse_r_from_eps_eaton_linear
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


def design_curves_sampled(
    radius_mm: float,
    eps_air: float,
    eps_m: float,
    product: LensProduct,
    n_samples: int = 128,
) -> dict:
    """连续曲线 r, n(r), eps(r), Vf(r)（Vf 由 EMT 反演）。"""
    from grin import emt

    R = float(radius_mm)
    r = np.linspace(0.0, R, n_samples)
    eps = epsilon_at_r(r, R, eps_air, eps_m, product)
    n = np.sqrt(np.maximum(eps, 1e-9))
    vf = np.array([emt.invert_vf_solid_for_epsilon(float(e), eps_m, eps_air) for e in eps])
    return {"r_mm": r, "epsilon_r": eps, "n_r": n, "vf_r": vf}


def wavelength_mm_vacuum(frequency_ghz: float) -> float:
    c = 299.792458
    return c / float(frequency_ghz)
