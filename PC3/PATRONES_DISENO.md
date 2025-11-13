# Patrones de Diseño Aplicados

Este documento describe los patrones de diseño implementados en el proyecto.

## 1. Singleton (Patrón Creacional)

**Ubicación:** `database.py` - Clase `Database`

**Descripción:** Asegura que solo exista una instancia de la clase Database en toda la aplicación, evitando múltiples conexiones a la base de datos.

**Implementación:**
```python
_instance = None
_lock = threading.Lock()

def __new__(cls):
    if cls._instance is None:
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(Database, cls).__new__(cls)
    return cls._instance
```

**Beneficios:**
- Control centralizado de la conexión a la base de datos
- Evita conexiones duplicadas
- Thread-safe

---

## 2. Factory (Patrón Creacional)

**Ubicación:** 
- `message_handlers.py` - Clase `MessageHandlerFactory`
- `server.py` - Función `main()` (crea instancias de servidores)

**Descripción:** Centraliza la creación de objetos, permitiendo crear handlers de mensajes o servidores sin conocer los detalles de implementación.

**Implementación:**
```python
class MessageHandlerFactory:
    _handlers = [TextMessageHandler(), FileAvailableHandler(), CallActionHandler()]
    
    @classmethod
    def get_handler(cls, message_type: str) -> Optional[MessageHandler]:
        for handler in cls._handlers:
            if handler.can_handle(message_type):
                return handler
        return None
```

**Beneficios:**
- Desacopla la creación de objetos de su uso
- Facilita agregar nuevos tipos de handlers
- Centraliza la lógica de selección

---

## 3. Strategy (Patrón Comportamental)

**Ubicación:** `message_handlers.py` - Clases `MessageHandler` y sus implementaciones

**Descripción:** Define una familia de algoritmos (handlers de mensajes), los encapsula y los hace intercambiables. Permite que el algoritmo varíe independientemente de los clientes que lo usan.

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
    # ...
```

**Beneficios:**
- Facilita agregar nuevos tipos de mensajes
- Separa la lógica de procesamiento
- Permite cambiar algoritmos en tiempo de ejecución

---

## 4. Observer (Patrón Comportamental)

**Ubicación:** 
- `server.py` - Clase `ChatServer` (sistema de broadcast)
- `client.py` - Clase `ChatClient._recv_loop()` (observa mensajes del servidor)

**Descripción:** Define una dependencia uno-a-muchos entre objetos, de manera que cuando un objeto cambia de estado, todos sus dependientes son notificados automáticamente.

**Implementación:**
```python
# Servidor: mantiene lista de observadores (clientes)
self.clients: Dict[socket.socket, str] = {}

# Notificar a todos los observadores
def broadcast_to_all(clients, clients_lock, payload):
    for client_sock in clients.keys():
        ProtocolHandler.send_json(client_sock, payload)
```

**Beneficios:**
- Desacopla el sujeto (servidor) de los observadores (clientes)
- Permite notificar a múltiples clientes sin conocerlos directamente
- Facilita agregar/remover observadores dinámicamente

---

## 5. Facade (Patrón Estructural)

**Ubicación:**
- `protocol.py` - Clase `ProtocolHandler`
- `client.py` - Clases `ChatClient`, `VideoClient`, función `select_file()`
- `server.py` - Clase `UdpVideoRelay`

**Descripción:** Proporciona una interfaz unificada y simplificada a un conjunto de interfaces en un subsistema.

**Implementación:**
```python
class ProtocolHandler:
    @staticmethod
    def send_json(sock, payload):
        # Oculta la complejidad de serialización y envío
        data = json.dumps(payload).encode('utf-8')
        header = struct.pack('!I', len(data))
        sock.sendall(header + data)
```

**Beneficios:**
- Simplifica interfaces complejas
- Oculta la complejidad de implementación
- Facilita el uso del sistema

---

## 6. Template Method (Patrón Comportamental)

**Ubicación:** `server.py` - Clase `BaseServer`

**Descripción:** Define el esqueleto de un algoritmo en una clase base, permitiendo que las subclases redefinan ciertos pasos del algoritmo sin cambiar su estructura.

**Implementación:**
```python
class BaseServer:
    def start(self):
        # Template method: define el flujo
        self.server_sock.bind((self.host, self.port))
        self.server_sock.listen()
        threading.Thread(target=self._accept_loop, daemon=True).start()
    
    def _accept_loop(self):
        # Debe ser implementado por subclases
        raise NotImplementedError
```

**Beneficios:**
- Reutiliza código común
- Establece estructura común para servidores
- Permite personalización en subclases

---

## 7. Repository (Patrón Arquitectónico)

**Ubicación:** `database.py` - Clase `Database`

**Descripción:** Abstrae el acceso a datos, proporcionando una interfaz más orientada a objetos para acceder a la capa de persistencia.

**Implementación:**
```python
class Database:
    def register_user(self, username: str, password: str) -> Tuple[bool, str]:
        # Abstrae el acceso a la tabla users
        cursor.execute("INSERT INTO users ...")
    
    def login_user(self, username: str, password: str) -> Tuple[bool, str]:
        # Abstrae la consulta de autenticación
        cursor.execute("SELECT id FROM users WHERE ...")
```

**Beneficios:**
- Separa la lógica de negocio del acceso a datos
- Facilita testing (puede mockearse)
- Centraliza la lógica de acceso a datos

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

## Beneficios Generales

1. **Mantenibilidad:** Código más organizado y fácil de modificar
2. **Extensibilidad:** Fácil agregar nuevas funcionalidades
3. **Testabilidad:** Componentes desacoplados son más fáciles de testear
4. **Reutilización:** Código común reutilizable
5. **Claridad:** Estructura clara y bien definida

