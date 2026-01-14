import socket, threading
import protocol
import json, base64, os, time, hashlib

SERVER_HOST = "127.0.0.1"
PORT_INBOUND = 666
PORT_OUTBOUND = 999
USERS_FILE = "users.json"

threads = []
userSockets = {}
pendingMessages = {}
usersDb = None

userSocketsSemaphore = threading.Semaphore()
pendingMessagesSemaphore = threading.Semaphore()
usersDbSemaphore = threading.Semaphore()


def sendReply(sock, text):
    """
    Sends a short reply ("OK" / "KO") safely.
    Returns True if send succeeded, False otherwise.
    """
    ok = True
    try:
        sock.send(text.encode())
    except ConnectionResetError:
        ok = False
    except Exception:
        ok = False
    return ok


def sendReplyAndMaybeClose(connection, text):
    """
    Send 'OK' or 'KO' safely.
    Returns new value for 'activo'.

    Policy:
      - KO => always stop handler
      - OK => keep running unless send fails
    """
    sent = True
    try:
        connection.send(text.encode())
    except Exception:
        sent = False

    if text == "KO":
        return False

    # text == "OK"
    if not sent:
        return False

    return True


def loadUsersDb():
    global usersDb
    Acquired = False
    while not Acquired:
        if usersDbSemaphore.acquire(timeout=1):
            Acquired = True
            
            data = None
            f = None
            try:
                if os.path.exists(USERS_FILE):
                    f = open(USERS_FILE, "r", encoding="utf-8")
                    data = f.read()
            except Exception:
                print(f"Error leyendo fichero de usuarios")
            finally:
                if f is not None:
                    f.close()

            if data is None:
                usersDb = {"users": {}}
            else:
                try:
                    usersDb = json.loads(data)
                except Exception:
                    print(f"Error parseando fichero de usuarios")
                    usersDb = {"users": {}}

            usersDbSemaphore.release()
        else:
            time.sleep(0.1)


def verifyPassword(password, salt_b64, hash_b64, iterations):
    ok = False
    try:
        salt = base64.b64decode(salt_b64.encode())
        expected = base64.b64decode(hash_b64.encode())
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, int(iterations))
        if dk == expected:
            ok = True
    except Exception:
        ok = False
    return ok

def parseLogin(msgText):
    # Returns (isLogin, username, password)
    isLogin = False
    u = None
    p = None
    try:
        parts = msgText.split(":", 2)
        if len(parts) == 3:
            if parts[0] == "LOGIN":
                isLogin = True
                u = parts[1].strip()
                p = parts[2]
    except Exception:
        isLogin = False
    return isLogin, u, p

def authenticate(username, password):
    loadUsersDb()
    ok = False

    # read usersDb without holding semaphore forever: we loaded it already
    try:
        users = usersDb.get("users", {})
        entry = users.get(username, None)
        if entry is not None:
            salt_b64 = entry.get("salt", "")
            hash_b64 = entry.get("hash", "")
            iters = entry.get("iterations", 200000)
            ok = verifyPassword(password, salt_b64, hash_b64, iters)
    except Exception:
        ok = False

    return ok

def inboundHandler(connection):
    global userSockets, pendingMessages
    sender = None
    receiver = None
    datos = None
    print(f"Se ha conectado: {connection}")
    activo = True
    
    # Login handshake
    authUser = None
    first = None

    try:
        first = connection.recv(1024)
    except ConnectionResetError:
        activo = False
    except Exception:
        activo = False

    if activo and not first:
        activo = False
    elif activo and first:
        text = first.decode().strip()
        isLogin, u, p = parseLogin(text)
        if isLogin and u is not None and p is not None:
            if authenticate(u, p):
                authUser = u
                activo = sendReplyAndMaybeClose(connection, "OK")
            else:
                activo = sendReplyAndMaybeClose(connection, "KO")
        else:
            activo = sendReplyAndMaybeClose(connection, "KO")

    while activo:
        try:
            datos = connection.recv(1024)
        except ConnectionResetError:
            activo = False
        if not datos:
            print(f"No hemos recibido datos")
            activo = False
        else:
            message = datos.decode()
            try:
                sender, receiver, msg = message.split(":", 2)
                if authUser is None or sender != authUser:
                    activo = sendReplyAndMaybeClose(connection, "KO")
                else:
                    Acquired = False
                    while not Acquired:
                        if userSocketsSemaphore.acquire(timeout=1):
                            Acquired = True
                            if receiver in userSockets:
                                sreceiver = userSockets[receiver]
                                fullMessage = protocol.makeDeliver999(sender, msg)
                                userSocketsSemaphore.release()
                                sentOk = sendReply(sreceiver, fullMessage)
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
                    print(f"{connection}: Los datos recibidos son: {datos.decode()}")
                    activo = sendReplyAndMaybeClose(connection, "OK")
            except ValueError:
                print(f"Mensaje mal formado: {message}")
                activo = sendReplyAndMaybeClose(connection, "KO")

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

def outboundHandler(connection):
    global userSockets, pendingMessages
    receiver = None
    activo = True
    print(f"Se ha conectado: {connection}")

    datos = None    
    # First message should be the user identification
    try:
        datos = connection.recv(1024)
    except ConnectionResetError:
        activo = False
    except Exception:
        activo = False

    if activo:    
        if not datos:
            activo = False
        else:
            text = datos.decode().strip()
            isLogin, u, p = parseLogin(text)

            if isLogin and u is not None and p is not None:
                if authenticate(u, p):
                    receiver = u
                else:
                    activo = False
            else:
                activo = False

            if activo:
            # Save the socket (connection)
                Acquired = False
                while not Acquired:
                    if userSocketsSemaphore.acquire(timeout=1):
                        Acquired = True
                        if receiver in userSockets:
                            del userSockets[receiver]
                        userSockets.update({receiver: connection})
                        activo = sendReplyAndMaybeClose(connection, "OK")
                        userSocketsSemaphore.release()
                    else:
                        time.sleep(0.1)    

                # Polling loop
                connection.settimeout(1)

                while activo:
                    pollData = None
                    gotPoll = False

                    try:
                        pollData = connection.recv(1024)
                        gotPoll = True
                    except socket.timeout:
                        gotPoll = False         # Already is, but to avoid pass / continue / break commands
                    except ConnectionResetError:
                        activo = False          # gotPoll already is False by default
                    except Exception:
                        activo = False          # gotPoll already is False by default
                    
                    if activo and gotPoll:
                        if not pollData:
                            activo = False
                        else:
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
                                        activo = sendReply(connection, fullMessage)

                    elif activo and not gotPoll:
                        dummy = 0
            else:
                activo = sendReplyAndMaybeClose(connection, "KO")

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