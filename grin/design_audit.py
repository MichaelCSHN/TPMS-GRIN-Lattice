"""
设计逻辑与代码实现对照（报告 JSON / GUI 提示）。

说明：本模块不参与数值计算，仅汇总「规范步骤」与当前实现的差异，便于审查与后续迭代。
"""

from __future__ import annotations


def get_spec_audit_report(geometry_shape: str) -> dict[str, str]:
    """
    与用户给定的七步逻辑逐项对照（短句，写入 report_extra['spec_audit']）。
    """
    return {
        "1_理想n_eps连续": (
            "已实现：龙伯 ε_id(r)=2-(r/R)²、n_id=√ε_id；目标 ε_eff 取 ε_id（EMT 用 ε_m、ε_air）；"
            "design_curves_sampled 与 GUI 曲线。"
        ),
        "2_离散n_eps_i": (
            "已实现：build_radial_edges + build_shell_table，壳心处 epsilon_target 作为层目标；"
            "shell_stair_targets 在图中叠加阶梯（物理 ε、n、Vf）。"
        ),
        "3_EMT得Vf_i": (
            "已实现：emt.invert_vf_solid_for_epsilon(ε_target|ε_m,ε_air)→ vf_solid，"
            "cli 中写入 quantile_q 并驱动分层 iso。"
        ),
        "4_晶格阵列与包络": (
            f"已实现：立方体边长 d=2R+2·envelope_margin_mm（默认 0 即 d=2R）；"
            f"TPMS K 与 Sx/Sy/Sz 均基于 d；球心域内径向分层；geometry_shape={geometry_shape} 仅记录。"
        ),
        "5_隐式场调节Vf壁厚与a_i": (
            "部分：tpms_radial_shells 用壳层分位映射 iso，使 |Phi| 等值面体现径向 Vf 梯度；"
            "vf_measurement 中距离带宽度与 d_c 相关；"
            "各壳层独立胞元尺度 a(i) 未实现（现为全局 K）；Mixer 的 st.RD 等未与 EMT 强联动。"
        ),
        "6_实测Vf与理论对比": (
            "部分：vf_measurement.measure_vf_band_proxy 为薄壳距离带蒙特卡洛代理；"
            "metrics_geo.angular_vf_by_phi 为角向 Vf 代理；"
            "与严格体素分割或沿任意径向逼近理论 Vf(r)、n(r)、ε(r) 仍有差距。"
        ),
        "7_据实测迭代优化": (
            "已实现：vf_optimizer.optimize_quantiles_iterative 据代理实测逐壳调整 quantile_q；"
            "GUI/CLI 可开关 measure_vf 与包络余量；收敛判据为 RMSE 阈值。"
        ),
    }


# 底部文本区一行摘要（避免过长）
GUI_SPEC_AUDIT_BRIEF = (
    "设计对照：①②③已实现；④d=2R+2·余量，K 与域基于 d；"
    "⑤分层 iso 分位+带距与 d_c 相关代理，逐壳 a(i) 未实现；⑥蒙特卡洛带距代理+角向 φ 统计；⑦分位迭代优化可选。"
)
