import os
import socket
import threading
import json
import struct
from typing import Dict, List, Tuple

CHAT_HOST = '0.0.0.0'
CHAT_PORT = 9009
FILE_HOST = '0.0.0.0'
FILE_PORT = 9010
MEDIA_HOST = '0.0.0.0'
MEDIA_PORT = 9020  # UDP video relay

SERVER_STORAGE_DIR = os.path.join(os.path.dirname(__file__), 'server_storage')
os.makedirs(SERVER_STORAGE_DIR, exist_ok=True)

# -------------------- Helpers (length-prefixed JSON/text) --------------------

def send_json(sock: socket.socket, payload: dict) -> None:
    data = json.dumps(payload).encode('utf-8')
    header = struct.pack('!I', len(data))
    sock.sendall(header + data)


def recv_json(sock: socket.socket) -> dict:
    header = _recv_exact(sock, 4)
    if not header:
        raise ConnectionError('Client disconnected')
    (length,) = struct.unpack('!I', header)
    data = _recv_exact(sock, length)
    if not data:
        raise ConnectionError('Client disconnected while receiving payload')
    return json.loads(data.decode('utf-8'))


def _recv_exact(sock: socket.socket, nbytes: int) -> bytes:
    buf = bytearray()
    while len(buf) < nbytes:
        chunk = sock.recv(nbytes - len(buf))
        if not chunk:
            return b''
        buf.extend(chunk)
    return bytes(buf)

# -------------------- Chat Server --------------------

class ChatServer:
    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.clients_lock = threading.Lock()
        self.clients: Dict[socket.socket, str] = {}

    def start(self) -> None:
        self.server_sock.bind((self.host, self.port))
        self.server_sock.listen()
        print(f'[CHAT] Listening on {self.host}:{self.port}')
        threading.Thread(target=self._accept_loop, daemon=True).start()

    def _accept_loop(self) -> None:
        while True:
            client_sock, addr = self.server_sock.accept()
            threading.Thread(target=self._handle_client, args=(client_sock, addr), daemon=True).start()

    def _handle_client(self, client_sock: socket.socket, addr: Tuple[str, int]) -> None:
        try:
            hello = recv_json(client_sock)
            username = hello.get('name') or f'user_{addr[1]}'
            with self.clients_lock:
                self.clients[client_sock] = username
            print(f'[CHAT] {username} connected from {addr}')
            self._broadcast({
                'type': 'system',
                'text': f'{username} se unió al chat',
            })

            while True:
                msg = recv_json(client_sock)
                mtype = msg.get('type')
                if mtype == 'message':
                    self._broadcast({'type': 'message', 'from': username, 'text': msg.get('text', '')})
                elif mtype == 'file_available':
                    # Notify clients a file is ready to download
                    self._broadcast({
                        'type': 'file_available',
                        'from': username,
                        'filename': msg.get('filename'),
                        'size': msg.get('size'),
                        'file_id': msg.get('file_id'),
                    })
                elif mtype == 'call':
                    # Simple call signaling: start/stop video call
                    action = msg.get('action')
                    self._broadcast({'type': 'call', 'from': username, 'action': action})
                elif mtype == 'quit':
                    break
                else:
                    # Ignore unknowns
                    pass
        except Exception as e:
            # print(f'[CHAT] Error with {addr}: {e}')
            pass
        finally:
            with self.clients_lock:
                username = self.clients.pop(client_sock, 'alguien')
            try:
                client_sock.close()
            except Exception:
                pass
            print(f'[CHAT] {username} disconnected')
            self._broadcast({'type': 'system', 'text': f'{username} salió del chat'})

    def _broadcast(self, payload: dict) -> None:
        with self.clients_lock:
            dead: List[socket.socket] = []
            for cs in self.clients.keys():
                try:
                    send_json(cs, payload)
                except Exception:
                    dead.append(cs)
            for cs in dead:
                self.clients.pop(cs, None)
                try:
                    cs.close()
                except Exception:
                    pass

# -------------------- File Server --------------------

