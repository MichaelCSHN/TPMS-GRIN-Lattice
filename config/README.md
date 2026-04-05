# 配置目录说明

| 文件 | 用途 |
|------|------|
| `grin_defaults.yaml` | GRIN / 龙伯：频率、半径、层数、基体 \(\varepsilon_r\) |
| `process_fdm.yaml` | 首选工艺 FDM：喷嘴、层高、最小特征、悬垂阈值 |
| `emt_mixing.yaml` | 等效介质：混合律、夹紧范围 |
| `lattice_registry.yaml` | 晶格类型代码与实现状态（与 `docs/03_LATTICE_CATALOG.md` 同步） |

应用启动或 CLI 应支持：`--config path/to/override.yaml` 合并覆盖默认值。

环境与依赖同步见 **`docs/05_ENVIRONMENT.md`**（使用 **`tpms`** Conda 环境）。
