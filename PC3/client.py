"""
Cliente de chat con soporte para mensajes, archivos y videollamadas
Patrón: Facade - Simplifica la interfaz del cliente
"""
import os
import sys
import cv2
import socket
import threading
import argparse
import struct
import time
import numpy as np
import getpass
from typing import Optional, Dict, Tuple, Callable
from tkinter import filedialog
import tkinter as tk
from protocol import ProtocolHandler

# Configuración
CHAT_HOST = '127.0.0.1'
CHAT_PORT = 9009
FILE_HOST = '127.0.0.1'
FILE_PORT = 9010
MEDIA_HOST = '127.0.0.1'
MEDIA_PORT = 9020

DOWNLOADS_DIR = os.path.join(os.path.dirname(__file__), 'downloads')
os.makedirs(DOWNLOADS_DIR, exist_ok=True)

# -------------------- Chat Client --------------------

class ChatClient:
    def __init__(self, host: str, port: int, username: str) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.sock: Optional[socket.socket] = None
        self.running = False

    def authenticate(self, auth_type: str, username: str, password: str) -> Tuple[bool, str]:
        """
        Autentica al usuario (login o register)
        Patrón: Strategy - Diferentes estrategias de autenticación
        """
        try:
            ProtocolHandler.send_json(self.sock, {
                'type': auth_type,
                'username': username,
                'password': password
            })
            response = ProtocolHandler.recv_json(self.sock)
            if response.get('type') == 'auth_response':
                success = response.get('success', False)
                message = response.get('message', '')
                if success:
                    success_msg = ProtocolHandler.recv_json(self.sock)
                    if success_msg.get('type') == 'auth_success':
                        self.username = success_msg.get('username', username)
                return success, message
            return False, 'Respuesta inválida del servidor'
        except Exception as e:
            return False, f'Error de autenticación: {e}'
    
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
        """
        Loop de recepción de mensajes
        Patrón: Observer - Observa y reacciona a mensajes del servidor
        """
        while self.running:
            try:
                msg = ProtocolHandler.recv_json(self.sock)
                mtype = msg.get('type')
                
                # Strategy pattern: diferentes handlers para diferentes tipos
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
        """Envía un mensaje de texto"""
        if self.sock:
            try:
                ProtocolHandler.send_json(self.sock, {'type': 'message', 'text': text})
            except Exception as e:
                print(f'[ERROR] No se pudo enviar el mensaje: {e}')

    def notify_file_available(self, filename: str, size: int, file_id: str) -> None:
        """Notifica que un archivo está disponible"""
        if self.sock:
            try:
                ProtocolHandler.send_json(self.sock, {
                    'type': 'file_available',
                    'filename': filename,
                    'size': size,
                    'file_id': file_id
                })
            except Exception as e:
                print(f'[ERROR] No se pudo notificar archivo: {e}')

    def send_call_action(self, action: str) -> None:
        """Envía una acción de videollamada"""
        if self.sock:
            try:
                ProtocolHandler.send_json(self.sock, {'type': 'call', 'action': action})
            except Exception as e:
                print(f'[ERROR] No se pudo enviar acción de llamada: {e}')

    def disconnect(self) -> None:
        """Desconecta del servidor"""
        self.running = False
        if self.sock:
            try:
                ProtocolHandler.send_json(self.sock, {'type': 'quit'})
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
            ProtocolHandler.send_json(sock, {
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
            resp = ProtocolHandler.recv_json(sock)
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
            ProtocolHandler.send_json(sock, {'type': 'download', 'file_id': file_id})
            resp = ProtocolHandler.recv_json(sock)
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
    """
    Cliente de videollamada
    Patrón: Facade - Simplifica el manejo de video
    Patrón: Observer - Callback para notificar eventos
    """
    def __init__(self, host: str, port: int, room_id: int, client_id: int, 
                 on_stop_callback: Optional[Callable] = None) -> None:
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
        """Loop separado para mostrar todos los videos en una sola ventana (grid)"""
        window_name = 'Videollamada Grupal'
        while self.running:
            try:
                with self.frames_lock:
                    # Recopilar todos los frames (local + remotos)
                    all_frames = []
                    
                    # Agregar frame local
                    if self.local_frame is not None:
                        local_display = self.local_frame.copy()
                        cv2.putText(local_display, 'TU VIDEO', (10, 30), 
                                  cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                        all_frames.append(('Local', local_display))
                    
                    # Agregar frames remotos
                    for sender_id, frame in self.remote_frames.items():
                        frame_copy = frame.copy()
                        cv2.putText(frame_copy, f'Usuario {sender_id}', (10, 30), 
                                  cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                        all_frames.append((f'User{sender_id}', frame_copy))
                
                # Crear grid de videos
                if all_frames:
                    frame_height, frame_width = all_frames[0][1].shape[:2]
                    black_frame = np.zeros((frame_height, frame_width, 3), dtype=np.uint8)
                    
                    if len(all_frames) == 1:
                        # Solo un video, mostrarlo completo
                        combined = all_frames[0][1]
                    elif len(all_frames) == 2:
                        # Dos videos, lado a lado
                        combined = np.hstack([all_frames[0][1], all_frames[1][1]])
                    elif len(all_frames) == 3:
                        # Tres videos: 2 arriba, 1 abajo centrado
                        top_row = np.hstack([all_frames[0][1], all_frames[1][1]])
                        bottom_row = np.hstack([black_frame, all_frames[2][1], black_frame])
                        combined = np.vstack([top_row, bottom_row])
                    elif len(all_frames) == 4:
                        # Cuatro videos, grid 2x2
                        top_row = np.hstack([all_frames[0][1], all_frames[1][1]])
                        bottom_row = np.hstack([all_frames[2][1], all_frames[3][1]])
                        combined = np.vstack([top_row, bottom_row])
                    else:
                        # Más de 4 videos, grid 3x3 (máximo 9)
                        rows = []
                        for i in range(0, min(len(all_frames), 9), 3):
                            row_frames = [all_frames[j][1] for j in range(i, min(i+3, len(all_frames)))]
                            while len(row_frames) < 3:
                                row_frames.append(black_frame)
                            rows.append(np.hstack(row_frames))
                        while len(rows) < 3:
                            rows.append(np.hstack([black_frame, black_frame, black_frame]))
                        combined = np.vstack(rows)
                    
                    cv2.imshow(window_name, combined)
                
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

# -------------------- File Selection Helper --------------------

def select_file() -> Optional[str]:
    """
    Abre un diálogo para seleccionar un archivo
    Patrón: Facade - Simplifica el uso de tkinter
    """
    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        
        filepath = filedialog.askopenfilename(
            title="Seleccionar archivo para enviar",
            filetypes=[("Todos los archivos", "*.*")]
        )
        root.destroy()
        return filepath if filepath else None
    except Exception as e:
        print(f'[ERROR] Error al abrir diálogo de archivos: {e}')
        return None

# -------------------- Main --------------------

def main() -> None:
    parser = argparse.ArgumentParser(description='Cliente de chat con archivos y video')
    parser.add_argument('--host', type=str, default=CHAT_HOST, help='Host del servidor')
    args = parser.parse_args()

    # Conectar al servidor
    chat = ChatClient(args.host, CHAT_PORT, '')
    if not chat.connect():
        return

    # Autenticación
    print('\n=== AUTENTICACIÓN ===')
    while True:
        print('1. Login')
        print('2. Register')
        choice = input('Selecciona una opción (1 o 2): ').strip()
        
        username = input('Usuario: ').strip()
        password = getpass.getpass('Contraseña: ')
        
        if choice == '1':
            auth_type = 'login'
        elif choice == '2':
            auth_type = 'register'
        else:
            print('[ERROR] Opción inválida')
            continue
        
        success, message = chat.authenticate(auth_type, username, password)
        print(f'[{auth_type.upper()}] {message}')
        
        if success:
            chat.running = True
            threading.Thread(target=chat._recv_loop, daemon=True).start()
            break
        else:
            retry = input('¿Intentar de nuevo? (s/n): ').strip().lower()
            if retry != 's':
                chat.disconnect()
                return

    print(f'\n[CLIENTE] Conectado como {chat.username}')
    print('\n[AYUDA] Comandos:')
    print('  - Escribe un mensaje para enviarlo al chat')
    print('  - /upload - Abre diálogo para seleccionar y subir un archivo')
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
                elif line == '/upload' or line.startswith('/upload '):
                    # Si hay ruta en el comando, usarla; si no, abrir diálogo
                    if line.startswith('/upload '):
                        filepath = line[8:].strip()
                    else:
                        print('[ARCHIVO] Abriendo diálogo de selección de archivos...')
                        filepath = select_file()
                        if not filepath:
                            print('[ARCHIVO] No se seleccionó ningún archivo')
                            continue
                    
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

