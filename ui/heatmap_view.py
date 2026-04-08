from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from scipy.interpolate import splprep, splev
from scipy.ndimage import zoom
from PySide6.QtCore import QPointF, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QToolTip, QVBoxLayout, QWidget

from config import (
    ADC_COLS,
    ADC_ROWS,
    DEFAULT_FOOT_ZONES,
    HEATMAP_UPSAMPLE,
    INSOLE_CONTOUR_RIGHT,
)

_BG_COLOR = "#151a22"
_BG_RGB = (21, 26, 34)


def _smooth_contour(
    raw_pts: list[tuple[float, float]], num_out: int = 400
) -> np.ndarray:
    """Periodic cubic spline interpolation for smooth closed contour."""
    arr = np.array(raw_pts, dtype=np.float64)
    tck, _ = splprep([arr[:, 0], arr[:, 1]], s=0, per=True, k=3)
    u = np.linspace(0, 1, num_out, endpoint=False)
    x, y = splev(u, tck)
    return np.column_stack([x, y])


def _build_polygon_mask(
    verts: np.ndarray,
    shape_hw: tuple[int, int],
    x_range: tuple[float, float],
    y_range: tuple[float, float],
) -> np.ndarray:
    """Scanline polygon fill → boolean mask."""
    h, w = shape_hw
    x0, x1 = x_range
    y0, y1 = y_range
    mask = np.zeros((h, w), dtype=bool)

    px = (verts[:, 0] - x0) / (x1 - x0) * w
    py = (verts[:, 1] - y0) / (y1 - y0) * h
    n = len(px)

    for row in range(h):
        yc = row + 0.5
        xs: list[float] = []
        for i in range(n):
            j = (i + 1) % n
            ya, yb = py[i], py[j]
            if (ya <= yc < yb) or (yb <= yc < ya):
                t = (yc - ya) / (yb - ya)
                xs.append(float(px[i] + t * (px[j] - px[i])))
        xs.sort()
        for k in range(0, len(xs) - 1, 2):
            c0 = max(0, int(xs[k]))
            c1 = min(w, int(xs[k + 1] + 1))
            mask[row, c0:c1] = True
    return mask


