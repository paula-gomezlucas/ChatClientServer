import socket
import threading
import protocol

server = "127.0.0.1"
puerto = 12345

outbox = 666
inbox = 999
user = ""

def inboxHandler(miSocket):
    print(f"Se ha conectado al inbox: {miSocket}")
    activo = True
    
    while activo:
        datos = miSocket.recv(1024)
        if not datos:
            print(f"No hemos recibido datos")
            activo = False
        else:
            print(f"{miSocket}: Los datos recibidos son: {datos.decode()}")
            miSocket.send("OK".encode())
    print("El cliente ha cerrado su conexion al inbox")

def outboxHandler(miSocket):
    print(f"Se ha conectado al outbox: {miSocket}")
    activo = True
    
    while activo:
        datos = miSocket.recv(1024)
        if not datos:
            print(f"No hemos recibido datos")
            activo = False
        else:
            print(f"{miSocket}: Los datos recibidos son: {datos.decode()}")
            miSocket.send("OK".encode())
    print("El cliente ha cerrado su conexion al outbox")

def client999():
    global server, inbox, user
    conectado = False
    try:
        scliente = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        scliente.settimeout(10.0)
        scliente.connect((server,inbox))
        conectado = True
    except ConnectionRefusedError as CRE:
            print(f"Ha habido un error de conexion: {CRE}")
    except Exception as E:
        print(f"Ha habido un error: {E}")

    if conectado==True:
        try:
            if user.strip() != "":
                scliente.send(user.encode())
                datos = scliente.recv(1024)
                print(f"Respuesta: {datos.decode()}")
        except ConnectionResetError as cE:
            print(f"Ha habido un error: {cE}")
            scliente = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            scliente.connect((server,inbox))
        except ConnectionRefusedError as CRE:
            print(f"Ha habido un error de conexion: {CRE}")
        except Exception as E:
            print(f"Ha habido un error: {E}")

        print(f"Conectado a {server}:{inbox} con {scliente}")
        
        scliente.settimeout(None)
        buffer = b""
        while conectado:
            try:
                datos = scliente.recv(1024)
                if not datos:
                    conectado = False
                else:
                    buffer += datos
                    lines, buffer = protocol.splitLines(buffer)
                    for line in lines:
                        print(line)
            except ConnectionResetError as cE:
                print(f"Ha habido un error: {cE}")
                scliente = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                scliente.connect((server,inbox))
            except ConnectionRefusedError as CRE:
                print(f"Ha habido un error de conexion: {CRE}")
            except Exception as E:
                print(f"Ha habido un error: {E}")


def client666():
    global server, outbox, user
    conectado = False
    try:
        scliente = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        scliente.settimeout(10.0)
        scliente.connect((server,outbox))
        conectado = True
    except ConnectionRefusedError as CRE:
            print(f"Ha habido un error de conexion: {CRE}")
    except Exception as E:
        print(f"Ha habido un error: {E}")

    if conectado==True:

        print(f"Conectado a {server}:{outbox} con {scliente}")

        while conectado:
            try:
                mensaje = input(f"{user}: Introduce tu mensaje (formato destinatario:mensaje): ")
                mensaje = user + ":" + mensaje
                if mensaje.strip() != "" and ":" in mensaje and mensaje.count(":")>=2:
                    scliente.send(mensaje.encode())
                    datos = scliente.recv(1024)
                    print(f"Respuesta: {datos.decode()}")
            except ConnectionResetError as cE:
                print(f"Ha habido un error: {cE}")
                scliente = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                scliente.connect((server,outbox))
            except ConnectionRefusedError as CRE:
                print(f"Ha habido un error de conexion: {CRE}")
            except Exception as E:
                print(f"Ha habido un error: {E}")

tmp_user = input("User: @")
if tmp_user is None:
    tmp_user = ""
user = tmp_user.strip()

recvThread = threading.Thread(target=client999)
sendThread = threading.Thread(target=client666)
# hiloEscuchar = threading.Thread(target=menu)

recvThread.start()
sendThread.start()
# hiloEscuchar.start()

recvThread.join()
sendThread.join()
# hiloEscuchar.join()