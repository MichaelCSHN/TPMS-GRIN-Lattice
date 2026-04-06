# 七步设计逻辑与实现对照

**版本**：2026-04-05  
**用途**：与产品/论文级流程逐项对照代码与 GUI，标明已实现、部分实现与未实现项。

---

## 总览

| 步骤 | 内容 | 主要实现位置 | GUI / 报告 |
|------|------|----------------|------------|
| 1 | 透镜类型 → 理想 \(n(r)\)、\(\varepsilon(r)\) | `grin/lens_profiles.py`：`luneburg_epsilon_ideal`、`luneburg_n_ideal`；龙伯 \(\varepsilon_{\mathrm{eff}}=\varepsilon_{\mathrm{id}}\) | 曲线「理想 n/ε」 |
| 2 | 分层方式、层数 → 离散 \(n(i)\)、\(\varepsilon(i)\) | `build_radial_edges`、`build_shell_table`；壳心 `epsilon_target` | 阶梯「分层·理想/物理」 |
| 3 | EMT → 各层 \(V_f(i)\) | `grin/emt.py`：`invert_vf_solid_for_epsilon`（Maxwell Garnett） | `meta_layers[].vf_solid_emt`、`quantile_q` |
| 4 | 透镜尺寸 + 晶格类型 + 胞元尺度 \(a\) → 包络阵列 \(d \ge 2R\) | `metrics_geo.resolve_tpms_periods_K`；`st.K*`、`st.S*`；`envelope_margin_mm` | 包络余量、\(d\)、\(K\)、\(a \approx d/K\) |
| 5 | 隐式场调节径向 \(V_f\)：壁厚、可选逐壳 \(a(i)\) | `tpms_radial_shells`：壳层分位 iso；`d_c_mm` 参与 `vf_measurement` 带宽 | 工艺 \(d_c\)；**逐壳 \(a(i)\)** 未实现（全局 \(K\)） |
| 6 | 小体积元「实测」网格 \(V_f\)：径向逼近、角向分散 | `vf_measurement`、`metrics_geo.angular_vf_by_phi` | 蒙特卡洛带距代理、角向图；**非**严格体素真值 |
| 7 | 据实测迭代优化 | `vf_optimizer.optimize_quantiles_iterative` | 「Vf 迭代优化」、`vf_optimization_history` |

---

## 1. 理想 \(n(r)\)、\(\varepsilon(r)\)

- **龙伯**：\(\varepsilon_{\mathrm{id}}(r)=2-(r/R)^2\)，\(n=\sqrt{\varepsilon_{\mathrm{id}}}\)（相对介电常数，球面为 1）。
- **目标等效介电常数**（供 EMT 与分层）：\(\varepsilon_{\mathrm{eff}}(r)=\varepsilon_{\mathrm{id}}(r)\)，**不**再将 \(\varepsilon_{\mathrm{id}}\) 线性拉伸到 \([\varepsilon_{\mathrm{air}},\varepsilon_m]\)（避免球心误判为全实体）。
- **伊顿**：`epsilon_at_r` 线性剖面（占位扩展）。

---

## 2. 离散 \(n(i)\)、\(\varepsilon(i)\)

- **等厚** / **\(\Delta n\)** / **\(\Delta\varepsilon\)**：`LayeringMode` + `build_radial_edges`。
- 每层在壳心处取 `epsilon_target`，用于 EMT 与 TPMS 分层。

---

## 3. EMT → \(V_f(i)\)

- Maxwell Garnett：基体 \(\varepsilon_m\)、空气 inclusion \(\varepsilon_{\mathrm{air}}\)，反求实体体积分数 `vf_solid`。
- CLI/GUI 将 `vf_solid` **近似映射**为壳层 `quantile_q`（`np.quantile(|Φ|, q)`），与真实几何 \(V_f\) 仍有偏差，见步骤 5、6。

---

## 4. 晶格阵列与包络

- 立方体边长 **\(d = 2R + 2\cdot\)**`envelope_margin_mm`（默认 0 即 \(d=2R\)）。
- **\(K\)** 由 \(d\)、目标 \(a\)、最薄壳层等解析（`resolve_tpms_periods_K`）；`Sx=Sy=Sz=d`，`Kx=Ky=Kz=K`。
- **对称加速（可选）**：`mesh_domain=octant` 时仅 **+X+Y+Z** 卦限体素（约 1/8 算量）；壳层分位统计子集与 **full** 略有差异，定稿建议 **full**。

---

## 5. 隐式场与 \(V_f(r)\)

- **已实现**：径向壳层内对 \(|Φ|\) 取分位数得 iso，形成径向梯度；`d_c_mm` 进入实测带距代理。
- **未实现 / 差异**：**逐壳独立胞元尺度 \(a(i)\)**（当前全局 \(K\)）；**壁厚**不作为 iso 的硬约束（最小杆径为工艺记录与代理关联，非网格生成内约束）；Mixer `st.RD` 与 EMT 弱联动。

---

## 6. 「实测」\(V_f\)

- **带距蒙特卡洛**：`measure_vf_band_proxy`（薄壳 + 距离带，与 `d_c` 相关）。
- **角向**：`angular_vf_by_phi`（壳层目标 \(V_f\) + 顶点 \(\varphi\) 分箱，工程近似）。
- **局限**：非沿任意射线密集采样；非体素投票真值；与理论 \(V_f(r)\)、\(n(r)\)、\(\varepsilon(r)\) 为逼近关系。

---

## 7. 迭代优化

- `optimize_quantiles_iterative`：据代理 RMSE 调整 `quantile_override`。
- **收敛**：`tol_rmse` 等见 `vf_optimizer.py`；可与步骤 6 同开 `measure_vf`。

---

## GUI 与 `compute_grin_mesh` 参数对应

| 参数 | 含义 |
|------|------|
| `radius_mm`, `n_layers`, `layering_mode`, `lens_product` | 步骤 1–2 |
| `epsilon_matrix`, `epsilon_air` | 步骤 3 EMT |
| `type_tpms`, 混合, `a_cell_mm`, `envelope_margin_mm`, `res` | 步骤 4 |
| `mesh_domain` | 步骤 4（体素域 full/octant） |
| `d_c_mm` | 步骤 5–6（代理） |
| `measure_vf` | 步骤 6 |
| `quantile_override`（内部） | 步骤 7 |
| 3D「显示范围」 | 仅视图裁剪（1/8/1/4/半球/全球），**不改变**计算域 |

---

## 相关文件

- `grin/cli.py`：`compute_grin_mesh`、报告字段。
- `grin/design_audit.py`：`spec_audit` 短句（写入 JSON）。
- `config/grin_defaults.yaml`：默认几何/材料/网格选项。
