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
import tempfile
import wave
import numpy as np
import queue
import sounddevice as sd
import getpass
from typing import Optional, Dict, Tuple, Callable
from tkinter import filedialog, messagebox, scrolledtext, ttk
import tkinter as tk
from PIL import Image, ImageTk
from protocol import ProtocolHandler

# Configuración
CHAT_HOST = '127.0.0.1'
CHAT_PORT = 9009
FILE_HOST = '127.0.0.1'
FILE_PORT = 9010
MEDIA_HOST = '127.0.0.1'
MEDIA_PORT = 9020
AUDIO_PORT = 9030

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

    def send_audio_message(self, file_id: str, filename: str, duration: float) -> None:
        """Envía una notificación de mensaje de audio"""
        if self.sock:
            try:
                ProtocolHandler.send_json(self.sock, {
                    'type': 'audio_message',
                    'file_id': file_id,
                    'filename': filename,
                    'duration': duration
                })
            except Exception as e:
                print(f'[ERROR] No se pudo enviar el audio: {e}')

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
    AUDIO_SAMPLE_RATE = 16000
    AUDIO_CHANNELS = 1
    AUDIO_FRAME_DURATION = 0.02  # 20 ms por bloque
    AUDIO_QUEUE_SIZE = 50
    def __init__(self, host: str, port: int, room_id: int, client_id: int, 
                 username: str, on_stop_callback: Optional[Callable] = None,
                 audio_port: Optional[int] = None, 
                 frame_update_callback: Optional[Callable[[np.ndarray], None]] = None) -> None:
        self.host = host
        self.port = port
        self.room_id = room_id
        self.client_id = client_id
        self.username = username
        self.audio_port = audio_port
        self.sock: Optional[socket.socket] = None
        self.audio_sock: Optional[socket.socket] = None
        self.running = False
        self.cap: Optional[cv2.VideoCapture] = None
        self.remote_frames: Dict[int, np.ndarray] = {}  # sender_id -> frame
        self.remote_usernames: Dict[int, str] = {}  # sender_id -> username
        self.local_frame: Optional[np.ndarray] = None
        self.frames_lock = threading.Lock()
        self.on_stop_callback = on_stop_callback
        self.frame_update_callback = frame_update_callback
        self.audio_input_stream: Optional[sd.InputStream] = None
        self.audio_output_stream: Optional[sd.OutputStream] = None
        self.audio_queue: queue.Queue = queue.Queue(maxsize=self.AUDIO_QUEUE_SIZE)
        self.audio_chunk_frames = int(self.AUDIO_SAMPLE_RATE * self.AUDIO_FRAME_DURATION)
        self._username_bytes = self.username.encode('utf-8')

    def start(self) -> bool:
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.settimeout(0.1)  # Timeout para no bloquear indefinidamente
            if self.audio_port:
                self.audio_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self.audio_sock.settimeout(0.1)
            self.cap = cv2.VideoCapture(0)
            if not self.cap.isOpened():
                print('[ERROR] No se pudo abrir la cámara')
                return False
            self.running = True
            threading.Thread(target=self._send_loop, daemon=True).start()
            threading.Thread(target=self._recv_loop, daemon=True).start()
            if self.frame_update_callback:
                threading.Thread(target=self._display_loop, daemon=True).start()
            else:
                # Modo consola (backward compatibility)
                threading.Thread(target=self._display_loop_console, daemon=True).start()
            if self.audio_port and not self._start_audio_components():
                self.stop()
                return False
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
                # Formato del paquete: room_id(4) | client_id(4) | username_len(4) | username(bytes) | frame_data(bytes)
                username_bytes = self.username.encode('utf-8')
                username_len = len(username_bytes)
                packet = (struct.pack('!III', self.room_id, self.client_id, username_len) + 
                         username_bytes + buffer.tobytes())
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
                if len(data) < 12:  # Mínimo: room_id(4) + client_id(4) + username_len(4)
                    continue
                room_id = struct.unpack('!I', data[0:4])[0]
                sender_id = struct.unpack('!I', data[4:8])[0]
                username_len = struct.unpack('!I', data[8:12])[0]
                
                if room_id != self.room_id or sender_id == self.client_id:
                    continue
                
                if len(data) < 12 + username_len:
                    continue
                
                # Extraer username
                username = data[12:12+username_len].decode('utf-8', errors='ignore')
                frame_data = data[12+username_len:]
                
                frame = cv2.imdecode(np.frombuffer(frame_data, np.uint8), cv2.IMREAD_COLOR)
                if frame is not None:
                    with self.frames_lock:
                        self.remote_frames[sender_id] = frame
                        self.remote_usernames[sender_id] = username
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f'[VIDEO] Error en recepción: {e}')
                break

    def _get_combined_frame(self) -> Optional[np.ndarray]:
        """Genera el frame combinado de todos los videos"""
        with self.frames_lock:
            all_frames = []
            
            if self.local_frame is not None:
                local_display = self.local_frame.copy()
                cv2.putText(local_display, 'TU VIDEO', (10, 30), 
                          cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                all_frames.append(('Local', local_display))
            
            for sender_id, frame in self.remote_frames.items():
                frame_copy = frame.copy()
                username = self.remote_usernames.get(sender_id, f'Usuario {sender_id}')
                cv2.putText(frame_copy, username, (10, 30), 
                          cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                all_frames.append((f'User{sender_id}', frame_copy))
        
        if not all_frames:
            return None
        
        STANDARD_HEIGHT = 360
        STANDARD_WIDTH = 640
        
        resized_frames = []
        for name, frame in all_frames:
            resized = cv2.resize(frame, (STANDARD_WIDTH, STANDARD_HEIGHT))
            resized_frames.append((name, resized))
        
        frame_height, frame_width = STANDARD_HEIGHT, STANDARD_WIDTH
        black_frame = np.zeros((frame_height, frame_width, 3), dtype=np.uint8)
        
        if len(resized_frames) == 1:
            combined = resized_frames[0][1]
        elif len(resized_frames) == 2:
            combined = np.hstack([resized_frames[0][1], resized_frames[1][1]])
        elif len(resized_frames) == 3:
            top_row = np.hstack([resized_frames[0][1], resized_frames[1][1]])
            bottom_row = np.hstack([resized_frames[2][1], black_frame])
            combined = np.vstack([top_row, bottom_row])
        elif len(resized_frames) == 4:
            top_row = np.hstack([resized_frames[0][1], resized_frames[1][1]])
            bottom_row = np.hstack([resized_frames[2][1], resized_frames[3][1]])
            combined = np.vstack([top_row, bottom_row])
        else:
            rows = []
            for i in range(0, min(len(resized_frames), 9), 3):
                row_frames = [resized_frames[j][1] for j in range(i, min(i+3, len(resized_frames)))]
                while len(row_frames) < 3:
                    row_frames.append(black_frame)
                rows.append(np.hstack(row_frames))
            while len(rows) < 3:
                rows.append(np.hstack([black_frame, black_frame, black_frame]))
            combined = np.vstack(rows)
        
        return combined

    def _display_loop(self) -> None:
        """Loop para actualizar frame en GUI"""
        while self.running:
            try:
                combined = self._get_combined_frame()
                if combined is not None and self.frame_update_callback:
                    self.frame_update_callback(combined)
                time.sleep(0.033)  # ~30 FPS
            except Exception as e:
                if self.running:
                    print(f'[VIDEO] Error en display: {e}')
                break

    def _display_loop_console(self) -> None:
        """Loop para mostrar video en consola (backward compatibility)"""
        window_name = 'Videollamada Grupal'
        while self.running:
            try:
                combined = self._get_combined_frame()
                if combined is not None:
                    cv2.imshow(window_name, combined)
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

    def _start_audio_components(self) -> bool:
        """Inicializa captura, reproducción y sockets de audio bidireccional"""
        try:
            if not self.audio_sock:
                print('[AUDIO] No se configuró un puerto de audio')
                return False
            self.audio_input_stream = sd.InputStream(
                samplerate=self.AUDIO_SAMPLE_RATE,
                channels=self.AUDIO_CHANNELS,
                dtype='float32',
                blocksize=self.audio_chunk_frames
            )
            self.audio_output_stream = sd.OutputStream(
                samplerate=self.AUDIO_SAMPLE_RATE,
                channels=self.AUDIO_CHANNELS,
                dtype='float32',
                blocksize=self.audio_chunk_frames,
                callback=self._audio_playback_callback
            )
            self.audio_input_stream.start()
            self.audio_output_stream.start()
            threading.Thread(target=self._audio_send_loop, daemon=True).start()
            threading.Thread(target=self._audio_recv_loop, daemon=True).start()
            print('[AUDIO] Captura y reproducción de audio activadas')
            return True
        except Exception as e:
            print(f'[ERROR] No se pudo iniciar el audio: {e}')
            return False

    def _audio_send_loop(self) -> None:
        """Captura audio del micrófono y lo envía por UDP"""
        if not self.audio_input_stream or not self.audio_sock:
            return
        username_len = len(self._username_bytes)
        while self.running:
            try:
                data, overflowed = self.audio_input_stream.read(self.audio_chunk_frames)
                if overflowed:
                    print('[AUDIO] Overflow en captura de audio')
                payload = np.asarray(data, dtype=np.float32).tobytes()
                packet = (
                    struct.pack('!III', self.room_id, self.client_id, username_len) +
                    self._username_bytes +
                    payload
                )
                self.audio_sock.sendto(packet, (self.host, self.audio_port))
            except sd.PortAudioError as e:
                if self.running:
                    print(f'[AUDIO] Error de captura: {e}')
                break
            except Exception as e:
                if self.running:
                    print(f'[AUDIO] Error en envío: {e}')
                break

    def _audio_recv_loop(self) -> None:
        """Recibe audio remoto y lo agrega a la cola de reproducción"""
        if not self.audio_sock:
            return
        while self.running:
            try:
                data, _ = self.audio_sock.recvfrom(32768)
                if len(data) < 12:
                    continue
                room_id = struct.unpack('!I', data[0:4])[0]
                sender_id = struct.unpack('!I', data[4:8])[0]
                username_len = struct.unpack('!I', data[8:12])[0]
                if room_id != self.room_id or sender_id == self.client_id:
                    continue
                if len(data) < 12 + username_len:
                    continue
                audio_bytes = data[12+username_len:]
                if not audio_bytes:
                    continue
                samples = np.frombuffer(audio_bytes, dtype=np.float32)
                if samples.size == 0:
                    continue
                try:
                    samples = samples.reshape((-1, self.AUDIO_CHANNELS))
                except ValueError:
                    continue
                try:
                    self.audio_queue.put_nowait(samples)
                except queue.Full:
                    # Descartar audio si el buffer está lleno para evitar latencia acumulada
                    pass
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f'[AUDIO] Error en recepción: {e}')
                break

    def _audio_playback_callback(self, outdata, frames, _time_info, status) -> None:
        """Callback de reproducción: obtiene audio de la cola y lo envía a los parlantes"""
        if status:
            print(f'[AUDIO] Estado de reproducción: {status}')
        if not self.running:
            outdata.fill(0)
            return
        try:
            chunk = self.audio_queue.get_nowait()
        except queue.Empty:
            outdata.fill(0)
            return
        if chunk.shape[0] < frames:
            pad = np.zeros((frames - chunk.shape[0], self.AUDIO_CHANNELS), dtype=np.float32)
            chunk = np.vstack((chunk, pad))
        elif chunk.shape[0] > frames:
            chunk = chunk[:frames]
        outdata[:] = chunk

    def stop(self) -> None:
        self.running = False
        if self.cap:
            self.cap.release()
        if self.sock:
            self.sock.close()
        if self.audio_sock:
            self.audio_sock.close()
        if self.audio_input_stream:
            try:
                self.audio_input_stream.stop()
                self.audio_input_stream.close()
            except Exception:
                pass
            self.audio_input_stream = None
        if self.audio_output_stream:
            try:
                self.audio_output_stream.stop()
                self.audio_output_stream.close()
            except Exception:
                pass
            self.audio_output_stream = None
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                break
        if not self.frame_update_callback:
            cv2.destroyAllWindows()
        print('[VIDEO] Videollamada detenida')

# -------------------- File Selection Helper --------------------

def select_file(parent=None) -> Optional[str]:
    """
    Abre un diálogo para seleccionar un archivo
    Patrón: Facade - Simplifica el uso de tkinter
    """
    try:
        if parent is None:
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            filepath = filedialog.askopenfilename(
                title="Seleccionar archivo para enviar",
                filetypes=[("Todos los archivos", "*.*")]
            )
            root.destroy()
        else:
            filepath = filedialog.askopenfilename(
                parent=parent,
                title="Seleccionar archivo para enviar",
                filetypes=[("Todos los archivos", "*.*")]
            )
        return filepath if filepath else None
    except Exception as e:
        print(f'[ERROR] Error al abrir diálogo de archivos: {e}')
        return None

# -------------------- GUI Client --------------------

class ChatGUI:
    """
    Interfaz gráfica para el cliente de chat
    Patrón: Facade - Simplifica toda la interfaz del usuario
    """
    
    def __init__(self, host: str):
        self.host = host
        self.chat_client: Optional[ChatClient] = None
        self.video_client: Optional[VideoClient] = None
        self.root = tk.Tk()
        self.root.title("💬 Chat - Cliente")
        self.root.geometry("1200x750")
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Colores del tema
        self.colors = {
            'bg_main': '#2b2b2b',
            'bg_secondary': '#3c3c3c',
            'bg_chat': '#1e1e1e',
            'bg_input': '#2d2d2d',
            'bg_button': '#4a9eff',
            'bg_button_hover': '#5ba8ff',
            'bg_button_active': '#3a8eef',
            'fg_main': '#ffffff',
            'fg_secondary': '#b0b0b0',
            'fg_accent': '#4a9eff',
            'border': '#404040',
            'success': '#4caf50',
            'error': '#f44336',
            'warning': '#ff9800',
            'info': '#2196f3'
        }
        
        # Configurar estilo
        self.root.configure(bg=self.colors['bg_main'])
        
        # Variables
        self.username = ""
        self.room_id = 1
        self.client_id = int(time.time() * 1000) % 1000000
        self.available_files: Dict[str, Dict] = {}  # file_id -> {filename, from_user}
        self._updating_layout = False  # Bandera para evitar recursión
        self.audio_recording = False
        self.audio_record_stream: Optional[sd.InputStream] = None
        self.audio_record_frames: list = []
        self.audio_record_start = 0.0
        self.audio_sample_rate = 16000
        self.audio_channels = 1
        self.audio_messages: Dict[str, Dict] = {}  # file_id -> metadata
        self.audio_message_frames: list = []
        self.audio_playback_thread: Optional[threading.Thread] = None
        
        # Crear interfaz
        self._create_widgets()
        self._main_frame_visible = False
        self.main_frame.pack_forget()
        self.root.attributes('-alpha', 0.0)
        
        # Mostrar diálogo de conexión
        self._show_connection_dialog()
    
    def _create_widgets(self):
        """Crea todos los widgets de la interfaz"""
        # Frame principal con padding
        self.main_frame = tk.Frame(self.root, bg=self.colors['bg_main'], padx=10, pady=10)
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Binding para recalcular proporción cuando se redimensione la ventana
        def on_resize(event=None):
            # Evitar recursión y solo procesar eventos de la ventana principal
            if self._updating_layout or event is None or event.widget != self.root:
                return
            if self.video_client is not None:
                # Si hay videollamada activa, forzar recálculo de proporción 3:1
                # Usar after para evitar múltiples llamadas
                if not hasattr(self, '_resize_scheduled'):
                    self._resize_scheduled = True
                    self.root.after(50, lambda: self._handle_resize())
        
        self.root.bind('<Configure>', on_resize)
        
        # Configurar grid: inicialmente solo chat ocupa todo (sin video)
        self.main_frame.columnconfigure(0, weight=3)  # Video (oculto inicialmente, pero configurado para 75%)
        self.main_frame.columnconfigure(1, weight=1)  # Chat (25%)
        self.main_frame.rowconfigure(0, weight=1)
        
        # Layout horizontal: Video izquierda, Chat derecha
        # Frame de video (izquierda) - inicialmente oculto
        self.video_container = tk.Frame(self.main_frame, bg=self.colors['bg_secondary'], relief=tk.FLAT, bd=0)
        self.video_container.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 5))
        self.video_container.columnconfigure(0, weight=1)
        self.video_container.rowconfigure(1, weight=1)
        self.video_container.grid_remove()  # Ocultar inicialmente
        
        # Título del video
        video_title = tk.Label(self.video_container, text="📹 Videollamada", 
                               bg=self.colors['bg_secondary'], fg=self.colors['fg_main'],
                               font=('Segoe UI', 14, 'bold'), pady=10)
        video_title.grid(row=0, column=0, sticky=(tk.W, tk.E))
        
        # Frame de video con borde
        video_frame = tk.Frame(self.video_container, bg='#000000', relief=tk.FLAT, bd=2)
        video_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=10, pady=(0, 10))
        video_frame.columnconfigure(0, weight=1)
        video_frame.rowconfigure(0, weight=1)
        
        self.video_label = tk.Label(video_frame, 
                                    text="📹\n\nNo hay videollamada activa\n\nPresiona el botón para iniciar", 
                                    bg='#000000', fg='#888888',
                                    font=('Segoe UI', 11), justify=tk.CENTER)
        self.video_label.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Frame de chat - ocupa todo el espacio cuando no hay video
        self.chat_container = tk.Frame(self.main_frame, bg=self.colors['bg_secondary'], relief=tk.FLAT, bd=0)
        self.chat_container.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.chat_container.config(width=0)  # Sin ancho fijo, que el grid lo controle
        self.chat_container.columnconfigure(0, weight=1)
        self.chat_container.rowconfigure(1, weight=1)
        
        # Configurar grid del chat_container
        self.chat_container.columnconfigure(0, weight=1)
        self.chat_container.rowconfigure(1, weight=1)  # Área de chat expandible
        
        # Título del chat
        chat_title = tk.Label(self.chat_container, text="💬 Chat", 
                             bg=self.colors['bg_secondary'], fg=self.colors['fg_main'],
                             font=('Segoe UI', 14, 'bold'), pady=10)
        chat_title.grid(row=0, column=0, sticky=(tk.W, tk.E))
        
        # Área de mensajes
        chat_text_frame = tk.Frame(self.chat_container, bg=self.colors['bg_chat'], relief=tk.FLAT, bd=1)
        chat_text_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=10, pady=(0, 10))
        chat_text_frame.columnconfigure(0, weight=1)
        chat_text_frame.rowconfigure(0, weight=1)
        
        self.chat_text = scrolledtext.ScrolledText(
            chat_text_frame, 
            wrap=tk.WORD, 
            state=tk.DISABLED,
            bg=self.colors['bg_chat'],
            fg=self.colors['fg_main'],
            font=('Segoe UI', 10),
            relief=tk.FLAT,
            bd=0,
            padx=10,
            pady=10,
            insertbackground=self.colors['fg_main']
        )
        self.chat_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.chat_text.bind("<Configure>", self._resize_audio_bubbles)
        
        # Configurar tags de color para mensajes
        self.chat_text.tag_config("system", foreground=self.colors['info'], font=('Segoe UI', 10, 'italic'))
        self.chat_text.tag_config("error", foreground=self.colors['error'], font=('Segoe UI', 10, 'bold'))
        self.chat_text.tag_config("file", foreground=self.colors['success'], font=('Segoe UI', 10))
        self.chat_text.tag_config("message", foreground=self.colors['fg_main'], font=('Segoe UI', 10))
        
        # Frame de entrada de mensaje
        self.input_frame = tk.Frame(self.chat_container, bg=self.colors['bg_secondary'])
        self.input_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), padx=10, pady=(0, 10))
        self.input_frame.columnconfigure(0, weight=1)
        self.input_frame.columnconfigure(1, weight=0, minsize=56)  # Botón enviar
        self.input_frame.columnconfigure(2, weight=0, minsize=56)  # Botón audio
        self.input_frame.rowconfigure(0, weight=1)
        
        self.message_entry = tk.Entry(
            self.input_frame,
            bg=self.colors['bg_input'],
            fg=self.colors['fg_main'],
            font=('Segoe UI', 10),
            relief=tk.FLAT,
            bd=5,
            insertbackground=self.colors['fg_main']
        )
        self.message_entry.grid(row=0, column=0, sticky=(tk.W, tk.E), ipady=6, padx=(0, 5))
        self.message_entry.bind('<Return>', lambda e: self.send_message())
        self.message_entry.bind('<FocusIn>', lambda e: self.message_entry.config(bg='#353535'))
        self.message_entry.bind('<FocusOut>', lambda e: self.message_entry.config(bg=self.colors['bg_input']))
        
        # Contenedor para el botón de envío (asegura centrado y tamaño mínimo)
        self.send_btn_container = tk.Frame(self.input_frame, bg=self.colors['bg_secondary'])
        self.send_btn_container.grid(row=0, column=1, sticky=(tk.N, tk.S, tk.E, tk.W), padx=(5, 0))
        self.send_btn_container.rowconfigure(0, weight=1)
        self.send_btn_container.columnconfigure(0, weight=1)
        
        self.send_btn = tk.Button(
            self.send_btn_container,
            text="➤",
            command=self.send_message,
            bg=self.colors['bg_button'],
            fg='white',
            font=('Segoe UI', 14, 'bold'),
            relief=tk.FLAT,
            bd=0,
            anchor=tk.CENTER,
            cursor='hand2',
            activebackground=self.colors['bg_button_hover'],
            activeforeground='white'
        )
        self.send_btn.grid(row=0, column=0, sticky=(tk.N, tk.S, tk.E, tk.W))

        # Botón para grabar audio (estilo WhatsApp)
        # Contenedor para el botón de audio (permite centrar el icono)
        self.audio_btn_container = tk.Frame(self.input_frame, bg=self.colors['bg_secondary'])
        self.audio_btn_container.grid(row=0, column=2, sticky=(tk.N, tk.S, tk.E, tk.W), padx=(5, 0))
        self.audio_btn_container.rowconfigure(0, weight=1)
        self.audio_btn_container.columnconfigure(0, weight=1)

        self.audio_btn = tk.Button(
            self.audio_btn_container,
            text="🎙️",
            command=self.toggle_audio_recording,
            bg=self.colors['bg_button'],
            fg='white',
            font=('Segoe UI', 16, 'bold'),
            relief=tk.FLAT,
            bd=0,
            anchor=tk.CENTER,
            cursor='hand2',
            activebackground=self.colors['bg_button_hover'],
            activeforeground='white'
        )
        self.audio_btn.pack(expand=True, fill=tk.BOTH)
        self.input_frame.bind("<Configure>", self._resize_input_controls)
        
        # Frame de botones (abajo, centrado)
        self.buttons_frame = tk.Frame(self.chat_container, bg=self.colors['bg_secondary'])
        self.buttons_frame.grid(row=3, column=0, sticky=(tk.W, tk.E), padx=10, pady=(0, 10))
        self.buttons_frame.config(width=0)  # Sin ancho fijo
        self.buttons_frame.columnconfigure(0, weight=1)
        self.buttons_frame.columnconfigure(1, weight=1)
        self.buttons_frame.columnconfigure(2, weight=1)
        self.buttons_frame.columnconfigure(3, weight=1)
        self.buttons_frame.columnconfigure(4, weight=0)  # Botón salir sin expandir
        
        # Botón de videollamada con icono
        self.video_btn = tk.Button(
            self.buttons_frame,
            text="📹 Iniciar Videollamada",
            command=self.toggle_video_call,
            bg=self.colors['bg_button'],
            fg='white',
            font=('Segoe UI', 9, 'bold'),
            relief=tk.FLAT,
            bd=0,
            padx=8,
            pady=8,
            cursor='hand2',
            activebackground=self.colors['bg_button_hover'],
            activeforeground='white',
            wraplength=80  # Permitir que el texto se ajuste
        )
        self.video_btn.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=2)
        
        # Botón subir archivo
        self.upload_btn = tk.Button(
            self.buttons_frame,
            text="📤",
            command=self.upload_file,
            bg=self.colors['bg_secondary'],
            fg=self.colors['fg_main'],
            font=('Segoe UI', 10),
            relief=tk.FLAT,
            bd=1,
            padx=8,
            pady=8,
            cursor='hand2',
            activebackground='#4a4a4a',
            activeforeground=self.colors['fg_main']
        )
        self.upload_btn.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=2)
        
        # Botón ver archivos
        self.files_btn = tk.Button(
            self.buttons_frame,
            text="📁",
            command=self.show_files,
            bg=self.colors['bg_secondary'],
            fg=self.colors['fg_main'],
            font=('Segoe UI', 10),
            relief=tk.FLAT,
            bd=1,
            padx=8,
            pady=8,
            cursor='hand2',
            activebackground='#4a4a4a',
            activeforeground=self.colors['fg_main']
        )
        self.files_btn.grid(row=0, column=2, sticky=(tk.W, tk.E), padx=2)
        
        # Botón salir
        self.quit_btn = tk.Button(
            self.buttons_frame,
            text="❌",
            command=self.on_closing,
            bg=self.colors['error'],
            fg='white',
            font=('Segoe UI', 10, 'bold'),
            relief=tk.FLAT,
            bd=0,
            padx=8,
            pady=8,
            cursor='hand2',
            activebackground='#d32f2f',
            activeforeground='white'
        )
        self.quit_btn.grid(row=0, column=4, sticky=(tk.W, tk.E), padx=2)
    
    def _show_connection_dialog(self):
        """Muestra diálogo de conexión y autenticación"""
        dialog = tk.Toplevel(self.root)
        dialog.title("🔐 Conectar al Servidor")
        dialog.geometry("450x400")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, False)
        dialog.configure(bg=self.colors['bg_main'])
        dialog.protocol("WM_DELETE_WINDOW", self.root.destroy)
        
        # Centrar ventana
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")
        
        frame = tk.Frame(dialog, bg=self.colors['bg_main'], padx=30, pady=30)
        frame.pack(fill=tk.BOTH, expand=True)
        
        # Título
        title_label = tk.Label(
            frame, 
            text="🔐 Conectar al Servidor",
            bg=self.colors['bg_main'],
            fg=self.colors['fg_main'],
            font=('Segoe UI', 16, 'bold')
        )
        title_label.pack(pady=(0, 20))
        
        # Host
        host_label = tk.Label(
            frame, 
            text="🌐 Host del servidor:",
            bg=self.colors['bg_main'],
            fg=self.colors['fg_secondary'],
            font=('Segoe UI', 10),
            anchor=tk.W
        )
        host_label.pack(fill=tk.X, pady=(0, 5))
        
        entry_width = 30
        
        host_entry = tk.Entry(
            frame,
            bg=self.colors['bg_input'],
            fg=self.colors['fg_main'],
            font=('Segoe UI', 11),
            relief=tk.FLAT,
            bd=5,
            insertbackground=self.colors['fg_main'],
            width=entry_width
        )
        host_entry.insert(0, self.host)
        host_entry.pack(fill=tk.X, pady=(0, 15), ipady=8)
        
        # Tipo de autenticación
        auth_frame = tk.Frame(frame, bg=self.colors['bg_main'])
        auth_frame.pack(fill=tk.X, pady=(0, 15))
        
        auth_type = tk.StringVar(value="login")
        
        login_radio = tk.Radiobutton(
            auth_frame,
            text="🔑 Login",
            variable=auth_type,
            value="login",
            bg=self.colors['bg_main'],
            fg=self.colors['fg_main'],
            font=('Segoe UI', 10),
            selectcolor=self.colors['bg_secondary'],
            activebackground=self.colors['bg_main'],
            activeforeground=self.colors['fg_main']
        )
        login_radio.pack(side=tk.LEFT, padx=(0, 20))
        
        register_radio = tk.Radiobutton(
            auth_frame,
            text="✨ Registrarse",
            variable=auth_type,
            value="register",
            bg=self.colors['bg_main'],
            fg=self.colors['fg_main'],
            font=('Segoe UI', 10),
            selectcolor=self.colors['bg_secondary'],
            activebackground=self.colors['bg_main'],
            activeforeground=self.colors['fg_main']
        )
        register_radio.pack(side=tk.LEFT)
        
        # Usuario
        user_label = tk.Label(
            frame,
            text="👤 Usuario:",
            bg=self.colors['bg_main'],
            fg=self.colors['fg_secondary'],
            font=('Segoe UI', 10),
            anchor=tk.W
        )
        user_label.pack(fill=tk.X, pady=(0, 5))
        
        user_entry = tk.Entry(
            frame,
            bg=self.colors['bg_input'],
            fg=self.colors['fg_main'],
            font=('Segoe UI', 11),
            relief=tk.FLAT,
            bd=5,
            insertbackground=self.colors['fg_main'],
            width=entry_width
        )
        user_entry.pack(fill=tk.X, pady=(0, 15), ipady=8)
        user_entry.focus()
        
        # Contraseña
        pass_label = tk.Label(
            frame,
            text="🔒 Contraseña:",
            bg=self.colors['bg_main'],
            fg=self.colors['fg_secondary'],
            font=('Segoe UI', 10),
            anchor=tk.W
        )
        pass_label.pack(fill=tk.X, pady=(0, 5))
        
        pass_entry = tk.Entry(
            frame,
            bg=self.colors['bg_input'],
            fg=self.colors['fg_main'],
            font=('Segoe UI', 11),
            relief=tk.FLAT,
            bd=5,
            show="*",
            insertbackground=self.colors['fg_main'],
            width=entry_width
        )
        pass_entry.pack(fill=tk.X, pady=(0, 20), ipady=8)
        
        status_label = tk.Label(
            frame,
            text="",
            bg=self.colors['bg_main'],
            fg=self.colors['error'],
            font=('Segoe UI', 9)
        )
        status_label.pack(pady=(0, 10))
        
        def connect():
            host = host_entry.get().strip()
            username = user_entry.get().strip()
            password = pass_entry.get()
            auth = auth_type.get()
            
            if not host or not username or not password:
                status_label.config(text="Por favor completa todos los campos")
                return
            
            status_label.config(text="Conectando...", foreground="blue")
            dialog.update()
            
            # Conectar
            chat = ChatClient(host, CHAT_PORT, '')
            if not chat.connect():
                status_label.config(text="Error: No se pudo conectar al servidor", foreground="red")
                return
            
            # Autenticar
            success, message = chat.authenticate(auth, username, password)
            if not success:
                status_label.config(text=f"Error: {message}", foreground="red")
                chat.disconnect()
                return
            
            # Éxito
            self.host = host
            self.username = chat.username
            self.chat_client = chat
            self.chat_client.running = True
            threading.Thread(target=self._recv_loop, daemon=True).start()
            
            self.root.title(f"💬 Chat - {self.username}")
            dialog.destroy()
            if not self._main_frame_visible:
                self.main_frame.pack(fill=tk.BOTH, expand=True)
                self._main_frame_visible = True
            self.root.attributes('-alpha', 1.0)
            self._add_message("SISTEMA", f"✅ Conectado como {self.username}", "system")
        
        connect_btn = tk.Button(
            frame,
            text="🚀 Conectar",
            command=connect,
            bg=self.colors['bg_button'],
            fg='white',
            font=('Segoe UI', 12, 'bold'),
            relief=tk.FLAT,
            bd=0,
            padx=30,
            pady=12,
            cursor='hand2',
            activebackground=self.colors['bg_button_hover'],
            activeforeground='white'
        )
        connect_btn.pack(pady=10)
        
        pass_entry.bind('<Return>', lambda e: connect())
        user_entry.bind('<Return>', lambda e: pass_entry.focus())
    
    def _recv_loop(self):
        """Loop de recepción de mensajes"""
        while self.chat_client and self.chat_client.running:
            try:
                msg = ProtocolHandler.recv_json(self.chat_client.sock)
                mtype = msg.get('type')
                
                if mtype == 'message':
                    from_user = msg.get('from', 'unknown')
                    text = msg.get('text', '')
                    self.root.after(0, lambda u=from_user, t=text: self._add_message(u, t, "message"))
                elif mtype == 'system':
                    text = msg.get('text', '')
                    self.root.after(0, lambda t=text: self._add_message("SISTEMA", t, "system"))
                elif mtype == 'file_available':
                    from_user = msg.get('from')
                    filename = msg.get('filename')
                    file_id = msg.get('file_id')
                    self.available_files[file_id] = {'filename': filename, 'from': from_user}
                    info = f"{from_user} compartió: {filename} (ID: {file_id})"
                    self.root.after(0, lambda text=info: self._add_message("SISTEMA", text, "file"))
                elif mtype == 'call':
                    action = msg.get('action')
                    from_user = msg.get('from')
                    if action == 'start':
                        self.root.after(0, lambda user=from_user: self._add_message(
                            "SISTEMA", f"{user} inició una videollamada", "system"))
                    elif action == 'stop':
                        self.root.after(0, lambda user=from_user: self._add_message(
                            "SISTEMA", f"{user} terminó la videollamada", "system"))
                elif mtype == 'audio_message':
                    from_user = msg.get('from', 'unknown')
                    file_id = msg.get('file_id')
                    filename = msg.get('filename')
                    duration = msg.get('duration', 0)
                    self.root.after(0, lambda u=from_user, fid=file_id, fn=filename, d=duration:
                                    self._add_audio_message(u, fid, fn, d))
            except Exception:
                if self.chat_client and self.chat_client.running:
                    self.root.after(0, lambda: self._add_message("SISTEMA",
                                                                 "Conexión perdida con el servidor",
                                                                 "error"))
                break
    
    def _add_message(self, user: str, text: str, msg_type: str = "message"):
        """Agrega un mensaje al área de chat"""
        self.chat_text.config(state=tk.NORMAL)
        
        # Emojis según tipo
        emoji_map = {
            "system": "ℹ️",
            "error": "❌",
            "file": "📁",
            "message": "💬"
        }
        emoji = emoji_map.get(msg_type, "💬")
        
        if msg_type == "system":
            self.chat_text.insert(tk.END, f"{emoji} [{user}]: {text}\n", "system")
        elif msg_type == "error":
            self.chat_text.insert(tk.END, f"{emoji} [{user}]: {text}\n", "error")
        elif msg_type == "file":
            self.chat_text.insert(tk.END, f"{emoji} [{user}]: {text}\n", "file")
        else:
            self.chat_text.insert(tk.END, f"{emoji} [{user}]: {text}\n", "message")
        
        self.chat_text.config(state=tk.DISABLED)
        self.chat_text.see(tk.END)

    def _post_message(self, user: str, text: str, msg_type: str = "message"):
        """Agenda la inserción de un mensaje en el hilo principal de Tk"""
        self.root.after(0, lambda u=user, t=text, m=msg_type: self._add_message(u, t, m))

    def _format_duration(self, duration: float) -> str:
        """Devuelve la duración en formato mm:ss"""
        seconds = max(0, int(round(duration)))
        minutes = seconds // 60
        secs = seconds % 60
        return f"{minutes:02d}:{secs:02d}"

    def _add_audio_message(self, user: str, file_id: str, filename: str, duration: float):
        """Inserta un mensaje de audio con un botón de reproducción"""
        if file_id in self.audio_messages and self.audio_messages[file_id].get('rendered'):
            # Ya fue agregado, no duplicar
            return
        
        local_path = os.path.join(DOWNLOADS_DIR, filename)
        meta = self.audio_messages.get(file_id, {})
        meta.update({
            'filename': filename,
            'duration': duration,
            'local_path': local_path if os.path.exists(local_path) else meta.get('local_path'),
            'downloading': False,
            'rendered': True
        })
        self.audio_messages[file_id] = meta
        
        self.chat_text.config(state=tk.NORMAL)
        container_height = 50
        container = tk.Frame(self.chat_text, bg=self.colors['bg_secondary'], padx=8, pady=6, height=container_height)
        container.grid_propagate(False)
        container.columnconfigure(0, weight=1)
        container.columnconfigure(1, weight=0)
        
        info_frame = tk.Frame(container, bg=self.colors['bg_secondary'], height=container_height-12)
        info_frame.grid(row=0, column=0, sticky=(tk.W, tk.E))
        info_frame.grid_propagate(False)
        info_frame.columnconfigure(1, weight=1)
        
        icon_label = tk.Label(
            info_frame,
            text="🎙️",
            bg=self.colors['bg_secondary'],
            fg=self.colors['fg_main'],
            font=('Segoe UI', 12, 'bold')
        )
        icon_label.grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
        
        text_label = tk.Label(
            info_frame,
            text=f"[{user}] · {self._format_duration(duration)}",
            bg=self.colors['bg_secondary'],
            fg=self.colors['fg_main'],
            font=('Segoe UI', 10, 'bold'),
            anchor='w'
        )
        text_label.grid(row=0, column=1, sticky=(tk.W, tk.E))
        
        play_btn = tk.Button(
            container,
            text="▶️ Reproducir",
            command=lambda fid=file_id: self.play_audio_message(fid),
            bg=self.colors['bg_button'],
            fg='white',
            font=('Segoe UI', 9, 'bold'),
            relief=tk.FLAT,
            bd=0,
            padx=12,
            cursor='hand2',
            activebackground=self.colors['bg_button_hover'],
            activeforeground='white'
        )
        play_btn.grid(row=0, column=1, sticky=tk.E, padx=(10, 0))
        
        self.chat_text.window_create(tk.END, window=container)
        self.chat_text.insert(tk.END, "\n")
        self.chat_text.config(state=tk.DISABLED)
        self.chat_text.see(tk.END)
        self.audio_message_frames.append({
            'frame': container,
            'info': info_frame,
            'button': play_btn
        })
        self._resize_audio_bubbles()
        self.root.after_idle(self._resize_audio_bubbles)

    def _resize_audio_bubbles(self, event=None):
        """Ajusta el ancho de las burbujas de audio según el tamaño del chat"""
        if not self.audio_message_frames:
            return
        available_width = max(160, self.chat_text.winfo_width() - 20)
        for item in self.audio_message_frames:
            frame = item.get('frame')
            info = item.get('info')
            button = item.get('button')
            try:
                frame.configure(width=available_width)
                info_width = max(80, available_width - (button.winfo_reqwidth() + 30))
                if info is not None:
                    info.configure(width=info_width)
                    info.grid_propagate(False)
            except Exception:
                pass

    def _resize_input_controls(self, event=None):
        """Mantiene tamaños proporcionales para los botones de enviar y audio"""
        if not hasattr(self, 'send_btn_container') or not hasattr(self, 'audio_btn_container'):
            return
        frame_width = max(1, self.input_frame.winfo_width())
        # Calcular ancho deseado (entre 36 y 52 px) según el ancho disponible
        target = max(36, min(52, int(frame_width * 0.05)))
        for col in (1, 2):
            self.input_frame.columnconfigure(col, minsize=target)
        for container in (self.send_btn_container, self.audio_btn_container):
            try:
                container.configure(width=target)
            except Exception:
                pass

    def toggle_audio_recording(self):
        """Inicia o detiene la grabación de audio"""
        if self.audio_recording:
            self._stop_audio_recording()
        else:
            self._start_audio_recording()

    def _start_audio_recording(self):
        if self.audio_recording:
            return
        try:
            self.audio_record_frames = []
            self.audio_record_stream = sd.InputStream(
                samplerate=self.audio_sample_rate,
                channels=self.audio_channels,
                dtype='int16',
                callback=self._audio_record_callback
            )
            self.audio_record_stream.start()
            self.audio_record_start = time.time()
            self.audio_recording = True
            self.audio_btn.config(text="⏹️", bg=self.colors['error'])
        except Exception as e:
            self.audio_record_stream = None
            self.audio_recording = False
            self.audio_btn.config(text="🎙️", bg=self.colors['bg_button'])
            self._post_message("SISTEMA", f"No se pudo iniciar la grabación: {e}", "error")

    def _audio_record_callback(self, indata, frames, time_info, status):  # pragma: no cover - callback
        if status:
            print(f'[AUDIO] Record status: {status}')
        self.audio_record_frames.append(indata.copy())

    def _stop_audio_recording(self):
        if not self.audio_recording:
            return
        self.audio_recording = False
        self.audio_btn.config(text="🎙️", bg=self.colors['bg_button'])
        stream = self.audio_record_stream
        self.audio_record_stream = None
        if stream:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
        duration = time.time() - self.audio_record_start
        frames_copy = [frame.copy() for frame in self.audio_record_frames]
        self.audio_record_frames = []
        if not frames_copy or duration < 0.5:
            self._post_message("SISTEMA", "Audio demasiado corto", "error")
            return
        threading.Thread(
            target=self._process_audio_recording,
            args=(frames_copy, duration),
            daemon=True
        ).start()

    def _process_audio_recording(self, frames, duration: float):
        temp_path = None
        try:
            audio_data = np.concatenate(frames, axis=0)
            temp_fd, temp_path = tempfile.mkstemp(suffix='.wav', prefix='voice_')
            os.close(temp_fd)
            with wave.open(temp_path, 'wb') as wf:
                wf.setnchannels(self.audio_channels)
                wf.setsampwidth(2)  # int16
                wf.setframerate(self.audio_sample_rate)
                wf.writeframes(audio_data.tobytes())
            
            filename = f"voice_{int(time.time() * 1000)}.wav"
            final_path = os.path.join(DOWNLOADS_DIR, filename)
            os.replace(temp_path, final_path)
            temp_path = None
            
            file_id = FileClient.upload_file(self.host, FILE_PORT, final_path)
            if not file_id:
                self._post_message("SISTEMA", "No se pudo subir el audio", "error")
                return
            if self.chat_client:
                self.chat_client.send_audio_message(file_id, filename, round(duration, 1))
            self.root.after(0, lambda fid=file_id, fn=filename, d=duration:
                            self._add_audio_message(self.username, fid, fn, d))
        except Exception as e:
            self._post_message("SISTEMA", f"Error al procesar audio: {e}", "error")
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass

    def play_audio_message(self, file_id: str):
        """Descarga (si es necesario) y reproduce un mensaje de audio"""
        if file_id not in self.audio_messages:
            self._post_message("SISTEMA", "Audio no disponible", "error")
            return
        meta = self.audio_messages[file_id]
        if meta.get('downloading'):
            return
        
        def worker():
            path = meta.get('local_path')
            if not path or not os.path.exists(path):
                meta['downloading'] = True
                success = FileClient.download_file(self.host, FILE_PORT, file_id)
                meta['downloading'] = False
                if not success:
                    self._post_message("SISTEMA", "No se pudo descargar el audio", "error")
                    return
                path = os.path.join(DOWNLOADS_DIR, meta['filename'])
                meta['local_path'] = path
            self._play_audio_file(path)
        
        threading.Thread(target=worker, daemon=True).start()

    def _play_audio_file(self, path: str):
        """Reproduce un archivo WAV usando sounddevice"""
        try:
            sd.stop()
            with wave.open(path, 'rb') as wf:
                frames = wf.readframes(wf.getnframes())
                audio_data = np.frombuffer(frames, dtype=np.int16)
                audio_data = audio_data.reshape(-1, wf.getnchannels())
                sd.play(audio_data, wf.getframerate())
                sd.wait()
        except Exception as e:
            self._post_message("SISTEMA", f"No se pudo reproducir el audio: {e}", "error")
    
    def send_message(self):
        """Envía un mensaje"""
        text = self.message_entry.get().strip()
        if not text or not self.chat_client:
            return
        
        self.chat_client.send_message(text)
        self.message_entry.delete(0, tk.END)
    
    def _handle_resize(self):
        """Maneja el redimensionamiento de la ventana"""
        if hasattr(self, '_resize_scheduled'):
            self._resize_scheduled = False
        if self.video_client is not None:
            # Forzar recálculo del layout con relación 3:1
            self._set_layout_ratio(3, 1, show_video=True)
    
    def _set_layout_ratio(self, video_weight: int, chat_weight: int, show_video: bool = True):
        """Cambia la proporción del layout entre video y chat"""
        if self._updating_layout:
            return
        self._updating_layout = True
        
        def apply_layout():
            try:
                if show_video:
                    # Quitar place si estaba usando place
                    self.chat_container.place_forget()
                    
                    # Forzar actualización para obtener dimensiones actuales
                    self.root.update_idletasks()
                    
                    # Obtener ancho total del main_frame
                    main_width = self.main_frame.winfo_width()
                    
                    # Configurar los pesos del grid para relación 3:1 (75%:25%)
                    # Usar uniform para mantener la proporción de forma consistente
                    self.main_frame.columnconfigure(0, weight=video_weight, minsize=0, uniform='videochat')
                    self.main_frame.columnconfigure(1, weight=chat_weight, minsize=0, uniform='videochat')
                    
                    # Resetear ancho del chat_container para que el grid lo controle completamente
                    self.chat_container.config(width=0)
                    
                    # Mostrar video_container en columna 0
                    self.video_container.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 5))
                    
                    # Mostrar chat_container en columna 1 usando grid
                    self.chat_container.grid(row=0, column=1, columnspan=1, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(5, 0))
                    
                else:
                    # Ocultar video
                    self.video_container.grid_forget()
                    # Quitar place del chat si estaba usando place
                    self.chat_container.place_forget()
                    # Reposicionar chat para que ocupe todo el espacio con grid
                    self.chat_container.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S))
                    self.main_frame.columnconfigure(0, weight=1, minsize=0, uniform=None)
                    self.main_frame.columnconfigure(1, weight=0, minsize=0, uniform=None)
                    self.chat_container.config(width=0)
                
                # Forzar actualización del layout
                self.root.update_idletasks()
                self.root.update()
            finally:
                # Liberar la bandera después de un pequeño delay
                self.root.after(100, lambda: setattr(self, '_updating_layout', False))
        
        # Ejecutar en el siguiente ciclo del event loop
        self.root.after_idle(apply_layout)
    
    def toggle_video_call(self):
        """Inicia o detiene la videollamada"""
        if self.video_client is None:
            # Iniciar videollamada
            def stop_callback():
                self.video_client = None
                self.video_btn.config(text="📹 Iniciar Videollamada", bg=self.colors['bg_button'], wraplength=80)
                self.video_label.config(image='', text="📹\n\nNo hay videollamada activa\n\nPresiona el botón para iniciar")
                # Ocultar sección de video cuando no hay videollamada
                self._set_layout_ratio(3, 1, show_video=False)
                if self.chat_client:
                    self.chat_client.send_call_action('stop')
            
            # Guardar tamaño fijo del contenedor para evitar expansión
            if not hasattr(self, '_video_container_size'):
                self._video_container_size = None
            
            def frame_update(frame: np.ndarray):
                # Convertir BGR a RGB
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                
                # Obtener tamaño del contenedor de video de forma fija
                try:
                    # Obtener tamaño del frame de video (el contenedor negro)
                    video_frame = self.video_label.master
                    container = video_frame.master  # video_container
                    
                    # Obtener tamaño actual del contenedor
                    container_width = container.winfo_width()
                    container_height = container.winfo_height()
                    
                    # Si el tamaño del contenedor es válido, guardarlo como referencia fija
                    if container_width > 100 and container_height > 100:
                        # Solo actualizar el tamaño de referencia si no existe o si cambió significativamente (redimensionamiento de ventana)
                        if (self._video_container_size is None or 
                            abs(self._video_container_size[0] - container_width) > 50 or
                            abs(self._video_container_size[1] - container_height) > 50):
                            self._video_container_size = (container_width, container_height)
                        
                        # Usar el tamaño de referencia fijo para evitar expansión progresiva
                        ref_width, ref_height = self._video_container_size
                        widget_width = max(ref_width - 20, 100)  # Menos padding
                        widget_height = max(ref_height - 60, 100)  # Menos título y padding
                    else:
                        # Si el contenedor aún no tiene tamaño, usar valores por defecto
                        if self._video_container_size is None:
                            widget_width = 900  # 75% de 1200px
                            widget_height = 700
                        else:
                            ref_width, ref_height = self._video_container_size
                            widget_width = max(ref_width - 20, 100)
                            widget_height = max(ref_height - 60, 100)
                except:
                    # Fallback: usar tamaño por defecto
                    if self._video_container_size is None:
                        widget_width = 900
                        widget_height = 700
                    else:
                        ref_width, ref_height = self._video_container_size
                        widget_width = max(ref_width - 20, 100)
                        widget_height = max(ref_height - 60, 100)
                
                # Asegurar que el tamaño sea válido y no exceda límites razonables
                widget_width = max(100, min(widget_width, 1920))
                widget_height = max(100, min(widget_height, 1080))
                
                # Redimensionar el frame para ajustarse al tamaño fijo
                height, width = frame_rgb.shape[:2]
                frame_resized = cv2.resize(frame_rgb, (widget_width, widget_height))
                
                # Convertir a PhotoImage
                img = Image.fromarray(frame_resized)
                photo = ImageTk.PhotoImage(image=img)
                
                # Actualizar label (sin cambiar su tamaño, solo la imagen)
                self.video_label.config(image=photo, text='')
                self.video_label.image = photo  # Mantener referencia
            
            self.video_client = VideoClient(
                self.host, MEDIA_PORT, self.room_id, self.client_id,
                self.username, stop_callback, AUDIO_PORT, frame_update
            )
            
            if self.video_client.start():
                self.video_btn.config(text="📹 Terminar", bg=self.colors['error'], wraplength=60)
                # Resetear tamaño de referencia al iniciar videollamada
                self._video_container_size = None
                # Mostrar video y aplicar relación 3:1 (75%:25%) cuando hay videollamada activa
                self._set_layout_ratio(3, 1, show_video=True)
                if self.chat_client:
                    self.chat_client.send_call_action('start')
                self._add_message("SISTEMA", "Videollamada iniciada", "system")
            else:
                self.video_client = None
                messagebox.showerror("Error", "No se pudo iniciar la videollamada")
        else:
            # Detener videollamada
            self.video_client.stop()
            self.video_client = None
            self.video_btn.config(text="📹 Iniciar Videollamada", bg=self.colors['bg_button'], wraplength=80)
            self.video_label.config(image='', text="📹\n\nNo hay videollamada activa\n\nPresiona el botón para iniciar")
            # Ocultar sección de video cuando no hay videollamada
            self._set_layout_ratio(3, 1, show_video=False)
            if self.chat_client:
                self.chat_client.send_call_action('stop')
            self._add_message("SISTEMA", "Videollamada terminada", "system")
    
    def upload_file(self):
        """Sube un archivo"""
        filepath = select_file(self.root)
        if not filepath:
            return
        
        if not self.chat_client:
            messagebox.showerror("Error", "No estás conectado al servidor")
            return
        
        def upload_thread():
            file_id = FileClient.upload_file(self.host, FILE_PORT, filepath)
            if file_id:
                filename = os.path.basename(filepath)
                size = os.path.getsize(filepath)
                self.chat_client.notify_file_available(filename, size, file_id)
                self.root.after(0, lambda: self._add_message("SISTEMA", 
                    f"Archivo subido: {filename}", "file"))
            else:
                self.root.after(0, lambda: messagebox.showerror("Error", 
                    "No se pudo subir el archivo"))
        
        threading.Thread(target=upload_thread, daemon=True).start()
    
    def show_files(self):
        """Muestra ventana de archivos disponibles"""
        if not self.available_files:
            messagebox.showinfo("📁 Archivos", "No hay archivos disponibles")
            return
        
        files_window = tk.Toplevel(self.root)
        files_window.title("📁 Archivos Disponibles")
        files_window.geometry("600x500")
        files_window.configure(bg=self.colors['bg_main'])
        
        frame = tk.Frame(files_window, bg=self.colors['bg_main'], padx=20, pady=20)
        frame.pack(fill=tk.BOTH, expand=True)
        
        title_label = tk.Label(
            frame,
            text="📁 Archivos Disponibles",
            bg=self.colors['bg_main'],
            fg=self.colors['fg_main'],
            font=('Segoe UI', 14, 'bold')
        )
        title_label.pack(anchor=tk.W, pady=(0, 15))
        
        listbox_frame = tk.Frame(frame, bg=self.colors['bg_chat'], relief=tk.FLAT, bd=1)
        listbox_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 15))
        
        listbox = tk.Listbox(
            listbox_frame,
            bg=self.colors['bg_chat'],
            fg=self.colors['fg_main'],
            font=('Segoe UI', 10),
            relief=tk.FLAT,
            bd=0,
            selectbackground=self.colors['bg_button'],
            selectforeground='white'
        )
        listbox.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        for file_id, info in self.available_files.items():
            listbox.insert(tk.END, f"📄 {info['filename']} (de {info['from']}) - ID: {file_id}")
        
        def download_selected():
            selection = listbox.curselection()
            if not selection:
                messagebox.showwarning("⚠️ Advertencia", "Selecciona un archivo")
                return
            
            index = selection[0]
            file_id = list(self.available_files.keys())[index]
            
            def download_thread():
                success = FileClient.download_file(self.host, FILE_PORT, file_id)
                if success:
                    filename = self.available_files[file_id]['filename']
                    self.root.after(0, lambda: messagebox.showinfo("✅ Éxito", 
                        f"Archivo descargado: {filename}\nGuardado en: {DOWNLOADS_DIR}"))
                else:
                    self.root.after(0, lambda: messagebox.showerror("❌ Error", 
                        "No se pudo descargar el archivo"))
            
            threading.Thread(target=download_thread, daemon=True).start()
        
        download_btn = tk.Button(
            frame,
            text="⬇️ Descargar Seleccionado",
            command=download_selected,
            bg=self.colors['bg_button'],
            fg='white',
            font=('Segoe UI', 11, 'bold'),
            relief=tk.FLAT,
            bd=0,
            padx=20,
            pady=10,
            cursor='hand2',
            activebackground=self.colors['bg_button_hover'],
            activeforeground='white'
        )
        download_btn.pack()
    
    def on_closing(self):
        """Maneja el cierre de la ventana"""
        if self.video_client:
            self.video_client.stop()
        if self.chat_client:
            self.chat_client.disconnect()
        self.root.destroy()
    
    def run(self):
        """Inicia el loop principal de la GUI"""
        self.root.mainloop()

# -------------------- Main --------------------

def main() -> None:
    parser = argparse.ArgumentParser(description='Cliente de chat con archivos y video')
    parser.add_argument('--host', type=str, default=CHAT_HOST, help='Host del servidor')
    parser.add_argument('--console', action='store_true', help='Usar modo consola (por defecto: GUI)')
    args = parser.parse_args()

    if args.console:
        # Modo consola (backward compatibility)
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
                            def stop_callback():
                                nonlocal video_client
                                chat.send_call_action('stop')
                                video_client = None
                                print('[VIDEO] Notificando a otros usuarios que terminaste la videollamada')
                            video_client = VideoClient(
                                args.host, MEDIA_PORT, room_id, client_id,
                                chat.username, stop_callback, audio_port=AUDIO_PORT
                            )
                            if video_client.start():
                                chat.send_call_action('start')
                                print('[VIDEO] Videollamada iniciada. Presiona "q" en la ventana de video para terminar.')
                            else:
                                video_client = None
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
    else:
        # Modo GUI (por defecto)
        app = ChatGUI(args.host)
        app.run()


if __name__ == '__main__':
    main()

