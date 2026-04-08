from __future__ import annotations

import logging
from threading import Lock

from PySide6.QtCore import QThread, Signal
import serial
from serial import SerialException
from serial.tools import list_ports

from config import SERIAL_BAUDRATE, SERIAL_BYTESIZE, SERIAL_PARITY, SERIAL_STOPBITS


class SerialManager(QThread):
    data_received = Signal(bytes)
    connection_changed = Signal(bool)
    error_occurred = Signal(str)
    stats_updated = Signal(dict)

    def __init__(self) -> None:
        super().__init__()
        self._logger = logging.getLogger("comm.serial")
        self._lock = Lock()
        self._port_name: str | None = None
        self._serial: serial.Serial | None = None
        self._running = False
        self._state = "DISCONNECTED"
        self._stats = {
            "rx_bytes": 0,
            "reconnect_count": 0,
        }

    def scan_ports(self) -> list[str]:
        return [item.device for item in list_ports.comports()]

    def connect_port(self, port: str) -> bool:
        with self._lock:
            if self._state == "CONNECTED" and self._port_name == port:
                return True
            self._port_name = port
            self._running = True
            self._set_state("CONNECTING")

        if not self.isRunning():
            self.start()
        return True

    def disconnect_port(self) -> None:
        with self._lock:
            self._running = False
            serial_obj = self._serial
            self._serial = None
            self._port_name = None
        if serial_obj is not None:
            self._close_serial(serial_obj)
        self.wait(1000)
        self._set_state("DISCONNECTED")
        self.connection_changed.emit(False)

    def run(self) -> None:
        while True:
            with self._lock:
                should_run = self._running
                port_name = self._port_name
                serial_obj = self._serial

            if not should_run:
                break
            if not port_name:
                self.msleep(20)
                continue
            if serial_obj is None:
                serial_obj = self._open_serial(port_name)
                if serial_obj is None:
                    self.msleep(500)
                    continue

            try:
                data = serial_obj.read(serial_obj.in_waiting or 1)
                if data:
                    self._stats["rx_bytes"] += len(data)
                    self.data_received.emit(data)
                    self.stats_updated.emit(dict(self._stats))
            except SerialException as exc:
                self._logger.warning("Serial read failed on %s: %s", port_name, exc)
                self.error_occurred.emit(f"串口读取异常: {exc}")
                self._handle_disconnect(serial_obj)
                self.msleep(500)
            except OSError as exc:
                self._logger.warning("Serial device removed %s: %s", port_name, exc)
                self.error_occurred.emit(f"串口设备断开: {exc}")
                self._handle_disconnect(serial_obj)
                self.msleep(500)
            else:
                self.msleep(1)

        with self._lock:
            serial_obj = self._serial
            self._serial = None
        if serial_obj is not None:
            self._close_serial(serial_obj)

    def _open_serial(self, port: str) -> serial.Serial | None:
        try:
            ser = serial.Serial(
                port=port,
                baudrate=SERIAL_BAUDRATE,
                bytesize=SERIAL_BYTESIZE,
                parity=SERIAL_PARITY,
                stopbits=SERIAL_STOPBITS,
                timeout=0,
                write_timeout=0,
            )
        except SerialException as exc:
            self._set_state("ERROR")
            self.error_occurred.emit(f"串口连接失败: {exc}")
            return None

        with self._lock:
            self._serial = ser
            self._stats["reconnect_count"] += 1
        self._set_state("CONNECTED")
        self.connection_changed.emit(True)
        self.stats_updated.emit(dict(self._stats))
        return ser

    def _handle_disconnect(self, serial_obj: serial.Serial) -> None:
        self._close_serial(serial_obj)
        with self._lock:
            self._serial = None
        self._set_state("ERROR")
        self.connection_changed.emit(False)

    @staticmethod
    def _close_serial(serial_obj: serial.Serial) -> None:
        try:
            if serial_obj.is_open:
                serial_obj.close()
        except SerialException:
            pass

    def _set_state(self, state: str) -> None:
        self._state = state
