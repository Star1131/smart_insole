from __future__ import annotations

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from communication.serial_manager import SerialManager


class SerialPanel(QWidget):
    data_received = Signal(bytes)
    connection_changed = Signal(bool)
    error_occurred = Signal(str)

    def __init__(self, serial_manager: SerialManager | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._serial_manager = serial_manager or SerialManager()
        self._owns_manager = serial_manager is None
        self._is_connected = False

        self.port_combo = QComboBox()
        self.port_combo.setPlaceholderText("请选择串口")
        self.refresh_button = QPushButton("刷新")
        self.connect_button = QPushButton("连接")

        self.status_value = QLabel("未连接")
        self.rx_bytes_value = QLabel("0")
        self.reconnect_value = QLabel("0")

        self._build_ui()
        self._bind_signals()
        self.refresh_ports()

    def _build_ui(self) -> None:
        action_layout = QHBoxLayout()
        action_layout.addWidget(self.port_combo, 1)
        action_layout.addWidget(self.refresh_button)
        action_layout.addWidget(self.connect_button)

        status_form = QFormLayout()
        status_form.addRow("状态", self.status_value)
        status_form.addRow("接收字节", self.rx_bytes_value)
        status_form.addRow("重连次数", self.reconnect_value)

        root_layout = QVBoxLayout(self)
        root_layout.addLayout(action_layout)
        root_layout.addLayout(status_form)
        root_layout.addStretch(1)

    def _bind_signals(self) -> None:
        self.refresh_button.clicked.connect(self.refresh_ports)
        self.connect_button.clicked.connect(self._toggle_connection)
        self._serial_manager.connection_changed.connect(self._on_connection_changed)
        self._serial_manager.error_occurred.connect(self._on_error_occurred)
        self._serial_manager.stats_updated.connect(self._on_stats_updated)
        self._serial_manager.data_received.connect(self.data_received.emit)

    @Slot()
    def refresh_ports(self) -> None:
        current_port = self.port_combo.currentText()
        ports = self._serial_manager.scan_ports()
        self.port_combo.clear()
        self.port_combo.addItems(ports)
        if current_port in ports:
            self.port_combo.setCurrentText(current_port)
        elif ports:
            self.port_combo.setCurrentIndex(0)

    @Slot()
    def _toggle_connection(self) -> None:
        if self._is_connected:
            self._serial_manager.disconnect_port()
            return

        port_name = self.port_combo.currentText().strip()
        if not port_name:
            self._set_status("未选择串口")
            self.error_occurred.emit("请先选择串口")
            return
        self._serial_manager.connect_port(port_name)
        self._set_status(f"连接中: {port_name}")

    @Slot(bool)
    def _on_connection_changed(self, connected: bool) -> None:
        self._is_connected = connected
        self.port_combo.setEnabled(not connected)
        self.refresh_button.setEnabled(not connected)
        self.connect_button.setText("断开" if connected else "连接")
        self._set_status("已连接" if connected else "未连接")
        self.connection_changed.emit(connected)

    @Slot(dict)
    def _on_stats_updated(self, stats: dict) -> None:
        self.rx_bytes_value.setText(str(stats.get("rx_bytes", 0)))
        self.reconnect_value.setText(str(stats.get("reconnect_count", 0)))

    @Slot(str)
    def _on_error_occurred(self, message: str) -> None:
        self._set_status("错误")
        self.error_occurred.emit(message)

    def _set_status(self, value: str) -> None:
        self.status_value.setText(value)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self._owns_manager:
            self._serial_manager.disconnect_port()
        super().closeEvent(event)
