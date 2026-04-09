from __future__ import annotations

from datetime import datetime
from functools import partial
from pathlib import Path

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWizard,
    QWizardPage,
)

from config import ADC_COLS, ADC_ROWS, CALIBRATION_DEFAULT_DURATION_SEC, CALIBRATION_DIR, DEFAULT_FOOT_ZONES
from data.calibration_engine import CalibrationEngine
from data.models import CalibrationPoint, CalibrationProfile, FootZone, ZoneCalibrationResult


class CalibrationWizard(QWizard):
    profile_ready = Signal(object, bool)

    STEP_PREPARE = 0
    STEP_ZERO = 1
    STEP_COLLECT = 2
    STEP_FIT = 3
    STEP_SAVE = 4

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("分区标定向导")
        self.resize(980, 760)

        self._zones = self._load_default_zones()
        self._engine = CalibrationEngine(zones=self._zones)
        self._mask_ready = False
        self._zero_ready = False
        self._fit_ready = False
        self._fit_results: dict[str, ZoneCalibrationResult] = {}
        self._last_points: dict[str, CalibrationPoint] = {}
        self._collect_target_zone: str = ""
        self._collect_position_label: str = ""
        self._collect_repeats_total: int = 0
        self._collect_repeats_done: int = 0
        self._batch_point_count: int = 0
        self._current_force_n: float = 0.0
        self._batch_force_idx: int = 0
        self._batch_overview_start_row: int = 0
        self._force_input_dialog: QInputDialog | None = None

        self._build_pages()
        self._bind_signals()
        self._sync_collection_hint()

    def feed_adc_frame(self, adc_data: np.ndarray) -> None:
        self._engine.feed_frame(np.asarray(adc_data))

    def set_device_id(self, device_id: str) -> None:
        self._engine.set_device_id(device_id)

    def _build_pages(self) -> None:
        self._prepare_page = QWizardPage()
        self._prepare_page.setTitle("Step 0: 准备")
        self._build_prepare_page(self._prepare_page)
        self.addPage(self._prepare_page)

        self._zero_page = QWizardPage()
        self._zero_page.setTitle("Step 1: 零点校准")
        self._build_zero_page(self._zero_page)
        self.addPage(self._zero_page)

        self._collect_page = QWizardPage()
        self._collect_page.setTitle("Step 2: 多点采集")
        self._build_collect_page(self._collect_page)
        self.addPage(self._collect_page)

        self._fit_page = QWizardPage()
        self._fit_page.setTitle("Step 3: 曲线拟合")
        self._build_fit_page(self._fit_page)
        self.addPage(self._fit_page)

        self._save_page = QWizardPage()
        self._save_page.setTitle("Step 4: 保存")
        self._build_save_page(self._save_page)
        self.addPage(self._save_page)

    def _bind_signals(self) -> None:
        self._start_mask_btn.clicked.connect(self._on_start_mask_detection)
        self._apply_zones_btn.clicked.connect(self._on_apply_zones)
        self._area_spin.valueChanged.connect(self._on_area_changed)
        self._start_zero_btn.clicked.connect(self._on_start_zero)
        self._start_collect_btn.clicked.connect(self._on_start_collection)
        self._fit_btn.clicked.connect(self._on_fit_all)
        self._browse_btn.clicked.connect(self._on_browse_file)
        self._save_btn.clicked.connect(self._on_save_profile)

        self._engine.collection_progress.connect(self._on_collection_progress)
        self._engine.mask_detected.connect(self._on_mask_detected)
        self._engine.zero_complete.connect(self._on_zero_complete)
        self._engine.collection_complete.connect(self._on_collection_complete)
        self._engine.fit_complete.connect(self._on_fit_complete)

    def validateCurrentPage(self) -> bool:
        if self.currentId() == self.STEP_PREPARE and not self._mask_ready:
            QMessageBox.warning(self, "提示", "请先完成有效掩码检测。")
            return False
        if self.currentId() == self.STEP_ZERO and not self._zero_ready:
            QMessageBox.warning(self, "提示", "请先完成零点校准。")
            return False
        if self.currentId() == self.STEP_COLLECT:
            has_points = any(self._engine.get_data_point_count(z.name) >= 2 for z in self._zones)
            if not has_points:
                QMessageBox.warning(self, "提示", "请至少采集 2 个砝码点后再进入拟合步骤。")
                return False
        if self.currentId() == self.STEP_FIT and not self._fit_ready:
            QMessageBox.warning(self, "提示", "请先执行拟合。")
            return False
        return super().validateCurrentPage()

    def _build_prepare_page(self, page: QWizardPage) -> None:
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("输入砝码底面积，检测有效传感器掩码，并确认分区边界。"))

        form = QFormLayout()
        self._area_spin = QDoubleSpinBox(page)
        self._area_spin.setRange(0.1, 10000.0)
        self._area_spin.setValue(50.0)
        self._area_spin.setSuffix(" cm²")
        self._area_spin.setDecimals(2)
        form.addRow("砝码底面积:", self._area_spin)
        layout.addLayout(form)

        self._mask_status = QLabel("掩码状态：未检测")
        self._start_mask_btn = QPushButton("开始检测（1秒）")
        hl = QHBoxLayout()
        hl.addWidget(self._mask_status, 1)
        hl.addWidget(self._start_mask_btn)
        layout.addLayout(hl)

        zone_group = QGroupBox("分区边界配置")
        zone_layout = QGridLayout(zone_group)
        zone_layout.addWidget(QLabel("分区"), 0, 0)
        zone_layout.addWidget(QLabel("起始行"), 0, 1)
        zone_layout.addWidget(QLabel("结束行"), 0, 2)
        self._zone_row_spins: dict[str, tuple[QSpinBox, QSpinBox]] = {}
        for i, zone in enumerate(self._zones, start=1):
            zone_layout.addWidget(QLabel(zone.display_name), i, 0)
            start_spin = QSpinBox(zone_group)
            end_spin = QSpinBox(zone_group)
            start_spin.setRange(0, ADC_ROWS - 1)
            end_spin.setRange(0, ADC_ROWS - 1)
            start_spin.setValue(zone.row_start)
            end_spin.setValue(zone.row_end)
            zone_layout.addWidget(start_spin, i, 1)
            zone_layout.addWidget(end_spin, i, 2)
            self._zone_row_spins[zone.name] = (start_spin, end_spin)
        self._apply_zones_btn = QPushButton("应用分区")
        zone_layout.addWidget(self._apply_zones_btn, len(self._zones) + 1, 2)
        layout.addWidget(zone_group)

        self._zone_preview = QTableWidget(ADC_ROWS, ADC_COLS, page)
        self._zone_preview.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._zone_preview.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._zone_preview.verticalHeader().setDefaultSectionSize(20)
        self._zone_preview.horizontalHeader().setDefaultSectionSize(28)
        layout.addWidget(self._zone_preview, 1)
        self._render_zone_preview(np.ones((ADC_ROWS, ADC_COLS), dtype=bool))

    def _build_zero_page(self, page: QWizardPage) -> None:
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("空载采集 3 秒，计算每区 zero_offset。"))
        self._zero_progress = QProgressBar(page)
        self._zero_progress.setRange(0, 100)
        self._start_zero_btn = QPushButton("开始零点校准")
        layout.addWidget(self._zero_progress)
        layout.addWidget(self._start_zero_btn)

        self._zero_table = QTableWidget(len(self._zones), 2, page)
        self._zero_table.setHorizontalHeaderLabels(["分区", "zero_offset"])
        self._zero_table.verticalHeader().setVisible(False)
        for i, zone in enumerate(self._zones):
            self._zero_table.setItem(i, 0, QTableWidgetItem(zone.display_name))
            self._zero_table.setItem(i, 1, QTableWidgetItem("--"))
        layout.addWidget(self._zero_table, 1)

    def _build_collect_page(self, page: QWizardPage) -> None:
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel(
            "选择分区和位置，先输入本次要采集的压力点数量，"
            "系统会在标定过程中逐点提示输入当前力值并自动完成多次重复采集。"
        ))

        form = QFormLayout()
        self._zone_combo = QComboBox(page)
        self._refresh_zone_combo()
        self._position_edit = QLineEdit(page)
        self._position_edit.setText("中心")
        self._repeat_spin = QSpinBox(page)
        self._repeat_spin.setRange(1, 20)
        self._repeat_spin.setValue(3)
        self._repeat_spin.valueChanged.connect(self._sync_collection_hint)
        self._point_count_spin = QSpinBox(page)
        self._point_count_spin.setRange(1, 10)
        self._point_count_spin.setValue(3)
        self._point_count_spin.valueChanged.connect(self._sync_collection_hint)
        self._collection_hint = QLabel("--")
        form.addRow("目标分区:", self._zone_combo)
        form.addRow("放置位置:", self._position_edit)
        form.addRow("每力值重复:", self._repeat_spin)
        form.addRow("压力点数量:", self._point_count_spin)
        form.addRow("采集计划:", self._collection_hint)
        layout.addLayout(form)

        self._collect_progress = QProgressBar(page)
        self._collect_progress.setRange(0, 100)
        self._collect_round_status = QLabel("状态：未开始")
        self._start_collect_btn = QPushButton("开始批量采集")
        layout.addWidget(self._collect_progress)
        layout.addWidget(self._collect_round_status)
        layout.addWidget(self._start_collect_btn)

        self._overview_table = QTableWidget(0, 6, page)
        self._overview_table.setHorizontalHeaderLabels(
            ["分区", "位置", "力值(N)", "压强(kPa)", "重复进度", "状态"]
        )
        self._overview_table.verticalHeader().setVisible(False)
        self._overview_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self._overview_table, 1)

    def _build_fit_page(self, page: QWizardPage) -> None:
        layout = QVBoxLayout(page)
        self._fit_btn = QPushButton("执行每区线性拟合")
        layout.addWidget(self._fit_btn)

        plots_group = QGroupBox("分区散点 + 拟合曲线 + R²")
        plots_layout = QGridLayout(plots_group)
        self._zone_plots: dict[str, pg.PlotWidget] = {}
        for idx, zone in enumerate(self._zones):
            plot = pg.PlotWidget(plots_group)
            plot.showGrid(x=True, y=True, alpha=0.25)
            plot.setLabel("left", "Pressure (kPa)")
            plot.setLabel("bottom", "ADC (avg - offset)")
            plot.setTitle(zone.display_name)
            plots_layout.addWidget(plot, idx // 2, idx % 2)
            self._zone_plots[zone.name] = plot
        layout.addWidget(plots_group, 1)

        self._fit_table = QTableWidget(len(self._zones), 4, page)
        self._fit_table.setHorizontalHeaderLabels(["分区", "a", "b", "R²"])
        self._fit_table.verticalHeader().setVisible(False)
        for i, zone in enumerate(self._zones):
            self._fit_table.setItem(i, 0, QTableWidgetItem(zone.display_name))
            for col in range(1, 4):
                self._fit_table.setItem(i, col, QTableWidgetItem("--"))
        layout.addWidget(self._fit_table)

    def _build_save_page(self, page: QWizardPage) -> None:
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("保存 JSON v2.0 标定文件，并可选择立即应用。"))

        row = QHBoxLayout()
        self._path_edit = QLineEdit(page)
        self._path_edit.setText(str(self._default_save_path()))
        self._browse_btn = QPushButton("浏览")
        row.addWidget(self._path_edit, 1)
        row.addWidget(self._browse_btn)
        layout.addLayout(row)

        self._apply_now = QCheckBox("保存后立即应用到当前数据流（若主窗口已接入）")
        self._apply_now.setChecked(True)
        self._save_btn = QPushButton("保存标定文件")
        self._save_status = QLabel("状态：未保存")
        layout.addWidget(self._apply_now)
        layout.addWidget(self._save_btn)
        layout.addWidget(self._save_status)
        layout.addStretch(1)

    def _on_start_mask_detection(self) -> None:
        self._engine.set_contact_area(float(self._area_spin.value()))
        self._engine.start_mask_detection(duration_sec=1.0)
        self._mask_status.setText("掩码状态：采集中...")
        self._start_mask_btn.setEnabled(False)

    def _on_apply_zones(self) -> None:
        new_zones: list[FootZone] = []
        for zone in self._zones:
            start_spin, end_spin = self._zone_row_spins[zone.name]
            row_start = int(start_spin.value())
            row_end = int(end_spin.value())
            if row_start > row_end:
                QMessageBox.warning(self, "分区无效", f"{zone.display_name} 的起始行不能大于结束行。")
                return
            new_zones.append(
                FootZone(
                    name=zone.name,
                    display_name=zone.display_name,
                    row_start=row_start,
                    row_end=row_end,
                )
            )
        self._zones = new_zones
        self._engine.set_zones(self._zones)
        self._refresh_zone_combo()
        self._render_zone_preview(
            self._engine.valid_mask
            if self._engine.valid_mask is not None
            else np.ones((ADC_ROWS, ADC_COLS), dtype=bool)
        )

    def _on_area_changed(self, _value: float) -> None:
        self._sync_collection_hint()

    def _on_start_zero(self) -> None:
        self._zero_ready = False
        self._zero_progress.setValue(0)
        self._engine.start_zero_calibration(duration_sec=CALIBRATION_DEFAULT_DURATION_SEC)
        self._start_zero_btn.setEnabled(False)

    def _on_start_collection(self) -> None:
        if self._engine.is_collecting:
            return
        zone_name = str(self._zone_combo.currentData() or "")
        if not zone_name:
            QMessageBox.warning(self, "提示", "请选择要采集的分区。")
            return

        position_label = self._position_edit.text().strip() or "未命名位置"
        self._collect_target_zone = zone_name
        self._collect_position_label = position_label
        self._collect_repeats_total = int(self._repeat_spin.value())
        self._batch_point_count = int(self._point_count_spin.value())
        self._current_force_n = 0.0
        self._batch_force_idx = 0

        self._start_collect_btn.setEnabled(False)
        self._zone_combo.setEnabled(False)
        self._position_edit.setEnabled(False)
        self._repeat_spin.setEnabled(False)
        self._point_count_spin.setEnabled(False)

        self._batch_overview_start_row = self._overview_table.rowCount()
        for _ in range(self._batch_point_count):
            row = self._overview_table.rowCount()
            self._overview_table.insertRow(row)
            for col, text in enumerate([
                self._zone_combo.currentText(),
                position_label,
                "--",
                "--",
                f"0/{self._collect_repeats_total}",
                "待输入",
            ]):
                self._overview_table.setItem(row, col, QTableWidgetItem(text))

        QTimer.singleShot(0, self._prompt_and_start_next_force)

    def _prompt_and_start_next_force(self) -> None:
        if self._force_input_dialog is not None:
            return
        if self._batch_point_count <= 0 or self._batch_force_idx >= self._batch_point_count:
            return

        idx = self._batch_force_idx + 1
        dialog = QInputDialog(self)
        dialog.setWindowTitle("输入当前力值")
        dialog.setLabelText(
            f"第 {idx}/{self._batch_point_count} 个压力点\n"
            f"分区：{self._zone_combo.currentText()}\n"
            f"位置：{self._collect_position_label}\n\n"
            "请输入当前力值 (N)，确认后开始采集。"
        )
        dialog.setInputMode(QInputDialog.InputMode.DoubleInput)
        dialog.setDoubleRange(0.1, 10000.0)
        dialog.setDoubleDecimals(1)
        dialog.setDoubleValue(max(self._current_force_n, 49.0))
        dialog.finished.connect(
            partial(self._on_force_input_finished, self._batch_force_idx, dialog)
        )
        self._force_input_dialog = dialog
        dialog.open()

    def _on_force_input_finished(
        self, force_idx: int, dialog: QInputDialog, result: int
    ) -> None:
        accepted = result == int(QDialog.DialogCode.Accepted)
        force_n = float(dialog.doubleValue())
        if self._force_input_dialog is dialog:
            self._force_input_dialog = None
        dialog.deleteLater()
        self._handle_force_input_decision(force_idx, accepted, force_n)

    def _handle_force_input_decision(
        self, force_idx: int, accepted: bool, force_n: float
    ) -> None:
        if force_idx != self._batch_force_idx or self._batch_point_count <= 0:
            return
        if not accepted:
            self._on_batch_cancelled()
            return

        self._current_force_n = float(force_n)
        overview_row = self._batch_overview_start_row + self._batch_force_idx
        pressure = self._current_force_n * 10.0 / float(self._area_spin.value())
        self._overview_table.item(overview_row, 2).setText(f"{self._current_force_n:.1f}")
        self._overview_table.item(overview_row, 3).setText(f"{pressure:.3f}")
        self._overview_table.item(overview_row, 5).setText("采集中")
        self._collect_repeats_done = 0
        self._collect_progress.setValue(0)
        self._start_next_collection_repeat()

    def _start_next_collection_repeat(self) -> None:
        next_repeat = self._collect_repeats_done + 1
        total_steps = self._batch_point_count * self._collect_repeats_total
        current_step = self._batch_force_idx * self._collect_repeats_total + next_repeat
        self._collect_round_status.setText(
            f"状态：{self._zone_combo.currentText()} - {self._collect_position_label} - "
            f"{self._current_force_n:.1f}N - 重复 {next_repeat}/{self._collect_repeats_total} "
            f"[总进度 {current_step}/{total_steps}]"
        )
        self._engine.start_point_collection(
            force_n=self._current_force_n,
            duration_sec=CALIBRATION_DEFAULT_DURATION_SEC,
            zone_name=self._collect_target_zone,
            position_label=self._collect_position_label,
            repeat_index=next_repeat,
        )

    def _on_fit_all(self) -> None:
        self._fit_results = self._engine.fit_all_zones()
        self._fit_ready = len(self._fit_results) > 0
        if not self._fit_ready:
            QMessageBox.warning(self, "拟合失败", "至少需要 2 个采样点才能拟合。")

    def _on_browse_file(self) -> None:
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "保存标定文件",
            self._path_edit.text(),
            "Calibration JSON (*.json)",
        )
        if file_path:
            self._path_edit.setText(file_path)

    def _on_save_profile(self) -> None:
        if not self._fit_ready:
            QMessageBox.warning(self, "提示", "请先完成拟合。")
            return
        path = Path(self._path_edit.text()).expanduser()
        if path.suffix.lower() != ".json":
            path = path.with_suffix(".json")
        path.parent.mkdir(parents=True, exist_ok=True)
        self._engine.export_json(str(path))
        raw_path = path.with_name(f"{path.stem}_raw.csv")
        self._engine.export_raw_csv(str(raw_path))
        profile = self._engine.build_profile()
        self._save_status.setText(f"状态：已保存 JSON: {path.name}，RAW: {raw_path.name}")
        self.profile_ready.emit(profile, bool(self._apply_now.isChecked()))

    def _on_collection_progress(self, progress: float) -> None:
        pct = int(max(0.0, min(1.0, float(progress))) * 100)
        if self._engine.is_collecting:
            if self.currentId() == self.STEP_ZERO:
                self._zero_progress.setValue(pct)
            elif self.currentId() == self.STEP_COLLECT:
                self._collect_progress.setValue(pct)
        else:
            self._zero_progress.setValue(100)
            self._collect_progress.setValue(100)
            self._start_mask_btn.setEnabled(True)
            self._start_zero_btn.setEnabled(True)
            if self._batch_point_count <= 0:
                self._start_collect_btn.setEnabled(True)

    def _on_mask_detected(self, mask: np.ndarray) -> None:
        self._mask_ready = True
        active_count = int(np.sum(mask))
        self._mask_status.setText(f"掩码状态：完成（有效 {active_count}/{ADC_ROWS * ADC_COLS}）")
        self._render_zone_preview(mask)

    def _on_zero_complete(self, zero_offsets: dict[str, float]) -> None:
        self._zero_ready = True
        for i, zone in enumerate(self._zones):
            value = float(zero_offsets.get(zone.name, 0.0))
            self._zero_table.item(i, 1).setText(f"{value:.3f}")

    def _on_collection_complete(self, zone_name: str, point: CalibrationPoint) -> None:
        self._last_points[zone_name] = point
        if zone_name != self._collect_target_zone or self._batch_point_count <= 0:
            return

        self._collect_repeats_done += 1
        overview_row = self._batch_overview_start_row + self._batch_force_idx
        self._overview_table.item(overview_row, 4).setText(
            f"{self._collect_repeats_done}/{self._collect_repeats_total}"
        )

        if self._collect_repeats_done < self._collect_repeats_total:
            self._start_next_collection_repeat()
            return

        self._overview_table.item(overview_row, 5).setText("已完成")
        self._batch_force_idx += 1

        if self._batch_force_idx < self._batch_point_count:
            QTimer.singleShot(0, self._prompt_and_start_next_force)
        else:
            zone_text = self._zone_combo.currentText()
            self._batch_point_count = 0
            self._current_force_n = 0.0
            self._unlock_collect_ui()
            self._collect_round_status.setText(
                f"状态：批量采集完成（{zone_text} - {self._collect_position_label}）"
            )

    def _on_batch_cancelled(self) -> None:
        if self._force_input_dialog is not None:
            self._force_input_dialog.deleteLater()
            self._force_input_dialog = None
        for i in range(self._batch_force_idx, self._batch_point_count):
            row = self._batch_overview_start_row + i
            if row < self._overview_table.rowCount():
                item = self._overview_table.item(row, 5)
                if item and item.text() != "已完成":
                    item.setText("已取消")
        self._batch_point_count = 0
        self._current_force_n = 0.0
        self._unlock_collect_ui()
        self._collect_round_status.setText("状态：批量采集已取消")

    def _unlock_collect_ui(self) -> None:
        self._start_collect_btn.setEnabled(True)
        self._zone_combo.setEnabled(True)
        self._position_edit.setEnabled(True)
        self._repeat_spin.setEnabled(True)
        self._point_count_spin.setEnabled(True)

    def _on_fit_complete(self, results: dict[str, ZoneCalibrationResult]) -> None:
        row_map = {zone.name: idx for idx, zone in enumerate(self._zones)}
        for zone_name, result in results.items():
            row = row_map.get(zone_name)
            if row is None:
                continue
            self._fit_table.item(row, 1).setText(f"{result.a:.6f}")
            self._fit_table.item(row, 2).setText(f"{result.b:.6f}")
            self._fit_table.item(row, 3).setText(f"{result.r_squared:.6f}")
            self._render_zone_plot(zone_name, result)

    def _render_zone_plot(self, zone_name: str, result: ZoneCalibrationResult) -> None:
        plot = self._zone_plots.get(zone_name)
        if plot is None:
            return
        plot.clear()
        if not result.data_points:
            return
        x = np.array([p.avg_adc for p in result.data_points], dtype=float)
        y = np.array([p.pressure_kpa for p in result.data_points], dtype=float)
        order = np.argsort(x)
        x = x[order]
        y = y[order]
        plot.plot(
            x,
            y,
            pen=None,
            symbol="o",
            symbolSize=7,
            symbolBrush=pg.mkBrush("#4FC3F7"),
        )
        x_line = np.linspace(float(x.min()), float(x.max()), num=50)
        y_line = result.a * x_line + result.b
        plot.plot(x_line, y_line, pen=pg.mkPen("#FFB74D", width=2))
        zone_display = next((z.display_name for z in self._zones if z.name == zone_name), zone_name)
        plot.setTitle(f"{zone_display} | R²={result.r_squared:.4f}")

    def _render_zone_preview(self, mask: np.ndarray) -> None:
        zone_row_names = np.full((ADC_ROWS,), "", dtype=object)
        for zone in self._zones:
            zone_row_names[zone.row_start : zone.row_end + 1] = zone.display_name

        color_map = {
            "后跟区": "#546E7A",
            "足弓区": "#4CAF50",
            "前掌区": "#FF9800",
            "脚趾区": "#7E57C2",
        }
        for r in range(ADC_ROWS):
            for c in range(ADC_COLS):
                name = str(zone_row_names[r]) if zone_row_names[r] else "未分区"
                item = QTableWidgetItem(name if c == 0 else "")
                bg = color_map.get(name, "#424242")
                if mask is not None and not bool(mask[r, c]):
                    bg = "#212121"
                item.setBackground(pg.mkColor(bg))
                self._zone_preview.setItem(r, c, item)

    def _sync_collection_hint(self) -> None:
        if not hasattr(self, "_point_count_spin") or not hasattr(self, "_repeat_spin"):
            return
        point_count = int(self._point_count_spin.value())
        repeat_count = int(self._repeat_spin.value())
        total_rounds = point_count * repeat_count
        self._collection_hint.setText(
            f"{point_count} 个压力点，共 {total_rounds} 轮采集；每个压力点开始前输入当前力值 (N)。"
        )

    def _default_save_path(self) -> Path:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return CALIBRATION_DIR / f"calibration_v2_{stamp}.json"

    def _refresh_zone_combo(self) -> None:
        if not hasattr(self, "_zone_combo"):
            return
        selected = str(self._zone_combo.currentData() or "")
        self._zone_combo.blockSignals(True)
        self._zone_combo.clear()
        for zone in self._zones:
            self._zone_combo.addItem(zone.display_name, zone.name)
        if selected:
            idx = self._zone_combo.findData(selected)
            if idx >= 0:
                self._zone_combo.setCurrentIndex(idx)
        self._zone_combo.blockSignals(False)

    @staticmethod
    def _load_default_zones() -> list[FootZone]:
        return [
            FootZone(
                name=str(item["name"]),
                display_name=str(item["display_name"]),
                row_start=int(item["row_start"]),
                row_end=int(item["row_end"]),
            )
            for item in DEFAULT_FOOT_ZONES
        ]
