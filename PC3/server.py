"""
Servidor de chat con soporte para mensajes, archivos y videollamadas
Patrón: Observer - Sistema de broadcast para notificar a todos los clientes
Patrón: Factory - Crea handlers para diferentes tipos de servicios
"""
import os
import socket
import threading
import json
import struct
from typing import Dict, List, Tuple, Optional
from database import Database
from protocol import ProtocolHandler
from message_handlers import MessageHandlerFactory, AuthHandler


# Configuración de puertos
CHAT_HOST = '0.0.0.0'
CHAT_PORT = 9009
FILE_HOST = '0.0.0.0'
FILE_PORT = 9010
MEDIA_HOST = '0.0.0.0'
MEDIA_PORT = 9020
AUDIO_PORT = 9030

SERVER_STORAGE_DIR = os.path.join(os.path.dirname(__file__), 'server_storage')
os.makedirs(SERVER_STORAGE_DIR, exist_ok=True)


class BaseServer:
    """
    Clase base para servidores
    Patrón: Template Method - Define la estructura común de servidores
    """
    
    def __init__(self, host: str, port: int, service_name: str):
        self.host = host
        self.port = port
        self.service_name = service_name
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    def start(self) -> None:
        """Inicia el servidor (Template Method)"""
        self.server_sock.bind((self.host, self.port))
        self.server_sock.listen()
        print(f'[{self.service_name}] Listening on {self.host}:{self.port}')
        threading.Thread(target=self._accept_loop, daemon=True).start()
    
    def _accept_loop(self) -> None:
        """Loop de aceptación de conexiones (debe ser implementado por subclases)"""
        raise NotImplementedError
    
    def _handle_client(self, client_sock: socket.socket, addr: Tuple[str, int]) -> None:
        """Maneja un cliente (debe ser implementado por subclases)"""
        raise NotImplementedError


class ChatServer(BaseServer):
    """
    Servidor de chat
    Patrón: Observer - Notifica a todos los observadores (clientes) de eventos
    """
    
    def __init__(self, host: str, port: int, db: Database):
        super().__init__(host, port, 'CHAT')
        self.clients_lock = threading.Lock()
        self.clients: Dict[socket.socket, str] = {}  # Observer pattern: lista de observadores
        self.db = db
        self.auth_handler = AuthHandler(db)
    
    def _accept_loop(self) -> None:
        """Acepta conexiones de clientes"""
        while True:
            client_sock, addr = self.server_sock.accept()
            threading.Thread(
                target=self._handle_client,
                args=(client_sock, addr),
                daemon=True
            ).start()
    
    def _handle_client(self, client_sock: socket.socket, addr: Tuple[str, int]) -> None:
        """Maneja la conexión de un cliente"""
        username = None
        try:
            # Autenticación
            try:
                auth_msg = ProtocolHandler.recv_json(client_sock)
            except (ConnectionError, OSError, json.JSONDecodeError, struct.error) as e:
                print(f'[CHAT] Error al recibir mensaje de autenticación de {addr}: {e}')
                try:
                    # Intentar enviar mensaje de error antes de cerrar
                    ProtocolHandler.send_json(client_sock, {
                        'type': 'auth_response',
                        'success': False,
                        'message': 'Error de protocolo: formato de mensaje inválido'
                    })
                except:
                    pass
                client_sock.close()
                return
            
            if not auth_msg or 'type' not in auth_msg:
                print(f'[CHAT] Mensaje de autenticación inválido de {addr}')
                try:
                    ProtocolHandler.send_json(client_sock, {
                        'type': 'auth_response',
                        'success': False,
                        'message': 'Mensaje de autenticación inválido'
                    })
                except:
                    pass
                client_sock.close()
                return
            
            try:
                success, username = self.auth_handler.handle_auth(auth_msg, client_sock)
            except Exception as e:
                print(f'[CHAT] Error al procesar autenticación de {addr}: {e}')
                try:
                    ProtocolHandler.send_json(client_sock, {
                        'type': 'auth_response',
                        'success': False,
                        'message': f'Error interno del servidor: {str(e)}'
                    })
                except:
                    pass
                client_sock.close()
                return
            
            if not success or not username:
                # El handler ya envió la respuesta
                # Dar un pequeño tiempo para que el cliente lea la respuesta antes de cerrar
                import time
                time.sleep(0.1)  # 100ms para que el cliente pueda leer la respuesta
                try:
                    client_sock.close()
                except:
                    pass
                return
            
            # Registrar cliente (Observer pattern: agregar observador)
            with self.clients_lock:
                self.clients[client_sock] = username
            
            print(f'[CHAT] {username} connected from {addr}')
            
            # Notificar a otros clientes (Observer pattern: notificar observadores)
            self.broadcast_to_all(self.clients, self.clients_lock, {
                'type': 'system',
                'text': f'{username} se unió al chat',
            })
            
            # Procesar mensajes
            while True:
                msg = ProtocolHandler.recv_json(client_sock)
                msg_type = msg.get('type')
                
                if msg_type == 'quit':
                    break
                
                # Strategy pattern: obtener handler apropiado
                handler = MessageHandlerFactory.get_handler(msg_type)
                if handler:
                    handler.handle(msg, client_sock, username, self.clients, self.clients_lock)
                    
        except (ConnectionError, OSError):
            pass
        finally:
            # Remover cliente (Observer pattern: remover observador)
            with self.clients_lock:
                username = self.clients.pop(client_sock, None) or 'alguien'
            
            try:
                client_sock.close()
            except Exception:
                pass
            
            if username:
                print(f'[CHAT] {username} disconnected')
                self.broadcast_to_all(self.clients, self.clients_lock, {
                    'type': 'system',
                    'text': f'{username} salió del chat'
                })
    
    @staticmethod
    def broadcast_to_all(clients: Dict, clients_lock: threading.Lock, payload: Dict,
                         exclude: Optional[socket.socket] = None) -> None:
        """
        Notifica a todos los clientes (Observer pattern)
        Patrón: Observer - Notifica a todos los observadores registrados
        """
        with clients_lock:
            dead_clients: List[socket.socket] = []
            for client_sock in clients.keys():
                try:
                    if exclude and client_sock is exclude:
                        continue
                    ProtocolHandler.send_json(client_sock, payload)
                except Exception:
                    dead_clients.append(client_sock)
            
            # Limpiar clientes desconectados
            for client_sock in dead_clients:
                clients.pop(client_sock, None)
                try:
                    client_sock.close()
                except Exception:
                    pass


