"""
MiniBuf

Toy protocol buffers implementation on python (and for python) without dependencies.

Reference: https://protobuf.dev/

"""

from ._types import double, fixed32, fixed64, int32, int64, sfixed32, sfixed64, sint32, sint64, uint32, uint64
from .common import field
from .message import BaseMessage

__all__ = [
    'BaseMessage',
    'double',
    'field',
    'fixed32',
    'fixed64',
    'int32',
    'int64',
    'sfixed32',
    'sfixed64',
    'sint32',
    'sint64',
    'uint32',
    'uint64',
]
