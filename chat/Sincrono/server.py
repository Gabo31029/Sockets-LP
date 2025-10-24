import socket

server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

host = 'localhost'
port = 123

server_socket.bind((host,port))

server_socket.listen(2)
print(f"Servidor escuchando en {host}: {port} ...")

conn , addr = server_socket.accept()
print(f"Conexion desde {addr}")


while True:
    msg_in = conn.recv(1024).decode()
    if not msg_in:
        print("El cliente cerró la conexión.")
        break
    print(f"Cliente: {msg_in}")
    if msg_in.lower() == "exit":
        print("Cliente cerró el chat.")
        conn.send("exit".encode())  # avisamos al cliente
        break
    msg = input("Tu: ")
    if not msg.strip():  # ignorar mensajes vacíos
        continue
    conn.send(msg.encode())
    if msg.lower() == "exit":
        break

conn.close()
print("Chat con el cliente cerrado")