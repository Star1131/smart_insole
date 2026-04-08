from __future__ import annotations

from collections import deque
from typing import Iterable

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Slot
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from data.models import ProcessedFrame


class TimeSeriesView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._display_mode = "raw"
        self._selected_channel: int | None = None
        self._window_seconds = 10.0
        self._timestamps: deque[float] = deque()
        self._values: deque[float] = deque()

        self._channel_combo = QComboBox(self)
        self._channel_combo.addItem("总压力", None)
        for idx in range(128):
            self._channel_combo.addItem(f"CH {idx:03d}", idx)
        self._channel_combo.currentIndexChanged.connect(self._on_channel_changed)

        self._window_combo = QComboBox(self)
        self._window_combo.addItem("5s", 5.0)
        self._window_combo.addItem("10s", 10.0)
        self._window_combo.addItem("30s", 30.0)
        self._window_combo.setCurrentIndex(1)
        self._window_combo.currentIndexChanged.connect(self._on_window_changed)

        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel("通道:", self))
        top_bar.addWidget(self._channel_combo)
        top_bar.addSpacing(8)
        top_bar.addWidget(QLabel("窗口:", self))
        top_bar.addWidget(self._window_combo)
        top_bar.addStretch(1)

        self._plot = pg.PlotWidget(parent=self)
        self._plot.setBackground("default")
        self._plot.showGrid(x=True, y=True, alpha=0.25)
        self._plot.setLabel("bottom", "时间", units="s")
        self._plot.setLabel("left", "数值")
        self._plot.setMenuEnabled(False)
        self._curve = self._plot.plot(
            np.array([], dtype=np.float64),
            np.array([], dtype=np.float64),
            pen=pg.mkPen(color="#39a0ff", width=2),
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(top_bar)
        layout.addWidget(self._plot)

    def set_display_mode(self, mode: str) -> None:
        if mode in ("raw", "calibrated"):
            self._display_mode = mode
            self._plot.setLabel("left", "数值", units=("kPa" if mode == "calibrated" else "ADC"))

    def set_channel(self, channel_index: int) -> None:
        if 0 <= int(channel_index) < 128:
            self._channel_combo.setCurrentIndex(int(channel_index) + 1)

    def clear(self) -> None:
        self._timestamps.clear()
        self._values.clear()
        self._curve.setData(np.array([], dtype=np.float64), np.array([], dtype=np.float64))

    @Slot(object)
    def update_frame(self, frame: ProcessedFrame) -> None:
        self.append_frames((frame,))

    def append_frames(self, frames: Iterable[ProcessedFrame]) -> None:
        for frame in frames:
            if not isinstance(frame, ProcessedFrame):
                continue
            self._timestamps.append(float(frame.timestamp))
            self._values.append(float(self._extract_channel_value(frame)))
        self._trim_window()
        self._refresh_curve()

    @Slot(int)
    def _on_channel_changed(self, index: int) -> None:
        channel = self._channel_combo.itemData(index)
        self._selected_channel = None if channel is None else max(0, min(127, int(channel)))
        self.clear()

    @Slot(int)
    def _on_window_changed(self, index: int) -> None:
        seconds = self._window_combo.itemData(index)
        if seconds is None:
            return
        self._window_seconds = float(seconds)
        self._trim_window()
        self._refresh_curve()

    def _extract_channel_value(self, frame: ProcessedFrame) -> float:
        if self._selected_channel is None:
            return float(frame.total_pressure)
        matrix = frame.adc_calibrated if self._display_mode == "calibrated" else frame.adc_raw
        flat = np.asarray(matrix).reshape(-1)
        return float(flat[self._selected_channel])

    def _trim_window(self) -> None:
        if not self._timestamps:
            return
        latest = self._timestamps[-1]
        min_ts = latest - self._window_seconds
        while self._timestamps and self._timestamps[0] < min_ts:
            self._timestamps.popleft()
            self._values.popleft()

    def _refresh_curve(self) -> None:
        if not self._timestamps:
            self._curve.setData(np.array([], dtype=np.float64), np.array([], dtype=np.float64))
            return
        xs = np.fromiter(self._timestamps, dtype=np.float64)
        ys = np.fromiter(self._values, dtype=np.float64)
        self._curve.setData(xs, ys)
