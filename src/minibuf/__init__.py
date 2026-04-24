"""
MiniBuf

Toy protocol buffers implementation on python (and for python) without dependencies.

Reference: https://protobuf.dev/

"""

from . import types
from .common import field
from .message import BaseMessage

__all__ = ['BaseMessage', 'field']
