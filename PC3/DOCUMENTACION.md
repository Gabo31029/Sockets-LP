# Documentación Completa del Proyecto - Sistema de Chat con Videollamadas

## Tabla de Contenidos

1. [Arquitectura General](#arquitectura-general)
2. [Componentes del Sistema](#componentes-del-sistema)
3. [Protocolos de Comunicación](#protocolos-de-comunicación)
4. [Flujo de Datos](#flujo-de-datos)
5. [Patrones de Diseño Implementados](#patrones-de-diseño-implementados)
6. [Base de Datos](#base-de-datos)
7. [Guía de Uso](#guía-de-uso)

---

## Arquitectura General

El proyecto implementa un sistema cliente-servidor de chat en tiempo real con las siguientes características:

- **Comunicación TCP**: Para chat y transferencia de archivos (conexiones confiables)
- **Comunicación UDP**: Para videollamadas (baja latencia, tolerante a pérdidas)
- **Base de Datos MySQL**: Para autenticación de usuarios
- **Arquitectura multihilo**: Servidor concurrente que maneja múltiples clientes simultáneamente

### Diagrama de Arquitectura

```
┌─────────────┐         ┌──────────────┐         ┌─────────────┐
│   Cliente 1 │────────▶│              │◀────────│   Cliente 2 │
│             │  TCP    │   Servidor   │  TCP    │             │
│  - Chat     │  :9009  │              │  :9009  │  - Chat     │
│  - Archivos │  :9010  │  - Chat      │  :9010  │  - Archivos │
│  - Video    │  :9020  │  - Archivos  │  :9020  │  - Video    │
└─────────────┘  UDP    │  - Video     │  UDP    └─────────────┘
                        │  - MySQL     │
                        └──────┬───────┘
                               │
                        ┌──────▼───────┐
                        │   MySQL DB   │
                        │  (usuarios)  │
                        └──────────────┘
```

---

## Componentes del Sistema

### Servidor (`server.py`)

El servidor está compuesto por tres servicios independientes:

#### 1. ChatServer (Puerto TCP 9009)
- **Función**: Maneja mensajes de texto y autenticación
- **Protocolo**: TCP con mensajes JSON length-prefixed
- **Características**:
  - Autenticación (login/register)
  - Broadcast de mensajes a todos los clientes
  - Notificaciones de sistema

#### 2. FileServer (Puerto TCP 9010)
- **Función**: Maneja subida y descarga de archivos
- **Protocolo**: TCP con JSON + datos binarios
- **Características**:
  - Almacenamiento temporal de archivos
  - Índice de archivos compartidos
  - Transferencia en chunks de 64KB

#### 3. UdpVideoRelay (Puerto UDP 9020)
- **Función**: Relay de paquetes de video entre clientes
- **Protocolo**: UDP con paquetes binarios
- **Características**:
  - Agrupa clientes por `room_id`
  - Reenvía paquetes a todos en la misma sala
  - No procesa el contenido, solo reenvía

### Cliente (`client.py`)

El cliente tiene tres componentes principales:

#### 1. ChatClient
- **Función**: Maneja la conexión de chat y autenticación
- **Características**:
  - Login/Register
  - Envío/recepción de mensajes
  - Notificaciones de archivos y llamadas

#### 2. FileClient
- **Función**: Sube y descarga archivos
- **Características**:
  - Diálogo de selección de archivos (tkinter)
  - Transferencia de archivos grandes
  - Notificación automática al chat

#### 3. VideoClient
- **Función**: Maneja videollamadas
- **Características**:
  - Captura de video con OpenCV
  - Envío/recepción de frames por UDP
  - Visualización en grid (todos los videos en una ventana)

---

## Protocolos de Comunicación

### Protocolo TCP (Chat y Archivos)

**Formato de Mensaje:**
```
[4 bytes: longitud] [N bytes: JSON]
```

**Ejemplo de Mensaje:**
```json
{
  "type": "message",
  "text": "Hola mundo"
}
```

**Tipos de Mensajes:**
- `login` / `register`: Autenticación
- `message`: Mensaje de texto
- `file_available`: Notificación de archivo
- `call`: Acción de videollamada (start/stop)
- `quit`: Desconexión

### Protocolo UDP (Video)

**Formato de Paquete:**
```
[4 bytes: room_id] [4 bytes: client_id] [4 bytes: username_len] [N bytes: username] [M bytes: JPEG frame]
```

**Ejemplo:**
```
room_id=1 (4 bytes)
client_id=123456 (4 bytes)
username_len=5 (4 bytes)
username="Juan" (5 bytes)
JPEG frame data (variable)
```

---

## Flujo de Datos

### 1. Autenticación

```
Cliente                    Servidor                    MySQL
  │                          │                          │
  │─── login/register ───────▶│                          │
  │                          │─── verificar/crear ─────▶│
  │                          │◀─── resultado ───────────│
  │◀── auth_response ────────│                          │
  │◀── auth_success ─────────│                          │
  │                          │                          │
```

**Código relevante:**
- `client.py`: `ChatClient.authenticate()`
- `server.py`: `ChatServer._handle_client()` (líneas 79-96)
- `message_handlers.py`: `AuthHandler.handle_auth()`

### 2. Envío de Mensaje

```
Cliente A                  Servidor                  Cliente B
  │                          │                          │
  │─── message ──────────────▶│                          │
  │                          │─── broadcast ────────────▶│
  │                          │                          │◀── mensaje recibido
```

**Código relevante:**
- `client.py`: `ChatClient.send_message()`
- `server.py`: `ChatServer.broadcast_to_all()`
- `message_handlers.py`: `TextMessageHandler.handle()`

### 3. Transferencia de Archivos

#### Subida:
```
Cliente                    Servidor
  │                          │
  │─── upload (JSON) ───────▶│
  │─── datos binarios ───────▶│─── guardar en disco
  │◀── upload_ok ────────────│
  │─── notify (chat) ────────▶│─── broadcast
```

#### Descarga:
```
Cliente                    Servidor
  │                          │
  │─── download (JSON) ─────▶│
  │◀── download_meta ────────│
  │◀── datos binarios ───────│
```

**Código relevante:**
- `client.py`: `FileClient.upload_file()`, `FileClient.download_file()`
- `server.py`: `FileServer._handle_upload()`, `FileServer._handle_download()`

### 4. Videollamada

```
Cliente A                  Servidor UDP              Cliente B
  │                          │                          │
  │─── frame ───────────────▶│                          │
  │                          │─── reenviar ────────────▶│
  │                          │                          │◀── frame recibido
  │                          │◀── frame ────────────────│
  │◀── frame ────────────────│                          │
```

**Código relevante:**
- `client.py`: `VideoClient._send_loop()`, `VideoClient._recv_loop()`
- `server.py`: `UdpVideoRelay._recv_loop()`

---

## Patrones de Diseño Implementados

### 1. Singleton (Creacional)

**Ubicación:** `database.py` - Clase `Database`

**Propósito:** Asegurar una única instancia de la conexión a la base de datos en toda la aplicación.

**Implementación:**
```python
class Database:
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(Database, cls).__new__(cls)
        return cls._instance
```

**Cómo Funciona:**
1. La primera vez que se crea `Database()`, se crea la instancia
2. Las siguientes llamadas retornan la misma instancia
3. Thread-safe usando locks para evitar condiciones de carrera

**Beneficios:**
- Evita múltiples conexiones a MySQL
- Control centralizado de la conexión
- Ahorro de recursos

**Uso en el Proyecto:**
```python
# En server.py
db = Database()  # Primera vez: crea instancia
db2 = Database()  # Retorna la misma instancia
```

---

### 2. Factory (Creacional)

**Ubicación:** 
- `message_handlers.py` - `MessageHandlerFactory`
- `server.py` - función `main()`

**Propósito:** Centralizar la creación de objetos sin exponer la lógica de creación.

#### Factory de Handlers

**Implementación:**
```python
class MessageHandlerFactory:
    _handlers = [
        TextMessageHandler(),
        FileAvailableHandler(),
        CallActionHandler()
    ]
    
    @classmethod
    def get_handler(cls, message_type: str):
        for handler in cls._handlers:
            if handler.can_handle(message_type):
                return handler
        return None
```

**Cómo Funciona:**
1. El servidor recibe un mensaje con `type`
2. Llama a `MessageHandlerFactory.get_handler(type)`
3. El factory retorna el handler apropiado
4. El servidor usa el handler para procesar el mensaje

**Flujo:**
```
Mensaje recibido
    │
    ▼
MessageHandlerFactory.get_handler("message")
    │
    ▼
TextMessageHandler.handle()
```

#### Factory de Servidores

**Implementación:**
```python
# En server.py main()
chat_server = ChatServer(CHAT_HOST, CHAT_PORT, db)
file_server = FileServer(FILE_HOST, FILE_PORT)
media_relay = UdpVideoRelay(MEDIA_HOST, MEDIA_PORT)
```

**Beneficios:**
- Fácil agregar nuevos tipos de mensajes
- Desacopla la creación del uso
- Centraliza la lógica de selección

---

### 3. Strategy (Comportamental)

**Ubicación:** `message_handlers.py` - Clases `MessageHandler` y subclases

**Propósito:** Definir una familia de algoritmos (handlers), encapsularlos y hacerlos intercambiables.

**Implementación:**
```python
class MessageHandler(ABC):
    @abstractmethod
    def can_handle(self, message_type: str) -> bool:
        pass
    
    @abstractmethod
    def handle(self, message: Dict, ...) -> None:
        pass

class TextMessageHandler(MessageHandler):
    def can_handle(self, message_type: str) -> bool:
        return message_type == 'message'
    
    def handle(self, message: Dict, ...):
        # Procesar mensaje de texto
        ChatServer.broadcast_to_all(...)
```

**Cómo Funciona:**
1. Cada tipo de mensaje tiene su propio handler (estrategia)
2. Todos implementan la misma interfaz `MessageHandler`
3. El servidor selecciona la estrategia apropiada según el tipo
4. Cada estrategia procesa el mensaje de forma diferente

**Flujo:**
```
Mensaje: {"type": "message", "text": "Hola"}
    │
    ▼
Factory.get_handler("message")
    │
    ▼
TextMessageHandler.handle()
    │
    ▼
Broadcast a todos los clientes
```

**Estrategias Implementadas:**
- `TextMessageHandler`: Mensajes de texto
- `FileAvailableHandler`: Notificaciones de archivos
- `CallActionHandler`: Acciones de videollamada

**Beneficios:**
- Fácil agregar nuevos tipos de mensajes
- Código más organizado y mantenible
- Cada handler es independiente

---

### 4. Observer (Comportamental)

**Ubicación:** 
- `server.py` - `ChatServer.broadcast_to_all()`
- `client.py` - `ChatClient._recv_loop()`

**Propósito:** Definir una dependencia uno-a-muchos entre objetos, de manera que cuando un objeto cambia de estado, todos sus dependientes son notificados.

#### En el Servidor (Sujeto)

**Implementación:**
```python
class ChatServer:
    def __init__(self, ...):
        self.clients: Dict[socket.socket, str] = {}  # Lista de observadores
    
    def _handle_client(self, ...):
        # Agregar observador
        self.clients[client_sock] = username
    
    @staticmethod
    def broadcast_to_all(clients, clients_lock, payload):
        # Notificar a todos los observadores
        for client_sock in clients.keys():
            ProtocolHandler.send_json(client_sock, payload)
```

**Cómo Funciona:**
1. Los clientes se registran como observadores al conectarse
2. Cuando ocurre un evento (mensaje, archivo, llamada), el servidor notifica a todos
3. Cada cliente recibe y procesa la notificación

**Flujo:**
```
Evento: Nuevo mensaje
    │
    ▼
ChatServer.broadcast_to_all()
    │
    ├──▶ Cliente 1 (observador)
    ├──▶ Cliente 2 (observador)
    └──▶ Cliente 3 (observador)
```

#### En el Cliente (Observador)

**Implementación:**
```python
class ChatClient:
    def _recv_loop(self):
        while self.running:
            msg = ProtocolHandler.recv_json(self.sock)
            # Reaccionar a la notificación
            if msg['type'] == 'message':
                print(f"[{msg['from']}]: {msg['text']}")
```

**Beneficios:**
- Desacopla el servidor de los clientes
- Fácil agregar/remover clientes dinámicamente
- Notificaciones automáticas a todos

---

### 5. Facade (Estructural)

**Ubicación:**
- `protocol.py` - `ProtocolHandler`
- `client.py` - `ChatClient`, `VideoClient`, `select_file()`
- `server.py` - `UdpVideoRelay`

**Propósito:** Proporcionar una interfaz unificada y simplificada a un conjunto de interfaces en un subsistema.

#### ProtocolHandler (Facade de Comunicación)

**Implementación:**
```python
class ProtocolHandler:
    @staticmethod
    def send_json(sock, payload):
        # Oculta: serialización JSON, encoding, struct packing, etc.
        data = json.dumps(payload).encode('utf-8')
        header = struct.pack('!I', len(data))
        sock.sendall(header + data)
    
    @staticmethod
    def recv_json(sock):
        # Oculta: struct unpacking, decoding, JSON parsing, etc.
        header = _recv_exact(sock, 4)
        length = struct.unpack('!I', header)[0]
        data = _recv_exact(sock, length)
        return json.loads(data.decode('utf-8'))
```

**Cómo Funciona:**
- Antes: El código tenía que hacer manualmente: `json.dumps()` → `encode()` → `struct.pack()` → `sendall()`
- Ahora: Solo llama `ProtocolHandler.send_json(sock, payload)`
- Oculta toda la complejidad de serialización

**Uso:**
```python
# Antes (complejo):
data = json.dumps(payload).encode('utf-8')
header = struct.pack('!I', len(data))
sock.sendall(header + data)

# Ahora (simple):
ProtocolHandler.send_json(sock, payload)
```

**Beneficios:**
- Simplifica el código
- Centraliza la lógica de protocolo
- Fácil cambiar el protocolo en el futuro

#### ChatClient (Facade del Cliente)

**Implementación:**
```python
class ChatClient:
    def send_message(self, text):
        # Oculta: creación de mensaje, envío, manejo de errores
        ProtocolHandler.send_json(self.sock, {'type': 'message', 'text': text})
```

**Beneficios:**
- El usuario solo llama `chat.send_message("Hola")`
- No necesita saber sobre sockets, protocolos, etc.

---

### 6. Template Method (Comportamental)

**Ubicación:** `server.py` - Clase `BaseServer`

**Propósito:** Definir el esqueleto de un algoritmo en una clase base, permitiendo que las subclases redefinan ciertos pasos sin cambiar la estructura.

**Implementación:**
```python
class BaseServer:
    def start(self):
        # Template method: define el flujo común
        self.server_sock.bind((self.host, self.port))
        self.server_sock.listen()
        threading.Thread(target=self._accept_loop, daemon=True).start()
    
    def _accept_loop(self):
        # Debe ser implementado por subclases
        raise NotImplementedError
    
    def _handle_client(self, ...):
        # Debe ser implementado por subclases
        raise NotImplementedError

class ChatServer(BaseServer):
    def _accept_loop(self):
        # Implementación específica para chat
        while True:
            client_sock, addr = self.server_sock.accept()
            threading.Thread(target=self._handle_client, ...).start()
    
    def _handle_client(self, ...):
        # Implementación específica para chat
        # Autenticación, procesamiento de mensajes, etc.
```

**Cómo Funciona:**
1. `BaseServer.start()` define el algoritmo común (template)
2. Las subclases implementan los pasos específicos
3. Todas las subclases siguen la misma estructura

**Flujo:**
```
BaseServer.start() (template)
    │
    ├── bind()
    ├── listen()
    └── _accept_loop() (implementado por subclase)
            │
            └── _handle_client() (implementado por subclase)
```

**Beneficios:**
- Reutiliza código común
- Estructura consistente para todos los servidores
- Fácil agregar nuevos tipos de servidores

---

### 7. Repository (Arquitectónico)

**Ubicación:** `database.py` - Clase `Database`

**Propósito:** Abstraer el acceso a datos, proporcionando una interfaz más orientada a objetos para acceder a la capa de persistencia.

**Implementación:**
```python
class Database:
    def register_user(self, username: str, password: str) -> Tuple[bool, str]:
        # Abstrae: conexión, query SQL, manejo de errores
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users ...")
        conn.commit()
        return True, "Usuario registrado"
    
    def login_user(self, username: str, password: str) -> Tuple[bool, str]:
        # Abstrae el acceso a la tabla users
        cursor.execute("SELECT id FROM users WHERE ...")
        return success, message
```

**Cómo Funciona:**
1. El código de negocio no conoce SQL directamente
2. Usa métodos del Repository: `db.register_user()`, `db.login_user()`
3. El Repository maneja todos los detalles de la base de datos

**Flujo:**
```
Código de negocio
    │
    ▼
Database.register_user() (Repository)
    │
    ▼
MySQL (implementación)
```

**Beneficios:**
- Separa lógica de negocio de acceso a datos
- Fácil cambiar de MySQL a otra BD
- Facilita testing (puede mockearse)

---

## Base de Datos

### Esquema

```sql
CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP NULL
);
```

### Operaciones

1. **Registro**: `Database.register_user(username, password)`
   - Verifica si el usuario existe
   - Hashea la contraseña (SHA-256)
   - Inserta en la base de datos

2. **Login**: `Database.login_user(username, password)`
   - Hashea la contraseña
   - Busca coincidencia en la BD
   - Actualiza `last_login`

### Seguridad

- Contraseñas hasheadas con SHA-256 (no se almacenan en texto plano)
- Validación de usuarios únicos
- Manejo de errores de conexión

---

## Flujo Completo de una Videollamada

### Paso 1: Inicio

```
Usuario A ejecuta: /call start
    │
    ▼
VideoClient.start()
    │
    ├── Abre cámara (cv2.VideoCapture)
    ├── Crea socket UDP
    └── Inicia 3 threads:
        ├── _send_loop()    (envía frames)
        ├── _recv_loop()    (recibe frames)
        └── _display_loop() (muestra ventana)
    │
    ▼
Envía notificación al chat: "call start"
```

### Paso 2: Otro Usuario se Une

```
Usuario B ejecuta: /call start
    │
    ▼
VideoClient.start() (mismo room_id = 1)
    │
    ▼
Empieza a enviar frames al servidor UDP
```

### Paso 3: Relay del Servidor

```
Servidor UDP recibe frame de Usuario A
    │
    ▼
Extrae room_id = 1
    │
    ▼
Busca todos los clientes en room_id = 1
    │
    ├── Usuario A (remitente, se omite)
    └── Usuario B (destinatario)
    │
    ▼
Reenvía frame a Usuario B
```

### Paso 4: Recepción y Visualización

```
Usuario B recibe frame
    │
    ▼
Extrae: room_id, sender_id, username, frame_data
    │
    ▼
Decodifica JPEG → frame OpenCV
    │
    ▼
Almacena en remote_frames[sender_id]
    │
    ▼
_display_loop() crea grid:
    ├── Frame local (TU VIDEO)
    └── Frame remoto (Usuario A)
    │
    ▼
Muestra en ventana "Videollamada Grupal"
```

---

## Guía de Uso

### Iniciar el Servidor

```bash
python server.py
```

**Salida esperada:**
```
[DB] Base de datos inicializada
[CHAT] Listening on 0.0.0.0:9009
[FILE] Listening on 0.0.0.0:9010
[MEDIA] UDP relay on 0.0.0.0:9020
[SERVER] All services started...
```

### Iniciar Clientes

```bash
# Cliente 1
python client.py --host IP_DEL_SERVIDOR

# Cliente 2 (en otra terminal)
python client.py --host IP_DEL_SERVIDOR
```

### Flujo de Autenticación

1. Cliente se conecta al servidor
2. Selecciona Login o Register
3. Ingresa usuario y contraseña
4. Servidor valida/crea en MySQL
5. Cliente recibe confirmación y puede usar el chat

### Comandos Disponibles

- **Mensaje de texto**: Escribe y presiona Enter
- **`/upload`**: Abre diálogo para seleccionar archivo
- **`/download <file_id>`**: Descarga un archivo compartido
- **`/call start`**: Inicia/une videollamada (todos en room_id=1)
- **`/call stop`**: Sale de la videollamada
- **`/quit`**: Cierra el cliente

---

## Detalles Técnicos

### Threading

**Servidor:**
- Cada cliente tiene su propio thread
- Threads daemon (se cierran al terminar el programa)
- Locks para proteger estructuras compartidas

**Cliente:**
- Thread separado para recibir mensajes
- Threads separados para video (enviar, recibir, mostrar)

### Manejo de Errores

- Timeouts en sockets para evitar bloqueos
- Try-except en loops críticos
- Limpieza de recursos en finally blocks
- Mensajes de error descriptivos

### Optimizaciones

- Frames de video redimensionados (320x240) para menor ancho de banda
- JPEG con calidad 70% para balance tamaño/calidad
- Chunks de 64KB para transferencia de archivos
- Timeout de 0.1s en UDP para no bloquear

---

## Resumen de Patrones por Archivo

| Archivo | Patrones Aplicados |
|---------|-------------------|
| `database.py` | Singleton, Repository, Factory (conexiones) |
| `protocol.py` | Facade |
| `message_handlers.py` | Strategy, Factory |
| `server.py` | Observer, Template Method, Factory |
| `client.py` | Facade, Observer, Strategy |

---

## Conclusión

Este proyecto demuestra una arquitectura bien estructurada usando patrones de diseño estándar, lo que resulta en:

- **Código mantenible**: Fácil de entender y modificar
- **Extensible**: Fácil agregar nuevas funcionalidades
- **Robusto**: Manejo adecuado de errores y recursos
- **Eficiente**: Uso apropiado de threading y protocolos

Los patrones de diseño no son solo teoría, sino herramientas prácticas que mejoran la calidad del código y facilitan el mantenimiento a largo plazo.

