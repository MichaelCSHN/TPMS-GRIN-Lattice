# TPMS Lattice Generator (TPMS Mixer)

An interactive GUI tool for generating **Triply Periodic Minimal Surface (TPMS)** lattices and **hybrid/graded** TPMS structures for additive manufacturing and porous structure research.

If you work with **Gyroid / Diamond / Primitive** (and friends), want controllable **relative density**, and need a quick way to explore **hybrid ratios + transition thickness**, this tool is built for that workflow.

---

## ✨ Highlights

- **TPMS types**: Primitive (P), Gyroid (G), Diamond (D), I-WP (I), Neovius (N)
- **Hybrid / graded structures** between two TPMS fields
  - Grading directions: **Z**, **X**, and **Diagonal (X–Z)**
  - Control **transition center** `d0` and **steepness** `k` (logistic blend)
- **Target relative density (RD)** control using an iso-surface quantile strategy
- **Real-time 3D preview**
- **High-resolution STL export**
- **Screenshot** export from the viewport
- **UI features**:
  - **Dark / Light theme**
  - **中文 / English language switch**
  - Quick views: **Reset / Top / Front / Right**, plus **Zoom in/out**

---

## 📐 GRIN / Luneburg development (roadmap)

Design inputs, technical specification, FDM-oriented defaults, and GitHub push instructions for a **MichaelCSHN** fork or new remote:

- `docs/00_INDEX.md` — document index  
- `docs/01_DEV_INPUT.md` — development inputs (Chinese)  
- `docs/02_SPEC.md` — technical specification (Chinese)  
- `docs/03_LATTICE_CATALOG.md` — lattice type catalog (implicit + \(V_f(r)\))  
- `docs/04_TECH_STACK_FULLSCALE.md` — full-scale design / modeling / visualization stack  
- `docs/GITHUB_NEW_REPO.md` — create `https://github.com/MichaelCSHN/...` and push  
- `config/` — YAML defaults (`grin_defaults.yaml`, `process_fdm.yaml`, `emt_mixing.yaml`)

### GRIN / Luneburg CLI (new)

From the repo root, with **`conda activate tpms`**:

```bash
pip install -r requirements.txt
python -m grin.cli --config config/grin_defaults.yaml --out output/luneburg_tpms.stl --report output/luneburg_report.json --res 32
```

See `grin/README.md` for module layout. The original GUI file `TPMS_Mixer_v1.1.0.py` is **not modified**.

---

## 🚀 Download & Run

### Option A — Windows App (Release) ✅ Recommended
If you just want to use the software without installing Python:

1. Go to **Releases** on the right side of this repository.
2. Download the latest `TPMS_Mixer.zip`.
3. Unzip it to any folder.
4. Run `TPMS_Mixer.exe`.

---

### Option B — Run from Source (Python)
If you want to run or modify the code:

1. Clone this repository (or download as ZIP).
2. Use the **`tpms`** Conda environment (recommended):
   ```bash
   conda env create -f environment.yml
   conda activate tpms
   ```
   Or install with pip only: `pip install -r requirements.txt`
3. Launch the GUI:
   ```bash
   python TPMS_Mixer_v1.1.0.py
   ```

**Development / debugging / dependency updates**: always use **`conda activate tpms`** and keep `requirements.txt` in sync with `environment.yml` — see [docs/05_ENVIRONMENT.md](docs/05_ENVIRONMENT.md) (Chinese).

---

## 🧩 Version Update — v1.1.0

Based on recent optimizations and modifications, v1.1.0 includes:

- **Viewport interaction overhaul**
  - Smoother pan/zoom, double‑click reset, left-click rotate, right-click pan.
- **Re-processing at Model Boundaries**
  - Voxel padding was used to reproduce isocaps boundary closure.
- **Optimize the UI interface**
  - Optimized background display in Light and Dark modes.