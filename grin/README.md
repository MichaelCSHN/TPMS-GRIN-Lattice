# GRIN / 龙伯模块

- `emt.py`：Maxwell Garnett 与实体体积分数反演  
- `luneburg.py`：龙伯映射 \(\varepsilon(r)\)、径向分层表  
- `tpms_radial_shells.py`：按球壳分位数生成 TPMS 网格（调用 `TPMS_Mixer_v1.1.0` 中 `get_field`，**不修改该文件**）  
- `tpms_mixer_bridge.py`：`importlib` 加载主程序  
- `cli.py`：命令行导出 STL + JSON 报告  

## 用法

在仓库根目录：

```bash
conda activate tpms
pip install pyyaml trimesh
python -m grin.cli --config config/grin_defaults.yaml --out output/luneburg_tpms.stl --report output/luneburg_report.json --res 32
```

**说明**：当前将 EMT 反演的 `vf_solid` 作为各壳 `np.quantile(absPhi, q)` 的近似 `q`，与真实几何 \(V_f\) 仍有偏差；后续迭代体积校正（见 `docs/02_SPEC.md`）。
