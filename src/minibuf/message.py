import base64
import enum
import io
import json
import math
import pprint
import textwrap
import warnings
from abc import abstractmethod
from collections.abc import Mapping
from copy import deepcopy
from os import PathLike
from typing import Any, ClassVar, NamedTuple, Self, Union, dataclass_transform, get_args, get_origin, get_type_hints, overload

from . import varint
from .common import Encoded, Field, TypeBase, WireType, type_str
from .common import field as field_fn
from .logger import logger
from .registry import TYPE_REGISTRY

MAX_FIELD_NUMBER = 2**29 - 1

RepeatedType = list[Any] | tuple[Any]  # | array


class Tag(NamedTuple):
    wt: WireType
    id: int
    size: int


class MessageMeta(type):
    def __str__(cls) -> str:
        if cls.__name__ == '_MapEntry':
            return f'map({getattr(cls, "type_str", lambda: "<unknown>, <unknown>")()})'
        return f'{cls.__name__}'


@dataclass_transform(
    kw_only_default=False,
    frozen_default=True,
    field_specifiers=(field_fn,),
)
class BaseMessage(metaclass=MessageMeta):
    """Message base class.

    .. note::
        All messages and enums should be defined before they are used in a field type hint.
        Although the :func:`typing.get_type_hints()` function resolves forward references,
        it cannot help if a class is defined _after_ the field where it is used, so it may raise a NameError.

    .. code:: python

        class UserRole(enum.IntEnum):
            USER = enum.auto()
            GUEST = enum.auto()

        class UserProfile(BaseMessage):
            user_id: uint64 = field(1)
            username: str = field(2)

            role: UserRole | None = field(3)

    """

    unknown_fields: dict[int, tuple[WireType, bytes]]
    missed_fields: dict[int, Any]

    _spec_cache: ClassVar[dict[int, Field[Any]] | None] = None

    @abstractmethod
    def __init__(self, *args, **kwargs) -> None: ...

    @abstractmethod
    def to_dict(self) -> dict[str, Any]:
        """Serialize field values into a dictionary.

        key - field.name

        :return: Field data
        :rtype: dict[str, Any]
        """

    @abstractmethod
    def pretty(
        self,
        indent: int = 1,
        width: int = 80,
        depth: int | None = None,
        *,
        compact: bool = False,
        sort_dicts: bool = True,
        underscore_numbers: bool = False,
    ) -> str:
        """Creates the formatted representation of message, followed by a newline.

        .. seealso::
            :func:`pprint.pprint`

        """

    @classmethod
    def __init_subclass__(cls) -> None:
        fields: dict[str, Field[Any]] = {
            name: cls.__dict__[name] for name in cls.__annotations__ if name in cls.__dict__ and isinstance(cls.__dict__[name], Field)
        }
        seen_numbers: dict[int, str] = {}
        for field_name, field in fields.items():
            if field.number <= 0 or field.number > MAX_FIELD_NUMBER:
                msg = f'{cls.__name__}.{field_name} field number must be a positive integer between 1 and {MAX_FIELD_NUMBER:,} (got {field.number:,})'
                raise ValueError(msg)

            if field.number in seen_numbers:
                msg = f"{cls.__name__}.{field_name} field number {field.number} is already being used by '{seen_numbers[field.number]}'"
                raise ValueError(msg)

            seen_numbers[field.number] = field_name

        fields_spec = list(cls._get_spec().values())

        def init_method(self: Self, *args: Any, **kwargs: Any):
            def validate_type(arg: Any, *, is_keyword: bool) -> None:
                kw = 'keyword ' if is_keyword else ''
                if field.is_repeated and arg is not None:
                    if field.is_mapping:
                        if not issubclass(type(arg), Mapping) and (isinstance(arg, list) and arg[0].__class__.__name__ != '_MapEntry'):
                            msg = f'{cls.__name__}.__init__() {kw}argument {field.name!r} must be Mapping type, not {type(arg).__name__}'  # type: ignore
                            raise TypeError(msg)
                    elif not issubclass(type(arg), (list, tuple)):
                        msg = f'{cls.__name__}.__init__() {kw}argument {field.name!r} must be list[T] | tuple[T] type, not {type(arg).__name__!r}'
                        raise TypeError(msg)

            for i, field in enumerate(fields_spec):
                if i < len(args):
                    validate_type(args[i], is_keyword=False)
                    setattr(self, field.name, args[i])
                elif field.name in kwargs:
                    validate_type(kwargs[field.name], is_keyword=True)
                    setattr(self, field.name, kwargs[field.name])
                elif field.default is not None:
                    setattr(self, field.name, field.default)
                elif field.default_factory is not None:
                    setattr(self, field.name, field.default_factory())
                elif field.is_optional:
                    setattr(self, field.name, None)
                else:
                    msg = f"Missing required argument: '{field.name}'"
                    raise TypeError(msg)

        def repr_method(self: Self) -> str:
            spec = self._get_spec()  # type: ignore
            cls_dict = self.__dict__
            parts: list[str] = []
            for field in spec.values():
                value = cls_dict.get(field.name)
                if isinstance(value, BaseMessage):
                    parts.append(f'{field!r}={value!s}')
                else:
                    parts.append(f'{field!r}={value!s}')
            return f'{self.__class__.__name__}({", ".join(parts)})'

        def to_dict_method(self: Self) -> dict[str, Any]:
            spec = self._get_spec()
            cls_dict = self.__dict__

            result: dict[str, Any] = {}
            for field in spec.values():
                value = cls_dict.get(field.name)
                result[field.name] = serialize_value(value)
            return result

        def pretty_method(self: Self, *args, **kwargs) -> str:
            stream = io.StringIO('')
            pprint.pprint(self.to_dict(), stream, *args, **kwargs)  # type: ignore
            stream.seek(0)
            return stream.read()

        cls.__init__ = init_method  # type: ignore[method-assign]
        cls.__repr__ = repr_method  # type: ignore[method-assign]
        cls.to_dict = to_dict_method  # type: ignore[method-assign]
        cls.pretty = pretty_method  # type: ignore[method-assign]

        cls.unknown_fields = {}
        cls.missed_fields = {}

    @classmethod
    def _get_spec(cls) -> dict[int, Field[Any]]:
        """Cached :class:`~minibuf.BaseMessage` specification used in serialization and parsing."""

        def is_type_supported(typ: type[Any]):
            if typ not in TYPE_REGISTRY and typ:
                msg = f"Type '{typ}' is not supported"
                raise TypeError(msg)

        if cls._spec_cache:
            return cls._spec_cache
        logger.debug('First-time loading spec for %s', cls.__qualname__)
        fields: dict[str, Field[Any]] = {name: val for name, val in cls.__dict__.items() if isinstance(val, Field)}

        annotations = get_type_hints(cls, include_extras=False)

        spec: dict[int, Field[Any]] = {}
        try:
            for name, field in fields.items():
                field.type, type_is_optional, type_is_repeated, type_is_mapping = process_type_annotation(
                    annotations[name], cls.__qualname__, field_name=name
                )
                field.is_optional = field.is_optional if field.is_optional is not None else type_is_optional
                field.is_repeated = field.is_repeated if field.is_repeated is not None else type_is_repeated
                field.is_mapping = field.is_mapping if field.is_mapping is not None else type_is_mapping

                if issubclass(field.type, BaseMessage):
                    TYPE_REGISTRY.new_embedded(field.type)
                elif issubclass(field.type, enum.IntEnum):
                    TYPE_REGISTRY.new_enum(field.type)

                is_type_supported(field.type)

                spec[field.number] = field
                field.name = name
        except TypeError as err:
            msg = f'{cls.__name__}.{name}.{field.number} {err}'  # type: ignore
            raise TypeError(msg) from err

        cls._spec_cache = spec
        return spec

    def encode(self) -> Encoded[Self]:
        """Wrapper for :meth:`~minibuf.BaseMessage.from_bytes` method.

        :return: :class:`~minibuf.common.Encoded` object
        :rtype: Encoded[Self]

        .. seealso::
            :class:`~minibuf.common.Encoded`

        """
        return Encoded(self, self.to_bytes())

    def to_bytes(self) -> bytes:
        """Serialize field data.

        :return: Raw bytes object
        :rtype: bytes
        :raises: OverflowError
        """

        def _encode_wt_len(v):
            data = type_info.encode(v)
            size = varint.encode_u(len(data))
            return tag_byte + size + data

        result = bytearray()
        field_values: list[tuple[Field[Any], Any]] = []
        cls_dict = self.__dict__

        for field in self._get_spec().values():
            value = cls_dict[field.name]
            if field.is_optional and value is None:
                continue

            if field.is_repeated and field.is_mapping:  # {K: V, ...} becomes [_Mapping(key=K, value=V), ...]
                value = [field.type.from_dict({'key': k, 'value': v}) for k, v in value.items()]

            field_values.append((field, value))

        try:
            for field, value in field_values:
                type_info = TYPE_REGISTRY[field.type]

                if field.is_repeated:
                    tag_byte = varint.encode_u((field.number << 3) | WireType.LEN)

                    if type_info.wt == WireType.LEN:
                        result.extend(b''.join(_encode_wt_len(v) for v in value))
                        continue

                    packed_data = b''.join([type_info.encode(v) for v in value])
                    size = varint.encode_u(len(packed_data))
                    result.extend(tag_byte + size + packed_data)
                    continue

                if type_info.wt == WireType.LEN:
                    tag_byte = varint.encode_u((field.number << 3) | WireType.LEN)
                    result.extend(_encode_wt_len(value))
                    continue

                tag_byte = varint.encode_u((field.number << 3) | type_info.wt.value)
                value_bytes = type_info.encode(value)
                result.extend(tag_byte + value_bytes)
        except OverflowError as e:
            msg = f'{self.__class__.__qualname__}: Integer overflow in field {field.number} ({field.name}): {e}'  # type: ignore
            raise OverflowError(msg) from e
        return bytes(result)

    @classmethod
    def from_base64(cls, string: str) -> Self:
        """Create and initialize a new message object from a Base64-encoded *string*.

        :param string: Base64-encoded data string
        :type string: str
        :return: A new message object initialized with the deserialized data
        :rtype: Self
        """
        return cls.from_bytes(base64.b64decode(string))

    @classmethod
    def from_hex(cls, string: str) -> Self:
        """Create and initialize a new message object from a hexadecimal *string*.

        :param string: Hexadecimal-encoded data string
        :type string: str
        :return: A new message object initialized with the deserialized data
        :rtype: Self
        """
        return cls.from_bytes(bytes.fromhex(string))

    @classmethod
    def from_bytes(cls, data: bytes) -> Self:
        """Create and initialize a new message object from a bytes object.

        Implements core deserialization logic.

        .. seealso::
            * :meth:`~minibuf.BaseMessage.from_base64`
            * :meth:`~minibuf.BaseMessage.from_hex`

        :param data: Data bytes
        :type data: bytes
        :return: A new message object initialized with the deserialized data
        :rtype: Self
        :raises: ValueError
        """
        offset = 0

        def read_tag() -> Tag:
            nonlocal offset
            result = shift = 0
            bytes_consumed = 0
            while offset < len(data):
                byte = data[offset]
                result |= (byte & 0x7F) << shift
                offset += 1
                bytes_consumed += 1

                if (byte & 0x80) == 0:
                    break
                shift += 7

            return Tag(WireType(result & 0x07), result >> 3, bytes_consumed)

        def read_varint_u() -> Any:
            nonlocal offset
            value, consumed = varint.decode_u(data[offset:])
            offset += consumed
            return value

        def decode_len():
            nonlocal offset
            size = read_varint_u()
            item, _ = type_info.decode(data[offset : offset + size])
            offset += size
            return item

        spec = cls._get_spec()
        result_fields: dict[int, tuple[str, Any]] = {}
        unknown_fields: dict[int, tuple[WireType, bytes]] = {}

        while offset < len(data):
            tag = read_tag()
            field = spec.get(tag.id)

            if not field:  # save unknown fields
                if tag.wt == WireType.VARINT:
                    unknown_result = read_varint_u()
                elif tag.wt == WireType.LEN:
                    size = read_varint_u()
                    unknown_result = data[offset : offset + size]
                    offset += size
                else:
                    size = 8 if tag.wt == WireType.I64 else 4
                    unknown_result = data[offset : offset + size]
                    offset += size

                unknown_fields[tag.id] = WireType(tag.wt), unknown_result
            else:
                result = None
                type_info = TYPE_REGISTRY[field.type]

                if field.is_repeated:
                    repeated_result: list[Any] = []
                    if type_info.wt == WireType.LEN:  # Not packed LEN
                        while True:
                            repeated_result.append(decode_len())
                            if (next_tag := read_tag()) != tag:
                                offset -= next_tag.size
                                break
                    elif type_info.wt == WireType.VARINT:  # Packed VARINT
                        size = read_varint_u()
                        data_end = offset + size
                        while offset < data_end:
                            item, consumed = type_info.decode(data[offset:])
                            offset += consumed
                            repeated_result.append(item)
                    else:
                        size = read_varint_u()  # Packed I32, I64
                        for _ in range(size // type_info.numspec.size_bytes):
                            item, consumed = type_info.decode(data[offset : offset + type_info.numspec.size_bytes])
                            offset += consumed
                            repeated_result.append(item)

                    result_fields[field.number] = field.name, dict(repeated_result) if field.is_mapping else repeated_result
                    continue

                if tag.wt == WireType.LEN:
                    result = decode_len()

                elif tag.wt == WireType.VARINT:
                    result, consumed = type_info.decode(data[offset:])
                    offset += consumed

                else:  # Fixed I32, I64
                    result, consumed = type_info.decode(data[offset : offset + type_info.numspec.size_bytes])
                    offset += consumed

                result_fields[field.number] = field.name, result

        missed_fields: dict[int, Any] = {}
        for field in spec.values():
            if field.number not in result_fields:
                # FIXME: If the field is optional and is not present, it cannot be missed
                val = None if field.is_optional else TYPE_REGISTRY[field.type].default
                missed_fields[field.number] = field.name, val

        result_fields.update(missed_fields)

        args = dict(result_fields.values())

        instance = cls(**args)
        instance.unknown_fields = unknown_fields
        instance.missed_fields = missed_fields

        return instance

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Create instance using dictionary for field inputs.

        Example::

            class MyMessage(BaseMessage):
                a: int32 = field(1)
                b: NestedType = field(2)

            msg = MyMessage.from_dict({"a": 123, "b": {"c": 456}})

        :param data: Field inputs
        :type data: dict[str, Any]
        :return: Instance with parsed fields
        :rtype: Self

        .. note::
            This method parses over keys and values,
            attempting to convert them into the specified field type.

        """
        data_copy: dict[str, Any] = deepcopy(data)
        nested: dict[str, Any] = {}
        for field in cls._get_spec().values():
            if (value := data_copy.get(field.name)) is not None:
                type_obj: Any = field.type.py_type if issubclass(field.type, TypeBase) else field.type
                if field.is_repeated:
                    if field.is_mapping:
                        if type_obj.__name__ == '_MapEntry' or isinstance(value, type_obj):
                            nested[field.name] = value
                        else:
                            msg = f'type={type_obj}, value={value}'
                            raise ValueError(msg)
                    else:
                        nested[field.name] = [parse_value_of_type(type_obj, v) for v in value]
                else:
                    nested[field.name] = parse_value_of_type(type_obj, value)

            elif not field.has_default() and not field.is_optional:
                logger.warning('Missing field %s of %s', field.name, cls.__qualname__)
        data_copy.update(nested)

        return cls(**data_copy)

    @classmethod
    def from_json(cls, file_path: str | PathLike[Any]) -> Self:
        """Create instance using json data for field inputs.

        Wrapper for :meth:`~minibuf.BaseMessage.from_dict`

        :param file_path: Path to json file
        :type file_path: str | PathLike
        :return: Instance with parsed fields
        :rtype: Self
        """
        with open(file_path, encoding='utf-8') as f:
            data = json.load(f)
        return cls.from_dict(data)

    @overload
    @classmethod
    def to_proto3(cls, *, indent: int = 2) -> str:
        """Translate message to proto3 language and return string.

        :return: proto3 string
        :rtype: str
        """

    @overload
    @classmethod
    def to_proto3(cls, file_path: str | PathLike[Any], *, indent: int = 2) -> None:
        """Translate message to proto3 language and write to file.

        :param file_path: ...
        :type file_path: str | PathLike
        """

    @classmethod
    def to_proto3(cls, file_path: str | PathLike[Any] | None = None, *, indent: int = 2) -> str | None:
        """
        :param file_path: ...
        :type file_path: str | PathLike | None
        :return: ...
        :rtype: str | None
        """
        res = 'syntax = "proto3";\n' + cls._to_proto3({}, set(), indent, root=True)
        if file_path:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(res)
            return None
        else:
            return res

    @classmethod
    def _to_proto3(cls, all_types: dict[str, str], namespace: set[str], indent: int, *, root: bool) -> str:
        prefix = ' ' * indent

        def type_to_proto(t: type[Any]) -> str:
            if issubclass(t, BaseMessage):
                if t.__name__ == '_MapEntry':
                    field = t._get_spec()[1]
                    if is_type_invalid_in_proto3_mapping_key(field.type):
                        msg = f'illegal key type {field.type} in Mapping.\n\tNote: Although this works in python, it will generate invalid proto3'
                        raise ValueError(msg)
                return t._to_proto3(all_types, namespace, indent, root=False)
            elif issubclass(t, enum.IntEnum):
                items = [f'{item.name} = {item.value};' for item in list(t)]
                body = '\n' + textwrap.indent('\n'.join(items), prefix) + '\n'
                return f'\nenum {t.__name__} {{{body}}}'
            return ''  # Basic type

        types: list[str] = []
        for name, value in cls.__dict__.items():
            if name.startswith('_'):
                continue
            if is_proto_type(value):
                types.append(type_to_proto(value))
                namespace.add(value.__qualname__)

        field_strings: list[str] = []
        for field in cls._get_spec().values():
            field_strings.append(field.to_proto3())
            type_name = field.type.__qualname__
            if type_name not in namespace:
                all_types[type_name] = type_to_proto(field.type)

        body_string = textwrap.indent('\n'.join(types), prefix)
        body_string += '\n' + textwrap.indent('\n'.join(field_strings), prefix) + '\n'

        message_string = '' if cls.__name__ == '_MapEntry' else f'\nmessage {cls.__name__} {{{body_string}}}'

        return ''.join(all_types.values()) + message_string if root else message_string


def is_proto_type(t: Any):
    return isinstance(t, type) and issubclass(t, (BaseMessage, enum.IntEnum))


def is_type_invalid_in_proto3_mapping_key(t: Any):
    if hasattr(t, 'py_type'):  # issubclass(t, _TypeBase)
        t = t.py_type
    return is_proto_type(t) or t in {float, bytes}


def serialize_value(value: Any) -> Any:
    if hasattr(value, 'to_dict'):
        return value.to_dict()  # type: ignore
    elif isinstance(value, float):
        return None if math.isnan(value) else ('-Inf' if value < 0 else 'Inf') if math.isinf(value) else value
    elif isinstance(value, (bytearray, bytes)):
        return list(value)
    elif isinstance(value, enum.IntEnum):
        return value.name
    elif isinstance(value, list):
        return [serialize_value(v) for v in value]  # type: ignore
    else:
        return value


def process_type_annotation(type_obj: type[Any], qualname, field_name: str = 'unnamed') -> tuple[type, bool, bool, bool]:
    type_is_optional = False
    type_is_repeated = False
    type_is_mapping = False

    if origin := get_origin(type_obj):
        if origin is Union:
            args = get_args(type_obj)
            if len(args) == 2 and type(None) in args:
                type_is_optional = True
                type_obj = next(arg for arg in args if arg is not type(None))
                inner_type, _, inner_type_repeated, inner_type_mapping = process_type_annotation(type_obj, field_name)
                return inner_type, type_is_optional, inner_type_repeated, inner_type_mapping
            else:
                msg = 'Union types with more than 2 elements are not supported, and Optional types must be expressed as `type | None`'
                raise TypeError(msg)

        elif issubclass(origin, RepeatedType):  # type: ignore
            type_is_repeated = True
            type_is_optional = True
            args = get_args(type_obj)
            if args:
                type_obj = args[0]
            else:
                msg = f'list | tuple type must have type argument, got {type_obj}'
                raise TypeError(msg)

        elif issubclass(origin, Mapping):
            type_is_repeated = True
            type_is_mapping = True
            type_is_optional = True
            args = get_args(type_obj)
            if args:
                if len(args) < 2:
                    msg = f'`Mapping` type must have 2 type arguments, got {len(args)}'
                    raise TypeError(msg)
                key_t, value_t = args

                if is_type_invalid_in_proto3_mapping_key(key_t):
                    warnings.warn(
                        f'illegal key type {key_t} in Mapping. Note: Although this works in python, it will generate invalid proto3',
                        RuntimeWarning,
                        stacklevel=4,
                    )

                class _MapEntry(BaseMessage):
                    __qualname__ = f'{qualname}._MapEntry'

                    key: key_t = Field(1)  # type: ignore
                    value: value_t = Field(2)  # type: ignore

                    def __iter__(self):
                        return iter((self.key, self.value))  # type: ignore

                    @classmethod
                    def type_str(cls):
                        return f'{type_str(cls.key.type)}, {type_str(cls.value.type)}'  # type: ignore

                return _MapEntry, type_is_optional, type_is_repeated, type_is_mapping

            else:
                msg = f'`Mapping` type must have type argument, got {type_obj}'
                raise TypeError(msg)

    return type_obj, type_is_optional, type_is_repeated, type_is_mapping


def parse_value_of_type(type_obj: Any, value: Any) -> Any:  # noqa: PLR0911
    if type_obj is int:
        return int(value) if isinstance(value, str) else value

    elif type_obj is float:
        return float('nan') if value is None else float(value) if isinstance(value, str) else value

    elif type_obj is bytes:
        return value.encode() if isinstance(value, str) else bytes(value) if isinstance(value, list) else value

    elif type_obj is bytearray:
        return bytearray(value.encode()) if isinstance(value, str) else bytearray(value) if isinstance(value, list) else value

    elif issubclass(type_obj, BaseMessage):
        if isinstance(value, type_obj):
            return value

        return type_obj.from_dict(value)

    elif issubclass(type_obj, enum.IntEnum):
        return (type_obj(int(value)) if value.isdecimal() else type_obj[value]) if type(value) is str else type_obj(value)

    return value
