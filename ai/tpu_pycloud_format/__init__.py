"""The wire format of a cloud task and of its answer.

What goes into a message body - tensors or a path to a pickled sample, metadata, the
worker's report - and which headers travel beside it. Nothing here knows about the
broker: how a message gets to the worker and back is tpu_pycloud_connection's business,
and a client that speaks to the cloud through any other transport needs only this.
"""

__all__ = [
    'PyTask',
    'serialize',
    'deserialize',
    'MESSAGE_ID_ATTR_NAME',
    'RESPONSE_ROUTING_KEYS_ATTR_NAME',
    'TARGET_URI_ATTR_NAME',
]

from ._io import PyTask
from ._io import deserialize
from ._io import serialize
from .headers import MESSAGE_ID_ATTR_NAME
from .headers import RESPONSE_ROUTING_KEYS_ATTR_NAME
from .headers import TARGET_URI_ATTR_NAME