class FileServer:
    """
    Receives files from clients and stores them on disk. Notifies via ChatServer (caller should forward
    a file_available message). Also serves file downloads to clients upon request.
    Protocol (length-prefixed JSON control + raw bytes for upload):
    - For upload: {type: 'upload', file_id, filename, size}
      followed by exactly 'size' bytes of content.
    - For download: {type: 'download', file_id}
      Server replies {type: 'download_meta', filename, size} then streams raw bytes.
    """
    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.file_index_lock = threading.Lock()
        # file_id -> (path, filename, size)
        self.file_index: Dict[str, Tuple[str, str, int]] = {}

    def start(self) -> None:
        self.server_sock.bind((self.host, self.port))
        self.server_sock.listen()
        print(f'[FILE] Listening on {self.host}:{self.port}')
        threading.Thread(target=self._accept_loop, daemon=True).start()

    def _accept_loop(self) -> None:
        while True:
            client_sock, addr = self.server_sock.accept()
            threading.Thread(target=self._handle_client, args=(client_sock, addr), daemon=True).start()

    def _handle_client(self, client_sock: socket.socket, addr: Tuple[str, int]) -> None:
        try:
            req = recv_json(client_sock)
            rtype = req.get('type')
            if rtype == 'upload':
                file_id = req['file_id']
                filename = os.path.basename(req['filename'])
                size = int(req['size'])
                dest_path = os.path.join(SERVER_STORAGE_DIR, f'{file_id}__{filename}')
                remaining = size
                with open(dest_path, 'wb') as f:
                    while remaining > 0:
                        chunk = client_sock.recv(min(64 * 1024, remaining))
                        if not chunk:
                            raise ConnectionError('Upload interrupted')
                        f.write(chunk)
                        remaining -= len(chunk)
                with self.file_index_lock:
                    self.file_index[file_id] = (dest_path, filename, size)
                send_json(client_sock, {'type': 'upload_ok'})
            elif rtype == 'download':
                file_id = req['file_id']
                with self.file_index_lock:
                    if file_id not in self.file_index:
                        send_json(client_sock, {'type': 'error', 'message': 'file not found'})
                        return
                    path, filename, size = self.file_index[file_id]
                send_json(client_sock, {'type': 'download_meta', 'filename': filename, 'size': size})
                with open(path, 'rb') as f:
                    while True:
                        data = f.read(64 * 1024)
                        if not data:
                            break
                        client_sock.sendall(data)
            else:
                send_json(client_sock, {'type': 'error', 'message': 'unknown request'})
        except Exception as e:
            # print(f'[FILE] Error with {addr}: {e}')
            try:
                send_json(client_sock, {'type': 'error', 'message': 'server error'})
            except Exception:
                pass
        finally:
            try:
                client_sock.close()
            except Exception:
                pass

# -------------------- Media (UDP) Video Relay --------------------

class UdpVideoRelay:
    """
    Minimal UDP relay: receives packets and forwards to all other participants in the room.
    Packet format (binary): room(4 bytes int) | sender(4 bytes int) | payload (JPEG chunk)
    The client handles frame reassembly based on JPEG decoding of received datagrams (small frames recommended).
    """
    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.rooms_lock = threading.Lock()
        # room_id -> set of (addr)
        self.rooms: Dict[int, set] = {}

    def start(self) -> None:
        self.sock.bind((self.host, self.port))
        print(f'[MEDIA] UDP relay on {self.host}:{self.port}')
        threading.Thread(target=self._recv_loop, daemon=True).start()

    def _recv_loop(self) -> None:
        while True:
            try:
                data, addr = self.sock.recvfrom(65536)
                if len(data) < 8:
                    continue
                room_id = struct.unpack('!I', data[0:4])[0]
                sender_id = struct.unpack('!I', data[4:8])[0]
                with self.rooms_lock:
                    if room_id not in self.rooms:
                        self.rooms[room_id] = set()
                    self.rooms[room_id].add(addr)
                    dests = [a for a in self.rooms[room_id] if a != addr]
                for d in dests:
                    try:
                        self.sock.sendto(data, d)
                    except Exception:
                        pass
            except Exception:
                pass

# -------------------- Main --------------------

def get_local_ip() -> str:
    """Obtiene la IP local de la máquina"""
    try:
        # Conectar a un servidor externo para obtener la IP local
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def main() -> None:
    chat = ChatServer(CHAT_HOST, CHAT_PORT)
    files = FileServer(FILE_HOST, FILE_PORT)
    media = UdpVideoRelay(MEDIA_HOST, MEDIA_PORT)
    chat.start()
    files.start()
    media.start()
    
    local_ip = get_local_ip()
    print('[SERVER] All services started. Press Ctrl+C to stop.')
    print(f'[SERVER] Para conectarte desde otra máquina, usa esta IP: {local_ip}')
    print(f'[SERVER] Ejemplo: python client.py --name TuNombre --host {local_ip}')
    print(f'[SERVER] Asegúrate de permitir estos puertos en el firewall:')
    print(f'[SERVER]   - TCP {CHAT_PORT} (Chat)')
    print(f'[SERVER]   - TCP {FILE_PORT} (Archivos)')
    print(f'[SERVER]   - UDP {MEDIA_PORT} (Video)')
    
    try:
        while True:
            threading.Event().wait(3600)
    except KeyboardInterrupt:
        print('\n[SERVER] Shutting down...')


if __name__ == '__main__':
    main()
