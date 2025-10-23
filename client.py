import socket 

client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

host = 'localhost'
port = 12345

client_socket.connect((host, port))

n1 = float(input("Ingrese el primer número: "))
n2 = float(input("Ingrese el segundo número: "))

client_socket.send(f"{n1} {n2}".encode())

resultado = client_socket.recv(1024).decode()

print(f"El resultado de la suma es: {resultado}")

client_socket.close()
print("Conexión cerrada.")