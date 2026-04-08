from __future__ import annotations


class RingBuffer:
    def __init__(self, capacity: int = 65536) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be > 0")
        self.capacity = capacity
        self._buffer = bytearray(capacity)
        self._head = 0
        self._tail = 0
        self._size = 0

    def push(self, data: bytes) -> None:
        if not data:
            return

        data_len = len(data)
        if data_len >= self.capacity:
            data = data[-self.capacity :]
            data_len = len(data)
            self._head = 0
            self._tail = 0
            self._size = 0

        overflow = self._size + data_len - self.capacity
        if overflow > 0:
            self._head = (self._head + overflow) % self.capacity
            self._size -= overflow

        first = min(data_len, self.capacity - self._tail)
        self._buffer[self._tail : self._tail + first] = data[:first]
        second = data_len - first
        if second:
            self._buffer[0:second] = data[first:]

        self._tail = (self._tail + data_len) % self.capacity
        self._size += data_len

    def pop(self, size: int) -> bytes:
        if size <= 0 or self._size == 0:
            return b""

        size = min(size, self._size)
        first = min(size, self.capacity - self._head)
        second = size - first

        if second:
            output = bytes(self._buffer[self._head : self._head + first] + self._buffer[0:second])
        else:
            output = bytes(self._buffer[self._head : self._head + first])

        self._head = (self._head + size) % self.capacity
        self._size -= size
        return output

    def peek(self, size: int) -> bytes:
        if size <= 0 or self._size == 0:
            return b""
        size = min(size, self._size)
        first = min(size, self.capacity - self._head)
        second = size - first
        if second:
            return bytes(self._buffer[self._head : self._head + first] + self._buffer[0:second])
        return bytes(self._buffer[self._head : self._head + first])

    def clear(self) -> None:
        self._head = 0
        self._tail = 0
        self._size = 0

    def __len__(self) -> int:
        return self._size
