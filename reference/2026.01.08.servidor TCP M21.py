import socket
import time
import threading

server = "127.0.0.1"
puerto = 12345
listaHilos = []


def gestionarConexion(miSocket):
    print(f"Se ha conectado: {miSocket}")
    activo = True
    
    while activo:
        datos = miSocket.recv(1024)
        if not datos:
            print(f"No hemos recibido datos")
            activo = False
        else:
            print(f"{miSocket}: Los datos recibidos son: {datos.decode()}")
            miSocket.send("OK".encode())
        # time.sleep(1/10)
    print("El cliente ha cerrado su conexion")
def servirServidoramente():

    global listaHilos
    sservidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    sservidor.bind((server,puerto))
    sservidor.settimeout(15)
    sservidor.listen(2)

    print(f"Servidor escuchando en {server}:{puerto}")

    continuar = True
    while continuar:
        scliente, direccion=sservidor.accept()
        t=threading.Thread(target=gestionarConexion, args=[scliente,])
        listaHilos.append(scliente)
        t.start()

    for j in listaHilos:
        j.join()


def menu():
    global listaHilos
    print()

hiloEscuchar = threading.Thread(target=servirServidoramente)
hiloEscuchar = threading.Thread(target=menu)

hiloEscuchar.start()
hiloEscuchar.start()

hiloEscuchar.join()
hiloEscuchar.join()
 

 




