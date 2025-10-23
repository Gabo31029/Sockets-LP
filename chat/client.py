import socket

client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

host = 'localhost'
port = 123

client_socket.connect((host,port))

msg = ""

while True:
    msg = input("Tu: ")
    if not msg.strip():  # ignorar mensajes vacíos
        continue

    client_socket.send(msg.encode())
    if msg.lower() == "exit":
        break
    msg_in = client_socket.recv(1024).decode()
    if not msg_in:
        print("El servidor cerró la conexión.")
        break
    if msg_in.lower() == "exit":
        print("Servidor cerró el chat.")
        break
    print(f"Servidor: {msg_in}")

client_socket.close()
print("Chat con el servidor cerrado")