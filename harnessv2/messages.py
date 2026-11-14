"""Message formats. Everything is versioned so later phases (secure
aggregation, differential privacy, compression) can add fields or encodings.

Sensor events and labels are small JSON objects. Model weights travel as raw
float32 bytes behind a JSON header:  b"DUC1" | header length (4 bytes) | header | arrays
"""

from __future__ import annotations

import json
import struct

import numpy as np

VERSION = 1
MAGIC = b"DUC1"


def event(stream: str, seq: int, t_us: int, sensor: str, sensor_type: str, loc: str, value) -> bytes:
    """One sensor event in the standard format every source is translated to."""
    return json.dumps({"v": VERSION, "stream": stream, "seq": seq, "t": t_us, "sensor": sensor,
                       "type": sensor_type, "loc": loc, "value": value},
                      separators=(",", ":")).encode()


def label(stream: str, seq: int, t_us: int, activity) -> bytes:
    return json.dumps({"v": VERSION, "stream": stream, "seq": seq, "t": t_us, "activity": activity},
                      separators=(",", ":")).encode()


def end_of_stream(stream: str, seq: int) -> bytes:
    return json.dumps({"v": VERSION, "stream": stream, "seq": seq, "eos": True}).encode()


def pack(header: dict, arrays: list[np.ndarray]) -> bytes:
    """Header plus arrays -> bytes. Shapes go in the header; data is float32."""
    header = dict(header, v=VERSION, encoding="float32-raw",
                  shapes=[list(a.shape) for a in arrays])
    h = json.dumps(header, separators=(",", ":")).encode()
    return MAGIC + struct.pack("<I", len(h)) + h + b"".join(
        np.ascontiguousarray(a, dtype="<f4").tobytes() for a in arrays)


def unpack(payload: bytes) -> tuple[dict, list[np.ndarray]]:
    if payload[:4] != MAGIC:
        raise ValueError("not a DUC model message")
    (n,) = struct.unpack("<I", payload[4:8])
    header = json.loads(payload[8:8 + n])
    arrays, pos = [], 8 + n
    for shape in header["shapes"]:
        size = int(np.prod(shape)) * 4
        arrays.append(np.frombuffer(payload, dtype="<f4", count=size // 4, offset=pos).reshape(shape).copy())
        pos += size
    return header, arrays
