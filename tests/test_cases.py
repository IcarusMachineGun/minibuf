import enum
import logging

logging.getLogger('minibuf').setLevel('DEBUG')

from minibuf import BaseMessage, field
from minibuf.types import *


class ScalarTypes(BaseMessage):
    double_field: double = field(1)
    float_field: float = field(2)
    int32_field: int32 = field(3)
    int64_field: int64 = field(4)
    uint32_field: uint32 = field(5)
    uint64_field: uint64 = field(6)
    sint32_field: sint32 = field(7)
    sint64_field: sint64 = field(8)
    fixed32_field: fixed32 = field(9)
    fixed64_field: fixed64 = field(10)
    sfixed32_field: sfixed32 = field(11)
    sfixed64_field: sfixed64 = field(12)
    bool_field: bool = field(13)
    string_field: str = field(14)
    bytes_field: bytes = field(15)


class Status(enum.IntEnum):
    UNKNOWN = 0
    ACTIVE = enum.auto()
    INACTIVE = enum.auto()
    PENDING = enum.auto()


class WithDefaults(BaseMessage):
    name: str = field(1, default='Test Message')
    count: int32 = field(2, default=42)
    enabled: bool = field(3, default=False)
    score: double = field(4, default=95.5)
    status: Status = field(5, default=Status.ACTIVE)


class InnerMessage(BaseMessage):
    value: int32 = field(1)
    description: str = field(2)


class OuterMessage(BaseMessage):
    id: str = field(1)
    inner: InnerMessage = field(2)
    tags: list[str] = field(3)


class RepeatedFields(BaseMessage):
    numbers: list[int32] = field(1)
    names: list[str] = field(2)
    statuses: list[Status] = field(3)
    items: list[InnerMessage] = field(4)


class MapFields(BaseMessage):
    string_map: dict[str, str] = field(1)
    numeric_map: dict[int32, double] = field(2)
    enum_map: dict[str, Status] = field(3)
    object_map: dict[str, InnerMessage] = field(4)


class ComplexMessage(BaseMessage):
    id: str = field(1)
    scalars: ScalarTypes = field(2)
    items: list[WithDefaults] = field(3)
    mappings: dict[str, InnerMessage] = field(4)
    status_history: list[Status] = field(5)
    signature: bytes = field(6)


class EdgeCases(BaseMessage):
    zero_int: int32 = field(1)
    zero_double: double = field(2)
    false_bool: bool = field(3)
    empty_string: str = field(4)

    max_int32: int32 = field(5)
    min_int32: int32 = field(6)
    max_int64: int64 = field(7)
    min_int64: int64 = field(8)

    nan_value: float = field(9)
    infinity_value: float = field(10)
    neg_infinity_value: float = field(11)
    double_nan: double = field(12)

    unicode_string: str = field(13)
    escaped_string: str = field(14)

    large_bytes: bytes = field(15)


class AllFieldNumbers(BaseMessage):
    field1: int32 = field(1)
    field100: int32 = field(100)
    field1000: int32 = field(1000)
    field10000: int32 = field(10000)
    field50000: int32 = field(50000)
