from __future__ import annotations

import logging
from time import monotonic

from PySide6.QtCore import QObject, Signal

from config import FRAME_HEADER, PACK1_DATA_LEN, PACK1_SEQ, PACK2_DATA_LEN, PACK2_SEQ
from data.models import MergedFrame, RawPacket


class ProtocolParser(QObject):
    frame_merged = Signal(object)
    stats_updated = Signal(dict)

    def __init__(self, pair_timeout_sec: float = 0.5) -> None:
        super().__init__()
        self._logger = logging.getLogger("comm.protocol")
        self._pair_timeout_sec = pair_timeout_sec
        self._buffer = bytearray()
        self._pending_packets: dict[int, dict[int, RawPacket]] = {}
        self._stats = {
            "rx_bytes": 0,
            "frames_ok": 0,
            "frames_drop": 0,
            "format_err": 0,
        }

    def feed(self, raw_bytes: bytes) -> None:
        if not raw_bytes:
            self._cleanup_expired()
            self.stats_updated.emit(dict(self._stats))
            return

        self._stats["rx_bytes"] += len(raw_bytes)
        self._buffer.extend(raw_bytes)
        self._drain_buffer()
        self._cleanup_expired()
        self.stats_updated.emit(dict(self._stats))

    def _drain_buffer(self) -> None:
        while True:
            if len(self._buffer) < len(FRAME_HEADER):
                return

            if self._buffer[: len(FRAME_HEADER)] != FRAME_HEADER:
                header_pos = self._buffer.find(FRAME_HEADER, 1)
                if header_pos == -1:
                    # 保留尾部，避免帧头跨 feed 边界时被误删。
                    del self._buffer[:-len(FRAME_HEADER) + 1]
                    return
                del self._buffer[:header_pos]
                self._stats["format_err"] += 1
                continue

            if len(self._buffer) < len(FRAME_HEADER) + 2:
                return

            seq = self._buffer[len(FRAME_HEADER)]
            sensor_type = self._buffer[len(FRAME_HEADER) + 1]
            if seq not in (PACK1_SEQ, PACK2_SEQ):
                self._stats["format_err"] += 1
                del self._buffer[0]
                continue

            payload_len = PACK1_DATA_LEN if seq == PACK1_SEQ else PACK2_DATA_LEN
            packet_total_len = len(FRAME_HEADER) + 2 + payload_len
            if len(self._buffer) < packet_total_len:
                return
            payload_start = len(FRAME_HEADER) + 2
            payload_end = payload_start + payload_len
            payload = bytes(self._buffer[payload_start:payload_end])
            del self._buffer[:packet_total_len]

            packet = RawPacket(
                seq=seq,
                sensor_type=sensor_type,
                payload=payload,
                recv_ts=monotonic(),
            )
            self._cache_packet(packet)

    def _cache_packet(self, packet: RawPacket) -> None:
        sensor_packets = self._pending_packets.setdefault(packet.sensor_type, {})
        sensor_packets[packet.seq] = packet
        pack1 = sensor_packets.get(PACK1_SEQ)
        pack2 = sensor_packets.get(PACK2_SEQ)
        if pack1 is None or pack2 is None:
            return

        merged = MergedFrame(
            sensor_type=packet.sensor_type,
            data=pack1.payload + pack2.payload,
            timestamp=max(pack1.recv_ts, pack2.recv_ts),
        )
        # 先移除缓存，再发信号，避免槽函数里进入嵌套事件循环后重入 feed()
        # 导致同一 sensor_type 被再次处理并提前删除，返回这里时触发 KeyError。
        self._pending_packets.pop(packet.sensor_type, None)
        self._stats["frames_ok"] += 1
        self.frame_merged.emit(merged)

    def _cleanup_expired(self) -> None:
        if not self._pending_packets:
            return
        now = monotonic()
        expired: list[int] = []
        for sensor_type, packets in self._pending_packets.items():
            oldest_recv = min(item.recv_ts for item in packets.values())
            if now - oldest_recv > self._pair_timeout_sec:
                expired.append(sensor_type)
                self._stats["frames_drop"] += len(packets)
        for sensor_type in expired:
            del self._pending_packets[sensor_type]
