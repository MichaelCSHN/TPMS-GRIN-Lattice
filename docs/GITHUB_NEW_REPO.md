# 在 GitHub `MichaelCSHN` 账户下新建仓库并推送

当前本机 **未检测到 GitHub CLI（`gh`）**，无法在自动化流程中代你创建远程仓库。请任选下列方式之一。

**建议新仓库名称**：`TPMS-GRIN-Lattice`（可自行改名）

**目标地址**：`https://github.com/MichaelCSHN/TPMS-GRIN-Lattice`

---

## 方式 A：网页创建（最通用）

1. 使用账号 **MichaelCSHN** 登录 [GitHub](https://github.com)。  
2. 右上角 **+** → **New repository**。  
3. **Repository name** 填：`TPMS-GRIN-Lattice`（或你的命名）。  
4. 选择 **Public** 或 **Private**，**不要**勾选「Initialize with README」（本地已有历史时避免冲突）。  
5. 点击 **Create repository**。

在本地仓库根目录执行（已提交的前提下）：

```powershell
cd D:\Luneburg\TPMS_Lattice_Generator

git remote add michael https://github.com/MichaelCSHN/TPMS-GRIN-Lattice.git

git push -u michael main
```

若默认分支不是 `main`，将 `main` 改为你的分支名。

若已存在名为 `michael` 的 remote，可改用：

```powershell
git remote add michael https://github.com/MichaelCSHN/TPMS-GRIN-Lattice.git
# 若已存在则：
git remote set-url michael https://github.com/MichaelCSHN/TPMS-GRIN-Lattice.git
```

---

## 方式 B：安装 GitHub CLI 后一条命令创建

1. 安装：[GitHub CLI](https://cli.github.com/)（Windows 可用 `winget install GitHub.cli`）。  
2. 登录：`gh auth login`（选择 **GitHub.com**、**HTTPS**、浏览器登录）。  
3. 在仓库根目录：

```powershell
cd D:\Luneburg\TPMS_Lattice_Generator
gh repo create MichaelCSHN/TPMS-GRIN-Lattice --public --source=. --remote=michael --push
```

若希望远程名为 `origin`，创建仓库后可：

```powershell
git remote add origin https://github.com/MichaelCSHN/TPMS-GRIN-Lattice.git
git push -u origin main
```

---

## 当前仓库的远程（本机已切换）

`origin` 仅指向 **`https://github.com/MichaelCSHN/TPMS-GRIN-Lattice.git`**，**不再**关联 `Ian-Async/TPMS_Lattice_Generator`。日常 `git pull` / `git push` 即对该仓库。

若曾添加过 `michael` 远程，已合并为上述 `origin`，无需额外操作。

---

## 推送前请本地提交

```powershell
cd D:\Luneburg\TPMS_Lattice_Generator
git add docs/ config/ grin/
git status
git commit -m "docs: GRIN/Luneburg 开发输入与规范；FDM 与 EMT 配置；grin 包占位"
```

按需将 `environment.yml` 等一并纳入版本控制。