class HeatmapView(QWidget):
    hover_text_changed = Signal(str)

    def __init__(
        self,
        parent: QWidget | None = None,
        colormap: str = "viridis",
        upsample: int = HEATMAP_UPSAMPLE,
    ) -> None:
        super().__init__(parent)
        self._display_mode = "raw"
        self._rows = ADC_ROWS
        self._cols = ADC_COLS
        self._up = max(1, int(upsample))
        self._hi_h = self._rows * self._up
        self._hi_w = self._cols * self._up
        self._data = np.zeros((self._rows, self._cols), dtype=np.float32)
        self._zones = tuple(DEFAULT_FOOT_ZONES)

        xr = (0.0, float(self._cols))
        yr = (0.0, float(self._rows))
        self._contour = _smooth_contour(INSOLE_CONTOUR_RIGHT, 400)
        self._mask_hi = _build_polygon_mask(
            self._contour, (self._hi_h, self._hi_w), xr, yr
        )
        self._mask_lo = _build_polygon_mask(
            self._contour, (self._rows, self._cols), xr, yr
        )

        self._plot = pg.PlotWidget(parent=self)
        self._plot.setMenuEnabled(False)
        self._plot.setMouseEnabled(x=False, y=False)
        self._plot.hideAxis("left")
        self._plot.hideAxis("bottom")
        vb = self._plot.getViewBox()
        vb.setAspectLocked(True)
        vb.invertY(False)
        vb.setRange(xRange=xr, yRange=yr, padding=0.05)
        self._plot.setBackground(_BG_COLOR)

        self._image_item = pg.ImageItem(axisOrder="row-major")
        blank = np.zeros((self._hi_h, self._hi_w), dtype=np.float32)
        self._image_item.setImage(blank, autoLevels=False, levels=(0.0, 1.0))
        self._image_item.setRect(0, 0, self._cols, self._rows)
        self._plot.addItem(self._image_item)

        self._overlay = pg.ImageItem(axisOrder="row-major")
        self._init_overlay()
        self._plot.addItem(self._overlay)

        cx = np.append(self._contour[:, 0], self._contour[0, 0])
        cy = np.append(self._contour[:, 1], self._contour[0, 1])
        self._outline = pg.PlotCurveItem(
            x=cx, y=cy, pen=pg.mkPen("#f5c842", width=2.5)
        )
        self._outline.setZValue(20)
        self._plot.addItem(self._outline)

        self._zone_lines: list[pg.PlotCurveItem] = []
        self._zone_labels: list[pg.TextItem] = []
        self._init_zones()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._plot)

        self._plot.scene().sigMouseMoved.connect(self._on_mouse_moved)
        self.set_colormap(colormap)
        self.update_heatmap(self._data)

    # ── public API ──────────────────────────────────────────

    def available_colormaps(self) -> tuple[str, ...]:
        return ("jet", "viridis", "inferno")

    def set_colormap(self, name: str) -> None:
        if name not in self.available_colormaps():
            raise ValueError(f"Unsupported colormap: {name}")
        cmap = pg.colormap.get(name)
        self._image_item.setLookupTable(cmap.getLookupTable(nPts=256))

    def set_display_mode(self, mode: str) -> None:
        if mode in ("raw", "calibrated"):
            self._display_mode = mode

    def set_zones(self, zones: tuple[dict, ...] | list[dict]) -> None:
        self._zones = tuple(zones)
        self._init_zones()

    def update_heatmap(self, data: np.ndarray) -> None:
        mat = np.asarray(data, dtype=np.float32)
        if mat.shape != (self._rows, self._cols):
            raise ValueError(f"shape must be ({self._rows}, {self._cols})")

        self._data = mat
        if self._up > 1:
            hi = zoom(mat, self._up, order=1).astype(np.float32)
            hi = hi[: self._hi_h, : self._hi_w]
        else:
            hi = mat.copy()
        hi[~self._mask_hi] = 0.0
        vmax = float(np.max(hi))
        self._image_item.setImage(
            hi, autoLevels=False, levels=(0.0, max(vmax, 1.0))
        )

    # ── private ─────────────────────────────────────────────

    def _init_overlay(self) -> None:
        rgba = np.zeros((self._hi_h, self._hi_w, 4), dtype=np.uint8)
        outside = ~self._mask_hi
        rgba[outside, 0] = _BG_RGB[0]
        rgba[outside, 1] = _BG_RGB[1]
        rgba[outside, 2] = _BG_RGB[2]
        rgba[outside, 3] = 240
        self._overlay.setImage(rgba, autoLevels=False)
        self._overlay.setRect(0, 0, self._cols, self._rows)
        self._overlay.setZValue(10)

    def _init_zones(self) -> None:
        for item in self._zone_lines:
            self._plot.removeItem(item)
        self._zone_lines.clear()
        for item in self._zone_labels:
            self._plot.removeItem(item)
        self._zone_labels.clear()

        boundaries: set[int] = set()
        for z in self._zones:
            boundaries.add(int(z["row_end"]) + 1)

        for b in sorted(v for v in boundaries if 0 < v < self._rows):
            xl, xr = self._contour_x_at_y(float(b))
            if xl is None or xr is None:
                continue
            line = pg.PlotCurveItem(
                x=np.array([xl, xr]),
                y=np.array([float(b), float(b)]),
                pen=pg.mkPen(
                    "#888888", width=1,
                    style=pg.QtCore.Qt.PenStyle.DashLine,
                ),
            )
            line.setZValue(15)
            self._plot.addItem(line)
            self._zone_lines.append(line)

        for z in self._zones:
            yc = (int(z["row_start"]) + int(z["row_end"]) + 1) * 0.5
            xl, xr = self._contour_x_at_y(yc)
            xc = ((xl + xr) * 0.5) if xl is not None and xr is not None else self._cols * 0.5
            label = pg.TextItem(
                text=str(z["display_name"]),
                color="#ffffff",
                anchor=(0.5, 0.5),
            )
            label.setPos(xc, yc)
            label.setZValue(50)
            self._plot.addItem(label)
            self._zone_labels.append(label)

    def _contour_x_at_y(self, y: float) -> tuple[float | None, float | None]:
        pts = self._contour
        n = len(pts)
        xs: list[float] = []
        for i in range(n):
            j = (i + 1) % n
            ya, yb = pts[i, 1], pts[j, 1]
            if (ya <= y < yb) or (yb <= y < ya):
                t = (y - ya) / (yb - ya)
                xs.append(float(pts[i, 0] + t * (pts[j, 0] - pts[i, 0])))
        if len(xs) < 2:
            return None, None
        return min(xs), max(xs)

    def _zone_name(self, row: int) -> str:
        for z in self._zones:
            if int(z["row_start"]) <= row <= int(z["row_end"]):
                return str(z["display_name"])
        return "--"

    def _on_mouse_moved(self, pos: QPointF) -> None:
        if not self._image_item.sceneBoundingRect().contains(pos):
            return
        ip = self._image_item.mapFromScene(pos)
        col, row = int(ip.x()), int(ip.y())
        if not (0 <= row < self._rows and 0 <= col < self._cols):
            return
        val = float(self._data[row, col])
        inside = bool(self._mask_lo[row, col])
        zone = self._zone_name(row)
        unit = "kPa" if self._display_mode == "calibrated" else "ADC"
        tip = (
            f"通道: ({row}, {col}) | 值: {val:.2f} {unit} | "
            f"{'足底区域' if inside else '轮廓外'} | 分区: {zone}"
        )
        QToolTip.showText(QCursor.pos(), tip, self)
        self.hover_text_changed.emit(tip)
