"""Names of the message headers every party reads.

The body says what to compute; these say what to compute it with, where to send the
answer and how the sender tells answers apart. They ride as AMQP headers so the worker
can route and answer without parsing the body.
"""

#: the program to run, as a URI (``file:///auto/.../net.tpu?raw=False``)
TARGET_URI_ATTR_NAME = 'uri'

#: JSON list of routing keys the answer travels through, last hop first: the worker
#: pops the last one and sends there, a postprocessing server pops the next, and what
#: remains at the end is the client's own queue
RESPONSE_ROUTING_KEYS_ATTR_NAME = 'response_routing_keys'

#: the sender's own id of the task, echoed back untouched
MESSAGE_ID_ATTR_NAME = 'tpu_pycloud_message_id'
