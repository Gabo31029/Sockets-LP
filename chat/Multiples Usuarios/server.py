import socket
import threading

sv_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
host = '10.49.148.65'
port = 5000

sv_socket.bind((host, port))
sv_socket.listen(5)
print(f"Servidor escuchando en {host}:{port}")

clientes = {}

def exit_all():
    for cliente in list(clientes.keys()):
        try:
            clientes[cliente][0].send("exit".encode())
            clientes[cliente][0].close()
            del clientes[cliente]
        except:
            pass

def transmision_server():
    while True:
        msg_in = input(">>> ")
        if msg_in.lower() == "exit":
            print("Cerrando el servidor...")
            exit_all()
            sv_socket.close()
            break
        transmision("Servidor", f"Servidor: {msg_in}")

def transmision(cliente_in: str, mensaje: str):
    for cliente_out in clientes.keys():
        if cliente_out != cliente_in:
            try:
                clientes[cliente_out][0].send(mensaje.encode())
            except:
                print(f"No se pudo enviar el mensaje a {cliente_out}")

def manejar_cliente(nombre_cliente: str):
    conn, addr = clientes[nombre_cliente]
    print(f"Cliente {nombre_cliente} conectado desde {addr}")

    while True:
        try:
            msg_in = conn.recv(1024).decode()
        except:
            break
        if not msg_in:
            print(f"El cliente {nombre_cliente} cerró la conexión.")
            break
        if msg_in.lower() == "exit":
            print(f"{nombre_cliente} salió del chat.")
            transmision(nombre_cliente, f"{nombre_cliente} salió del chat.")
            break
        transmision(nombre_cliente, f"{nombre_cliente}: {msg_in}")

    conn.close()
    if nombre_cliente in clientes:
        del clientes[nombre_cliente]
    transmision("Servidor", f"{nombre_cliente} se desconectó.")

hilo_server = threading.Thread(target=transmision_server)
hilo_server.start()

while True:
    try:
        conn, addr = sv_socket.accept()
    except:
        break
    conn.send("Ingrese su nombre de usuario: ".encode())
    nombre_cliente = ""
    while True:
        nombre_cliente = conn.recv(1024).decode().strip()
        if nombre_cliente in clientes.keys():
            conn.send("Nombre en uso. Intente otro: ".encode())
        else:
            conn.send(f"Bienvenido al chat, {nombre_cliente}!\n".encode())
            clientes[nombre_cliente] = (conn, addr)
            print(f"Cliente {nombre_cliente} conectado desde {addr}")
            break

    hilo_cliente = threading.Thread(target=manejar_cliente, args=(nombre_cliente,))
    hilo_cliente.start()
