# 运行与调试环境（`tpms`）及依赖维护

**约定**：本仓库的 **运行、测试、调试** 均在 Conda 环境 **`tpms`** 中进行；新增或升级依赖时 **同步更新** `requirements.txt` 与 `environment.yml`。

---

## 1. 创建或更新环境

首次或换机器：

```powershell
conda env create -f environment.yml
```

已存在 `tpms` 时，拉齐依赖：

```powershell
conda activate tpms
conda env update -f environment.yml --prune
```

若 `conda-forge` 不可用，可仅用 pip（与 `requirements.txt` 一致）：

```powershell
conda activate tpms
pip install -r requirements.txt --upgrade
```

---

## 2. 日常命令

```powershell
conda activate tpms
cd D:\Luneburg\TPMS_Lattice_Generator
python TPMS_Mixer_v1.1.0.py
python -m grin.cli --help
python -m unittest discover -s tests -v
```

不激活环境时可用（需已安装 `conda`）：

```powershell
conda run -n tpms python -m grin.cli --help
```

---

## 3. 依赖更新流程（适时维护）

1. **修改代码若引入新包**：将包名及合理版本约束写入 **`requirements.txt`**。  
2. **同步** `environment.yml` 的 **`pip:`** 列表，保持与 `requirements.txt` **实质一致**（避免两套长期漂移）。  
3. **本地验证**：  
   - `pip install -r requirements.txt`  
   - `python -m unittest discover -s tests -v`  
   - 手动跑一次 GUI 或 `python -m grin.cli ...`  
4. **提交**：依赖变更与功能代码 **同一提交或紧邻提交**，并在 PR/说明中写一句「新增/升级依赖：xxx」。

**说明**：`environment.yml` 中 `conda-forge` 的 `vtk` 与 pip 的 `vtk` 二选一即可；当前文件以 **conda 提供 vtk + pip 提供 UI/GRIN 库** 为模板，可按本机镜像调整。

---

## 4. IDE / Cursor 调试

1. 选择解释器为 **`tpms` 环境中的 `python.exe`**（例如 `…\anaconda3\envs\tpms\python.exe`，路径因安装位置而异）。  
2. **Run and Debug** / 终端均应在 **已激活 `tpms`** 的前提下执行，避免用到 `base` 或其它环境。  
3. 若仓库根目录存在 **`.vscode/settings.json`**（本地可建，默认可能被 gitignore），可设置 `"python.defaultInterpreterPath"` 指向上述解释器。

---

## 5. 检查清单（发布或合并前）

- [ ] `conda activate tpms` 下测试通过  
- [ ] `requirements.txt` 与 `environment.yml`（pip 段）无矛盾  
- [ ] 新依赖已注明用途（可选：在 `requirements.txt` 顶部注释分类）

---

## 修订记录

| 版本 | 日期 | 说明 |
|------|------|------|
| 1.0 | 2026-04-06 | 首版 |
