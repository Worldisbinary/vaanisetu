"""Transports: loopback, UDP (stand-in for a Wi-Fi Direct link) and a simulated lossy link."""

from __future__ import annotations

import queue
import random
import socket
from abc import ABC, abstractmethod


class Transport(ABC):
    @abstractmethod
    def send(self, data: bytes) -> None: ...

    @abstractmethod
    def recv(self, timeout: float | None = None) -> bytes | None:
        """Next datagram, or None on timeout."""

    def close(self) -> None:  # pragma: no cover - trivial
        pass


class LoopbackTransport(Transport):
    """In-memory endpoint. Use `LoopbackTransport.pair()` to get two connected ends."""

    def __init__(self, inbox: queue.Queue, outbox: queue.Queue) -> None:
        self._in, self._out = inbox, outbox

    @classmethod
    def pair(cls) -> tuple[LoopbackTransport, LoopbackTransport]:
        a, b = queue.Queue(), queue.Queue()
        return cls(a, b), cls(b, a)

    def send(self, data: bytes) -> None:
        self._out.put(bytes(data))

    def recv(self, timeout: float | None = 0.0) -> bytes | None:
        try:
            return self._in.get(timeout=timeout) if timeout else self._in.get_nowait()
        except queue.Empty:
            return None


class UdpTransport(Transport):
    def __init__(self, bind: tuple[str, int] | None = None, peer: tuple[str, int] | None = None):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        if bind:
            self._sock.bind(bind)
        self._peer = peer

    @property
    def address(self) -> tuple[str, int]:
        return self._sock.getsockname()

    def send(self, data: bytes) -> None:
        if self._peer is None:
            raise RuntimeError("no peer configured")
        self._sock.sendto(data, self._peer)

    def recv(self, timeout: float | None = None) -> bytes | None:
        self._sock.settimeout(timeout)
        try:
            return self._sock.recvfrom(65535)[0]
        except (TimeoutError, BlockingIOError):
            return None

    def close(self) -> None:
        self._sock.close()


class LossyLink(Transport):
    """Wraps a Transport: drops datagrams with probability `drop_rate`, enforces `mtu`."""

    def __init__(self, inner: Transport, drop_rate: float = 0.0, mtu: int | None = None,
                 seed: int | None = None) -> None:
        self.inner, self.drop_rate, self.mtu = inner, drop_rate, mtu
        self._rng = random.Random(seed)
        self.sent = self.dropped = 0

    def send(self, data: bytes) -> None:
        if self.mtu is not None and len(data) > self.mtu:
            raise ValueError(f"datagram of {len(data)} bytes exceeds link MTU {self.mtu}")
        self.sent += 1
        if self._rng.random() < self.drop_rate:
            self.dropped += 1
            return
        self.inner.send(data)

    def recv(self, timeout: float | None = None) -> bytes | None:
        return self.inner.recv(timeout)

    def close(self) -> None:
        self.inner.close()
