"""
GRIN 主窗口：晶格选择、混合、设计目标、工艺、曲线与 3D。
"""

from __future__ import annotations

import json
import traceback
from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QCheckBox,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QScrollArea,
    QSplitter,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

import pyvista as pv

from grin.cli import compute_grin_mesh
from grin import metrics_geo
from grin.vf_optimizer import optimize_quantiles_iterative
from grin.lens_profiles import (
    LensProduct,
    LayeringMode,
    build_shell_table,
    design_curves_sampled,
    shell_stair_targets,
    wavelength_mm_vacuum,
)
from grin.gui.plot_panel import GrinPlotPanel
from grin.design_audit import GUI_SPEC_AUDIT_BRIEF

ROOT = Path(__file__).resolve().parent.parent.parent


def _faces_to_pyvista(faces: np.ndarray) -> np.ndarray:
    n = faces.shape[0]
    out = np.empty((n, 4), dtype=np.int32)
    out[:, 0] = 3
    out[:, 1:] = faces
    return out.ravel()


def _layering_cn(mode: LayeringMode) -> str:
    return {
        LayeringMode.EQUAL_THICKNESS: "等厚",
        LayeringMode.EQUAL_DELTA_N: "折射率 n 等差",
        LayeringMode.EQUAL_DELTA_EPS: "介电常数 ε 等差",
    }.get(mode, mode.value)


def _prepare_grin_mesh(verts, faces, box_mm: float):
    """与 TPMS_Mixer 预览一致：clean、三角化、裁剪到立方体域，大面数时降采样。"""
    conn = _faces_to_pyvista(faces)
    mesh = pv.PolyData(verts, conn)
    try:
        mesh = mesh.clean(tolerance=1e-6).triangulate()
    except Exception:
        try:
            mesh = mesh.triangulate()
        except Exception:
            pass
    try:
        S = float(box_mm)
        mesh.points = np.clip(np.asarray(mesh.points, dtype=np.float64), [0.0, 0.0, 0.0], [S, S, S])
    except Exception:
        pass
    try:
        if mesh.n_cells > 700_000:
            mesh = mesh.decimate_pro(0.82)
    except Exception:
        pass
    return mesh


def _clip_mesh_for_sphere_view(mesh: pv.PolyData, box_mm: float, mode: str) -> pv.PolyData:
    """
    以包络立方体中心为球心，用轴对齐盒裁剪 TPMS 外壳（仅预览）。
    - octant: x,y,z 均 ≥ 球心（1/8 球）
    - quarter: x,y ≥ 球心，z 全高（1/4 球）
    - hemisphere: z ≥ 球心（+Z 半球）
    - full: 不裁剪
    """
    if mode == "full" or mesh.n_cells == 0:
        return mesh
    S = float(box_mm)
    c = 0.5 * S
    tol = 1e-4
    # PyVista clip_box: xmin,xmax, ymin,ymax, zmin,zmax — 保留盒内部分
    if mode == "octant":
        bounds = (c - tol, S + tol, c - tol, S + tol, c - tol, S + tol)
    elif mode == "quarter":
        bounds = (c - tol, S + tol, c - tol, S + tol, -tol, S + tol)
    elif mode == "hemisphere":
        bounds = (-tol, S + tol, -tol, S + tol, c - tol, S + tol)
    else:
        return mesh
    try:
        out = mesh.clip_box(bounds=bounds, invert=False)
        if out.n_cells > 0:
            return out
    except Exception:
        pass
    return mesh


def _setup_grin_viewport(plotter, box_mm: float):
    """与 TPMS_Mixer 类似的背景、网格、光照与抗锯齿（不修改其源码）。"""
    eps = 1e-6
    S = float(box_mm)
    plotter.clear()
    plotter.set_background("#eceff1")
    try:
        plotter.show_grid(
            xtitle="X (mm)",
            ytitle="Y (mm)",
            ztitle="Z (mm)",
            color="#546e7a",
            grid="back",
            location="outer",
            bounds=(eps, S, eps, S, eps, S),
            font_size=8,
        )
    except Exception:
        plotter.show_grid()
    plotter.add_axes()
    try:
        plotter.add_orientation_widget()
    except Exception:
        pass
    try:
        plotter.remove_all_lights()
    except Exception:
        pass
    try:
        plotter.enable_lightkit()
    except Exception:
        pass
    try:
        plotter.enable_anti_aliasing("ssaa")
    except Exception:
        try:
            plotter.enable_anti_aliasing("fxaa")
        except Exception:
            pass
    try:
        plotter.enable_eye_dome_lighting()
    except Exception:
        pass
    try:
        plotter.disable_shadows()
    except Exception:
        pass


