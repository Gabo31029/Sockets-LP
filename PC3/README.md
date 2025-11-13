# PC3 - Chat cliente/servidor con sockets (mensajes, archivos y videollamadas)

Este proyecto implementa:

- Chat multiusuario (una sola sala) sobre TCP.
- Envío de mensajes de texto sin bloquear.
- Envío/recepción de archivos grandes (imágenes, videos, audios, etc.) por un canal TCP separado para no bloquear el chat.
- Señalización para llamadas y videollamadas y un relay UDP simple para videollamadas (video). Mensajería continúa mientras se transmite.

Requisitos (Windows):

```bash
pip install -r requirements.txt
```

**Configuración de MySQL:**

1. Asegúrate de tener MySQL instalado y ejecutándose
2. **Configurar base de datos:**
   - Copia `.env.example` a `.env`: `copy .env.example .env` (Windows) o `cp .env.example .env` (Linux/Mac)
   - Edita `.env` y completa con tus valores de MySQL
   - Ejecuta el script SQL: `mysql -u root -p < schema.sql`
3. **Opcional:** La base de datos se creará automáticamente al iniciar el servidor si no existe

**Variables en .env:**
- `DB_HOST` - Host de MySQL (por defecto: localhost)
- `DB_NAME` - Nombre de la base de datos (por defecto: chat_app)
- `DB_USER` - Usuario de MySQL (por defecto: root)
- `DB_PASSWORD` - Contraseña de MySQL (déjalo vacío si no tienes)
- `DB_PORT` - Puerto de MySQL (por defecto: 3306)

**Nota:** Si no creas el archivo `.env`, el sistema usará los valores por defecto.

Ejecutar servidor (3 servicios en uno):

```bash
# En una terminal
python server.py
```

El servidor mostrará la IP local que debes usar para conectarte desde otras máquinas.

**IMPORTANTE: Configurar el Firewall de Windows**

Antes de conectarte desde otra máquina, debes permitir los puertos en el firewall:

**Opción 1: Script automático (Recomendado)**
```powershell
# Ejecutar PowerShell como Administrador
PowerShell -ExecutionPolicy Bypass -File configurar_firewall.ps1
```

**Opción 2: Manualmente**
1. Abre "Firewall de Windows Defender" desde el Panel de Control
2. Haz clic en "Configuración avanzada"
3. Haz clic en "Reglas de entrada" → "Nueva regla"
4. Selecciona "Puerto" → Siguiente
5. TCP → Puertos específicos: `9009, 9010` → Siguiente
6. Permitir la conexión → Siguiente
7. Marca todos los perfiles → Siguiente
8. Nombre: "PC3 Chat Server TCP" → Finalizar
9. Repite para UDP puerto `9020`

Ejecutar cliente(s):

**Desde la misma máquina:**
```bash
python client.py
```

**Desde otra máquina en la red:**
```bash
# Reemplaza IP_DEL_SERVIDOR con la IP que muestra el servidor al iniciar
python client.py --host IP_DEL_SERVIDOR
```

Ejemplo:
```bash
python client.py --host 192.168.1.100
```

**Nota:** Al iniciar el cliente, se te pedirá:
1. Login (si ya tienes cuenta) o Register (para crear nueva cuenta)
2. Usuario y contraseña

Comandos desde el cliente:

- Texto normal: escribe y Enter para enviar.
- `/upload` - Abre un diálogo de Windows para seleccionar y subir un archivo (también puedes usar `/upload <ruta>` para especificar la ruta manualmente).
- `/download <file_id>` - Descarga un archivo compartido usando su ID (se muestra cuando alguien comparte un archivo).
- `/call start` - Inicia/une videollamada grupal (usa cámara, puerto UDP). Todos los videos aparecen en una sola ventana en formato grid.
- `/call stop` - Sale de la videollamada.
- `/quit` - Cierra el cliente.

Puertos por defecto:

- Chat TCP: 9009
- Archivos TCP: 9010
- Media relay UDP (video): 9020

Notas:

- **Autenticación:** Los usuarios deben registrarse o hacer login antes de usar el chat. Las contraseñas se almacenan con hash SHA-256.
- **Videollamada grupal:** Todos los videos (local y remotos) se muestran en una sola ventana en formato grid:
  - 1 video: pantalla completa
  - 2 videos: lado a lado
  - 3 videos: 2 arriba, 1 abajo
  - 4 videos: grid 2x2
  - 5-9 videos: grid 3x3
- **Selección de archivos:** Usa `/upload` sin parámetros para abrir el diálogo de Windows.
- El video usa OpenCV. Si no tienes cámara o permisos, la videollamada no iniciará.
- Audio no está habilitado por defecto para simplificar dependencias. Puede ampliarse.
- El servidor guarda archivos entrantes en `server_storage/` y los clientes en `downloads/`.

**Solución de problemas:**

- **Error 10061 (Conexión rechazada)**: El firewall de Windows está bloqueando las conexiones. Ejecuta el script `configurar_firewall.ps1` como administrador.
- **No puedo conectarme desde otra máquina**: Verifica que ambas máquinas estén en la misma red y que uses la IP correcta del servidor (la que muestra al iniciar).
- **El servidor no muestra la IP**: Verifica que tengas conexión a internet o usa `ipconfig` para encontrar tu IP local manualmente.

## Patrones de Diseño

El proyecto implementa varios patrones de diseño para mejorar la mantenibilidad y extensibilidad:

- **Singleton:** Base de datos (una única instancia)
- **Factory:** Creación de handlers y servidores
- **Strategy:** Diferentes handlers para tipos de mensajes
- **Observer:** Sistema de broadcast a clientes
- **Facade:** Simplificación de interfaces complejas
- **Template Method:** Estructura común para servidores
- **Repository:** Abstracción del acceso a datos

Ver `PATRONES_DISENO.md` para más detalles sobre cada patrón implementado.
