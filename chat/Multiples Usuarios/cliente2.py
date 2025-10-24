import socket
import threading

client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
host = 'localhost'
port = 5000

try:
    client_socket.connect((host, port))
except Exception as e:
    print("No se pudo conectar al servidor:", e)
    raise SystemExit

try:
    prompt = client_socket.recv(1024).decode()
except Exception:
    print("No se pudo recibir el prompt del servidor.")
    client_socket.close()
    raise SystemExit

print(prompt)

nombre = ""
while not nombre.strip():
    nombre = input().strip()
    if not nombre:
        print("Nombre inválido. Intenta de nuevo:")

try:
    client_socket.send(nombre.encode())
except Exception:
    print("No se pudo enviar el nombre al servidor.")
    client_socket.close()
    raise SystemExit

stop_event = threading.Event()

def recibir_mensajes():
    while not stop_event.is_set():
        try:
            msg_in = client_socket.recv(1024).decode()
        except Exception:
            break
        if not msg_in:
            print("El servidor cerró la conexión.")
            break
        if msg_in.lower() == "exit":
            print("El servidor cerró el chat.")
            stop_event.set()
            try:
                client_socket.shutdown(socket.SHUT_RDWR)
            except:
                pass
            try:
                client_socket.close()
            except:
                pass
            break
        print(msg_in)

hilo_receptor = threading.Thread(target=recibir_mensajes, daemon=True)
hilo_receptor.start()

try:
    while not stop_event.is_set():
        try:
            msg = input()
        except EOFError:
            msg = "exit"
        if not msg.strip():
            continue
        try:
            client_socket.send(msg.encode())
        except Exception:
            break
        if msg.lower() == "exit":
            stop_event.set()
            try:
                client_socket.shutdown(socket.SHUT_RDWR)
            except:
                pass
            try:
                client_socket.close()
            except:
                pass
            break
finally:
    stop_event.set()
    try:
        client_socket.close()
    except:
        pass
    print("Conexión cerrada")
