import socket

server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

host = 'localhost'
port = 12345

server_socket.bind((host,port))

server_socket.listen(1)
print(f"Server escuchando en {host}: {port} ...")

conn, addr = server_socket.accept()
print(f"Conexión desde {addr}")

data = conn.recv(1024).decode()
n1,n2 = map(float, data.split())

resultado = n1 + n2
conn.send(str(resultado).encode())
print(f"Resultado enviado: {resultado}")

conn.close()
server_socket.close()