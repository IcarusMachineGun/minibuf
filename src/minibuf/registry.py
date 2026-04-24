"""Type Registry"""

import enum
import math
import struct
from collections.abc import Callable
from functools import wraps
from typing import Any, NoReturn

from . import varint
from .common import DecodeResult, WireType
from .types import *


class Frozen:
    def __setattr__(self, name, value) -> NoReturn:
        msg = f"'{self.__class__.__name__}' object is immutable"
        raise AttributeError(msg)

    def __delattr__(self, name) -> NoReturn:
        msg = f"'{self.__class__.__name__}' object is immutable"
        raise AttributeError(msg)


class NumberSpec(Frozen):
    __slots__ = ['is_signed', 'max_signed', 'max_unsigned', 'min_value', 'size_bytes']
    size_bytes: int
    is_signed: bool
    max_signed: float
    min_value: float
    max_unsigned: float

    def is_overflow(self, value: float) -> bool:
        if isinstance(value, float) and (math.isinf(value) or math.isnan(value)):
            return False
        return value > self.max_unsigned or (self.is_signed and (value > self.max_signed or value < self.min_value))

    def __init__(self, size_bytes: int, is_signed: bool) -> None:
        object.__setattr__(self, 'size_bytes', size_bytes)
        object.__setattr__(self, 'max_unsigned', 2 ** (self.size_bytes * 8) - 1)
        object.__setattr__(self, 'max_signed', (2 ** (self.size_bytes * 8 - 1)) - 1)
        object.__setattr__(self, 'min_value', (-(2 ** (self.size_bytes * 8 - 1))) if is_signed else 0)
        object.__setattr__(self, 'is_signed', is_signed)


class TypeInfo(Frozen):
    __slots__ = ['decode', 'default', 'encode', 'numspec', 'wt']

    wt: WireType
    encode: Callable[[Any], bytes]
    decode: Callable[[bytes], DecodeResult]
    numspec: NumberSpec
    default: Any

    def __init__(
        self,
        wt: WireType,
        encode: Callable[[Any], bytes],
        decode: Callable[[bytes], DecodeResult],
        numspec: NumberSpec | None = None,
        default: Any = None,
    ) -> None:

        def encode_wrapper(func: Callable[[Any], bytes]):
            @wraps(func)
            def wrapper(value) -> bytes:
                if self.numspec is not None and self.numspec.is_overflow(value):  # type: ignore
                    msg = (
                        f'value {value} not in '
                        f'[{self.numspec.min_value}, '
                        f'{self.numspec.max_signed if self.numspec.is_signed else self.numspec.max_unsigned}]'
                    )
                    raise OverflowError(msg)
                return func(value)

            return wrapper  # type: ignore

        def decode_wrapper(func: Callable[[bytes], DecodeResult]):
            @wraps(func)
            def wrapper(data) -> DecodeResult:
                result: DecodeResult = func(data)
                if self.numspec is not None and self.numspec.is_overflow(result.value):  # type: ignore
                    raise ValueError
                return result

            return wrapper  # type: ignore

        object.__setattr__(self, 'wt', wt)
        object.__setattr__(self, 'encode', encode_wrapper(encode))
        object.__setattr__(self, 'decode', decode_wrapper(decode))
        object.__setattr__(self, 'numspec', numspec)
        object.__setattr__(self, 'default', default)


