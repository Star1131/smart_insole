from __future__ import annotations

from collections import deque
import logging

from PySide6.QtCore import QTimer, Qt, Slot
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import (
    QDockWidget,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from communication.protocol_parser import ProtocolParser
from config import APP_NAME, UI_REFRESH_INTERVAL_MS
from data.data_processor import DataProcessor
from data.models import ProcessedFrame
from ui.data_control_panel import DataControlPanel
from ui.calibration_wizard import CalibrationWizard
from ui.heatmap_view import HeatmapView
from ui.imu_view import IMUView
from ui.metrics_panel import MetricsPanel
from ui.serial_panel import SerialPanel
from ui.timeseries_view import TimeSeriesView


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self._logger = logging.getLogger(__name__)
        self.setWindowTitle(f"{APP_NAME} - 实时监控")
        self.resize(1360, 860)
        self.statusBar().showMessage("就绪")

        self._protocol_parser = ProtocolParser()
        self._data_processor = DataProcessor()

        self._pending_frames: deque[ProcessedFrame] = deque(maxlen=512)
        self._latest_frame: ProcessedFrame | None = None
        self._display_mode = "raw"
        self._calibration_wizard: CalibrationWizard | None = None

        self.serial_panel = SerialPanel(parent=self)
        self.data_control_panel = DataControlPanel(parent=self)
        self.metrics_panel = MetricsPanel(parent=self)
        self.heatmap_view = HeatmapView(parent=self)
        self.timeseries_view = TimeSeriesView(parent=self)
        self.imu_view = IMUView(parent=self)
        self.stream_hint_label = QLabel("串口链路状态：未收到数据", self)
        self.stream_hint_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.stream_hint_label.setStyleSheet(
            "padding: 6px 10px; border-radius: 6px; background: #1f2b3b; color: #b9d2ff;"
        )

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(int(UI_REFRESH_INTERVAL_MS))
        self._refresh_timer.timeout.connect(self._on_refresh_timer)

        self._setup_layout()
        self._setup_menu()
        self._bind_signals()
        self._set_display_mode(self._display_mode)
        self._refresh_timer.start()

    def _setup_layout(self) -> None:
        center_container = QWidget(self)
        center_layout = QVBoxLayout(center_container)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(8)
        center_layout.addWidget(self.heatmap_view, 1)
        center_layout.addWidget(self.stream_hint_label)
        self.setCentralWidget(center_container)

        left_panel = QWidget(self)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(8, 8, 8, 8)
        left_layout.setSpacing(8)
        left_layout.addWidget(self.serial_panel)
        left_layout.addWidget(self.data_control_panel)
        left_layout.addWidget(self.metrics_panel, 1)

        self.left_dock = self._create_dock("设备与指标", left_panel, Qt.DockWidgetArea.LeftDockWidgetArea)
        self.timeseries_dock = self._create_dock(
            "时序曲线", self.timeseries_view, Qt.DockWidgetArea.RightDockWidgetArea
        )
        self.imu_dock = self._create_dock("IMU", self.imu_view, Qt.DockWidgetArea.RightDockWidgetArea)
        self.tabifyDockWidget(self.timeseries_dock, self.imu_dock)
        self.timeseries_dock.raise_()

    def _create_dock(
        self, title: str, widget: QWidget, area: Qt.DockWidgetArea
    ) -> QDockWidget:
        dock = QDockWidget(title, self)
        dock.setObjectName(f"dock-{title}")
        dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea
            | Qt.DockWidgetArea.RightDockWidgetArea
            | Qt.DockWidgetArea.BottomDockWidgetArea
        )
        dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )
        dock.setWidget(widget)
        self.addDockWidget(area, dock)
        return dock

    def _setup_menu(self) -> None:
        menu_file = self.menuBar().addMenu("文件")
        import_action = QAction("导入标定文件", self)
        export_action = QAction("导出数据", self)
        menu_file.addAction(import_action)
        menu_file.addAction(export_action)
        import_action.triggered.connect(
            lambda: self._show_todo("标定导入将在 Day4 集成。")
        )
        export_action.triggered.connect(
            lambda: self._show_todo("数据导出/录制控制将在 Day4/Day5 集成。")
        )

        menu_tools = self.menuBar().addMenu("工具")
        calibration_action = QAction("打开标定向导", self)
        menu_tools.addAction(calibration_action)
        calibration_action.triggered.connect(self._open_calibration_wizard)

        menu_view = self.menuBar().addMenu("视图")
        reset_layout_action = QAction("重置布局", self)
        menu_view.addAction(reset_layout_action)
        reset_layout_action.triggered.connect(self._reset_layout)

        colormap_menu = menu_view.addMenu("热力图配色")
        for cmap_name in self.heatmap_view.available_colormaps():
            action = QAction(cmap_name, self)
            action.triggered.connect(
                lambda checked=False, name=cmap_name: self.heatmap_view.set_colormap(name)
            )
            colormap_menu.addAction(action)

        menu_mode = menu_view.addMenu("显示模式")
        mode_group = QActionGroup(self)
        mode_group.setExclusive(True)
        raw_action = QAction("ADC 原始值", self, checkable=True)
        calibrated_action = QAction("标定 kPa", self, checkable=True)
        raw_action.setChecked(True)
        mode_group.addAction(raw_action)
        mode_group.addAction(calibrated_action)
        menu_mode.addAction(raw_action)
        menu_mode.addAction(calibrated_action)
        raw_action.triggered.connect(lambda: self._set_display_mode("raw"))
        calibrated_action.triggered.connect(lambda: self._set_display_mode("calibrated"))

        menu_help = self.menuBar().addMenu("帮助")
        about_action = QAction("关于", self)
        menu_help.addAction(about_action)
        about_action.triggered.connect(
            lambda: QMessageBox.information(
                self,
                "关于",
                f"{APP_NAME}\n\n实时采集、解析与可视化工具。",
            )
        )

    def _bind_signals(self) -> None:
        self.serial_panel.data_received.connect(self._on_data_received)
        self.serial_panel.error_occurred.connect(self._on_serial_error)
        self.serial_panel.connection_changed.connect(self._on_connection_changed)

        self._protocol_parser.frame_merged.connect(self._data_processor.on_merged_frame)
        self._data_processor.frame_processed.connect(self._on_frame_processed)

    @Slot()
    def _reset_layout(self) -> None:
        self.removeDockWidget(self.left_dock)
        self.removeDockWidget(self.timeseries_dock)
        self.removeDockWidget(self.imu_dock)

        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.left_dock)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.timeseries_dock)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.imu_dock)
        self.tabifyDockWidget(self.timeseries_dock, self.imu_dock)
        self.timeseries_dock.raise_()
        self.statusBar().showMessage("布局已重置", 2000)

    def _set_display_mode(self, mode: str) -> None:
        self._display_mode = mode if mode in ("raw", "calibrated") else "raw"
        self._data_processor.set_display_mode(self._display_mode)
        self.heatmap_view.set_display_mode(self._display_mode)
        self.timeseries_view.set_display_mode(self._display_mode)
        self.metrics_panel.set_display_mode(self._display_mode)
        self.statusBar().showMessage(
            "显示模式：" + ("ADC 原始值" if self._display_mode == "raw" else "标定 kPa"),
            2000,
        )

    @Slot(bytes)
    def _on_data_received(self, data: bytes) -> None:
        self.stream_hint_label.setText(f"串口链路状态：收到 {len(data)} 字节")
        self._protocol_parser.feed(data)

    @Slot(bool)
    def _on_connection_changed(self, connected: bool) -> None:
        self.statusBar().showMessage("串口已连接" if connected else "串口未连接", 2000)

    @Slot(str)
    def _on_serial_error(self, message: str) -> None:
        self.stream_hint_label.setText(f"串口链路状态：{message}")
        self.statusBar().showMessage(f"串口异常：{message}", 3000)

    @Slot(object)
    def _on_frame_processed(self, frame: ProcessedFrame) -> None:
        if not isinstance(frame, ProcessedFrame):
            return
        self._latest_frame = frame
        self._pending_frames.append(frame)
        if self._calibration_wizard is not None and self._calibration_wizard.isVisible():
            self._calibration_wizard.set_device_id(str(frame.sensor_type))
            self._calibration_wizard.feed_adc_frame(frame.adc_raw)

    @Slot()
    def _on_refresh_timer(self) -> None:
        if self._latest_frame is None:
            return

        try:
            frame = self._latest_frame
            matrix = frame.adc_raw if self._display_mode == "raw" else frame.adc_calibrated
            self.heatmap_view.update_heatmap(matrix)
            self.metrics_panel.update_frame(frame)
            self.imu_view.update_frame(frame)

            if self._pending_frames:
                batch = list(self._pending_frames)
                self._pending_frames.clear()
                self.timeseries_view.append_frames(batch)
        except Exception:
            # 保护 UI 刷新链路：单帧异常不中断串口采集与后续渲染。
            self._logger.exception("UI refresh failed")
            self.statusBar().showMessage("UI 刷新异常，已自动恢复", 3000)
            self._pending_frames.clear()

    def _show_todo(self, message: str) -> None:
        QMessageBox.information(self, APP_NAME, message)

    def _open_calibration_wizard(self) -> None:
        if self._calibration_wizard is None:
            self._calibration_wizard = CalibrationWizard(self)
            self._calibration_wizard.profile_ready.connect(
                self._on_calibration_profile_ready
            )
        self._calibration_wizard.show()
        self._calibration_wizard.raise_()
        self._calibration_wizard.activateWindow()

    @Slot(object, bool)
    def _on_calibration_profile_ready(self, profile, apply_now: bool) -> None:
        if apply_now:
            self._data_processor.set_calibration(profile)
            self.statusBar().showMessage("已应用新的分区标定参数", 3000)
