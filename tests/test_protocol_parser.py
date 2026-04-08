from __future__ import annotations

import time

from communication.protocol_parser import ProtocolParser
from config import FRAME_HEADER, PACK1_DATA_LEN, PACK1_SEQ, PACK2_DATA_LEN, PACK2_SEQ


def _build_subpacket(seq: int, sensor_type: int, fill: int) -> bytes:
    payload_len = PACK1_DATA_LEN if seq == PACK1_SEQ else PACK2_DATA_LEN
    payload = bytes([fill]) * payload_len
    return FRAME_HEADER + bytes([seq, sensor_type]) + payload


def test_feed_merges_two_packets_same_sensor_type() -> None:
    parser = ProtocolParser()
    merged_frames: list = []
    parser.frame_merged.connect(merged_frames.append)

    parser.feed(_build_subpacket(PACK1_SEQ, 0x03, 0x11))
    parser.feed(_build_subpacket(PACK2_SEQ, 0x03, 0x22))

    assert len(merged_frames) == 1
    frame = merged_frames[0]
    assert frame.sensor_type == 0x03
    assert len(frame.data) == PACK1_DATA_LEN + PACK2_DATA_LEN
    assert frame.data[:PACK1_DATA_LEN] == bytes([0x11]) * PACK1_DATA_LEN
    assert frame.data[PACK1_DATA_LEN:] == bytes([0x22]) * PACK2_DATA_LEN


def test_feed_skips_noise_and_resyncs_header() -> None:
    parser = ProtocolParser()
    merged_frames: list = []
    stats_list: list[dict] = []
    parser.frame_merged.connect(merged_frames.append)
    parser.stats_updated.connect(stats_list.append)

    data = b"\x00\x01\x02" + _build_subpacket(PACK1_SEQ, 0x05, 0x33) + _build_subpacket(
        PACK2_SEQ, 0x05, 0x44
    )
    parser.feed(data)

    assert len(merged_frames) == 1
    assert stats_list[-1]["format_err"] >= 1


def test_feed_counts_invalid_seq_as_format_error() -> None:
    parser = ProtocolParser()
    stats_list: list[dict] = []
    parser.stats_updated.connect(stats_list.append)

    invalid_packet = FRAME_HEADER + bytes([0x09, 0x01]) + (b"\x00" * PACK2_DATA_LEN)
    parser.feed(invalid_packet)

    assert stats_list[-1]["format_err"] >= 1
    assert stats_list[-1]["frames_ok"] == 0


def test_cleanup_expired_incomplete_packets() -> None:
    parser = ProtocolParser(pair_timeout_sec=0.01)
    stats_list: list[dict] = []
    parser.stats_updated.connect(stats_list.append)

    parser.feed(_build_subpacket(PACK1_SEQ, 0x07, 0x55))
    time.sleep(0.03)
    parser.feed(b"")

    assert stats_list[-1]["frames_drop"] >= 1


def test_feed_half_packet_then_complete_packet() -> None:
    parser = ProtocolParser()
    merged_frames: list = []
    parser.frame_merged.connect(merged_frames.append)

    pack1 = _build_subpacket(PACK1_SEQ, 0x08, 0x10)
    split_at = len(pack1) // 2
    parser.feed(pack1[:split_at])
    parser.feed(pack1[split_at:])
    parser.feed(_build_subpacket(PACK2_SEQ, 0x08, 0x20))

    assert len(merged_frames) == 1
    assert merged_frames[0].sensor_type == 0x08
    assert len(merged_frames[0].data) == PACK1_DATA_LEN + PACK2_DATA_LEN


def test_feed_out_of_order_packets_still_merge() -> None:
    parser = ProtocolParser()
    merged_frames: list = []
    parser.frame_merged.connect(merged_frames.append)

    parser.feed(_build_subpacket(PACK2_SEQ, 0x09, 0x66))
    parser.feed(_build_subpacket(PACK1_SEQ, 0x09, 0x55))

    assert len(merged_frames) == 1
    frame = merged_frames[0]
    assert frame.data[:PACK1_DATA_LEN] == bytes([0x55]) * PACK1_DATA_LEN
    assert frame.data[PACK1_DATA_LEN:] == bytes([0x66]) * PACK2_DATA_LEN


def test_feed_interleaved_multi_sensor_packets() -> None:
    parser = ProtocolParser()
    merged_frames: list = []
    parser.frame_merged.connect(merged_frames.append)

    stream = (
        _build_subpacket(PACK1_SEQ, 0x11, 0x11)
        + _build_subpacket(PACK1_SEQ, 0x22, 0x22)
        + _build_subpacket(PACK2_SEQ, 0x11, 0x33)
        + _build_subpacket(PACK2_SEQ, 0x22, 0x44)
    )
    parser.feed(stream)

    assert len(merged_frames) == 2
    by_sensor = {frame.sensor_type: frame for frame in merged_frames}
    assert set(by_sensor.keys()) == {0x11, 0x22}
    assert by_sensor[0x11].data[:PACK1_DATA_LEN] == bytes([0x11]) * PACK1_DATA_LEN
    assert by_sensor[0x11].data[PACK1_DATA_LEN:] == bytes([0x33]) * PACK2_DATA_LEN
    assert by_sensor[0x22].data[:PACK1_DATA_LEN] == bytes([0x22]) * PACK1_DATA_LEN
    assert by_sensor[0x22].data[PACK1_DATA_LEN:] == bytes([0x44]) * PACK2_DATA_LEN
