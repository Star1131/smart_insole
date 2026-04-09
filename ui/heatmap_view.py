from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QPointF, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QToolTip, QVBoxLayout, QWidget
from scipy.spatial.distance import cdist

from config import (
    ADC_COLS,
    ADC_NOISE_THRESHOLD,
    ADC_ROWS,
    DEFAULT_FOOT_ZONES,
    HEATMAP_RBF_SIGMA,
    HEATMAP_TOE_RBF_SIGMA,
    HEATMAP_TOE_ROW_START,
    HEATMAP_TOE_TRANSITION_ROWS,
    HEATMAP_UPSAMPLE,
    INSOLE_CONTOUR_RIGHT,
)

class HeatmapView(QWidget):
    hover_text_changed = Signal(str)

    def __init__(
        self,
        parent: QWidget | None = None,
        colormap: str = "viridis",
    ) -> None:
        super().__init__(parent)
        self._display_mode = "raw"
        self._rows = ADC_ROWS
        self._cols = ADC_COLS
        self._display_noise_floor = float(ADC_NOISE_THRESHOLD)
        self._data = np.zeros((self._rows, self._cols), dtype=np.float32)
        self._zones = tuple(DEFAULT_FOOT_ZONES)
        self._zone_lines: list[pg.PlotDataItem] = []
        self._zone_labels: list[pg.TextItem] = []

        self._contour = list(INSOLE_CONTOUR_RIGHT)

        scale = max(1, HEATMAP_UPSAMPLE)
        self._canvas_h = self._rows * scale
        self._canvas_w = self._cols * scale

        self._sensor_xy = self._build_sensor_positions()
        self._canvas_mask = self._build_canvas_mask()
        self._inside_idx = np.where(self._canvas_mask.ravel())[0]
        self._interp_w = self._precompute_weights()

        # --- pyqtgraph ---
        self._plot = pg.PlotWidget(parent=self)
        self._plot.setMenuEnabled(False)
        self._plot.setMouseEnabled(x=False, y=False)
        self._plot.hideAxis("left")
        self._plot.hideAxis("bottom")
        vb = self._plot.getViewBox()
        vb.setAspectLocked(True)
        vb.invertY(False)
        vb.setRange(xRange=(0, self._cols), yRange=(0, self._rows), padding=0.05)

        self._image_item = pg.ImageItem(axisOrder="row-major")
        blank = np.zeros((self._canvas_h, self._canvas_w), dtype=np.float32)
        self._image_item.setImage(blank, autoLevels=False, levels=(0.0, 1.0))
        self._image_item.setRect(0, 0, self._cols, self._rows)
        self._plot.addItem(self._image_item)

        self._overlay_item = pg.ImageItem(axisOrder="row-major")
        self._plot.addItem(self._overlay_item)
        self._render_static_overlay()

        cx = [p[0] for p in self._contour] + [self._contour[0][0]]
        cy = [p[1] for p in self._contour] + [self._contour[0][1]]
        self._outline_item = pg.PlotDataItem(cx, cy, pen=pg.mkPen("#f5c842", width=2.5))
        self._plot.addItem(self._outline_item)

        self._init_zone_lines()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._plot)

        self._plot.scene().sigMouseMoved.connect(self._on_mouse_moved)
        self.set_colormap(colormap)
        self.update_heatmap(self._data)

    # ── public API ──

    def available_colormaps(self) -> tuple[str, ...]:
        return ("jet", "viridis", "inferno")

    def set_colormap(self, name: str) -> None:
        if name not in self.available_colormaps():
            raise ValueError(f"Unsupported colormap: {name}")
        cmap = pg.colormap.get(name)
        self._image_item.setLookupTable(cmap.getLookupTable(nPts=256))

    def set_zero_hold_frames(self, frames: int) -> None:
        _ = frames

    def set_display_mode(self, mode: str) -> None:
        if mode in ("raw", "calibrated"):
            self._display_mode = mode

    def set_zones(self, zones: tuple[dict, ...] | list[dict]) -> None:
        self._zones = tuple(zones)
        self._init_zone_lines()

    def update_heatmap(self, data: np.ndarray) -> None:
        matrix = np.asarray(data, dtype=np.float32)
        if matrix.shape != (self._rows, self._cols):
            raise ValueError(f"heatmap shape must be ({self._rows}, {self._cols})")

        display = matrix.copy()
        if self._display_mode == "raw":
            display[display < self._display_noise_floor] = 0.0
        else:
            display[display < 0.0] = 0.0

        self._data = display

        flat = display.ravel().astype(np.float64)
        canvas_flat = np.zeros(self._canvas_h * self._canvas_w, dtype=np.float64)
        canvas_flat[self._inside_idx] = self._interp_w @ flat
        canvas = np.clip(canvas_flat, 0.0, None).reshape(self._canvas_h, self._canvas_w)

        hi = float(np.max(canvas))
        self._image_item.setImage(
            canvas.astype(np.float32),
            autoLevels=False,
            levels=(0.0, max(hi, 1.0)),
        )
        self._image_item.setRect(0, 0, self._cols, self._rows)

    # ── sensor physical positions ──

    def _build_sensor_positions(self) -> np.ndarray:
        """Map each (row, col) sensor onto its physical (x, y) inside the foot contour."""
        pos = np.zeros((self._rows, self._cols, 2), dtype=np.float64)
        for row in range(self._rows):
            y_c = row + 0.5
            x_lo, x_hi = self._contour_x_bounds(y_c)
            if x_hi <= x_lo:
                x_lo, x_hi = 0.0, float(self._cols)
            for col in range(self._cols):
                t = (col + 0.5) / self._cols
                pos[row, col] = [x_lo + t * (x_hi - x_lo), y_c]
        return pos

    def _contour_x_bounds(self, y: float) -> tuple[float, float]:
        xs: list[float] = []
        n = len(self._contour)
        for i in range(n):
            x1, y1 = self._contour[i]
            x2, y2 = self._contour[(i + 1) % n]
            if (y1 <= y <= y2) or (y2 <= y <= y1):
                dy = y2 - y1
                if abs(dy) < 1e-12:
                    xs.extend([x1, x2])
                else:
                    t = (y - y1) / dy
                    if 0.0 <= t <= 1.0:
                        xs.append(x1 + t * (x2 - x1))
        if len(xs) < 2:
            return 0.0, float(self._cols)
        return min(xs), max(xs)

    # ── high-res foot mask (vectorised scanline) ──

    def _build_canvas_mask(self) -> np.ndarray:
        ys = (np.arange(self._canvas_h) + 0.5) / self._canvas_h * self._rows
        xs = (np.arange(self._canvas_w) + 0.5) / self._canvas_w * self._cols
        gy, gx = np.meshgrid(ys, xs, indexing="ij")

        poly = np.asarray(self._contour, dtype=np.float64)
        px, py = poly[:, 0], poly[:, 1]
        px_prev, py_prev = np.roll(px, 1), np.roll(py, 1)

        mask = np.zeros((self._canvas_h, self._canvas_w), dtype=bool)
        for i in range(len(poly)):
            yi, yj = float(py[i]), float(py_prev[i])
            xi, xj = float(px[i]), float(px_prev[i])
            cond = (yi > gy) != (yj > gy)
            if not np.any(cond):
                continue
            x_cross = (xj - xi) * (gy - yi) / (yj - yi + 1e-12) + xi
            mask ^= cond & (gx < x_cross)
        return mask

    # ── RBF interpolation weights ──

    def _precompute_weights(self) -> np.ndarray:
        ys = (np.arange(self._canvas_h) + 0.5) / self._canvas_h * self._rows
        xs = (np.arange(self._canvas_w) + 0.5) / self._canvas_w * self._cols
        gy, gx = np.meshgrid(ys, xs, indexing="ij")
        all_pts = np.column_stack([gx.ravel(), gy.ravel()])
        inside_pts = all_pts[self._inside_idx]

        sensor_pts = self._sensor_xy.reshape(-1, 2)
        dists = cdist(inside_pts, sensor_pts)
        sigma = _sigma_for_canvas_rows(inside_pts[:, 1])
        w = np.exp(-dists ** 2 / (2.0 * sigma[:, None] ** 2))
        sums = w.sum(axis=1, keepdims=True)
        sums[sums < 1e-15] = 1.0
        w /= sums
        return w.astype(np.float32)

    # ── static overlay & outline ──

    def _render_static_overlay(self) -> None:
        rgba = np.zeros((self._canvas_h, self._canvas_w, 4), dtype=np.uint8)
        outside = ~self._canvas_mask
        rgba[outside, 0] = 20
        rgba[outside, 1] = 20
        rgba[outside, 2] = 20
        rgba[outside, 3] = 220
        self._overlay_item.setImage(rgba, autoLevels=False)
        self._overlay_item.setRect(0, 0, self._cols, self._rows)

    # ── zone boundaries ──

    def _init_zone_lines(self) -> None:
        for item in self._zone_lines:
            self._plot.removeItem(item)
        self._zone_lines.clear()
        for item in self._zone_labels:
            self._plot.removeItem(item)
        self._zone_labels.clear()

        boundaries: set[int] = set()
        for zone in self._zones:
            boundaries.add(int(zone["row_end"]) + 1)

        for b in sorted(v for v in boundaries if 0 < v < self._rows):
            x_lo, x_hi = self._contour_x_bounds(float(b))
            line = pg.PlotDataItem(
                [x_lo, x_hi],
                [float(b), float(b)],
                pen=pg.mkPen(
                    color="#bbbbbb", width=1,
                    style=pg.QtCore.Qt.PenStyle.DashLine,
                ),
            )
            self._plot.addItem(line)
            self._zone_lines.append(line)

        for zone in self._zones:
            rs, re = int(zone["row_start"]), int(zone["row_end"])
            y_c = (rs + re + 1) * 0.5
            x_lo, x_hi = self._contour_x_bounds(y_c)
            label = pg.TextItem(
                text=str(zone["display_name"]),
                color="#ffffff",
                anchor=(0.5, 0.5),
            )
            label.setPos((x_lo + x_hi) * 0.5, y_c)
            label.setZValue(50)
            self._plot.addItem(label)
            self._zone_labels.append(label)

    # ── tooltip ──

    def _zone_name_by_row(self, row: int) -> str:
        for zone in self._zones:
            if int(zone["row_start"]) <= row <= int(zone["row_end"]):
                return str(zone["display_name"])
        return "--"

    def _on_mouse_moved(self, scene_pos: QPointF) -> None:
        if not self._image_item.sceneBoundingRect().contains(scene_pos):
            return
        image_pos = self._image_item.mapFromScene(scene_pos)
        x_plot, y_plot = image_pos.x(), image_pos.y()
        row, col = int(y_plot), int(x_plot)
        if not (0 <= row < self._rows and 0 <= col < self._cols):
            return

        in_foot = self._pip_scalar(x_plot, y_plot, self._contour)
        value = float(self._data[row, col])
        zone = self._zone_name_by_row(row)
        unit = "kPa" if self._display_mode == "calibrated" else "ADC"
        tip = (
            f"通道: ({row}, {col}) | 值: {value:.2f} {unit} | "
            f"{'足底区域' if in_foot else '轮廓外'} | 分区: {zone}"
        )
        QToolTip.showText(QCursor.pos(), tip, self)
        self.hover_text_changed.emit(tip)

    @staticmethod
    def _pip_scalar(x: float, y: float, poly: list[tuple[float, float]]) -> bool:
        inside = False
        n = len(poly)
        j = n - 1
        for i in range(n):
            xi, yi = poly[i]
            xj, yj = poly[j]
            if ((yi > y) != (yj > y)) and (
                x < (xj - xi) * (y - yi) / ((yj - yi) + 1e-12) + xi
            ):
                inside = not inside
            j = i
        return inside


def _sigma_for_canvas_rows(rows: np.ndarray) -> np.ndarray:
    row_values = np.asarray(rows, dtype=np.float64)
    transition = max(float(HEATMAP_TOE_TRANSITION_ROWS), 1e-6)
    blend_start = float(HEATMAP_TOE_ROW_START) - transition
    blend = np.clip((row_values - blend_start) / transition, 0.0, 1.0)
    sigma = float(HEATMAP_RBF_SIGMA) + (
        float(HEATMAP_TOE_RBF_SIGMA) - float(HEATMAP_RBF_SIGMA)
    ) * blend
    return np.maximum(sigma, 1e-6)
