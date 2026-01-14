import socket, threading
import protocol
import time

server = "127.0.0.1"
puerto = 12345

outbox = 666
inbox = 999
user = ""
password = ""

POLL_INTERVAL_SECONDS = 1
def testLogin():
    global server, inbox, user, password
    ok = False
    s = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(3.0)
        s.connect((server, inbox))
        loginMsg = "LOGIN:" + user + ":" + password
        s.send(loginMsg.encode())
        resp = s.recv(1024)
        if resp and resp.decode().strip() == "OK":
            ok = True
    except Exception:
        ok = False
    try:
        if s is not None:
            s.close()
    except Exception:
        dummy = 0
    return ok

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
    global server, inbox, user, password

    running = True
    retrySeconds = 1

    while running:
        conectado = False
        scliente = None

        try:
            scliente = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            scliente.settimeout(10.0)
            scliente.connect((server,inbox))
            conectado = True
        except ConnectionRefusedError as CRE:
                print(f"[999] Servidor no disponible: {CRE}")
        except Exception as E:
            print(f"[999] Error conectando: {E}")

        if conectado:
            okLogin = False
            try:
                loginMsg = "LOGIN:" + user + ":" + password
                scliente.send(loginMsg.encode())
                resp = scliente.recv(1024)
                if resp and resp.decode().strip() == "OK":
                    okLogin = True
                    print(f"[999] Login correcto")
                else:
                    conectado = False
                    print("[999] Login KO")
            except Exception as E:
                print(f"[999] Error en login: {E}")

            if not okLogin:
                try:
                    scliente.close()
                except Exception:
                    dummy = 0
                conectado = False

        if conectado:  
            print(f"[999] Conectado a {server}:{inbox} con {scliente}")
            
            pollInterval = POLL_INTERVAL_SECONDS
            lastPoll = time.time()

            scliente.settimeout(0.2)
            buffer = b""

            while conectado:
                now = time.time()
                if now - lastPoll >= pollInterval:
                    try:
                        scliente.send("POLL\n".encode())
                    except Exception as E:
                        print(f"[999] Servidor caído (POLL): {E}")
                        conectado = False
                    lastPoll = now

                if conectado:
                    datos = None
                    gotData = False  

                    try:
                        datos = scliente.recv(1024)
                        gotData = True
                    except socket.timeout:
                        gotData = False
                    except Exception as E:
                        print(f"[999] Servidor caído (recv): {E}")
                        conectado = False                 # gotData is False by default

                    if conectado and gotData:
                        if not datos:
                            print(f"[999] Conexión cerrada por el servidor")
                            conectado = False
                        else:
                            buffer += datos
                            lines, buffer = protocol.splitLines(buffer)
                            for line in lines:
                                print(line)
            
            # Closing connection before retrying                    
            try:
                scliente.close()
            except Exception:
                dummy = 0

        time.sleep(retrySeconds)


def client666():
    global server, outbox, user, password

    running = True
    retrySeconds = 1

    while running:
        conectado = False
        scliente = None
        resp = None
        try:
            scliente = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            scliente.settimeout(10.0)
            scliente.connect((server,outbox))
            conectado = True
        except ConnectionRefusedError as CRE:
                print(f"[666] Servidor no disponible: {CRE}")
        except Exception as E:
            print(f"[666] Error conectando: {E}")

        if conectado:
            okLogin = False
            try:
                loginMsg = "LOGIN:" + user + ":" + password
                scliente.send(loginMsg.encode())
                resp = scliente.recv(1024)
                if resp and resp.decode().strip() == "OK":
                    okLogin = True
                    print(f"[666] Login correcto")
                else:
                    print("[666] Login KO")
            except Exception as E:
                print(f"[666] Error en login: {E}")

            if not okLogin:
                try:
                    scliente.close()
                except Exception:
                    dummy = 0
                conectado = False
            
        if conectado:  
            print(f"[666] Conectado a {server}:{outbox} con {scliente}")
            scliente.settimeout(10)

            while conectado:                    
                mensaje = input(f"{user}: Introduce tu mensaje (formato destinatario:mensaje): ")
                mensaje = user + ":" + mensaje
                if mensaje.strip() != "" and ":" in mensaje and mensaje.count(":")>=2:
                    try:
                        scliente.send(mensaje.encode())
                        resp = scliente.recv(1024)
                        if not resp:
                            print(f"[666] Conexión cerrada por el servidor")
                            conectado = False
                        else:
                            print(f"Respuesta: {resp.decode()}")
                    except Exception as E:
                        print(f"[666] No se pudo enviar (servidor caído): {E}")
                        conectado = False
            try:
                scliente.close()
            except Exception:
                dummy = 0

        time.sleep(retrySeconds)


valid = False

while not valid:
    tmp_user = input("User: @")
    if tmp_user is None:
        tmp_user = ""
    user = tmp_user.strip()

    tmp_pass = input("Password: ")
    if tmp_pass is None:
        tmp_pass = ""
    password = tmp_pass

    if user.strip() == "" or password.strip() == "":
        print("User o password no pueden estar vacíos, pruebe de nuevo")
        time.sleep(0.5)
    else:
        if testLogin():
            print("Credenciales correctas")
            valid = True
        else:
            print("Credenciales incorrectas, pruebe de nuevo")
            time.sleep(0.5)

recvThread = threading.Thread(target=client999)
sendThread = threading.Thread(target=client666)
# hiloEscuchar = threading.Thread(target=menu)

recvThread.start()
sendThread.start()
# hiloEscuchar.start()

recvThread.join()
sendThread.join()
# hiloEscuchar.join()