class FileServer(BaseServer):
    """Servidor de archivos"""
    
    def __init__(self, host: str, port: int):
        super().__init__(host, port, 'FILE')
        self.file_index_lock = threading.Lock()
        self.file_index: Dict[str, Tuple[str, str, int]] = {}  # file_id -> (path, filename, size)
    
    def _accept_loop(self) -> None:
        """Acepta conexiones para transferencia de archivos"""
        while True:
            client_sock, addr = self.server_sock.accept()
            threading.Thread(
                target=self._handle_client,
                args=(client_sock, addr),
                daemon=True
            ).start()
    
    def _handle_client(self, client_sock: socket.socket, addr: Tuple[str, int]) -> None:
        """Maneja operaciones de archivos (upload/download)"""
        try:
            req = ProtocolHandler.recv_json(client_sock)
            req_type = req.get('type')
            
            if req_type == 'upload':
                self._handle_upload(client_sock, req)
            elif req_type == 'download':
                self._handle_download(client_sock, req)
            else:
                ProtocolHandler.send_json(client_sock, {
                    'type': 'error',
                    'message': 'unknown request'
                })
        except Exception:
            try:
                ProtocolHandler.send_json(client_sock, {
                    'type': 'error',
                    'message': 'server error'
                })
            except Exception:
                pass
        finally:
            try:
                client_sock.close()
            except Exception:
                pass
    
    def _handle_upload(self, client_sock: socket.socket, req: Dict) -> None:
        """Maneja la subida de un archivo"""
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
        
        ProtocolHandler.send_json(client_sock, {'type': 'upload_ok'})
    
    def _handle_download(self, client_sock: socket.socket, req: Dict) -> None:
        """Maneja la descarga de un archivo"""
        file_id = req['file_id']
        
        with self.file_index_lock:
            if file_id not in self.file_index:
                ProtocolHandler.send_json(client_sock, {
                    'type': 'error',
                    'message': 'file not found'
                })
                return
            path, filename, size = self.file_index[file_id]
        
        ProtocolHandler.send_json(client_sock, {
            'type': 'download_meta',
            'filename': filename,
            'size': size
        })
        
        with open(path, 'rb') as f:
            while True:
                data = f.read(64 * 1024)
                if not data:
                    break
                client_sock.sendall(data)


class UdpVideoRelay:
    """
    Relay UDP para videollamadas
    Patrón: Facade - Simplifica el relay de video
    """
    
    def __init__(self, host: str, port: int, service_name: str = 'MEDIA'):
        self.host = host
        self.port = port
        self.service_name = service_name
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.rooms_lock = threading.Lock()
        self.rooms: Dict[int, set] = {}  # room_id -> set of addresses
    
    def start(self) -> None:
        """Inicia el relay UDP"""
        self.sock.bind((self.host, self.port))
        print(f'[{self.service_name}] UDP relay on {self.host}:{self.port}')
        threading.Thread(target=self._recv_loop, daemon=True).start()
    
    def _recv_loop(self) -> None:
        """Loop de recepción y reenvío de paquetes UDP"""
        import struct
        while True:
            try:
                data, addr = self.sock.recvfrom(65536)
                # Verificar que tenga al menos el header básico (room_id + client_id + username_len)
                if len(data) < 12:
                    continue
                
                room_id = struct.unpack('!I', data[0:4])[0]
                
                with self.rooms_lock:
                    if room_id not in self.rooms:
                        self.rooms[room_id] = set()
                    self.rooms[room_id].add(addr)
                    destinations = [a for a in self.rooms[room_id] if a != addr]
                
                # Reenviar a todos los demás en la sala (el paquete ya incluye el username)
                for dest in destinations:
                    try:
                        self.sock.sendto(data, dest)
                    except Exception:
                        pass
            except Exception:
                pass


