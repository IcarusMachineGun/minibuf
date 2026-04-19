"""Some common stuff along with types"""

# ruff: noqa:  N801
import base64
import enum
import weakref
from collections.abc import Callable
from typing import Any, ClassVar, NamedTuple, NoReturn, TypedDict, Unpack


def type_str(t: type[Any]):
    return t.__name__ if t in {str, float, bytes, bytearray, bool} else str(t)


class DecodeResult(NamedTuple):
    value: Any
    bytes_consumed: int = 0


class WireType(enum.IntEnum):
    """
    :var VARINT: Variable-length integer encoding. Efficient for small positive numbers
    :vartype VARINT: Literal[0]
    :var I64: Fixed-length 64-bit data
    :vartype I64: Literal[1]
    :var LEN: The value is preceded by its length, which is encoded as a varint
    :vartype LEN: Literal[2]
    :var SGROUP: Start of a group. Not supported(deprecated in proto3)
    :vartype SGROUP: Literal[3]
    :var EGROUP: End of a group. Not supported (deprecated in proto3)
    :vartype EGROUP: Literal[4]
    :var I32: Fixed-length 32-bit data
    :vartype I32: Literal[5]
    """

    VARINT = 0
    I64 = 1
    LEN = 2
    SGROUP = 3
    EGROUP = 4
    I32 = 5


class TypeMeta(type):
    def __str__(cls) -> str:
        return f'{cls.__name__}'

    def __new__(mcs, name, bases, namespace, **_):
        py_type = None
        for base in bases:
            if base is not TypeBase and not isinstance(base, TypeMeta):
                py_type = base
                break

        if py_type:
            namespace['py_type'] = py_type

        return super().__new__(mcs, name, bases, namespace)


class TypeBase(metaclass=TypeMeta):
    py_type: ClassVar[type]


# --------------- types -----------------


class int32(int, TypeBase): ...


class int64(int, TypeBase): ...


class uint32(int, TypeBase): ...


class uint64(int, TypeBase): ...


class sint32(int, TypeBase): ...


class sint64(int, TypeBase): ...


class fixed64(int, TypeBase): ...


class sfixed64(int, TypeBase): ...


class fixed32(int, TypeBase): ...


class sfixed32(int, TypeBase): ...


class double(float, TypeBase, pytype=float): ...


class FieldTypedDict[T](TypedDict, total=False):
    default: T
    default_factory: Callable[[], T]
    is_optional: bool
    is_repeated: bool
    is_mapping: bool


def field[T: Any](number: int, **kwargs: Unpack[FieldTypedDict[T]]) -> Any:
    """Creates a protocol buffer field descriptor.

    The field type is primarily determined by Python type annotations. However,
    explicit flags (`is_optional`, `is_repeated`, `is_mapping`) take **higher
    priority** than type annotations when both are present.

    Priority rules:
        1. Explicit flags override type annotations
        2. If no flag is set, type annotations determine the field kind
        3. Regular type (no special flags) → scalar field
        4. `typing.Optional[T]` or `T | None` → optional field (unless `is_optional=False`)
        5. `list[T] | tuple[T]` → repeated field (unless `is_repeated=False`)
        6. `collections.abc.Mapping[K, V]` → map field (unless `is_mapping=False`)

    Examples:

        from typing import Optional

        # Type annotation determines field kind
        f1: int32 = field(1)                    # scalar
        f2: Optional[int32] = field(2)   # optional
        f3: list[int32] = field(3)              # repeated
        f4: dict[int32, bytes] = field(4)       # map

        # Using default values
        f8: int32 = field(8, default=42)                  # with default value
        f9: list[int32] = field(9, default_factory=list)  # with default factory

    :param number: A unique positive integer between 1 and 536,870,911
    :type number: int
    :param default: Default value for the field. Used when no value is provided.
        Cannot be used together with `default_factory`.
    :type default: Any | None
    :param default_factory: A zero-argument callable that returns the default value.
        Similar to `default_factory` in dataclasses - called each time a default
        value is needed. Useful for mutable default values like lists or dicts.
        Cannot be used together with `default`.
    :type default_factory: collections.abc.Callable[[], Any] | None = None
    :param is_optional: Explicitly mark field as optional. Same as `typing.Optional[T]`.
    :type is_optional: bool | None
    :param is_repeated: Explicitly mark field as repeated (0 or more values). Same as `list[T] | tuple[T]`.
    :type is_repeated: bool | None
    :param is_mapping: Explicitly mark field as a map type. Same as `collections.abc.Mapping[K, V]`.
    :type is_mapping: bool | None
    :return: :class:`minibuf.Field` object
    :rtype: Any
    """
    return Field[T](number, **kwargs)


class Field[T]:
    __slots__ = ['default', 'default_factory', 'is_mapping', 'is_optional', 'is_repeated', 'name', 'number', 'type']

    type: type[T]

    def __init__(self, number: int, **kwargs: Unpack[FieldTypedDict[T]]) -> None:
        self.number = number
        self.name = '<unnamed>'
        self.default = kwargs.get('default')
        self.default_factory = kwargs.get('default_factory')
        self.is_optional = kwargs.get('is_optional')
        self.is_repeated = kwargs.get('is_repeated')
        self.is_mapping = kwargs.get('is_mapping')

        if self.default is not None and self.default_factory is not None:
            msg = 'cannot specify both default and default_factory'
            raise ValueError(msg)

    def has_default(self) -> bool:
        return self.default is not None or self.default_factory is not None

    def to_proto3(self) -> str:
        """Translate field to proto3"""

        def type_to_string(t):
            return 'string' if t is str else str(t.__name__)

        if self.is_mapping:
            key_f, value_f = tuple(self.type._get_spec().values())  # type: ignore
            key_t = type_to_string(key_f.type)
            value_t = type_to_string(value_f.type)
            return f'map<{key_t}, {value_t}> {self.name} = {self.number};'
        else:
            typ_str = type_to_string(self.type)
            return f'{"repeated " if self.is_repeated else "optional " if self.is_optional else ""}{typ_str} {self.name} = {self.number};'

    def __repr__(self) -> str:
        return f'{self.name}({type_str(self.type)})'

    def __hash__(self) -> int:
        return self.number

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Field):
            return NotImplemented

        return self.number == other.number


class Encoded[T]:
    """Wrapper for encoded data after serialization

    :var message: weakref of Message instance
    :vartype message: T
    :var data: Encoded data
    :vartype data: bytes
    """

    __slots__ = ['_data', 'message']

    message: T
    _data: bytes

    def __init__(self, message: T, data: bytes) -> None:
        object.__setattr__(self, 'message', weakref.proxy(message))
        object.__setattr__(self, '_data', data)

    def __setattr__(self, *_, **__) -> NoReturn:
        msg = f'{self.__class__.__name__!r} object is immutable'
        raise AttributeError(msg)

    def __delattr__(self, *_, **__) -> NoReturn:
        msg = f'{self.__class__.__name__!r} object is immutable'
        raise AttributeError(msg)

    @property
    def bytes(self) -> bytes:
        """Bytes object of encoded data

        :return: `bytes` object
        :rtype: bytes
        """
        return self._data

    @property
    def size(self) -> int:
        """Size of encoded data"""
        return len(self._data)

    def hex(self) -> str:
        """Create a hex string from a bytes object

        :return:
        :rtype: str
        """
        return self._data.hex()

    def base64(self) -> str:
        """Encode the data using Base64 and return a string (utf-8)

        :return:
        :rtype: str
        """
        return base64.b64encode(self._data).decode('utf-8')
