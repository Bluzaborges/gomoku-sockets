import json
import struct


HEADER_SIZE = 4


def send_message(connection, message):
    payload = json.dumps(message).encode("utf-8")
    header = struct.pack("!I", len(payload))
    connection.sendall(header + payload)


def receive_message(connection):
    header = _receive_exactly(connection, HEADER_SIZE)
    if header is None:
        return None

    payload_size = struct.unpack("!I", header)[0]
    payload = _receive_exactly(connection, payload_size)
    if payload is None:
        return None

    return json.loads(payload.decode("utf-8"))


def _receive_exactly(connection, size):
    data = bytearray()

    while len(data) < size:
        chunk = connection.recv(size - len(data))
        if not chunk:
            return None

        data.extend(chunk)

    return bytes(data)
