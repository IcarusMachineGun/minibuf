# ruff: noqa: N801


class TypeMeta(type):
    def __str__(cls) -> str:
        return f'{cls.__name__}'


class TypeBase(metaclass=TypeMeta): ...


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


class double(float, TypeBase): ...
