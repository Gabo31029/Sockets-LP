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
python client.py --name TU_NOMBRE
```

**Desde otra máquina en la red:**
```bash
# Reemplaza IP_DEL_SERVIDOR con la IP que muestra el servidor al iniciar
python client.py --name TU_NOMBRE --host IP_DEL_SERVIDOR
```

Ejemplo:
```bash
python client.py --name Juan --host 192.168.1.100
```

Comandos desde el cliente:

- Texto normal: escribe y Enter para enviar.
- `/upload <ruta_archivo>` - Sube un archivo al servidor y notifica a los demás usuarios.
- `/download <file_id>` - Descarga un archivo compartido usando su ID (se muestra cuando alguien comparte un archivo).
- `/call start` - Inicia/une videollamada (usa cámara, puerto UDP). Presiona `q` en la ventana de video para terminar.
- `/call stop` - Sale de la videollamada.
- `/quit` - Cierra el cliente.

Puertos por defecto:

- Chat TCP: 9009
- Archivos TCP: 9010
- Media relay UDP (video): 9020

Notas:

- El video usa OpenCV. Si no tienes cámara o permisos, la videollamada no iniciará.
- Audio no está habilitado por defecto para simplificar dependencias. Puede ampliarse.
- El servidor guarda archivos entrantes en `server_storage/` y los clientes en `downloads/`.

**Solución de problemas:**

- **Error 10061 (Conexión rechazada)**: El firewall de Windows está bloqueando las conexiones. Ejecuta el script `configurar_firewall.ps1` como administrador.
- **No puedo conectarme desde otra máquina**: Verifica que ambas máquinas estén en la misma red y que uses la IP correcta del servidor (la que muestra al iniciar).
- **El servidor no muestra la IP**: Verifica que tengas conexión a internet o usa `ipconfig` para encontrar tu IP local manualmente.
