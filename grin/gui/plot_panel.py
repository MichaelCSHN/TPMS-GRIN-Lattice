"""Matplotlib：理想/物理 n、ε、MG 反演 Vf，壳层阶梯叠加，角向 Vf(φ)。"""

from __future__ import annotations

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.gridspec import GridSpec

from grin.gui.mpl_setup import configure_matplotlib_fonts


def _step_xy_post(r_edges: np.ndarray, y_per_shell: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """where='post' 阶梯：y[i] 作用于 [r_edges[i], r_edges[i+1])。"""
    y_ext = np.append(np.asarray(y_per_shell, dtype=np.float64), float(y_per_shell[-1]))
    return np.asarray(r_edges, dtype=np.float64), y_ext


class GrinPlotPanel(FigureCanvas):
    def __init__(self, parent=None):
        configure_matplotlib_fonts()
        self.fig = Figure(figsize=(8.6, 8.4), layout="constrained")
        super().__init__(self.fig)
        self.setParent(parent)
        try:
            self.fig.patch.set_facecolor("#fafafa")
        except Exception:
            pass
        gs = GridSpec(3, 2, figure=self.fig, height_ratios=[1.0, 1.0, 0.55], hspace=0.32, wspace=0.28)
        self.ax_n = self.fig.add_subplot(gs[0, 0])
        self.ax_eps = self.fig.add_subplot(gs[0, 1])
        self.ax_vf = self.fig.add_subplot(gs[1, 0])
        self.ax_phi = self.fig.add_subplot(gs[1, 1])
        self.ax_txt = self.fig.add_subplot(gs[2, :])
        for ax in (self.ax_n, self.ax_eps, self.ax_vf, self.ax_phi):
            ax.grid(True, alpha=0.3)

    def update_curves(
        self,
        r_mm: np.ndarray,
        n_ideal: np.ndarray,
        n_phys: np.ndarray,
        eps_ideal: np.ndarray,
        eps_phys: np.ndarray,
        vf_solid_emt: np.ndarray,
        a_mm: float | None,
        d_c_mm: float | None,
        angular: dict | None,
        lambda_mm: float | None,
        size_over_lambda: float | None,
        target_eff_pct: float | None,
        *,
        stair: dict | None = None,
        angular_phi: dict | None = None,
        layering_label: str | None = None,
        spec_audit_brief: str | None = None,
    ):
        self.ax_n.clear()
        self.ax_eps.clear()
        self.ax_vf.clear()
        self.ax_phi.clear()
        self.ax_txt.clear()
        for ax in (self.ax_n, self.ax_eps, self.ax_vf, self.ax_phi):
            ax.grid(True, alpha=0.3)

        dual_n = not np.allclose(n_ideal, n_phys, rtol=1e-5, atol=1e-7)
        dual_eps = not np.allclose(eps_ideal, eps_phys, rtol=1e-5, atol=1e-7)

        if dual_n:
            self.ax_n.plot(r_mm, n_ideal, color="#1565c0", linewidth=1.2, label="理想 n（连续）")
            self.ax_n.plot(r_mm, n_phys, color="#5c6bc0", linestyle="--", linewidth=1.2, label="物理 n（连续）")
        else:
            self.ax_n.plot(r_mm, n_phys, color="#1565c0", linewidth=1.2, label="n(r)")

        if dual_eps:
            self.ax_eps.plot(r_mm, eps_ideal, color="#2e7d32", linewidth=1.2, label="理想 ε（连续）")
            self.ax_eps.plot(r_mm, eps_phys, color="#66bb6a", linestyle="--", linewidth=1.2, label="物理 ε（连续）")
        else:
            self.ax_eps.plot(r_mm, eps_phys, color="#2e7d32", linewidth=1.2, label="epsilon(r)")

        self.ax_vf.plot(r_mm, vf_solid_emt, color="#c62828", linewidth=1.2, label="Vf 连续 (MG)")

        if stair is not None:
            r_e = stair["r_edges"]
            rx, y = _step_xy_post(r_e, stair["n_ideal_shell"])
            self.ax_n.step(rx, y, where="post", color="#ff6f00", linewidth=1.6, alpha=0.9, label="分层·理想 n")
            rx, y = _step_xy_post(r_e, stair["n_phys_shell"])
            self.ax_n.step(rx, y, where="post", color="#000000", linewidth=1.2, alpha=0.55, label="分层·物理 n")

            rx, y = _step_xy_post(r_e, stair["epsilon_ideal_shell"])
            self.ax_eps.step(rx, y, where="post", color="#ff6f00", linewidth=1.6, alpha=0.9, label="分层·理想 ε")
            rx, y = _step_xy_post(r_e, stair["epsilon_shell"])
            self.ax_eps.step(rx, y, where="post", color="#000000", linewidth=1.2, alpha=0.55, label="分层·物理 ε")

            rx, y = _step_xy_post(r_e, stair["vf_shell"])
            self.ax_vf.step(rx, y, where="post", color="#000000", linewidth=1.6, alpha=0.85, label="分层·目标 Vf")

        h1, l1 = self.ax_n.get_legend_handles_labels()
        by = dict(zip(l1, h1))
        self.ax_n.legend(by.values(), by.keys(), loc="best", fontsize=7)

        h2, l2 = self.ax_eps.get_legend_handles_labels()
        by2 = dict(zip(l2, h2))
        self.ax_eps.legend(by2.values(), by2.keys(), loc="best", fontsize=7)

        h3, l3 = self.ax_vf.get_legend_handles_labels()
        by3 = dict(zip(l3, h3))
        self.ax_vf.legend(by3.values(), by3.keys(), loc="best", fontsize=7)

        self.ax_n.set_xlabel("r (mm)")
        self.ax_n.set_ylabel("n(r)")
        self.ax_eps.set_xlabel("r (mm)")
        self.ax_eps.set_ylabel("epsilon(r)")
        self.ax_vf.set_xlabel("r (mm)")
        self.ax_vf.set_ylabel("实体体积分数 Vf")
        self.ax_vf.set_ylim(-0.02, 1.05)

        if angular_phi is not None and angular_phi.get("phi_deg") is not None and angular_phi.get("vf_mean") is not None:
            pd = angular_phi["phi_deg"]
            vm = angular_phi["vf_mean"]
            self.ax_phi.plot(pd, vm, color="#6a1b9a", linewidth=1.4, label=r"$\langle V_f\rangle(\varphi)$")
            g = angular_phi.get("vf_global_mean")
            if g is not None:
                self.ax_phi.axhline(g, color="#9e9e9e", linestyle=":", linewidth=1.0, label=f"全局均值 {g:.3f}")
            self.ax_phi.set_xlabel(r"方位角 $\varphi$ (°)")
            self.ax_phi.set_ylabel("角向平均 Vf")
            self.ax_phi.set_xlim(-185, 185)
            self.ax_phi.legend(loc="best", fontsize=7)
        else:
            self.ax_phi.text(
                0.5,
                0.5,
                "角向 Vf(φ)：生成网格后\n根据壳层目标 Vf 与顶点方位分箱",
                ha="center",
                va="center",
                transform=self.ax_phi.transAxes,
                fontsize=9,
                color="#616161",
            )
            self.ax_phi.set_xlabel(r"方位角 $\varphi$ (°)")
            self.ax_phi.set_ylabel("角向平均 Vf")

        lines = []
        if layering_label:
            lines.append(layering_label)
        if lambda_mm is not None:
            lines.append(f"真空波长 λ0≈{lambda_mm:.4f} mm（c/f）")
        if size_over_lambda is not None:
            lines.append(f"尺寸/λ0（半径）≈ {size_over_lambda:.2f}")
        if a_mm is not None:
            lines.append(f"单胞边长 d/K ≈ {a_mm:.4f} mm（物理周期，d=2R）")
        if d_c_mm is not None:
            lines.append(f"最小线径约束 d_c = {d_c_mm:.4f} mm")
        if target_eff_pct is not None and target_eff_pct > 1e-6:
            lines.append(f"目标效率（相对理想透镜）: {target_eff_pct:.1f} %（仅记录，未参与优化）")
        if angular and angular.get("cv") is not None:
            lines.append(f"顶点方位数密度 CV(φ) ≈ {angular['cv']:.4f}（占位）")
        if angular_phi and angular_phi.get("cv_vf") is not None:
            lines.append(f"角向 Vf 起伏 CV ≈ {angular_phi['cv_vf']:.4f}")
        if angular_phi and angular_phi.get("note"):
            lines.append(f"角向 Vf：{angular_phi['note']}")
        if spec_audit_brief:
            lines.append(spec_audit_brief)
        if not lines:
            lines.append("生成网格后更新工艺与角向指标。")
        self.ax_txt.axis("off")
        self.ax_txt.text(
            0.02,
            0.98,
            "\n".join(lines),
            transform=self.ax_txt.transAxes,
            va="top",
            fontsize=9,
            family="sans-serif",
        )
        self.draw()
