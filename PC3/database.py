"""
Módulo de base de datos para autenticación de usuarios
Patrón: Singleton - Asegura una única instancia de Database
Patrón: Repository - Abstrae el acceso a datos
"""
import mysql.connector
from mysql.connector import Error
import hashlib
from typing import Optional, Tuple
import os
import threading
from dotenv import load_dotenv

# Cargar variables de entorno desde .env si existe
load_dotenv()


class DatabaseConfig:
    """Configuración de la base de datos (Patrón: Value Object)"""
    def __init__(self):
        self.host = os.getenv('DB_HOST', 'localhost')
        self.database = os.getenv('DB_NAME', 'chat_app')
        self.user = os.getenv('DB_USER', 'root')
        self.password = os.getenv('DB_PASSWORD', '')
        self.port = int(os.getenv('DB_PORT', 3306))
    
    def to_dict(self, include_database: bool = True) -> dict:
        """Convierte la configuración a diccionario para mysql.connector"""
        config = {
            'host': self.host,
            'user': self.user,
            'password': self.password,
            'port': self.port
        }
        if include_database:
            config['database'] = self.database
        return config


class Database:
    """
    Clase para manejar operaciones de base de datos
    Patrón: Singleton - Una sola instancia en toda la aplicación
    Patrón: Repository - Abstrae el acceso a datos de usuarios
    """
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        """Singleton: asegura una única instancia"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(Database, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Inicializa la conexión solo una vez"""
        if hasattr(self, '_initialized'):
            return
        
        self._initialized = True
        self.config = DatabaseConfig()
        self.connection: Optional[mysql.connector.MySQLConnection] = None
        self._connection_lock = threading.Lock()
        self._initialize_database()
    
    def _get_connection(self) -> Optional[mysql.connector.MySQLConnection]:
        """
        Obtiene una conexión a la base de datos (thread-safe)
        Patrón: Factory - Crea conexiones cuando es necesario
        """
        with self._connection_lock:
            try:
                if self.connection is None or not self.connection.is_connected():
                    self.connection = mysql.connector.connect(**self.config.to_dict())
                return self.connection
            except Error as e:
                print(f'[DB] Error conectando a MySQL: {e}')
                return None
    
    def _initialize_database(self) -> None:
        """Inicializa la base de datos y la tabla en una sola operación"""
        try:
            # Crear base de datos si no existe
            temp_conn = mysql.connector.connect(**self.config.to_dict(include_database=False))
            cursor = temp_conn.cursor()
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS {self.config.database}")
            cursor.close()
            temp_conn.close()
            
            # Crear tabla si no existe
            conn = mysql.connector.connect(**self.config.to_dict())
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    username VARCHAR(50) UNIQUE NOT NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP NULL
                )
            """)
            conn.commit()
            cursor.close()
            conn.close()
        except Error as e:
            print(f'[DB] Error inicializando base de datos: {e}')
    
    def hash_password(self, password: str) -> str:
        """Hashea una contraseña usando SHA-256"""
        return hashlib.sha256(password.encode()).hexdigest()
    
    def register_user(self, username: str, password: str) -> Tuple[bool, str]:
        """
        Registra un nuevo usuario (Repository Pattern)
        Returns: (success, message)
        """
        try:
            conn = self._get_connection()
            if not conn:
                return False, "Error de conexión a la base de datos"
            
            cursor = conn.cursor()
            
            # Verificar si el usuario ya existe
            cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
            if cursor.fetchone():
                cursor.close()
                return False, "El usuario ya existe"
            
            # Crear nuevo usuario
            password_hash = self.hash_password(password)
            cursor.execute(
                "INSERT INTO users (username, password_hash) VALUES (%s, %s)",
                (username, password_hash)
            )
            conn.commit()
            cursor.close()
            return True, "Usuario registrado exitosamente"
        except Error as e:
            return False, f"Error al registrar usuario: {e}"
    
    def login_user(self, username: str, password: str) -> Tuple[bool, str]:
        """
        Autentica un usuario (Repository Pattern)
        Returns: (success, message)
        """
        try:
            conn = self._get_connection()
            if not conn:
                return False, "Error de conexión a la base de datos"
            
            cursor = conn.cursor()
            password_hash = self.hash_password(password)
            
            cursor.execute(
                "SELECT id FROM users WHERE username = %s AND password_hash = %s",
                (username, password_hash)
            )
            result = cursor.fetchone()
            
            if result:
                # Actualizar último login
                cursor.execute(
                    "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = %s",
                    (result[0],)
                )
                conn.commit()
                cursor.close()
                return True, "Login exitoso"
            else:
                cursor.close()
                return False, "Usuario o contraseña incorrectos"
        except Error as e:
            return False, f"Error al autenticar: {e}"
    
    def user_exists(self, username: str) -> bool:
        """Verifica si un usuario existe (Repository Pattern)"""
        try:
            conn = self._get_connection()
            if not conn:
                return False
            
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
            result = cursor.fetchone() is not None
            cursor.close()
            return result
        except Error:
            return False
    
    def close(self) -> None:
        """Cierra la conexión a la base de datos"""
        with self._connection_lock:
            if self.connection and self.connection.is_connected():
                self.connection.close()
                self.connection = None
