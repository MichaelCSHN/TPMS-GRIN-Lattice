# GRIN / 龙伯模块

实现 **径向分层 TPMS** 与 EMT 目标体积分数驱动，**不修改** `TPMS_Mixer_v1.1.0.py`（经 `tpms_mixer_bridge` 调用 `get_field` / `weld_vertices`）。

## 七步逻辑（摘要）

完整对照表见仓库 **`docs/06_DESIGN_LOGIC_7_STEPS.md`**。

| 步骤 | 说明 |
|------|------|
| ① 理想 \(n(r)\)、\(\varepsilon(r)\) | `lens_profiles`：龙伯 \(\varepsilon_{\mathrm{id}}\)，\(\varepsilon_{\mathrm{eff}}=\varepsilon_{\mathrm{id}}\) |
| ② 离散层目标 | `build_shell_table`，壳心 `epsilon_target` |
| ③ EMT → \(V_f(i)\) | `emt.invert_vf_solid_for_epsilon` → `quantile_q` 驱动分层 iso |
| ④ 包络 \(d\)、\(K\)、\(a\) | `metrics_geo.resolve_tpms_periods_K`；`d=2R+2·margin` |
| ⑤ 隐式场 | `tpms_radial_shells` 壳层分位；逐壳 \(a(i)\) **未**实现 |
| ⑥ 实测代理 | `vf_measurement`、`angular_vf_by_phi` |
| ⑦ 迭代 | `vf_optimizer.optimize_quantiles_iterative` |

## 模块一览

| 文件 | 作用 |
|------|------|
| `lens_profiles.py` | 透镜剖面、径向边、壳表、`design_curves_sampled` |
| `emt.py` | Maxwell Garnett 与 \(V_f\) 反演 |
| `cli.py` | `compute_grin_mesh`、命令行导出 STL + JSON |
| `tpms_radial_shells.py` | 球壳分位 TPMS 体素与 marching cubes |
| `tpms_mixer_bridge.py` | 加载 `TPMS_Mixer_v1.1.0` |
| `metrics_geo.py` | \(K\)、\(a\)、角向统计 |
| `vf_measurement.py` | 带距蒙特卡洛 \(V_f\) 代理 |
| `vf_optimizer.py` | 分位迭代 |
| `design_audit.py` | `spec_audit` 文案（写入报告） |
| `gui/` | PySide6 主窗、曲线、3D |

## 用法

### 图形界面（推荐）

```bash
conda activate tpms
python grin_gui.py
```

入口为根目录 `grin_gui.py`；逻辑在 `grin/gui/main_window.py`，曲线在 `grin/gui/plot_panel.py`。

### 命令行

```bash
conda activate tpms
pip install pyyaml trimesh
python -m grin.cli --config config/grin_defaults.yaml --out output/luneburg_tpms.stl --report output/luneburg_report.json --res 32
```

可选 YAML 字段见 `config/grin_defaults.yaml`（`mesh.mesh_domain`、`geometry.envelope_margin_mm` 等），会传入 `compute_grin_mesh`。

**说明**：各壳 `quantile_q` 由 EMT 的 `vf_solid` **近似**映射；真实几何 \(V_f\) 与 `vf_measurement` 代理用于对比与迭代，见设计文档。
