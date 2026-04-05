"""
GRIN / 龙伯透镜 — 独立图形界面（不修改 TPMS_Mixer_v1.1.0.py）。

运行：conda activate tpms && python grin_gui.py
"""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

import numpy as np
import pyvista as pv
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QComboBox,
    QDoubleSpinBox,
    QProgressDialog,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

ROOT = Path(__file__).resolve().parent


def _faces_to_pyvista(faces: np.ndarray) -> np.ndarray:
    n = faces.shape[0]
    out = np.empty((n, 4), dtype=np.int32)
    out[:, 0] = 3
    out[:, 1:] = faces
    return out.ravel()


class GrinComputeThread(QThread):
    finished_ok = Signal(object, object, object, object)
    failed = Signal(str)

    def __init__(self, radius_mm, n_layers, eps_m, eps_air, res, type_tpms):
        super().__init__()
        self.radius_mm = radius_mm
        self.n_layers = n_layers
        self.eps_m = eps_m
        self.eps_air = eps_air
        self.res = res
        self.type_tpms = type_tpms

    def run(self):
        try:
            from grin.cli import compute_grin_mesh

            verts, faces, meta_layers, report_extra = compute_grin_mesh(
                self.radius_mm,
                self.n_layers,
                self.eps_m,
                self.eps_air,
                self.res,
                self.type_tpms,
            )
            self.finished_ok.emit(verts, faces, meta_layers, report_extra)
        except Exception:
            self.failed.emit(traceback.format_exc())


class GrinMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GRIN / 龙伯透镜 — TPMS 径向分层")
        self.resize(1280, 780)

        self._verts = None
        self._faces = None
        self._meta_layers = None
        self._report_extra: dict = {}
        self._thread: GrinComputeThread | None = None

        central = QWidget()
        self.setCentralWidget(central)
        main = QHBoxLayout(central)

        split = QSplitter(Qt.Horizontal)

        # 左侧参数
        left = QWidget()
        left_l = QVBoxLayout(left)
        gb = QGroupBox("设计参数")
        g = QGridLayout(gb)

        g.addWidget(QLabel("透镜半径 R (mm)"), 0, 0)
        self.sp_radius = QDoubleSpinBox()
        self.sp_radius.setRange(10.0, 500.0)
        self.sp_radius.setDecimals(2)
        self.sp_radius.setValue(100.0)
        g.addWidget(self.sp_radius, 0, 1)

        g.addWidget(QLabel("径向层数 (3–10)"), 1, 0)
        self.sp_layers = QSpinBox()
        self.sp_layers.setRange(3, 10)
        self.sp_layers.setValue(6)
        g.addWidget(self.sp_layers, 1, 1)

        g.addWidget(QLabel("基体 ε_r"), 2, 0)
        self.sp_eps_m = QDoubleSpinBox()
        self.sp_eps_m.setRange(1.1, 20.0)
        self.sp_eps_m.setDecimals(3)
        self.sp_eps_m.setValue(2.8)
        g.addWidget(self.sp_eps_m, 2, 1)

        g.addWidget(QLabel("空气 ε_r"), 3, 0)
        self.sp_eps_air = QDoubleSpinBox()
        self.sp_eps_air.setRange(1.0, 1.01)
        self.sp_eps_air.setDecimals(4)
        self.sp_eps_air.setValue(1.0)
        g.addWidget(self.sp_eps_air, 3, 1)

        g.addWidget(QLabel("体素分辨率 Res"), 4, 0)
        self.sp_res = QSpinBox()
        self.sp_res.setRange(8, 200)
        self.sp_res.setValue(32)
        g.addWidget(self.sp_res, 4, 1)

        g.addWidget(QLabel("TPMS 类型"), 5, 0)
        self.cmb_type = QComboBox()
        for c, name in [
            ("P", "Primitive (P)"),
            ("G", "Gyroid (G)"),
            ("D", "Diamond (D)"),
            ("I", "I-WP (I)"),
            ("N", "Neovius (N)"),
        ]:
            self.cmb_type.addItem(name, c)
        self.cmb_type.setCurrentIndex(1)
        g.addWidget(self.cmb_type, 5, 1)

        left_l.addWidget(gb)

        gb_io = QGroupBox("导出路径")
        io = QGridLayout(gb_io)
        io.addWidget(QLabel("STL 文件"), 0, 0)
        self.le_stl = QLineEdit(str(ROOT / "output" / "luneburg_gui.stl"))
        io.addWidget(self.le_stl, 0, 1)
        self.btn_stl = QPushButton("浏览…")
        self.btn_stl.clicked.connect(self._browse_stl)
        io.addWidget(self.btn_stl, 0, 2)

        io.addWidget(QLabel("报告 JSON"), 1, 0)
        self.le_json = QLineEdit(str(ROOT / "output" / "luneburg_gui_report.json"))
        io.addWidget(self.le_json, 1, 1)
        self.btn_json = QPushButton("浏览…")
        self.btn_json.clicked.connect(self._browse_json)
        io.addWidget(self.btn_json, 1, 2)

        left_l.addWidget(gb_io)

        self.btn_preview = QPushButton("生成预览")
        self.btn_preview.setMinimumHeight(36)
        self.btn_export = QPushButton("导出 STL")
        self.btn_export.setMinimumHeight(36)
        self.btn_preview.clicked.connect(self._on_preview)
        self.btn_export.clicked.connect(self._on_export)

        row = QHBoxLayout()
        row.addWidget(self.btn_preview)
        row.addWidget(self.btn_export)
        left_l.addLayout(row)

        self.lbl_status = QLabel("就绪。点击「生成预览」开始计算。")
        self.lbl_status.setWordWrap(True)
        left_l.addWidget(self.lbl_status)
        left_l.addStretch()

        # 右侧 PyVista
        from pyvistaqt import QtInteractor

        right = QWidget()
        rl = QVBoxLayout(right)
        self.plotter = QtInteractor(right)
        self.plotter.show_grid()
        self.plotter.add_axes()
        rl.addWidget(self.plotter.interactor)

        split.addWidget(left)
        split.addWidget(right)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        main.addWidget(split)

        self._load_defaults_yaml()

    def _load_defaults_yaml(self):
        p = ROOT / "config" / "grin_defaults.yaml"
        if not p.is_file():
            return
        try:
            import yaml

            with open(p, encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
            g = cfg.get("geometry", {})
            m = cfg.get("material", {})
            rm = g.get("radius_mm", 100.0)
            self.sp_radius.setValue(float(rm["default"] if isinstance(rm, dict) else rm))
            self.sp_layers.setValue(int(g.get("radial_layers", 6)))
            em = m.get("epsilon_matrix", 2.8)
            self.sp_eps_m.setValue(float(em["default"] if isinstance(em, dict) else em))
        except Exception:
            pass

    def _browse_stl(self):
        path, _ = QFileDialog.getSaveFileName(self, "保存 STL", self.le_stl.text(), "STL (*.stl)")
        if path:
            self.le_stl.setText(path)

    def _browse_json(self):
        path, _ = QFileDialog.getSaveFileName(self, "保存报告 JSON", self.le_json.text(), "JSON (*.json)")
        if path:
            self.le_json.setText(path)

    def _params(self):
        return (
            float(self.sp_radius.value()),
            int(self.sp_layers.value()),
            float(self.sp_eps_m.value()),
            float(self.sp_eps_air.value()),
            int(self.sp_res.value()),
            self.cmb_type.currentData(),
        )

    def _on_preview(self):
        if self._thread is not None and self._thread.isRunning():
            return
        r, nl, em, ea, res, tt = self._params()
        self.btn_preview.setEnabled(False)
        self.lbl_status.setText("计算中…")

        dlg = QProgressDialog("正在生成龙伯分层 TPMS 网格…", "", 0, 0, self)
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.setCancelButton(None)
        dlg.show()

        self._thread = GrinComputeThread(r, nl, em, ea, res, tt)

        def ok(verts, faces, meta_layers, report_extra):
            dlg.reset()
            self.btn_preview.setEnabled(True)
            self._verts = verts
            self._faces = faces
            self._meta_layers = meta_layers
            self._report_extra = dict(report_extra) if report_extra else {}
            self.lbl_status.setText(
                f"完成。顶点 {len(verts)}，三角面 {len(faces)}。"
                + (
                    f" 体积≈{self._report_extra.get('volume_mm3', '—')} mm³"
                    if self._report_extra
                    else ""
                )
            )
            self._show_mesh(verts, faces)

        def fail(msg):
            dlg.reset()
            self.btn_preview.setEnabled(True)
            QMessageBox.critical(self, "计算失败", msg)
            self.lbl_status.setText("计算失败。")

        self._thread.finished_ok.connect(ok)
        self._thread.failed.connect(fail)
        self._thread.start()

    def _show_mesh(self, verts: np.ndarray, faces: np.ndarray):
        self.plotter.clear()
        self.plotter.show_grid()
        self.plotter.add_axes()
        poly = pv.PolyData(verts, _faces_to_pyvista(faces))
        self.plotter.add_mesh(poly, color=(0.2, 0.55, 0.95), show_edges=False)
        self.plotter.reset_camera()

    def _on_export(self):
        if self._verts is None or self._faces is None:
            QMessageBox.information(self, "提示", "请先生成预览。")
            return
        stl_path = Path(self.le_stl.text().strip())
        json_path = Path(self.le_json.text().strip())
        stl_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            from grin.tpms_mixer_bridge import get_mixer

            mod = get_mixer()
            mod.write_stl_binary_with_progress(str(stl_path), self._faces, self._verts)
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))
            return

        r, nl, em, ea, res, tt = self._params()
        report = {
            "radius_mm": r,
            "n_layers": nl,
            "epsilon_matrix": em,
            "epsilon_air": ea,
            "res": res,
            "type": tt,
            "stl": str(stl_path.resolve()),
        }
        if self._meta_layers is not None:
            report["layers"] = self._meta_layers
            report.update(self._report_extra)
        else:
            try:
                from grin.cli import compute_grin_mesh

                _, _, meta_layers, report_extra = compute_grin_mesh(r, nl, em, ea, res, tt)
                report["layers"] = meta_layers
                report.update(report_extra)
            except Exception:
                pass

        try:
            json_path.parent.mkdir(parents=True, exist_ok=True)
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
        except Exception as e:
            QMessageBox.warning(self, "JSON", f"STL 已保存，JSON 写入失败：{e}")
            return

        QMessageBox.information(self, "成功", f"已保存：\n{stl_path}\n{json_path}")


def main():
    app = QApplication(sys.argv)
    w = GrinMainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
