"""Simple Variable-length Integer Encoding and Decoding Module"""

from .common import DecodeResult


def encode_zigzag(value: int) -> bytes:
    value = value << 1 if value >= 0 else (-value << 1) - 1

    return encode_u(value)


def decode_zigzag(data: bytes) -> DecodeResult:
    result = decode_u(data)
    value = result.value

    value = -(value >> 1) - 1 if value & 1 else value >> 1

    return DecodeResult(value, result.bytes_consumed)


def encode_u(value: int) -> bytes:
    result = bytearray()

    while True:
        byte = value & 0x7F
        value >>= 7
        if value == 0:
            result.append(byte)
            break
        result.append(byte | 0x80)
    return bytes(result)


def decode_u(data: bytes) -> DecodeResult:
    result = 0
    shift = 0
    bytes_consumed = 0

    for byte in data:
        bytes_consumed += 1
        result |= (byte & 0x7F) << shift
        shift += 7
        if not (byte & 0x80):
            break

    return DecodeResult(result, bytes_consumed)


def encode_s(value: int) -> bytes:
    result = bytearray()

    if value < 0:
        value = value & ((1 << 64) - 1)

    while True:
        byte = value & 0x7F
        value >>= 7

        if (value == 0 and (byte & 0x40) == 0) or (value == -1 and (byte & 0x40) != 0):
            result.append(byte)
            break

        result.append(byte | 0x80)

    return bytes(result)


def decode_s(data: bytes) -> DecodeResult:
    result = decode_u(data)
    value = result.value

    if value & (1 << 63):
        value = value - (1 << 64)

    return DecodeResult(value, result.bytes_consumed)
