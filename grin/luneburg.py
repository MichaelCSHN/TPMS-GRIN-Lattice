"""
经典龙伯剖面（归一化折射率）映射到目标 ε(r)，并径向分层。

采用 n(r) = sqrt(2 - (r/R)^2)，r∈[0,R]，n(R)=1，n(0)=sqrt(2)。
将 n^2 的形状映射到 [ε_air, ε_matrix]：中心对应基体有效 ε，表面接近空气等效 ε。
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class LuneburgLayer:
    index: int
    r_inner_mm: float
    r_outer_mm: float
    r_center_mm: float
    n_ratio: float  # n(r)/n(R) 未用，保留
    epsilon_target: float


def epsilon_luneburg_mapped(
    r_mm: np.ndarray,
    radius_mm: float,
    epsilon_air: float,
    epsilon_matrix: float,
) -> np.ndarray:
    """
    ε(r) = ε_air + (ε_matrix - ε_air) * (n(r)^2 - n(R)^2) / (n(0)^2 - n(R)^2)
         = ε_air + (ε_matrix - ε_air) * (1 - (r/R)^2)，因 n^2 = 2 - (r/R)^2。
    """
    R = float(radius_mm)
    t = np.clip(r_mm / R, 0.0, 1.0)
    return epsilon_air + (epsilon_matrix - epsilon_air) * (1.0 - t**2)


def build_radial_layers(radius_mm: float, n_layers: int) -> tuple[np.ndarray, np.ndarray]:
    """
    返回 (r_edges, r_centers)，r_edges 长度 n_layers+1，从 0 到 radius_mm。
    """
    n_layers = int(max(3, min(10, n_layers)))
    r_edges = np.linspace(0.0, float(radius_mm), n_layers + 1)
    r_centers = 0.5 * (r_edges[:-1] + r_edges[1:])
    return r_edges, r_centers


def luneburg_layers_table(
    radius_mm: float,
    n_layers: int,
    epsilon_air: float,
    epsilon_matrix: float,
) -> list[LuneburgLayer]:
    r_edges, r_centers = build_radial_layers(radius_mm, n_layers)
    layers: list[LuneburgLayer] = []
    R = float(radius_mm)
    for k in range(n_layers):
        rc = r_centers[k]
        n_at = np.sqrt(max(0.0, 2.0 - (rc / R) ** 2))
        eps = float(epsilon_luneburg_mapped(np.array([rc]), R, epsilon_air, epsilon_matrix)[0])
        layers.append(
            LuneburgLayer(
                index=k,
                r_inner_mm=float(r_edges[k]),
                r_outer_mm=float(r_edges[k + 1]),
                r_center_mm=float(rc),
                n_ratio=float(n_at),
                epsilon_target=eps,
            )
        )
    return layers
