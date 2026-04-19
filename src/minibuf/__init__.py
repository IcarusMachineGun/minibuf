"""
MiniBuf

Toy protocol buffers implementation on python (and for python) without dependencies.

Reference: https://protobuf.dev/

"""

from .common import double, field, fixed32, fixed64, int32, int64, sfixed32, sfixed64, sint32, sint64, uint32, uint64
from .message import BaseMessage

# import sys
# from .logger import logger
# logger.info(f"System byte order: {sys.byteorder!r}")

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