class GrinMeshThread(QThread):
    finished_ok = Signal(object, object, object, object)
    failed = Signal(str)

    def __init__(self, params: dict):
        super().__init__()
        self.params = params

    def run(self):
        try:
            verts, faces, meta, extra = compute_grin_mesh(**self.params)
            self.finished_ok.emit(verts, faces, meta, extra)
        except Exception:
            self.failed.emit(traceback.format_exc())


class VFOptimizeThread(QThread):
    """据 vf_measurement 代理迭代调整各壳 quantile_q。"""

    finished_ok = Signal(object, object, object, object)
    failed = Signal(str)

    def __init__(self, params: dict, max_iter: int):
        super().__init__()
        self.params = params
        self.max_iter = max_iter

    def run(self):
        try:
            verts, faces, meta, extra, _hist = optimize_quantiles_iterative(
                compute_grin_mesh, self.params, max_iter=self.max_iter
            )
            self.finished_ok.emit(verts, faces, meta, extra)
        except Exception:
            self.failed.emit(traceback.format_exc())


class GrinMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GRIN 透镜设计 — 晶格 / 混合 / 目标 / 可视化")
        self.resize(1440, 880)

        self._verts = None
        self._faces = None
        self._meta = None
        self._extra: dict = {}
        self._thread: GrinMeshThread | None = None
        self._mesh_pv_unclipped: pv.PolyData | None = None
        self._d_box_last: float = 1.0

        central = QWidget()
        self.setCentralWidget(central)
        outer = QHBoxLayout(central)

        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_inner = QWidget()
        left_l = QVBoxLayout(left_inner)

        # 1 晶格大类/子类
        g1 = QGroupBox("1. 晶格类型")
        g1l = QGridLayout(g1)
        g1l.addWidget(QLabel("大类"), 0, 0)
        self.cmb_major = QComboBox()
        self.cmb_major.addItem("TPMS 壳/曲面（可计算）", "tpms")
        self.cmb_major.addItem("桁架（规划中，仅记录）", "truss")
        self.cmb_major.addItem("板系（规划中，仅记录）", "plate")
        g1l.addWidget(self.cmb_major, 0, 1)
        g1l.addWidget(QLabel("子类（TPMS）"), 1, 0)
        self.cmb_sub = QComboBox()
        for c, n in [("P", "P"), ("G", "G"), ("D", "D"), ("I", "I"), ("N", "N")]:
            self.cmb_sub.addItem(f"TPMS-{n}", c)
        self.cmb_sub.setCurrentIndex(1)
        g1l.addWidget(self.cmb_sub, 1, 1)
        left_l.addWidget(g1)

        # 2 混合
        g2 = QGroupBox("2. 晶格混合（可关闭）")
        g2l = QGridLayout(g2)
        self.chk_mix = QCheckBox("启用 A/B 混合（logistic）")
        g2l.addWidget(self.chk_mix, 0, 0, 1, 2)
        g2l.addWidget(QLabel("拓扑 B"), 1, 0)
        self.cmb_b = QComboBox()
        for c, n in [("P", "P"), ("G", "G"), ("D", "D"), ("I", "I"), ("N", "N")]:
            self.cmb_b.addItem(f"TPMS-{n}", c)
        g2l.addWidget(self.cmb_b, 1, 1)
        g2l.addWidget(QLabel("梯度方向"), 2, 0)
        self.cmb_dir = QComboBox()
        for c, n in [("Z", "Z"), ("X", "X"), ("XZ", "XZ")]:
            self.cmb_dir.addItem(n, c)
        g2l.addWidget(self.cmb_dir, 2, 1)
        g2l.addWidget(QLabel("过渡中心 d0"), 3, 0)
        self.sp_d0 = QDoubleSpinBox()
        self.sp_d0.setRange(0.01, 0.99)
        self.sp_d0.setDecimals(3)
        self.sp_d0.setValue(0.5)
        g2l.addWidget(self.sp_d0, 3, 1)
        g2l.addWidget(QLabel("陡峭度 k"), 4, 0)
        self.sp_k = QDoubleSpinBox()
        self.sp_k.setRange(0.5, 30.0)
        self.sp_k.setValue(6.0)
        g2l.addWidget(self.sp_k, 4, 1)

        def _sync_mix_ui():
            en = self.chk_mix.isChecked()
            self.cmb_b.setEnabled(en)
            self.cmb_dir.setEnabled(en)
            self.sp_d0.setEnabled(en)
            self.sp_k.setEnabled(en)

        self.chk_mix.toggled.connect(lambda _: _sync_mix_ui())
        _sync_mix_ui()
        left_l.addWidget(g2)

        # 3 设计目标
        g3 = QGroupBox("3. 设计目标")
        g3l = QGridLayout(g3)
        g3l.addWidget(QLabel("频率 f (GHz)"), 0, 0)
        self.sp_freq = QDoubleSpinBox()
        self.sp_freq.setRange(0.1, 500.0)
        self.sp_freq.setDecimals(3)
        self.sp_freq.setValue(10.0)
        g3l.addWidget(self.sp_freq, 0, 1)
        g3l.addWidget(QLabel("透镜类型"), 1, 0)
        self.cmb_lens = QComboBox()
        self.cmb_lens.addItem("龙伯 Luneburg", "luneburg")
        self.cmb_lens.addItem("伊顿 Eaton（线性 ε 占位）", "eaton")
        g3l.addWidget(self.cmb_lens, 1, 1)
        g3l.addWidget(QLabel("目标效率 (%)"), 2, 0)
        self.sp_eff = QDoubleSpinBox()
        self.sp_eff.setRange(0.0, 100.0)
        self.sp_eff.setDecimals(1)
        self.sp_eff.setSpecialValueText("未填")
        self.sp_eff.setMinimum(0.0)
        self.sp_eff.setValue(0.0)
        self.sp_eff.setToolTip("0 = 不记录目标效率；填写范围为 0–100 的百分数（仅存档，不参与自动优化）。")
        g3l.addWidget(self.sp_eff, 2, 1)
        g3l.addWidget(QLabel("特征尺寸：半径 R (mm)"), 3, 0)
        self.sp_R = QDoubleSpinBox()
        self.sp_R.setRange(5.0, 500.0)
        self.sp_R.setValue(100.0)
        g3l.addWidget(self.sp_R, 3, 1)
        self.lbl_lambda = QLabel("λ0、尺寸/λ 将显示在右下图")
        self.lbl_lambda.setWordWrap(True)
        g3l.addWidget(self.lbl_lambda, 4, 0, 1, 2)
        g3l.addWidget(QLabel("几何构型"), 5, 0)
        self.cmb_shape = QComboBox()
        self.cmb_shape.addItem("球分层 + 立方体包络域（当前实现）", "sphere_in_cube")
        self.cmb_shape.addItem("纯六面体域（同左，占位）", "cube")
        g3l.addWidget(self.cmb_shape, 5, 1)
        g3l.addWidget(QLabel("径向层数"), 6, 0)
        self.sp_layers = QSpinBox()
        self.sp_layers.setRange(3, 20)
        self.sp_layers.setValue(6)
        g3l.addWidget(self.sp_layers, 6, 1)
        g3l.addWidget(QLabel("分层方式"), 7, 0)
        self.cmb_layering = QComboBox()
        self.cmb_layering.addItem("等厚", LayeringMode.EQUAL_THICKNESS.value)
        self.cmb_layering.addItem("折射率 n 等差（壳边界）", LayeringMode.EQUAL_DELTA_N.value)
        self.cmb_layering.addItem("介电常数 ε 等差（壳边界）", LayeringMode.EQUAL_DELTA_EPS.value)
        g3l.addWidget(self.cmb_layering, 7, 1)
        left_l.addWidget(g3)

        # 4 工艺
        g4 = QGroupBox("4. 工艺约束")
        g4l = QGridLayout(g4)
        g4l.addWidget(QLabel("体素 Res"), 0, 0)
        self.sp_res = QSpinBox()
        self.sp_res.setRange(8, 200)
        self.sp_res.setValue(32)
        g4l.addWidget(self.sp_res, 0, 1)
        g4l.addWidget(QLabel("目标胞元尺度 a (mm)，空=自动估"), 1, 0)
        self.sp_a = QDoubleSpinBox()
        self.sp_a.setMinimum(0.0)
        self.sp_a.setMaximum(50.0)
        self.sp_a.setSpecialValueText("自动")
        self.sp_a.setValue(0.0)
        g4l.addWidget(self.sp_a, 1, 1)
        g4l.addWidget(QLabel("最小线径 d_c (mm)"), 2, 0)
        self.sp_dc = QDoubleSpinBox()
        self.sp_dc.setRange(0.05, 10.0)
        self.sp_dc.setDecimals(3)
        self.sp_dc.setValue(0.4)
        g4l.addWidget(self.sp_dc, 2, 1)
        g4l.addWidget(QLabel("基体 ε_r"), 3, 0)
        self.sp_epsm = QDoubleSpinBox()
        self.sp_epsm.setRange(1.1, 20.0)
        self.sp_epsm.setValue(2.8)
        g4l.addWidget(self.sp_epsm, 3, 1)
        g4l.addWidget(QLabel("空气 ε_r"), 4, 0)
        self.sp_epsa = QDoubleSpinBox()
        self.sp_epsa.setRange(1.0, 1.05)
        self.sp_epsa.setValue(1.0)
        g4l.addWidget(self.sp_epsa, 4, 1)
        g4l.addWidget(QLabel("包络余量 (mm/侧)"), 5, 0)
        self.sp_margin = QDoubleSpinBox()
        self.sp_margin.setRange(0.0, 100.0)
        self.sp_margin.setDecimals(2)
        self.sp_margin.setValue(0.0)
        self.sp_margin.setToolTip("立方体边长 d=2R+2×余量；0 表示与直径 2R 一致。")
        g4l.addWidget(self.sp_margin, 5, 1)
        self.chk_measure_vf = QCheckBox("生成后蒙特卡洛实测 Vf（报告与曲线）")
        self.chk_measure_vf.setChecked(True)
        g4l.addWidget(self.chk_measure_vf, 6, 0, 1, 2)
        g4l.addWidget(QLabel("Vf 优化最大迭代"), 7, 0)
        self.sp_vf_iter = QSpinBox()
        self.sp_vf_iter.setRange(1, 30)
        self.sp_vf_iter.setValue(5)
        g4l.addWidget(self.sp_vf_iter, 7, 1)
        self.chk_mesh_octant = QCheckBox("体素域仅 1/8 卦限（+X+Y+Z，约减 7/8 算量）")
        self.chk_mesh_octant.setChecked(False)
        self.chk_mesh_octant.setToolTip(
            "自 TPMS 场与壳层分位起仅用卦限子网格；壳内 |Phi| 非球对称，分位 iso 与「全球」略有差异，定稿请用未勾选。"
        )
        g4l.addWidget(self.chk_mesh_octant, 8, 0, 1, 2)
        left_l.addWidget(g4)

        # 导出路径
        g5 = QGroupBox("导出")
        g5l = QGridLayout(g5)
        g5l.addWidget(QLabel("STL"), 0, 0)
        self.le_stl = QLineEdit(str(ROOT / "output" / "grin_gui.stl"))
        g5l.addWidget(self.le_stl, 0, 1)
        b1 = QPushButton("浏览…")
        b1.clicked.connect(lambda: self._browse_save(self.le_stl, "STL (*.stl)"))
        g5l.addWidget(b1, 0, 2)
        g5l.addWidget(QLabel("报告 JSON"), 1, 0)
        self.le_json = QLineEdit(str(ROOT / "output" / "grin_report.json"))
        g5l.addWidget(self.le_json, 1, 1)
        b2 = QPushButton("浏览…")
        b2.clicked.connect(lambda: self._browse_save(self.le_json, "JSON (*.json)"))
        g5l.addWidget(b2, 1, 2)
        left_l.addWidget(g5)

        g6 = QGroupBox("3D 预览")
        g6l = QGridLayout(g6)
        g6l.addWidget(QLabel("显示范围（仅视图）"), 0, 0)
        self.cmb_view_scope = QComboBox()
        self.cmb_view_scope.addItem("1/8 球（默认）", "octant")
        self.cmb_view_scope.addItem("1/4 球", "quarter")
        self.cmb_view_scope.addItem("半球（+Z）", "hemisphere")
        self.cmb_view_scope.addItem("全球", "full")
        self.cmb_view_scope.setToolTip(
            "相对包络立方体中心裁剪，便于观察径向分层；导出 STL 仍为完整网格。"
        )
        g6l.addWidget(self.cmb_view_scope, 0, 1)
        hint = QLabel("1/8：+X+Y+Z 卦限；1/4：+X+Y 绕 Z；半球：Z≥中心；导出不受此项影响。")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#546e7a;font-size:11px;")
        g6l.addWidget(hint, 1, 0, 1, 2)
        left_l.addWidget(g6)

        row = QHBoxLayout()
        self.btn_curve = QPushButton("刷新设计曲线")
        self.btn_preview = QPushButton("生成 3D 网格")
        self.btn_vf_opt = QPushButton("Vf 迭代优化")
        self.btn_export = QPushButton("导出 STL")
        for b in (self.btn_curve, self.btn_preview, self.btn_vf_opt, self.btn_export):
            b.setMinimumHeight(34)
        self.btn_curve.clicked.connect(self._on_refresh_curves)
        self.btn_preview.clicked.connect(self._on_mesh)
        self.btn_vf_opt.clicked.connect(self._on_vf_optimize)
        self.btn_export.clicked.connect(self._on_export)
        self.btn_vf_opt.setToolTip("据蒙特卡洛带距代理逐壳调整分位，与 EMT 目标 Vf 对齐（耗时较长）。")
        row.addWidget(self.btn_curve)
        row.addWidget(self.btn_preview)
        row.addWidget(self.btn_vf_opt)
        row.addWidget(self.btn_export)
        left_l.addLayout(row)

        self.lbl_status = QLabel("就绪。")
        self.lbl_status.setWordWrap(True)
        left_l.addWidget(self.lbl_status)
        left_l.addStretch()

        left_scroll.setWidget(left_inner)
        left_scroll.setMinimumWidth(420)

        right = QSplitter(Qt.Vertical)
        self.plot_panel = GrinPlotPanel()
        right.addWidget(self.plot_panel)

        from pyvistaqt import QtInteractor

        self.pv_frame = QWidget()
        pvl = QVBoxLayout(self.pv_frame)
        self.plotter = QtInteractor(self.pv_frame)
        self.plotter.show_grid()
        self.plotter.add_axes()
        pvl.addWidget(self.plotter.interactor)
        right.addWidget(self.pv_frame)
        right.setStretchFactor(0, 2)
        right.setStretchFactor(1, 3)

        outer.addWidget(left_scroll)
        outer.addWidget(right, 1)

        self.sp_freq.valueChanged.connect(self._update_lambda_label)
        self.sp_R.valueChanged.connect(self._update_lambda_label)
        self._update_lambda_label()

        self.cmb_view_scope.currentIndexChanged.connect(self._on_view_scope_changed)

    def _browse_save(self, le: QLineEdit, filt: str):
        path, _ = QFileDialog.getSaveFileName(self, "保存", le.text(), filt)
        if path:
            le.setText(path)

    def _lens_product(self) -> LensProduct:
        v = self.cmb_lens.currentData()
        try:
            return LensProduct(v)
        except ValueError:
            return LensProduct.LUNEBURG

    def _update_lambda_label(self):
        f = self.sp_freq.value()
        lam = wavelength_mm_vacuum(f)
        R = self.sp_R.value()
        ratio = R / lam if lam > 0 else 0
        self.lbl_lambda.setText(
            f"真空波长 λ0≈{lam:.4f} mm（c/f）；半径 R/λ0≈{ratio:.2f}（介质中需按 ε 修正，此处为粗估）"
        )

    @staticmethod
    def _box_mm_from_params(p: dict) -> float:
        R = float(p["radius_mm"])
        m = float(p.get("envelope_margin_mm", 0.0))
        return 2.0 * R + 2.0 * m

    def _mesh_params(self) -> dict:
        major = self.cmb_major.currentData()
        if major != "tpms":
            raise ValueError("当前仅实现 TPMS 大类；请选择「TPMS 壳/曲面」。")
        tpms = self.cmb_sub.currentData()
        mix = self.chk_mix.isChecked()
        tb = self.cmb_b.currentData()
        return {
            "radius_mm": float(self.sp_R.value()),
            "n_layers": int(self.sp_layers.value()),
            "epsilon_matrix": float(self.sp_epsm.value()),
            "epsilon_air": float(self.sp_epsa.value()),
            "res": int(self.sp_res.value()),
            "type_tpms": tpms,
            "type_b": tb,
            "mix_enabled": mix,
            "mix_dir": self.cmb_dir.currentData(),
            "trans_center": float(self.sp_d0.value()),
            "trans_k": float(self.sp_k.value()),
            "lens_product": self.cmb_lens.currentData(),
            "layering_mode": self.cmb_layering.currentData(),
            "geometry_shape": self.cmb_shape.currentData(),
            "frequency_ghz": float(self.sp_freq.value()),
            "target_efficiency_pct": float(self.sp_eff.value()) if self.sp_eff.value() > 1e-6 else None,
            "d_c_mm": float(self.sp_dc.value()),
            "a_cell_mm": float(self.sp_a.value()) if self.sp_a.value() > 1e-9 else None,
            "envelope_margin_mm": float(self.sp_margin.value()),
            "measure_vf": self.chk_measure_vf.isChecked(),
            "mesh_domain": "octant" if self.chk_mesh_octant.isChecked() else "full",
        }

    def _on_view_scope_changed(self, _index: int):
        if self._mesh_pv_unclipped is None:
            return
        self._refresh_grin_3d_view()

    def _refresh_grin_3d_view(self):
        """按「显示范围」重绘 3D（不改变顶点缓存，导出仍用完整网格）。"""
        if self._mesh_pv_unclipped is None or self._mesh_pv_unclipped.n_cells == 0:
            return
        d_box = float(self._d_box_last)
        mode = self.cmb_view_scope.currentData()
        if not mode:
            mode = "octant"
        mesh_show = _clip_mesh_for_sphere_view(self._mesh_pv_unclipped, d_box, str(mode))
        _setup_grin_viewport(self.plotter, d_box)
        self.plotter.add_mesh(
            mesh_show,
            color=(0.14, 0.52, 0.96),
            smooth_shading=True,
            lighting=True,
            ambient=0.10,
            diffuse=0.95,
            specular=0.85,
            specular_power=45,
        )
        try:
            self.plotter.renderer.ResetCameraClippingRange()
        except Exception:
            pass
        self.plotter.view_isometric()
        self.plotter.reset_camera()
        try:
            self.plotter.update()
        except Exception:
            pass

    def _apply_grin_result(self, verts, faces, meta, extra: dict, p: dict, *, vf_opt_note: str = ""):
        """生成或 Vf 优化完成后：更新 3D、曲线与状态栏。"""
        nv, nf = len(verts), len(faces)
        d_box = float(extra.get("box_mm", self._box_mm_from_params(p)))
        if nv == 0 or nf == 0:
            QMessageBox.warning(
                self,
                "空网格",
                f"结果为空：顶点 {nv}，三角面 {nf}。请降低 res 或检查分层/材料参数。",
            )
            self.lbl_status.setText("网格为空，未显示 3D。")
            return

        self._verts = verts
        self._faces = faces
        self._meta = meta
        self._extra = extra

        hist = extra.get("vf_optimization_history")
        hist_tail = ""
        if isinstance(hist, list) and hist:
            last = hist[-1]
            rm = last.get("rmse")
            hist_tail = f" Vf 优化末次 RMSE≈{rm:.4f}（{len(hist)} 步）。" if rm is not None else f" Vf 优化 {len(hist)} 步。"

        self.lbl_status.setText(
            f"顶点 {nv}，面 {nf}。包络边长≈{d_box:.3f} mm，TPMS K={extra.get('tpms_periods_K', '?')}，"
            f"单胞边长≈{extra.get('a_cell_effective_mm', 0):.3f} mm。"
            f" {extra.get('volume_note', '')} {extra.get('lattice_note', '')}{vf_opt_note}{hist_tail}"
        )

        mesh_pv = _prepare_grin_mesh(verts, faces, d_box)
        if mesh_pv.n_cells == 0:
            self._mesh_pv_unclipped = None
            QMessageBox.warning(self, "空网格", "PyVista 未识别到三角面，无法显示 3D。")
            self.lbl_status.setText("PolyData 无面片。")
            return
        self._mesh_pv_unclipped = mesh_pv
        self._d_box_last = d_box
        self._refresh_grin_3d_view()

        product = LensProduct(p["lens_product"])
        try:
            mode = LayeringMode(p["layering_mode"])
        except ValueError:
            mode = LayeringMode.EQUAL_THICKNESS
        rows, r_edges = build_shell_table(
            p["radius_mm"],
            p["n_layers"],
            p["epsilon_air"],
            p["epsilon_matrix"],
            product,
            mode,
        )
        stair = shell_stair_targets(
            rows,
            r_edges,
            p["radius_mm"],
            p["epsilon_air"],
            p["epsilon_matrix"],
            product,
        )
        layering_label = (
            f"径向分层：{p['n_layers']} 层 · {_layering_cn(mode)} · "
            f"包络 d≈{d_box:.3f} mm · TPMS K={extra.get('tpms_periods_K', '?')} · "
            f"单胞边长≈{extra.get('a_cell_effective_mm', 0):.3f} mm"
        )
        dc = design_curves_sampled(
            p["radius_mm"],
            p["epsilon_air"],
            p["epsilon_matrix"],
            product,
        )
        lam = wavelength_mm_vacuum(p["frequency_ghz"])
        ratio = p["radius_mm"] / lam if lam > 0 else None
        au = extra.get("angular_uniformity")
        a_est = extra.get("a_cell_effective_mm", extra.get("a_est_mm"))
        center = np.array([d_box / 2, d_box / 2, d_box / 2], dtype=np.float64)
        r_e_m = metrics_geo.r_edges_from_meta_layers(meta)
        vf_bl = np.array([m["vf_solid_emt"] for m in meta], dtype=np.float64)
        angular_phi = extra.get("angular_vf_phi")
        if angular_phi is None:
            angular_phi = metrics_geo.angular_vf_by_phi(verts, center, r_e_m, vf_bl)
        self.plot_panel.update_curves(
            dc["r_mm"],
            dc["n_ideal"],
            dc["n_phys"],
            dc["epsilon_ideal"],
            dc["epsilon_phys"],
            dc["vf_solid_emt"],
            a_est,
            p.get("d_c_mm"),
            au,
            lam,
            ratio,
            p.get("target_efficiency_pct"),
            stair=stair,
            angular_phi=angular_phi,
            layering_label=layering_label,
            spec_audit_brief=GUI_SPEC_AUDIT_BRIEF,
        )

    def _on_refresh_curves(self):
        try:
            p = self._mesh_params()
        except ValueError as e:
            QMessageBox.warning(self, "提示", str(e))
            return
        product = LensProduct(p["lens_product"]) if p["lens_product"] in ("luneburg", "eaton") else LensProduct.LUNEBURG
        try:
            mode = LayeringMode(p["layering_mode"])
        except ValueError:
            mode = LayeringMode.EQUAL_THICKNESS
        rows, r_edges = build_shell_table(
            p["radius_mm"],
            p["n_layers"],
            p["epsilon_air"],
            p["epsilon_matrix"],
            product,
            mode,
        )
        stair = shell_stair_targets(
            rows,
            r_edges,
            p["radius_mm"],
            p["epsilon_air"],
            p["epsilon_matrix"],
            product,
        )
        d_box = self._box_mm_from_params(p)
        K_prev, k_meta = metrics_geo.resolve_tpms_periods_K(d_box, p["res"], r_edges, p.get("a_cell_mm"))
        layering_label = (
            f"径向分层：{p['n_layers']} 层 · {_layering_cn(mode)} · "
            f"包络 d≈{d_box:.3f} mm · TPMS K={K_prev} · 单胞边长≈{k_meta['a_effective_mm']:.3f} mm"
        )
        dc = design_curves_sampled(
            p["radius_mm"],
            p["epsilon_air"],
            p["epsilon_matrix"],
            product,
        )
        lam = wavelength_mm_vacuum(p["frequency_ghz"])
        R = float(p["radius_mm"])
        ratio = R / lam if lam > 0 else None
        eff = p.get("target_efficiency_pct")
        a_show = float(k_meta["a_effective_mm"])
        self.plot_panel.update_curves(
            dc["r_mm"],
            dc["n_ideal"],
            dc["n_phys"],
            dc["epsilon_ideal"],
            dc["epsilon_phys"],
            dc["vf_solid_emt"],
            a_show,
            p.get("d_c_mm"),
            None,
            lam,
            ratio,
            eff,
            stair=stair,
            angular_phi=None,
            layering_label=layering_label,
        )
        self.lbl_status.setText("已刷新目标剖面曲线（未生成网格）。3D 需点击「生成 3D 网格」。")

    def _on_mesh(self):
        if self._thread is not None and self._thread.isRunning():
            return
        try:
            p = self._mesh_params()
        except ValueError as e:
            QMessageBox.warning(self, "提示", str(e))
            return

        self._set_mesh_buttons_busy(True)
        dlg = QProgressDialog("正在生成网格…", "", 0, 0, self)
        dlg.setCancelButton(None)
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.show()

        self._thread = GrinMeshThread(p)

        def ok(verts, faces, meta, extra):
            dlg.reset()
            self._set_mesh_buttons_busy(False)
            self._apply_grin_result(verts, faces, meta, extra, p)

        def fail(msg):
            dlg.reset()
            self._set_mesh_buttons_busy(False)
            QMessageBox.critical(self, "失败", msg)

        self._thread.finished_ok.connect(ok)
        self._thread.failed.connect(fail)
        self._thread.start()

    def _set_mesh_buttons_busy(self, busy: bool):
        self.btn_preview.setEnabled(not busy)
        self.btn_vf_opt.setEnabled(not busy)

    def _on_vf_optimize(self):
        if self._thread is not None and self._thread.isRunning():
            return
        try:
            p = self._mesh_params()
        except ValueError as e:
            QMessageBox.warning(self, "提示", str(e))
            return
        if not p.get("measure_vf", True):
            QMessageBox.information(
                self,
                "提示",
                "已关闭「生成后蒙特卡洛实测 Vf」。优化依赖实测代理，将临时开启 measure_vf。",
            )
            p = dict(p)
            p["measure_vf"] = True

        self._set_mesh_buttons_busy(True)
        dlg = QProgressDialog("Vf 分位迭代优化中（可能较慢）…", "", 0, 0, self)
        dlg.setCancelButton(None)
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.show()

        self._thread = VFOptimizeThread(p, int(self.sp_vf_iter.value()))

        def ok(verts, faces, meta, extra):
            dlg.reset()
            self._set_mesh_buttons_busy(False)
            self._apply_grin_result(verts, faces, meta, extra, p, vf_opt_note=" 已完成分位迭代。")

        def fail(msg):
            dlg.reset()
            self._set_mesh_buttons_busy(False)
            QMessageBox.critical(self, "Vf 优化失败", msg)

        self._thread.finished_ok.connect(ok)
        self._thread.failed.connect(fail)
        self._thread.start()

    def _on_export(self):
        if self._verts is None:
            QMessageBox.information(self, "提示", "请先生成 3D 网格。")
            return
        stl = Path(self.le_stl.text().strip())
        js = Path(self.le_json.text().strip())
        stl.parent.mkdir(parents=True, exist_ok=True)
        try:
            from grin.tpms_mixer_bridge import get_mixer

            get_mixer().write_stl_binary_with_progress(str(stl), self._faces, self._verts)
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))
            return
        try:
            p = self._mesh_params()
            report = {**p, "layers": self._meta, **self._extra, "stl": str(stl.resolve())}
            with open(js, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2, default=str)
        except Exception as e:
            QMessageBox.warning(self, "JSON", f"STL 已保存，JSON 失败：{e}")
            return
        QMessageBox.information(self, "完成", f"已写入：\n{stl}\n{js}")


def run_app():
    import sys

    pv.global_theme.smooth_shading = True
    app = QApplication(sys.argv)
    w = GrinMainWindow()
    w.show()
    sys.exit(app.exec())
