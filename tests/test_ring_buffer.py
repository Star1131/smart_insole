from communication.ring_buffer import RingBuffer


def test_push_pop_fifo() -> None:
    rb = RingBuffer(capacity=8)
    rb.push(b"abcd")
    assert len(rb) == 4
    assert rb.pop(2) == b"ab"
    assert rb.pop(2) == b"cd"
    assert len(rb) == 0


def test_overflow_keeps_latest_bytes() -> None:
    rb = RingBuffer(capacity=5)
    rb.push(b"abc")
    rb.push(b"defg")
    assert len(rb) == 5
    assert rb.pop(10) == b"cdefg"


def test_peek_does_not_consume() -> None:
    rb = RingBuffer(capacity=6)
    rb.push(b"abcdef")
    assert rb.peek(3) == b"abc"
    assert len(rb) == 6
    assert rb.pop(3) == b"abc"
