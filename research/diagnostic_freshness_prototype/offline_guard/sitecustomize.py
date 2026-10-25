"""Best-effort Python network guard for disposable research CI.

Loaded by Python at startup through PYTHONPATH. Not an OS sandbox.
"""
import socket

def _blocked(*args, **kwargs):
    raise OSError("Network access disabled for V9.5 research regression")

socket.socket.connect = _blocked
socket.socket.connect_ex = _blocked
socket.socket.bind = _blocked
socket.socket.listen = _blocked
socket.create_connection = _blocked
socket.getaddrinfo = _blocked
