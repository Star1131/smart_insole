from __future__ import annotations

import csv
import os
import queue
import threading
from pathlib import Path
from time import monotonic

import numpy as np
from PySide6.QtCore import QObject

from config import ADC_NOISE_THRESHOLD
from data.models import ProcessedFrame


class DataRecorder(QObject):
    _STOP = object()

    def __init__(self, flush_batch_size: int = 100, flush_interval_sec: float = 0.2) -> None:
        super().__init__()
        self._flush_batch_size = max(1, int(flush_batch_size))
        self._flush_interval_sec = max(0.01, float(flush_interval_sec))
        self._queue: queue.Queue[ProcessedFrame | object] = queue.Queue()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._recording = False
        self._filepath = ""

    def start_recording(self, filepath: str) -> None:
        path = Path(filepath)
        if path.parent and str(path.parent) not in ("", "."):
            path.parent.mkdir(parents=True, exist_ok=True)

        if self._recording:
            self.stop_recording()

        self._filepath = str(path)
        self._recording = True
        self._thread = threading.Thread(target=self._writer_worker, daemon=True)
        self._thread.start()

    def stop_recording(self) -> str:
        with self._lock:
            if not self._recording:
                return self._filepath
            self._recording = False

        self._queue.put(self._STOP)
        thread = self._thread
        if thread is not None:
            thread.join(timeout=3.0)
        self._thread = None
        return self._filepath

    def write_frame(self, frame: ProcessedFrame) -> None:
        with self._lock:
            if not self._recording:
                return
        self._queue.put(frame)

    def load_csv(self, filepath: str) -> list[ProcessedFrame]:
        rows: list[ProcessedFrame] = []
        with open(filepath, "r", encoding="utf-8", newline="") as fp:
            reader = csv.DictReader(fp)
            if reader.fieldnames is None:
                return rows

            adc_cols = [f"ch_{idx:03d}" for idx in range(128)]
            if not all(name in reader.fieldnames for name in adc_cols):
                return rows

            for row in reader:
                adc_values = [self._parse_float(row.get(col), 0.0) for col in adc_cols]
                adc_matrix_u8 = np.asarray(adc_values, dtype=np.float64).clip(0, 255).astype(np.uint8).reshape(8, 16)
                adc_filtered = adc_matrix_u8.copy()
                adc_filtered[adc_filtered < int(ADC_NOISE_THRESHOLD)] = 0
                adc_calibrated = adc_filtered.astype(np.float64)

                quaternion = (
                    self._parse_float(row.get("imu_w"), 1.0),
                    self._parse_float(row.get("imu_x"), 0.0),
                    self._parse_float(row.get("imu_y"), 0.0),
                    self._parse_float(row.get("imu_z"), 0.0),
                )
                euler = self._quaternion_to_euler(*quaternion)

                total_pressure = float(np.sum(adc_filtered[adc_filtered > 0]))
                cop = self._compute_cop(adc_filtered.astype(np.float64), total_pressure)
                peak_index = int(np.argmax(adc_filtered))
                peak_position = tuple(int(v) for v in np.unravel_index(peak_index, (8, 16)))
                peak_pressure = float(adc_filtered[peak_position])

                timestamp_ms = self._parse_float(row.get("timestamp_ms"), 0.0)
                timestamp = self._parse_float(row.get("timestamp"), timestamp_ms / 1000.0)

                rows.append(
                    ProcessedFrame(
                        timestamp=timestamp,
                        sensor_type=self._parse_int(row.get("sensor_type"), 0),
                        adc_raw=adc_matrix_u8,
                        adc_filtered=adc_filtered,
                        adc_calibrated=adc_calibrated,
                        imu_quaternion=quaternion,
                        imu_euler=euler,
                        total_pressure=total_pressure,
                        cop=cop,
                        peak_pressure=peak_pressure,
                        peak_position=peak_position,
                        zone_metrics={},
                        fps=self._parse_float(row.get("fps"), 0.0),
                        frame_index=self._parse_int(row.get("frame_index"), 0),
                    )
                )
        return rows

    def _writer_worker(self) -> None:
        if not self._filepath:
            return

        adc_cols = [f"ch_{idx:03d}" for idx in range(128)]
        fieldnames = ["timestamp_ms", "timestamp", "sensor_type", "frame_index", *adc_cols, "imu_w", "imu_x", "imu_y", "imu_z", "fps"]

        with open(self._filepath, "w", encoding="utf-8", newline="") as fp:
            writer = csv.DictWriter(fp, fieldnames=fieldnames)
            writer.writeheader()

            batch: list[ProcessedFrame] = []
            last_flush_at = monotonic()

            while True:
                timeout = max(0.01, self._flush_interval_sec - (monotonic() - last_flush_at))
                try:
                    item = self._queue.get(timeout=timeout)
                except queue.Empty:
                    item = None

                if item is self._STOP:
                    if batch:
                        self._write_batch(writer, batch)
                        batch.clear()
                        fp.flush()
                        os.fsync(fp.fileno())
                    break

                if isinstance(item, ProcessedFrame):
                    batch.append(item)

                now = monotonic()
                if batch and (len(batch) >= self._flush_batch_size or (now - last_flush_at) >= self._flush_interval_sec):
                    self._write_batch(writer, batch)
                    batch.clear()
                    fp.flush()
                    last_flush_at = now

    def _write_batch(self, writer: csv.DictWriter, frames: list[ProcessedFrame]) -> None:
        for frame in frames:
            flat = np.asarray(frame.adc_raw, dtype=np.uint8).reshape(-1)
            row = {
                "timestamp_ms": int(frame.timestamp * 1000.0),
                "timestamp": f"{float(frame.timestamp):.6f}",
                "sensor_type": int(frame.sensor_type),
                "frame_index": int(frame.frame_index),
                "imu_w": f"{float(frame.imu_quaternion[0]):.8f}",
                "imu_x": f"{float(frame.imu_quaternion[1]):.8f}",
                "imu_y": f"{float(frame.imu_quaternion[2]):.8f}",
                "imu_z": f"{float(frame.imu_quaternion[3]):.8f}",
                "fps": f"{float(frame.fps):.4f}",
            }
            for idx in range(128):
                row[f"ch_{idx:03d}"] = int(flat[idx])
            writer.writerow(row)

    @staticmethod
    def _parse_float(value: str | None, default: float) -> float:
        if value is None or value == "":
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _parse_int(value: str | None, default: int) -> int:
        if value is None or value == "":
            return default
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _quaternion_to_euler(w: float, x: float, y: float, z: float) -> tuple[float, float, float]:
        sinr_cosp = 2.0 * (w * x + y * z)
        cosr_cosp = 1.0 - 2.0 * (x * x + y * y)
        roll = float(np.degrees(np.arctan2(sinr_cosp, cosr_cosp)))

        sinp = 2.0 * (w * y - z * x)
        sinp = float(np.clip(sinp, -1.0, 1.0))
        pitch = float(np.degrees(np.arcsin(sinp)))

        siny_cosp = 2.0 * (w * z + x * y)
        cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
        yaw = float(np.degrees(np.arctan2(siny_cosp, cosy_cosp)))
        return roll, pitch, yaw

    @staticmethod
    def _compute_cop(matrix: np.ndarray, total_pressure: float) -> tuple[float, float] | None:
        if total_pressure <= 0.0:
            return None
        rows, cols = np.indices((8, 16), dtype=np.float64)
        cop_r = float(np.sum(matrix * rows) / total_pressure)
        cop_c = float(np.sum(matrix * cols) / total_pressure)
        return cop_r, cop_c
