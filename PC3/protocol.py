"""
Módulo de protocolo de comunicación
Patrón: Facade - Simplifica la interfaz de comunicación
"""
import json
import struct
import socket
from typing import Dict, Optional


class ProtocolHandler:
    """
    Maneja el protocolo de comunicación (length-prefixed JSON)
    Patrón: Facade - Simplifica el envío/recepción de mensajes
    """
    
    @staticmethod
    def send_json(sock: socket.socket, payload: Dict) -> None:
        """Envía un mensaje JSON con prefijo de longitud"""
        data = json.dumps(payload).encode('utf-8')
        header = struct.pack('!I', len(data))
        sock.sendall(header + data)
    
    @staticmethod
    def recv_json(sock: socket.socket) -> Optional[Dict]:
        """Recibe un mensaje JSON con prefijo de longitud"""
        try:
            header = ProtocolHandler._recv_exact(sock, 4)
            if not header:
                raise ConnectionError('Connection closed')
            (length,) = struct.unpack('!I', header)
            data = ProtocolHandler._recv_exact(sock, length)
            if not data:
                raise ConnectionError('Connection closed while receiving')
            return json.loads(data.decode('utf-8'))
        except (json.JSONDecodeError, struct.error, ConnectionError) as e:
            raise ConnectionError(f'Protocol error: {e}')
    
    @staticmethod
    def _recv_exact(sock: socket.socket, nbytes: int) -> bytes:
        """Recibe exactamente nbytes del socket"""
        buf = bytearray()
        while len(buf) < nbytes:
            chunk = sock.recv(nbytes - len(buf))
            if not chunk:
                return b''
            buf.extend(chunk)
        return bytes(buf)