def get_local_ip() -> str:
    """
    Obtiene la IP local de la máquina usando solo sockets
    Intenta obtener la IP de la interfaz de red activa
    Prioriza IPs privadas (192.168.x.x, 10.x.x.x, 172.16-31.x.x)
    """
    import ipaddress
    
    def is_private_ip(ip_str: str) -> bool:
        """Verifica si una IP es privada (rango local)"""
        try:
            ip = ipaddress.ip_address(ip_str)
            return ip.is_private
        except:
            return False
    
    def is_valid_network_ip(ip_str: str) -> bool:
        """Verifica si una IP es válida para conexiones de red (no localhost, no virtual)"""
        if not ip_str or ip_str.startswith("127.") or ip_str == "0.0.0.0":
            return False
        # Filtrar IPs comunes de interfaces virtuales
        if ip_str.startswith("169.254."):  # Link-local
            return False
        return True
    
    # Método 1: Intentar conectar a un servidor externo para obtener IP de salida
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))  # Google DNS, no hace conexión real
        ip = s.getsockname()[0]
        s.close()
        if is_valid_network_ip(ip):
            return ip
    except Exception:
        pass
    
    # Método 2: Obtener todas las IPs del hostname
    try:
        hostname = socket.gethostname()
        # Obtener todas las IPs asociadas al hostname
        ip_list = socket.gethostbyname_ex(hostname)[2]
        
        # Priorizar IPs privadas
        private_ips = [ip for ip in ip_list if is_private_ip(ip) and is_valid_network_ip(ip)]
        if private_ips:
            return private_ips[0]  # Devolver la primera IP privada
        
        # Si no hay privadas, devolver la primera válida
        valid_ips = [ip for ip in ip_list if is_valid_network_ip(ip)]
        if valid_ips:
            return valid_ips[0]
    except Exception:
        pass
    
    # Método 3: Fallback - intentar obtener IP de interfaz activa
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("127.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        if is_valid_network_ip(ip):
            return ip
    except Exception:
        pass
    
    # Si todo falla, devolver 0.0.0.0 para que el servidor escuche en todas las interfaces
    return "0.0.0.0"


def main() -> None:
    """
    Función principal del servidor
    Patrón: Factory - Crea instancias de los diferentes servidores
    """
    # Singleton: obtener instancia única de Database
    db = Database()
    print('[DB] Base de datos inicializada')
    
    # Factory: crear servidores
    chat_server = ChatServer(CHAT_HOST, CHAT_PORT, db)
    file_server = FileServer(FILE_HOST, FILE_PORT)
    media_relay = UdpVideoRelay(MEDIA_HOST, MEDIA_PORT, service_name='VIDEO')
    audio_relay = UdpVideoRelay(MEDIA_HOST, AUDIO_PORT, service_name='AUDIO')
    
    # Iniciar todos los servicios
    chat_server.start()
    file_server.start()
    media_relay.start()
    audio_relay.start()
    
    local_ip = get_local_ip()
    print('[SERVER] All services started. Press Ctrl+C to stop.')
    print(f'[SERVER] Para conectarte desde otra máquina, usa esta IP: {local_ip}')
    print(f'[SERVER] Ejemplo: python client.py --host {local_ip}')
    
    # Mostrar todas las IPs disponibles para ayudar a diagnosticar
    try:
        import ipaddress
        hostname = socket.gethostname()
        all_ips = socket.gethostbyname_ex(hostname)[2]
        valid_ips = [ip for ip in all_ips if not ip.startswith("127.") and ip != "0.0.0.0"]
        if len(valid_ips) > 1:
            print(f'[SERVER] IPs disponibles en esta máquina: {", ".join(valid_ips)}')
            print(f'[SERVER] Si {local_ip} no funciona, prueba con las otras IPs mostradas arriba')
    except Exception:
        pass
    
    print(f'[SERVER] Asegúrate de permitir estos puertos en el firewall:')
    print(f'[SERVER]   - TCP {CHAT_PORT} (Chat)')
    print(f'[SERVER]   - TCP {FILE_PORT} (Archivos)')
    print(f'[SERVER]   - UDP {MEDIA_PORT} (Video)')
    print(f'[SERVER]   - UDP {AUDIO_PORT} (Audio)')
    
    try:
        while True:
            threading.Event().wait(3600)
    except KeyboardInterrupt:
        print('\n[SERVER] Shutting down...')
        db.close()


if __name__ == '__main__':
    main()
