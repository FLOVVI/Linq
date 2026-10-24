import io
import os
from datetime import datetime
from pathlib import Path
from google.protobuf.timestamp_pb2 import Timestamp
import numpy as np
from . import message_pb2
from dataclasses import dataclass
from typing import Mapping, Dict, Any, Optional, Sequence, Union, Tuple


@dataclass(frozen=True)
class PyTask:
    data: Mapping[str, np.ndarray] | os.PathLike

    # this field may contain result of postproc session
    metadata: Optional[Sequence[dict[str, np.ndarray]]] = None

    # these fields are needed for inference data from the worker
    # the client needs the default values of these fields.
    worker_pid: str = ''
    thread_name: str = ''
    inference_opening_timestamp: Optional[datetime] = None
    inference_time: Optional[float] = 0.0
    status_code: Optional[int] = 0
    error_message: str = ''


def serialize(
    pytask: PyTask
) -> bytes:
    tensor_message = message_pb2.Task()

    #
    tensor_message.worker_pid = pytask.worker_pid
    tensor_message.thread_name = pytask.thread_name
    tensor_message.error_message = pytask.error_message
    tensor_message.status_code = pytask.status_code

    if pytask.inference_time:
        tensor_message.inference_time = pytask.inference_time

    #
    if pytask.inference_opening_timestamp:
        ts = Timestamp()
        ts.FromDatetime(pytask.inference_opening_timestamp)
        tensor_message.inference_opening_timestamp.CopyFrom(ts)

    # check
    if isinstance(pytask.data, (str, bytes)):
        raise TypeError(f'PyTask.data got a {type(pytask.data).__name__};'
                        f' pass a mapping of tensors or wrap the path in pathlib.Path')

    #
    if isinstance(pytask.data, os.PathLike):
        tensor_message.data_path = os.fspath(pytask.data)
    else:
        for tensor_name, tensor_data in pytask.data.items():
            array = tensor_message.dict_data[tensor_name]
            array.dtype = tensor_data.dtype.name
            array.shape.extend(tensor_data.shape)
            array.byte_data = tensor_data.tobytes()

    if pytask.metadata is not None:
        for metadata_dct in pytask.metadata:
            metadata_msg = tensor_message.list_metadata.add()
            for key, value in metadata_dct.items():

                # postproc key may be None
                str_key = str(key) if key is None else key

                array = metadata_msg.items[str_key]
                array.dtype = value.dtype.name
                array.shape.extend(value.shape)
                array.byte_data = value.tobytes()

    return tensor_message.SerializeToString()


def deserialize(
    serialized_data: bytes
) -> Tuple[Union[Dict[str, np.ndarray], os.PathLike],
           Tuple[dict[str, np.ndarray], ...],
           Dict[str, Union[str, float, int]]]:

    tensor_message = message_pb2.Task()
    tensor_message.ParseFromString(serialized_data)

    if tensor_message.data_path:
        data = Path(tensor_message.data_path)
    else:
        data = dict()
        for tensor_name, array in dict(tensor_message.dict_data).items():
            with io.BytesIO(array.byte_data) as bytes_stream:
                tensor_data = np.frombuffer(
                    bytes_stream.getvalue(),
                    dtype=array.dtype
                ).reshape(array.shape)
            data[tensor_name] = tensor_data

    ts = tensor_message.inference_opening_timestamp

    #
    metadata = list()
    for metadata_msg in tensor_message.list_metadata:
        metadata_dict = {}
        for key, array in metadata_msg.items.items():

            with io.BytesIO(array.byte_data) as bytes_stream:
                tensor_data = np.frombuffer(bytes_stream.getvalue(), dtype=array.dtype).reshape(array.shape)

            # reverse postproc key may be None
            metadata_dict[None if key == 'None' else key] = tensor_data

        metadata.append(metadata_dict)

    #
    worker_data = {
        'worker_pid': tensor_message.worker_pid,
        'thread_name': tensor_message.thread_name,
        'inference_time': tensor_message.inference_time,
        'status_code': tensor_message.status_code,
        'error_message': tensor_message.error_message,
        'inference_opening_timestamp': ts.ToSeconds(),
    }

    return data, tuple(metadata), worker_data
