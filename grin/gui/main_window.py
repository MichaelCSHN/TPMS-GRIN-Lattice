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
from grin.lens_profiles import LensProduct, design_curves_sampled, wavelength_mm_vacuum, LayeringMode
from grin.gui.plot_panel import GrinPlotPanel

ROOT = Path(__file__).resolve().parent.parent.parent


def _faces_to_pyvista(faces: np.ndarray) -> np.ndarray:
    n = faces.shape[0]
    out = np.empty((n, 4), dtype=np.int32)
    out[:, 0] = 3
    out[:, 1:] = faces
    return out.ravel()


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
        g3l.addWidget(QLabel("目标效率 % (相对理想)"), 2, 0)
        self.sp_eff = QDoubleSpinBox()
        self.sp_eff.setRange(0.0, 100.0)
        self.sp_eff.setDecimals(1)
        self.sp_eff.setSpecialValueText("—")
        self.sp_eff.setValue(0.0)
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

        row = QHBoxLayout()
        self.btn_curve = QPushButton("刷新设计曲线")
        self.btn_preview = QPushButton("生成 3D 网格")
        self.btn_export = QPushButton("导出 STL")
        for b in (self.btn_curve, self.btn_preview, self.btn_export):
            b.setMinimumHeight(34)
        self.btn_curve.clicked.connect(self._on_refresh_curves)
        self.btn_preview.clicked.connect(self._on_mesh)
        self.btn_export.clicked.connect(self._on_export)
        row.addWidget(self.btn_curve)
        row.addWidget(self.btn_preview)
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
        }

    def _on_refresh_curves(self):
        try:
            p = self._mesh_params()
        except ValueError as e:
            QMessageBox.warning(self, "提示", str(e))
            return
        product = LensProduct(p["lens_product"]) if p["lens_product"] in ("luneburg", "eaton") else LensProduct.LUNEBURG
        dc = design_curves_sampled(
            p["radius_mm"],
            p["epsilon_air"],
            p["epsilon_matrix"],
            product,
        )
        lam = wavelength_mm_vacuum(p["frequency_ghz"])
        R = p["radius_mm"]
        ratio = R / lam if lam > 0 else None
        eff = p.get("target_efficiency_pct")
        self.plot_panel.update_curves(
            dc["r_mm"],
            dc["n_r"],
            dc["epsilon_r"],
            dc["vf_r"],
            p.get("a_cell_mm"),
            p.get("d_c_mm"),
            None,
            lam,
            ratio,
            eff,
        )
        self.lbl_status.setText("已刷新目标剖面曲线（未生成网格）。")

    def _on_mesh(self):
        if self._thread is not None and self._thread.isRunning():
            return
        try:
            p = self._mesh_params()
        except ValueError as e:
            QMessageBox.warning(self, "提示", str(e))
            return

        self.btn_preview.setEnabled(False)
        dlg = QProgressDialog("正在生成网格…", "", 0, 0, self)
        dlg.setCancelButton(None)
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.show()

        self._thread = GrinMeshThread(p)

        def ok(verts, faces, meta, extra):
            dlg.reset()
            self.btn_preview.setEnabled(True)
            self._verts = verts
            self._faces = faces
            self._meta = meta
            self._extra = extra
            self.lbl_status.setText(
                f"顶点 {len(verts)}，面 {len(faces)}。{extra.get('volume_note', '')}"
            )
            poly = pv.PolyData(verts, _faces_to_pyvista(faces))
            self.plotter.clear()
            self.plotter.show_grid()
            self.plotter.add_axes()
            self.plotter.add_mesh(poly, color=(0.2, 0.55, 0.95))
            self.plotter.reset_camera()

            product = LensProduct(p["lens_product"])
            dc = design_curves_sampled(
                p["radius_mm"],
                p["epsilon_air"],
                p["epsilon_matrix"],
                product,
            )
            lam = wavelength_mm_vacuum(p["frequency_ghz"])
            ratio = p["radius_mm"] / lam if lam > 0 else None
            au = extra.get("angular_uniformity")
            a_est = extra.get("a_est_mm")
            self.plot_panel.update_curves(
                dc["r_mm"],
                dc["n_r"],
                dc["epsilon_r"],
                dc["vf_r"],
                a_est,
                p.get("d_c_mm"),
                au,
                lam,
                ratio,
                p.get("target_efficiency_pct"),
            )

        def fail(msg):
            dlg.reset()
            self.btn_preview.setEnabled(True)
            QMessageBox.critical(self, "失败", msg)

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

    app = QApplication(sys.argv)
    w = GrinMainWindow()
    w.show()
    sys.exit(app.exec())
