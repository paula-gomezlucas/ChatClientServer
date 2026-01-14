import socket

server = "127.0.0.1"
puerto = 12345
conectado = False
try:
    scliente = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    scliente.settimeout(10.0)
    scliente.connect((server,puerto))
    conectado = True
except ConnectionRefusedError as CRE:
        print(f"Ha habido un error de conexion: {CRE}")
except Exception as E:
    print(f"Ha habido un error: {E}")

if conectado==True:

    print(f"Conectado a {server}:{puerto} con {scliente}")

    while conectado:
        try:
            mensaje = input(":")
            print(f"Enviando: {mensaje}")
            scliente.send(mensaje.encode())
            datos = scliente.recv(1024)
            print(f"Respuesta: {datos.decode()}")
        except ConnectionResetError as cE:
            print(f"Ha habido un error: {cE}")
            scliente = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            scliente.connect((server,puerto))
        except ConnectionRefusedError as CRE:
            print(f"Ha habido un error de conexion: {CRE}")
        except Exception as E:
            print(f"Ha habido un error: {E}")