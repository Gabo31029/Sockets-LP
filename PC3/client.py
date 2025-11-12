import os
import sys
import cv2
import socket
import threading
import argparse
import json
import struct
import time
import numpy as np
from typing import Optional, Dict

CHAT_HOST = '127.0.0.1'
CHAT_PORT = 9009
FILE_HOST = '127.0.0.1'
FILE_PORT = 9010
MEDIA_HOST = '127.0.0.1'
MEDIA_PORT = 9020  # UDP video relay

DOWNLOADS_DIR = os.path.join(os.path.dirname(__file__), 'downloads')
os.makedirs(DOWNLOADS_DIR, exist_ok=True)

# -------------------- Helpers --------------------

def send_json(sock: socket.socket, payload: dict) -> None:
    data = json.dumps(payload).encode('utf-8')
    header = struct.pack('!I', len(data))
    sock.sendall(header + data)


def recv_json(sock: socket.socket) -> dict:
    header = _recv_exact(sock, 4)
    if not header:
        raise ConnectionError('Server disconnected')
    (length,) = struct.unpack('!I', header)
    data = _recv_exact(sock, length)
    if not data:
        raise ConnectionError('Server disconnected while receiving payload')
    return json.loads(data.decode('utf-8'))


def _recv_exact(sock: socket.socket, nbytes: int) -> bytes:
    buf = bytearray()
    while len(buf) < nbytes:
        chunk = sock.recv(nbytes - len(buf))
        if not chunk:
            return b''
        buf.extend(chunk)
    return bytes(buf)

# -------------------- Chat Client --------------------

class ChatClient:
    def __init__(self, host: str, port: int, username: str) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.sock: Optional[socket.socket] = None
        self.running = False

    def connect(self) -> bool:
        try:
            # Validar que el host no esté vacío
            if not self.host or self.host.strip() == '':
                print('[ERROR] El host no puede estar vacío. Usa --host IP_DEL_SERVIDOR')
                return False
            
            # Intentar resolver el host
            try:
                socket.gethostbyname(self.host)
            except socket.gaierror as e:
                print(f'[ERROR] No se pudo resolver el host "{self.host}": {e}')
                print(f'[AYUDA] Verifica que la IP sea correcta. Ejemplo: --host 192.168.1.100')
                return False
            
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(5)  # Timeout de 5 segundos
            print(f'[CLIENTE] Intentando conectar a {self.host}:{self.port}...')
            self.sock.connect((self.host, self.port))
            self.sock.settimeout(None)  # Quitar timeout después de conectar
            send_json(self.sock, {'name': self.username})
            self.running = True
            threading.Thread(target=self._recv_loop, daemon=True).start()
            return True
        except socket.timeout:
            print(f'[ERROR] Timeout: No se pudo conectar a {self.host}:{self.port}')
            print(f'[AYUDA] Verifica que:')
            print(f'  1. El servidor esté ejecutándose')
            print(f'  2. La IP sea correcta: {self.host}')
            print(f'  3. El firewall permita conexiones en el puerto {self.port}')
            return False
        except ConnectionRefusedError:
            print(f'[ERROR] Conexión rechazada en {self.host}:{self.port}')
            print(f'[AYUDA] Verifica que:')
            print(f'  1. El servidor esté ejecutándose')
            print(f'  2. El firewall permita conexiones en el puerto {self.port}')
            print(f'  3. Ejecuta configurar_firewall.ps1 en el servidor')
            return False
        except Exception as e:
            error_msg = str(e)
            if 'getaddrinfo failed' in error_msg or '11001' in error_msg:
                print(f'[ERROR] No se pudo resolver el host "{self.host}"')
                print(f'[AYUDA] Verifica que:')
                print(f'  1. La IP sea correcta (ejemplo: 192.168.1.100)')
                print(f'  2. No uses "IP_DEL_SERVIDOR" literalmente, usa la IP real')
                print(f'  3. El servidor muestre la IP al iniciar')
            else:
                print(f'[ERROR] No se pudo conectar al servidor: {e}')
            return False

    def _recv_loop(self) -> None:
        while self.running:
            try:
                msg = recv_json(self.sock)
                mtype = msg.get('type')
                if mtype == 'message':
                    print(f'[{msg.get("from", "unknown")}]: {msg.get("text", "")}')
                elif mtype == 'system':
                    print(f'[SISTEMA]: {msg.get("text", "")}')
                elif mtype == 'file_available':
                    print(f'[ARCHIVO] {msg.get("from")} compartió: {msg.get("filename")} (ID: {msg.get("file_id")})')
                elif mtype == 'call':
                    action = msg.get('action')
                    from_user = msg.get('from')
                    if action == 'start':
                        print(f'[LLAMADA] {from_user} inició una videollamada')
                    elif action == 'stop':
                        print(f'[LLAMADA] {from_user} terminó la videollamada')
            except Exception:
                if self.running:
                    print('[ERROR] Conexión perdida con el servidor')
                break

    def send_message(self, text: str) -> None:
        if self.sock:
            try:
                send_json(self.sock, {'type': 'message', 'text': text})
            except Exception as e:
                print(f'[ERROR] No se pudo enviar el mensaje: {e}')

    def notify_file_available(self, filename: str, size: int, file_id: str) -> None:
        if self.sock:
            try:
                send_json(self.sock, {
                    'type': 'file_available',
                    'filename': filename,
                    'size': size,
                    'file_id': file_id
                })
            except Exception as e:
                print(f'[ERROR] No se pudo notificar archivo: {e}')

    def send_call_action(self, action: str) -> None:
        if self.sock:
            try:
                send_json(self.sock, {'type': 'call', 'action': action})
            except Exception as e:
                print(f'[ERROR] No se pudo enviar acción de llamada: {e}')

    def disconnect(self) -> None:
        self.running = False
        if self.sock:
            try:
                send_json(self.sock, {'type': 'quit'})
                self.sock.close()
            except Exception:
                pass

