from __future__ import annotations

from PySide6.QtCore import Slot
from PySide6.QtWidgets import QFormLayout, QLabel, QSizePolicy, QWidget

from data.models import ProcessedFrame


class MetricsPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._display_mode = "raw"

        self.total_pressure_value = QLabel("--", self)
        self.cop_value = QLabel("--", self)
        self.peak_pressure_value = QLabel("--", self)
        self.fps_value = QLabel("--", self)
        self.zone_values: dict[str, QLabel] = {}

        self._build_ui()

    def _build_ui(self) -> None:
        for value_label in (
            self.total_pressure_value,
            self.cop_value,
            self.peak_pressure_value,
            self.fps_value,
        ):
            value_label.setStyleSheet("font-size: 24px; font-weight: 700;")
            value_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        form = QFormLayout(self)
        form.setContentsMargins(0, 0, 0, 0)
        form.setVerticalSpacing(12)
        form.setHorizontalSpacing(14)
        form.addRow("总压力", self.total_pressure_value)
        form.addRow("CoP (row, col)", self.cop_value)
        form.addRow("峰值压力", self.peak_pressure_value)
        form.addRow("FPS", self.fps_value)

        for key, title in (
            ("heel", "后跟区"),
            ("midfoot", "足弓区"),
            ("forefoot", "前掌区"),
            ("toes", "脚趾区"),
        ):
            label = QLabel("--", self)
            label.setStyleSheet("font-size: 14px; font-weight: 500;")
            label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            self.zone_values[key] = label
            form.addRow(f"{title}", label)

    def set_display_mode(self, mode: str) -> None:
        if mode in ("raw", "calibrated"):
            self._display_mode = mode

    @Slot(object)
    def update_frame(self, frame: ProcessedFrame) -> None:
        total_unit = "kPa" if self._display_mode == "calibrated" else "ADC"
        peak_unit = "kPa" if self._display_mode == "calibrated" else "ADC"
        self.total_pressure_value.setText(f"{float(frame.total_pressure):.2f} {total_unit}")
        self.peak_pressure_value.setText(
            f"{float(frame.peak_pressure):.2f} {peak_unit} @ ({int(frame.peak_position[0])}, {int(frame.peak_position[1])})"
        )
        self.fps_value.setText(f"{float(frame.fps):.1f}")
        self.cop_value.setText(self._format_cop(frame.cop))

        for zone_name, label in self.zone_values.items():
            metric = frame.zone_metrics.get(zone_name)
            if metric is None:
                label.setText("--")
                continue
            if self._display_mode == "calibrated":
                if metric.pressure_kpa is None:
                    label.setText("-- kPa")
                else:
                    label.setText(f"{metric.pressure_kpa:.2f} kPa")
            else:
                label.setText(f"{metric.avg_adc:.2f} ADC")

    @staticmethod
    def _format_cop(cop: tuple[float, float] | None) -> str:
        if cop is None:
            return "--"
        return f"({float(cop[0]):.2f}, {float(cop[1]):.2f})"
