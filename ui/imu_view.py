from __future__ import annotations

import numpy as np
from PySide6.QtCore import Slot
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from data.models import ProcessedFrame
from utils.math_utils import normalize_quaternion, quaternion_to_euler

try:
    import pyqtgraph.opengl as gl
except Exception:  # pragma: no cover - 仅用于无 OpenGL 运行环境时降级
    gl = None

class IMUView(QWidget):
    def __init__(self, parent: QWidget | None = None, enable_3d: bool = True) -> None:
        super().__init__(parent)
        self._enable_3d = bool(enable_3d)
        self._axis_lines: list[object] = []

        self._quat_w = QLabel("--", self)
        self._quat_x = QLabel("--", self)
        self._quat_y = QLabel("--", self)
        self._quat_z = QLabel("--", self)
        self._euler_roll = QLabel("--", self)
        self._euler_pitch = QLabel("--", self)
        self._euler_yaw = QLabel("--", self)
        self._status_label = QLabel("", self)

        self._gl_view: object | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(10)

        values_group = QGroupBox("IMU 数值", self)
        value_layout = QFormLayout(values_group)
        value_layout.setContentsMargins(10, 10, 10, 10)
        value_layout.setVerticalSpacing(8)

        for label in (
            self._quat_w,
            self._quat_x,
            self._quat_y,
            self._quat_z,
            self._euler_roll,
            self._euler_pitch,
            self._euler_yaw,
        ):
            label.setStyleSheet("font-size: 14px; font-weight: 600;")
            label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        value_layout.addRow("Quaternion w", self._quat_w)
        value_layout.addRow("Quaternion x", self._quat_x)
        value_layout.addRow("Quaternion y", self._quat_y)
        value_layout.addRow("Quaternion z", self._quat_z)
        value_layout.addRow("Roll (deg)", self._euler_roll)
        value_layout.addRow("Pitch (deg)", self._euler_pitch)
        value_layout.addRow("Yaw (deg)", self._euler_yaw)
        main_layout.addWidget(values_group)

        pose_group = QGroupBox("3D 姿态 (可选)", self)
        pose_layout = QVBoxLayout(pose_group)
        pose_layout.setContentsMargins(10, 10, 10, 10)

        if self._enable_3d and gl is not None:
            self._gl_view = gl.GLViewWidget(parent=pose_group)
            self._gl_view.setCameraPosition(distance=3.2, elevation=15, azimuth=35)
            self._gl_view.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
            )
            pose_layout.addWidget(self._gl_view)
            self._init_gl_items()
            self._status_label.setText("3D 姿态：已启用")
        elif self._enable_3d:
            self._status_label.setText("3D 姿态：当前环境缺少 OpenGL 依赖，已自动禁用")
            pose_layout.addWidget(self._status_label)
        else:
            self._status_label.setText("3D 姿态：已关闭")
            pose_layout.addWidget(self._status_label)

        main_layout.addWidget(pose_group)

    def _init_gl_items(self) -> None:
        if self._gl_view is None or gl is None:
            return
        self._gl_view.addItem(gl.GLGridItem())
        self._axis_lines = [
            self._create_axis_line((1.0, 0.0, 0.0, 1.0)),  # X - red
            self._create_axis_line((0.0, 1.0, 0.0, 1.0)),  # Y - green
            self._create_axis_line((0.2, 0.6, 1.0, 1.0)),  # Z - blue
        ]
        for item in self._axis_lines:
            self._gl_view.addItem(item)

    def _create_axis_line(self, color: tuple[float, float, float, float]) -> object:
        if gl is None:
            return object()
        pts = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]], dtype=np.float32)
        return gl.GLLinePlotItem(pos=pts, color=color, width=4.0, antialias=True, mode="lines")

    @Slot(object)
    def update_frame(self, frame: ProcessedFrame) -> None:
        if not isinstance(frame, ProcessedFrame):
            return
        quat = tuple(float(v) for v in frame.imu_quaternion)
        euler = tuple(float(v) for v in frame.imu_euler)
        self.update_imu(quat, euler)

    def update_imu(
        self,
        quaternion: tuple[float, float, float, float],
        euler: tuple[float, float, float] | None = None,
    ) -> None:
        w, x, y, z = normalize_quaternion(*quaternion)
        if euler is None:
            roll, pitch, yaw = quaternion_to_euler(w, x, y, z)
        else:
            roll, pitch, yaw = (float(v) for v in euler)

        self._quat_w.setText(f"{w:.4f}")
        self._quat_x.setText(f"{x:.4f}")
        self._quat_y.setText(f"{y:.4f}")
        self._quat_z.setText(f"{z:.4f}")
        self._euler_roll.setText(f"{roll:.2f}")
        self._euler_pitch.setText(f"{pitch:.2f}")
        self._euler_yaw.setText(f"{yaw:.2f}")
        self._update_3d_axes(w, x, y, z)

    def _update_3d_axes(self, w: float, x: float, y: float, z: float) -> None:
        if self._gl_view is None or gl is None or len(self._axis_lines) != 3:
            return
        rotation = self._quaternion_to_rotation_matrix(w, x, y, z)
        origin = np.zeros(3, dtype=np.float32)
        axis_basis = np.eye(3, dtype=np.float32)
        rotated = (rotation @ axis_basis.T).T
        for index, item in enumerate(self._axis_lines):
            pts = np.stack((origin, rotated[index]), axis=0)
            item.setData(pos=pts)

    @staticmethod
    def _quaternion_to_rotation_matrix(
        w: float, x: float, y: float, z: float
    ) -> np.ndarray:
        return np.array(
            [
                [1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y - z * w), 2.0 * (x * z + y * w)],
                [2.0 * (x * y + z * w), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z - x * w)],
                [2.0 * (x * z - y * w), 2.0 * (y * z + x * w), 1.0 - 2.0 * (x * x + y * y)],
            ],
            dtype=np.float32,
        )
