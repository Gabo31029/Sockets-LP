"""
Handlers de mensajes del servidor
Patrón: Strategy - Diferentes estrategias para procesar tipos de mensajes
"""
from abc import ABC, abstractmethod
from typing import Dict, Tuple, Optional
from database import Database
from protocol import ProtocolHandler
import socket


class MessageHandler(ABC):
    """
    Interfaz base para handlers de mensajes
    Patrón: Strategy - Define la interfaz común para diferentes tipos de mensajes
    """
    
    @abstractmethod
    def can_handle(self, message_type: str) -> bool:
        """Verifica si este handler puede procesar el tipo de mensaje"""
        pass
    
    @abstractmethod
    def handle(self, message: Dict, client_sock: socket.socket, 
               username: str, clients: Dict, clients_lock) -> None:
        """Procesa el mensaje"""
        pass


class TextMessageHandler(MessageHandler):
    """Handler para mensajes de texto (Patrón: Strategy)"""
    
    def can_handle(self, message_type: str) -> bool:
        return message_type == 'message'
    
    def handle(self, message: Dict, client_sock: socket.socket,
               username: str, clients: Dict, clients_lock) -> None:
        from server import ChatServer
        ChatServer.broadcast_to_all(clients, clients_lock, {
            'type': 'message',
            'from': username,
            'text': message.get('text', '')
        })


class FileAvailableHandler(MessageHandler):
    """Handler para notificaciones de archivos disponibles (Patrón: Strategy)"""
    
    def can_handle(self, message_type: str) -> bool:
        return message_type == 'file_available'
    
    def handle(self, message: Dict, client_sock: socket.socket,
               username: str, clients: Dict, clients_lock) -> None:
        from server import ChatServer
        ChatServer.broadcast_to_all(clients, clients_lock, {
            'type': 'file_available',
            'from': username,
            'filename': message.get('filename'),
            'size': message.get('size'),
            'file_id': message.get('file_id'),
        })


class CallActionHandler(MessageHandler):
    """Handler para acciones de videollamada (Patrón: Strategy)"""
    
    def can_handle(self, message_type: str) -> bool:
        return message_type == 'call'
    
    def handle(self, message: Dict, client_sock: socket.socket,
               username: str, clients: Dict, clients_lock) -> None:
        from server import ChatServer
        ChatServer.broadcast_to_all(clients, clients_lock, {
            'type': 'call',
            'from': username,
            'action': message.get('action')
        })


class MessageHandlerFactory:
    """
    Factory para crear handlers de mensajes
    Patrón: Factory - Crea los handlers apropiados
    """
    
    _handlers = [
        TextMessageHandler(),
        FileAvailableHandler(),
        CallActionHandler()
    ]
    
    @classmethod
    def get_handler(cls, message_type: str) -> Optional[MessageHandler]:
        """Obtiene el handler apropiado para el tipo de mensaje"""
        for handler in cls._handlers:
            if handler.can_handle(message_type):
                return handler
        return None


class AuthHandler:
    """
    Handler de autenticación
    Patrón: Strategy - Maneja login y registro
    """
    
    def __init__(self, db: Database):
        self.db = db
    
    def handle_auth(self, auth_msg: Dict, client_sock: socket.socket) -> Tuple[bool, Optional[str]]:
        """
        Maneja la autenticación (login o register)
        Returns: (success, username)
        """
        auth_type = auth_msg.get('type')
        username = auth_msg.get('username', '')
        password = auth_msg.get('password', '')
        
        if auth_type == 'register':
            success, message = self.db.register_user(username, password)
        elif auth_type == 'login':
            success, message = self.db.login_user(username, password)
        else:
            ProtocolHandler.send_json(client_sock, {
                'type': 'auth_response',
                'success': False,
                'message': 'Tipo de autenticación inválido'
            })
            return False, None
        
        ProtocolHandler.send_json(client_sock, {
            'type': 'auth_response',
            'success': success,
            'message': message
        })
        
        if success:
            ProtocolHandler.send_json(client_sock, {
                'type': 'auth_success',
                'username': username
            })
            return True, username
        
        return False, None

