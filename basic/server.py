import socket
import time
import threading
import protocol

SERVER_HOST = "127.0.0.1"
puerto = 12345
threads = []

PORT_INBOUND = 666
PORT_OUTBOUND = 999

userSockets = {}
pendingMessages = {}

userSocketsSemaphore = threading.Semaphore()
pendingMessagesSemaphore = threading.Semaphore()

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

def inboundHandler(miSocket):
    global userSockets, pendingMessages
    sender = None
    receiver = None
    datos = None
    print(f"Se ha conectado: {miSocket}")
    activo = True
    
    while activo:
        try:
            datos = miSocket.recv(1024)
        except ConnectionResetError:
            activo = False
        if not datos:
            print(f"No hemos recibido datos")
            activo = False
        else:
            message = datos.decode()
            try:
                sender, receiver, msg = message.split(":", 2)
                Acquired = False
                while not Acquired:
                    if userSocketsSemaphore.acquire(timeout=1):
                        Acquired = True
                        if receiver in userSockets:
                            sreceiver = userSockets[receiver]
                            fullMessage = protocol.makeDeliver999(sender, msg)
                            userSocketsSemaphore.release()
                            sreceiver.send(fullMessage.encode())
                        else:
                            userSocketsSemaphore.release()
                            print(f"El usuario {receiver} no está conectado, guardando mensaje")
                            AcquiredMessages = False
                            while not AcquiredMessages:
                                if pendingMessagesSemaphore.acquire(timeout=1):
                                    AcquiredMessages = True
                                    if receiver in pendingMessages and sender in pendingMessages[receiver]:
                                        pendingMessages[receiver][sender].append(msg)
                                    elif receiver in pendingMessages:
                                        pendingMessages[receiver].update({sender: [msg]})
                                    else:
                                        pendingMessages.update({receiver: {sender: [msg]}})
                                    pendingMessagesSemaphore.release()
                                else:
                                    time.sleep(0.1)
                    else:
                        time.sleep(0.1)
                print(f"{miSocket}: Los datos recibidos son: {datos.decode()}")
                miSocket.send("OK".encode())
            except ValueError:
                print(f"Mensaje mal formado: {message}")                
                miSocket.send("KO".encode())        

        # time.sleep(1/10)
    print("El cliente ha cerrado su conexion 666")
    Acquired = False
    while not Acquired:
        if userSocketsSemaphore.acquire(timeout=1):
            Acquired = True
            if sender is not None:
                userSockets.pop(sender, None)
                # del userSockets[sender]
            userSocketsSemaphore.release()
        else:
            time.sleep(0.1)

def outboundHandler(miSocket):
    global userSockets, pendingMessages
    receiver = None
    print(f"Se ha conectado: {miSocket}")
    try:
        datos = miSocket.recv(1024)
    except ConnectionResetError:
        activo = False
    if not datos:
        print(f"No hemos recibido datos")
        activo = False
    else:
        receiver = datos.decode()
        Acquired = False
        while not Acquired:
            if userSocketsSemaphore.acquire(timeout=1):
                Acquired = True
                if receiver in userSockets:
                    del userSockets[receiver]
                userSockets.update({receiver: miSocket})
                miSocket.send("OK".encode())
                userSocketsSemaphore.release()
            else:
                time.sleep(0.1)    
        miSocket.settimeout(0.5)
        activo = True
        dataExists = True
        while activo:
            msg = None

            Acquired = False
            while not Acquired:
                if pendingMessagesSemaphore.acquire(timeout=1):
                    Acquired = True
                    mensaje = pendingMessages.get(receiver, None)
                    if mensaje:
                        msg = mensaje
                        del pendingMessages[receiver]
                    pendingMessagesSemaphore.release()
                else:
                    time.sleep(0.1)

            if msg:
                for k in msg:
                    msg_list = msg[k]
                    for m in msg_list:
                        fullMessage = protocol.makeDeliver999(k, m)
                        miSocket.send(fullMessage.encode())

    print("El cliente ha cerrado su conexion 999")
    Acquired = False
    while not Acquired:
        if userSocketsSemaphore.acquire(timeout=1):
            Acquired = True
            if receiver is not None:
                userSockets.pop(receiver, None)
                # del userSockets[sender]
            userSocketsSemaphore.release()
        else:
            time.sleep(0.1)
def listenInbound():

    global threads
    serverSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    serverSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    serverSocket.bind((SERVER_HOST,PORT_INBOUND))
    serverSocket.listen(10)
    # serverSocket.settimeout(0.5)

    print(f"Servidor escuchando en {SERVER_HOST}:{PORT_INBOUND}")

    continuar = True
    while continuar:
        scliente, direccion=serverSocket.accept()
        t=threading.Thread(target=inboundHandler, args=[scliente,])
        threads.append(t)
        t.start()


    for j in threads:
        j.join()

def listenOutbound():

    global threads
    serverSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    serverSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    serverSocket.bind((SERVER_HOST,PORT_OUTBOUND))
    serverSocket.listen(10)
    # serverSocket.settimeout(0.5)

    print(f"Servidor escuchando en {SERVER_HOST}:{PORT_OUTBOUND}")

    continuar = True
    while continuar:
        scliente, direccion=serverSocket.accept()
        t=threading.Thread(target=outboundHandler, args=[scliente,])
        threads.append(t)
        t.start()

    for j in threads:
        j.join()

# def menu():
#     global threads
#     print()

inboxListener = threading.Thread(target=listenInbound)
outboxListener = threading.Thread(target=listenOutbound)
# hiloEscuchar = threading.Thread(target=menu)

inboxListener.start()
outboxListener.start()
# hiloEscuchar.start()

inboxListener.join()
outboxListener.join()
# hiloEscuchar.join()