# -------------------- File Client --------------------

class FileClient:
    @staticmethod
    def upload_file(host: str, port: int, filepath: str) -> Optional[str]:
        """Upload a file and return its file_id"""
        try:
            if not os.path.exists(filepath):
                print(f'[ERROR] Archivo no encontrado: {filepath}')
                return None
            filename = os.path.basename(filepath)
            size = os.path.getsize(filepath)
            file_id = f'{int(time.time() * 1000)}_{filename}'
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((host, port))
            send_json(sock, {
                'type': 'upload',
                'file_id': file_id,
                'filename': filename,
                'size': size
            })
            with open(filepath, 'rb') as f:
                while True:
                    chunk = f.read(64 * 1024)
                    if not chunk:
                        break
                    sock.sendall(chunk)
            resp = recv_json(sock)
            sock.close()
            if resp.get('type') == 'upload_ok':
                print(f'[ARCHIVO] Subido exitosamente: {filename}')
                return file_id
            else:
                print(f'[ERROR] Error al subir archivo: {resp.get("message", "unknown")}')
                return None
        except Exception as e:
            print(f'[ERROR] Error al subir archivo: {e}')
            return None

    @staticmethod
    def download_file(host: str, port: int, file_id: str) -> bool:
        """Download a file by file_id"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((host, port))
            send_json(sock, {'type': 'download', 'file_id': file_id})
            resp = recv_json(sock)
            if resp.get('type') == 'error':
                print(f'[ERROR] {resp.get("message", "unknown error")}')
                sock.close()
                return False
            filename = resp.get('filename', 'unknown')
            size = int(resp.get('size', 0))
            dest_path = os.path.join(DOWNLOADS_DIR, filename)
            remaining = size
            with open(dest_path, 'wb') as f:
                while remaining > 0:
                    chunk = sock.recv(min(64 * 1024, remaining))
                    if not chunk:
                        raise ConnectionError('Download interrupted')
                    f.write(chunk)
                    remaining -= len(chunk)
            sock.close()
            print(f'[ARCHIVO] Descargado exitosamente: {filename} -> {dest_path}')
            return True
        except Exception as e:
            print(f'[ERROR] Error al descargar archivo: {e}')
            return False

# -------------------- Video Client --------------------

class VideoClient:
    def __init__(self, host: str, port: int, room_id: int, client_id: int, on_stop_callback=None) -> None:
        self.host = host
        self.port = port
        self.room_id = room_id
        self.client_id = client_id
        self.sock: Optional[socket.socket] = None
        self.running = False
        self.cap: Optional[cv2.VideoCapture] = None
        self.remote_frames: Dict[int, np.ndarray] = {}
        self.local_frame: Optional[np.ndarray] = None
        self.frames_lock = threading.Lock()
        self.on_stop_callback = on_stop_callback

    def start(self) -> bool:
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.settimeout(0.1)  # Timeout para no bloquear indefinidamente
            self.cap = cv2.VideoCapture(0)
            if not self.cap.isOpened():
                print('[ERROR] No se pudo abrir la cámara')
                return False
            self.running = True
            threading.Thread(target=self._send_loop, daemon=True).start()
            threading.Thread(target=self._recv_loop, daemon=True).start()
            threading.Thread(target=self._display_loop, daemon=True).start()
            print('[VIDEO] Cámara iniciada, enviando video...')
            return True
        except Exception as e:
            print(f'[ERROR] Error al iniciar video: {e}')
            return False

    def _send_loop(self) -> None:
        while self.running and self.cap and self.sock:
            try:
                ret, frame = self.cap.read()
                if not ret:
                    break
                # Resize frame for lower bandwidth
                frame = cv2.resize(frame, (320, 240))
                # Guardar frame local para mostrar
                with self.frames_lock:
                    self.local_frame = frame.copy()
                _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                packet = struct.pack('!II', self.room_id, self.client_id) + buffer.tobytes()
                self.sock.sendto(packet, (self.host, self.port))
                time.sleep(0.033)  # ~30 FPS
            except Exception as e:
                if self.running:
                    print(f'[VIDEO] Error en envío: {e}')
                break

    def _recv_loop(self) -> None:
        while self.running and self.sock:
            try:
                data, _ = self.sock.recvfrom(65536)
                if len(data) < 8:
                    continue
                room_id = struct.unpack('!I', data[0:4])[0]
                sender_id = struct.unpack('!I', data[4:8])[0]
                if room_id != self.room_id or sender_id == self.client_id:
                    continue
                frame_data = data[8:]
                frame = cv2.imdecode(np.frombuffer(frame_data, np.uint8), cv2.IMREAD_COLOR)
                if frame is not None:
                    with self.frames_lock:
                        self.remote_frames[sender_id] = frame
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f'[VIDEO] Error en recepción: {e}')
                break

    def _display_loop(self) -> None:
        """Loop separado para mostrar las ventanas de video"""
        while self.running:
            try:
                # Mostrar video local
                with self.frames_lock:
                    if self.local_frame is not None:
                        local_display = self.local_frame.copy()
                        cv2.putText(local_display, 'TU VIDEO', (10, 30), 
                                  cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                        cv2.imshow('Mi Video', local_display)
                    
                    # Mostrar videos remotos
                    for sender_id, frame in self.remote_frames.items():
                        cv2.imshow(f'Video - Cliente {sender_id}', frame)
                
                # waitKey es necesario para actualizar las ventanas
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    print('[VIDEO] Presionaste "q" para salir de la videollamada')
                    self.stop()
                    if self.on_stop_callback:
                        self.on_stop_callback()
                    break
                time.sleep(0.033)  # ~30 FPS
            except Exception as e:
                if self.running:
                    print(f'[VIDEO] Error en display: {e}')
                break

    def stop(self) -> None:
        self.running = False
        if self.cap:
            self.cap.release()
        if self.sock:
            self.sock.close()
        cv2.destroyAllWindows()
        print('[VIDEO] Videollamada detenida')

# -------------------- Main --------------------

def main() -> None:
    parser = argparse.ArgumentParser(description='Cliente de chat con archivos y video')
    parser.add_argument('--name', type=str, default='Usuario', help='Nombre de usuario')
    parser.add_argument('--host', type=str, default=CHAT_HOST, help='Host del servidor')
    args = parser.parse_args()

    chat = ChatClient(args.host, CHAT_PORT, args.name)
    if not chat.connect():
        return

    print(f'[CLIENTE] Conectado como {args.name}')
    print('[AYUDA] Comandos:')
    print('  - Escribe un mensaje para enviarlo al chat')
    print('  - /upload <ruta_archivo> - Subir un archivo')
    print('  - /download <file_id> - Descargar un archivo')
    print('  - /call start - Iniciar videollamada')
    print('  - /call stop - Terminar videollamada')
    print('  - /quit - Salir')

    video_client: Optional[VideoClient] = None
    room_id = 1
    client_id = int(time.time() * 1000) % 1000000

    try:
        while True:
            try:
                line = input().strip()
                if not line:
                    continue
                if line == '/quit':
                    break
                elif line.startswith('/upload '):
                    filepath = line[8:].strip()
                    file_id = FileClient.upload_file(args.host, FILE_PORT, filepath)
                    if file_id:
                        filename = os.path.basename(filepath)
                        size = os.path.getsize(filepath)
                        chat.notify_file_available(filename, size, file_id)
                elif line.startswith('/download '):
                    file_id = line[10:].strip()
                    FileClient.download_file(args.host, FILE_PORT, file_id)
                elif line == '/call start':
                    if video_client is None:
                        # Usar una lista para poder modificar desde la callback
                        video_client_ref = [None]
                        def stop_callback():
                            nonlocal video_client
                            chat.send_call_action('stop')
                            video_client = None
                            video_client_ref[0] = None
                            print('[VIDEO] Notificando a otros usuarios que terminaste la videollamada')
                        video_client = VideoClient(args.host, MEDIA_PORT, room_id, client_id, stop_callback)
                        video_client_ref[0] = video_client
                        if video_client.start():
                            chat.send_call_action('start')
                            print('[VIDEO] Videollamada iniciada. Presiona "q" en la ventana de video para terminar.')
                        else:
                            video_client = None
                            video_client_ref[0] = None
                    else:
                        print('[VIDEO] La videollamada ya está activa')
                elif line == '/call stop':
                    if video_client:
                        video_client.stop()
                        video_client = None
                        chat.send_call_action('stop')
                        print('[VIDEO] Videollamada terminada')
                    else:
                        print('[VIDEO] No hay videollamada activa')
                else:
                    chat.send_message(line)
            except EOFError:
                break
            except KeyboardInterrupt:
                break
    finally:
        if video_client:
            video_client.stop()
        chat.disconnect()
        print('[CLIENTE] Desconectado')


if __name__ == '__main__':
    main()