class TypeRegistry:
    def __init__(self) -> None:
        self._registry: dict[type[Any], TypeInfo] = {
            # ------------------ VARINT ------------------
            int32: TypeInfo(WireType.VARINT, varint.encode_s, varint.decode_s, NumberSpec(size_bytes=4, is_signed=True), default=0),
            int64: TypeInfo(WireType.VARINT, varint.encode_s, varint.decode_s, NumberSpec(size_bytes=8, is_signed=True), default=0),
            uint32: TypeInfo(WireType.VARINT, varint.encode_u, varint.decode_u, NumberSpec(size_bytes=4, is_signed=False), default=0),
            uint64: TypeInfo(WireType.VARINT, varint.encode_u, varint.decode_u, NumberSpec(size_bytes=8, is_signed=False), default=0),
            sint32: TypeInfo(
                WireType.VARINT, varint.encode_zigzag, varint.decode_zigzag, NumberSpec(size_bytes=4, is_signed=True), default=0
            ),
            sint64: TypeInfo(
                WireType.VARINT, varint.encode_zigzag, varint.decode_zigzag, NumberSpec(size_bytes=8, is_signed=True), default=0
            ),
            bool: TypeInfo(
                WireType.VARINT,
                lambda v: varint.encode_u(1 if v else 0),
                lambda v: DecodeResult((res := varint.decode_u(v))[0] != 0, res[1]),
                NumberSpec(size_bytes=1, is_signed=False),
                default=False,
            ),
            # ------------------ I64 ------------------
            fixed64: TypeInfo(
                WireType.I64,
                lambda v: v.to_bytes(8, byteorder='little'),
                lambda v: DecodeResult(int.from_bytes(v[:8], byteorder='little'), 8),
                NumberSpec(size_bytes=8, is_signed=False),
                default=0,
            ),
            sfixed64: TypeInfo(
                WireType.I64,
                lambda v: v.to_bytes(8, byteorder='little', signed=True),
                lambda v: DecodeResult(int.from_bytes(v[:8], byteorder='little', signed=True), 8),
                NumberSpec(size_bytes=8, is_signed=True),
                default=0,
            ),
            double: TypeInfo(
                WireType.I64,
                lambda v: struct.pack('<d', v),
                lambda v: DecodeResult(struct.unpack('<d', v[:8])[0], 8),
                NumberSpec(size_bytes=8, is_signed=True),
                default=0.0,
            ),
            # ------------------ I32 ------------------
            fixed32: TypeInfo(
                WireType.I32,
                lambda v: v.to_bytes(4, byteorder='little'),
                lambda v: DecodeResult(int.from_bytes(v[:4], byteorder='little'), 4),
                NumberSpec(size_bytes=4, is_signed=False),
                default=0,
            ),
            sfixed32: TypeInfo(
                WireType.I32,
                lambda v: v.to_bytes(4, byteorder='little', signed=True),
                lambda v: DecodeResult(int.from_bytes(v[:4], byteorder='little', signed=True), 4),
                NumberSpec(size_bytes=4, is_signed=True),
                default=0,
            ),
            float: TypeInfo(
                WireType.I32,
                lambda v: struct.pack('<f', v),
                lambda v: DecodeResult(struct.unpack('<f', v[:4])[0], 4),
                NumberSpec(size_bytes=4, is_signed=True),
                default=0.0,
            ),
            # ------------------ LEN ------------------
            str: TypeInfo(
                WireType.LEN,
                lambda v: v.encode('utf-8'),
                lambda v: DecodeResult(v.decode('utf-8')),
                default='',
            ),
            bytes: TypeInfo(
                WireType.LEN,
                lambda v: v,
                DecodeResult,
                default=b'\00',
            ),
            bytearray: TypeInfo(
                WireType.LEN,
                bytes,
                lambda v: DecodeResult(bytearray(v)),
                default=b'\00',
            ),
        }

    def __contains__(self, item) -> bool:
        return item in self._registry

    def __getitem__(self, key: type[Any]) -> TypeInfo:
        return self._registry[key]

    def new_embedded(self, type_obj: type[Any]) -> None:
        """Add embedded message type to registry

        :param type_obj: ...
        :type type_obj: type[Any]
        """
        self._registry[type_obj] = TypeInfo(
            WireType.LEN,
            lambda v: v.to_bytes(),
            lambda v: DecodeResult(type_obj.from_bytes(v)),
        )

    def new_enum(self, type_obj: enum.EnumType) -> None:
        """Add enum type to registry

        :param type_obj: ...
        :type type_obj: enum.EnumType
        """

        def decode_func_for_enum(v, type_obj) -> DecodeResult:
            res = varint.decode_u(v)
            type_value = type_obj[res[0]] if isinstance(v, str) else type_obj(res[0])  # type: ignore
            return DecodeResult(type_value, res[1])

        self._registry[type_obj] = TypeInfo(
            WireType.VARINT,
            varint.encode_u,
            lambda v: decode_func_for_enum(v, type_obj),
            default=0,
        )


TYPE_REGISTRY = TypeRegistry()
