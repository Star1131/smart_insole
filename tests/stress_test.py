from __future__ import annotations

import random
import time

from communication.protocol_parser import ProtocolParser
from config import FRAME_HEADER, PACK1_DATA_LEN, PACK1_SEQ, PACK2_DATA_LEN, PACK2_SEQ


def _build_subpacket(seq: int, sensor_type: int, fill: int) -> bytes:
    payload_len = PACK1_DATA_LEN if seq == PACK1_SEQ else PACK2_DATA_LEN
    return FRAME_HEADER + bytes([seq, sensor_type]) + (bytes([fill]) * payload_len)


def test_stress_200hz_stream_short_window() -> None:
    parser = ProtocolParser(pair_timeout_sec=0.5)
    stats: list[dict] = []
    parser.stats_updated.connect(stats.append)

    target_frames = 200
    stream = bytearray()
    for i in range(target_frames):
        stream.extend(_build_subpacket(PACK1_SEQ, 0x03, i % 251))
        stream.extend(_build_subpacket(PACK2_SEQ, 0x03, (i + 1) % 251))

    start = time.perf_counter()
    parser.feed(bytes(stream))
    elapsed = time.perf_counter() - start

    last = stats[-1]
    assert last["frames_ok"] == target_frames
    assert last["frames_drop"] == 0
    assert last["format_err"] == 0
    assert last["rx_bytes"] == len(stream)
    assert elapsed < 1.0


def test_fault_injection_noise_truncate_bad_header_no_crash() -> None:
    parser = ProtocolParser(pair_timeout_sec=0.01)
    stats: list[dict] = []
    parser.stats_updated.connect(stats.append)

    random.seed(7)
    payload = bytearray()
    payload.extend(_build_subpacket(PACK1_SEQ, 0x04, 0x10))
    payload.extend(bytes(random.randint(0, 255) for _ in range(64)))
    payload.extend(_build_subpacket(PACK2_SEQ, 0x04, 0x20))
    payload.extend(_build_subpacket(PACK1_SEQ, 0x06, 0x40))  # 孤立包，触发超时丢弃
    payload.extend(_build_subpacket(PACK1_SEQ, 0x05, 0x30)[:-20])  # 截断包
    payload.extend(b"\xAB\xCD\xEF\x01\x02\x03")  # 错误帧头噪声

    parser.feed(bytes(payload))
    time.sleep(0.02)
    parser.feed(b"")

    last = stats[-1]
    assert last["frames_ok"] >= 1
    assert last["format_err"] >= 1
    assert last["frames_drop"] >= 1
