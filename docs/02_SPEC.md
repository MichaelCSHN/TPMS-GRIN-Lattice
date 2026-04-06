# 技术规范

**文档版本**：1.0  
**日期**：2026-04-05  
**对应开发输入**：[01_DEV_INPUT.md](01_DEV_INPUT.md)

---

## 1. 系统架构（目标态）

```
┌─────────────────────────────────────────────────────────────┐
│  UI（现有 PySide6 + PyVista / 或后续拆分）                    │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│  grin/          龙伯剖面、层离散、EMT 反演、目标 V_f(r)        │
│  implicit/      TPMS / truss / plate / hybrid 隐式体素场     │
│  mesher/        等值面、水密修复、STL/OBJ                      │
│  calibrate/     几何体积 ↔ 目标 V_f 迭代                       │
│  metrics/       滑动体元、径向梯度、角向波动                  │
│  process/       FDM 等工艺预设与后验检查                        │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│  config/*.yaml   默认参数与工艺（见仓库 config/）             │
│  GPU（可选）     CuPy / PyTorch 体素与滑窗                    │
└─────────────────────────────────────────────────────────────┘
```

**当前代码库状态**：GRIN 龙伯管线已落在 `grin/`（见 `grin/README.md`）；`TPMS_Mixer_v1.1.0.py` 仅经桥接调用。**七步产品逻辑与实现逐项对照**见 **[06_DESIGN_LOGIC_7_STEPS.md](06_DESIGN_LOGIC_7_STEPS.md)**。其余目录（`implicit/`、`mesher/` 等）仍为 **规范目标布局**，按阶段迁移。

---

## 2. 数据与文件格式

| 类型 | 格式 | 说明 |
|------|------|------|
| 导出几何 | STL（二进制）、OBJ | 要求 **水密** 后方可作为 \(V_f\) 真值 |
| 运行记录 | JSON 或 YAML | 含版本、配置快照、每层目标/实测 \(V_f\)、\(\varepsilon\) |
| 用户配置 | YAML | 见 `config/` |

---

## 3. 算法规范

### 3.1 GRIN / 龙伯

- **输入**：外半径 \(R\)、剖面类型（首版：经典龙伯）、层数 \(N\in[3,10]\)。  
- **输出**：各层目标 **\(\varepsilon_{\mathrm{target},k}\)** 或连续 \(\varepsilon_{\mathrm{target}}(r)\)。  
- **龙伯 \(n(r)\)** 采用文献常用形式之一（实现时锁定单一公式并在代码注释引用），例如：

\[
n(r) = n_0 \sqrt{2 - \left(\frac{r}{R}\right)^2}, \quad 0 \le r \le R
\]

（若工作于 **非归一化** 介质，需明确 **\(n_0\)** 与 **基体 \(\varepsilon_m\)** 的关系；具体以选定文献为准。）

### 3.2 EMT

- **正问题**：\((\varepsilon_m, V_f) \rightarrow \varepsilon_{\mathrm{eff}}\)。  
- **反问题**：\(\varepsilon_{\mathrm{target}} \rightarrow V_f\)（数值求根，\(V_f \in [0,1]\)）。  
- **默认混合律**：在配置中声明（如 Maxwell Garnett：空气为 inclusion）；允许切换 **Bruggeman** 作对比。

### 3.3 隐式晶格

- **Shell（TPMS）**：延续现有 `get_field` + \(|\Phi|\) 与 iso/厚度调制。  
- **Truss / Plate / Hybrid**：用 **SDF / R-function** 等在笛卡尔体素上求 **实体指示**，与 shell **同一套** 体积统计与 MC 管线。

**扩展范围**：在统一框架下 **尽可能增加可选格型**（TPMS 族、桁架/板系、混合），见 **[03_LATTICE_CATALOG.md](03_LATTICE_CATALOG.md)** 与 **`config/lattice_registry.yaml`**。

**全尺寸建模与显示** 的技术选型与分层依赖见 **[04_TECH_STACK_FULLSCALE.md](04_TECH_STACK_FULLSCALE.md)**（GPU 体素、VTK 大规模网格、分块与 LOD 等）。

### 3.4 体积校正

- **真值**：水密网格的 **\(V_{\mathrm{solid}}/V_{\Omega}\)**；分壳时用 **球壳与实体交** 的体积。  
- **迭代**：调整 **iso**、**\(t(r)\)** 或 **层增益**，直至 \(|V_f^{\mathrm{geom}} - V_f^{\mathrm{target}}| \le \delta_V\)（\(\delta_V\) 默认建议 **0.005～0.02**，可配置）。

### 3.5 滑动体元指标

- **体元边长**：\(a_{\min}\) = 工艺允许的最小胞元（见 FDM 配置）。  
- **径向**：层间或滑窗中心 \(r\) 上 **\(V_f\)** 的差分/梯度。  
- **角向**：固定 \(r\) 壳上 **\(V_f\)** 的面元采样 **标准差** 或 **峰峰值**。

---

## 4. 工艺规范（FDM 首选）

- **默认参数**：见 `config/process_fdm.yaml`。  
- **建造方向**：默认 **Z** 为层叠方向；悬垂检查相对 **Z**。  
- **最小特征**：与 **喷嘴直径 \(D\)** 绑定，建议保守 **杆径/壁厚 \(\ge 2D\sim 3D\)**（可配置，需实验标定）。

---

## 5. 接口约定（Python）

以下为 **规范级** 签名目标，实现可分阶段完成。

```text
compute_target_epsilon_profile(lens_spec) -> RadialProfile
invert_emt(eps_target, eps_matrix, law) -> VfProfile
build_implicit_field(lattice_spec, vf_profile, grid_spec) -> voxel / sdf
mesh_and_export(...) -> paths, metadata
calibrate_vf(mesh, targets) -> CalibrateResult
sliding_window_metrics(mesh, a_min, shell_bins) -> MetricsReport
```

---

## 6. GPU（可选）

- **用途**：大规模体素 **卷积滑窗**、壳层 **binning**。  
- **环境**：Windows，CUDA 与驱动由用户安装；代码路径 **可选**，无 GPU 时回退 CPU。

---

## 7. 安全与许可

- 不存储密钥于仓库；若接入 CI，使用 **GitHub Secrets**。  
- 许可证延续仓库根目录 **LICENSE**。

---

## 8. 修订记录

| 版本 | 日期 | 说明 |
|------|------|------|
| 1.0 | 2026-04-05 | 首版 |
| 1.1 | 2026-04-06 | 引用晶格目录与全尺寸技术栈文档 |
