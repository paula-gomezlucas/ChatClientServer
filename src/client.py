import socket, threading
import protocol
import time, os, json

server = "127.0.0.1"
outbox = 666
inbox = 999
TMP_DIR = "data/tmp"
HIST_DIR = "data/client_history"
USERS_FILE = "data/users.json"
STATE_DIR = "data/state"
LASTTS_FILE = None

POLL_INTERVAL_SECONDS = 1

user = ""
password = ""
activeChat = None
pendingCounts = {}
lastTsSeen = 0.0
serverList = {}         
outgoing999 = []
historyLocks = {}                 # key: "a|b"  value: threading.Lock()

pendingCountsLock = threading.Lock()
lastTsSeenLock = threading.Lock()
serverListLock = threading.Lock()
outgoing999Lock = threading.Lock()
historyLocksSemaphore = threading.Semaphore(1)

def ensureTmpDir():
    ok = False
    try:
        if not os.path.exists("data"):
            os.mkdir("data")
        if not os.path.exists(TMP_DIR):
            os.makedirs(TMP_DIR)
        ok = True
    except Exception:
        ok = False
    return ok

def tmpFileForUser(u):
    ensureTmpDir()
    return TMP_DIR + "/tmp_" + u + ".txt"

def ensureStateDir():
    try:
        if not os.path.exists("data"):
            os.mkdir("data")
        if not os.path.exists(STATE_DIR):
            os.makedirs(STATE_DIR)
    except Exception:
        dummy = 0

def lastTsFileForUser(u):
    ensureStateDir()
    return os.path.join(STATE_DIR, "lastts_" + u + ".txt")

def loadLastTsSeen(u):
    path = lastTsFileForUser(u)
    f = None
    try:
        if os.path.exists(path):
            f = open(path, "r", encoding="utf-8")
            txt = f.read().strip()
            if txt != "":
                data = json.loads(txt)
                return float(data.get("lastTs", 0.0))
    except Exception:
        dummy = 0
    finally:
        try:
            if f is not None:
                f.close()
        except Exception:
            dummy2 = 0
    return 0.0

def saveLastTsSeen(u, val):
    path = lastTsFileForUser(u)
    protocol.atomicWriteJson(path, {"lastTs": val})

def histKey(a, b):
    a = str(a).strip()
    b = str(b).strip()
    if a < b:
        return a + "|" + b
    return b + "|" + a

def getHistoryLock(a, b):
    key = histKey(a, b)
    lk = None

    Acquired = False
    while not Acquired:
        if historyLocksSemaphore.acquire(timeout=5):
            Acquired = True
            try:
                if key in historyLocks:
                    lk = historyLocks[key]
                else:
                    lk = threading.Lock()
                    historyLocks[key] = lk
            finally:
                historyLocksSemaphore.release()
        else:
            time.sleep(0.1)

    return lk


def appendToTmpQueue(me, payloadLine):
    # payloadLine must be a single line WITHOUT trailing \n
    path = tmpFileForUser(me)
    f = None
    try:
        f = open(path, "a", encoding="utf-8")
        f.write(payloadLine.strip() + "\n")
    except Exception:
        dummy = 0
    finally:
        try:
            if f is not None:
                f.close()
        except Exception:
            dummy2 = 0


def loadUsersSet():
    users = set()
    data = None
    f = None
    try:
        if os.path.exists(USERS_FILE):
            f = open(USERS_FILE, "r", encoding="utf-8")
            data = f.read()
    except Exception:
        data = None
    finally:
        try:
            if f is not None:
                f.close()
        except Exception:
            dummy = 0

    if data is not None:
        try:
            obj = json.loads(data)
            u = obj.get("users", {})
            for k in u:
                users.add(k)
        except Exception:
            dummy = 0
    return users

def ensureHistDir():
    try:
        if not os.path.exists(HIST_DIR):
            os.makedirs(HIST_DIR)
    except Exception:
        dummy = 0

def histFileForPair(me, peer):
    ensureHistDir()
    f = os.path.join(HIST_DIR, me + "_" + peer + ".json")
    return f  

def loadPairHistory(a, b):
    path = histFileForPair(a, b)
    arr = []
    data = None
    f = None
    try:
        if os.path.exists(path):
            f = open(path, "r", encoding="utf-8")
            data = f.read()
    except Exception:
        data = None
    finally:
        try:
            if f is not None:
                f.close()
        except Exception:
            dummy = 0

    if data is not None and data.strip() != "":
        try:
            arr = json.loads(data)
            if type(arr) is not list:
                arr = []
        except Exception:
            arr = []
    return arr

# Not used, kept for reference
def appendPairHistory(me, peer, record):
    arr = loadPairHistory(me, peer)
    arr.append(record)
    path = histFileForPair(me, peer)
    protocol.atomicWriteJson(path, arr)

def estadoRank(e):
    # Higher = more advanced
    e = str(e).strip().upper()
    if e == "LEIDO":
        return 3
    if e == "ENTREGADO":
        return 2
    if e == "RECIBIDO":
        return 1
    if e == "ENVIADO":
        return 0
    return -1

def upsertPairHistory(me, peer, record):
    lock = getHistoryLock(me, peer)
    Acquired = False
    while not Acquired:
        if lock.acquire(timeout=5):
            Acquired = True
            arr = loadPairHistory(me, peer)

            r_from = record.get("from", None)
            r_to = record.get("to", None)
            r_ts = record.get("ts", None)

            found = False
            i = 0
            while i < len(arr) and not found:
                it = arr[i]
                try:
                    if it.get("from", None) == r_from and it.get("to", None) == r_to and float(it.get("ts", -1)) == float(r_ts):
                        # Merge / upgrade
                        old_estado = it.get("estado", "")
                        new_estado = record.get("estado", "")
                        if estadoRank(new_estado) > estadoRank(old_estado):
                            it["estado"] = new_estado
                            it["tsEstado"] = record.get("tsEstado", time.time())

                        # Keep body if new body empty
                        new_body = str(record.get("body", ""))
                        if new_body.strip() != "":
                            it["body"] = new_body

                        found = True
                except Exception:
                    dummy = 0
                i = i + 1

            if not found:
                arr.append(record)

            path = histFileForPair(me, peer)
            protocol.atomicWriteJson(path, arr)

            lock.release()
        else:
            time.sleep(0.1)


def hasMessageWithTs(me, peer, ts):
    arr = loadPairHistory(me, peer)
    i = 0
    found = False
    while i < len(arr) and not found:
        item = arr[i]
        try:
            if float(item.get("ts", -1)) == float(ts):
                found = True
        except Exception:
            dummy = 0
        i = i + 1
    return found

def getMyChats(me):
    ensureHistDir()
    chats = set()
    try:
        files = os.listdir(HIST_DIR)
    except Exception:
        files = []

    i = 0
    while i < len(files):
        name = files[i]
        if name.endswith(".json"):
            base = name[:-5]  # remove .json
            parts = base.split("_")
            if len(parts) == 2:
                a = parts[0]
                b = parts[1]
                if a == me and b != "":
                    chats.add(b)
                elif b == me and a != "":
                    chats.add(a)
        i = i + 1

    # return sorted list for stable display
    out = list(chats)
    try:
        out.sort()
    except Exception:
        dummy = 0
    return out

def printChatHistory(me, peer):
    arr = loadPairHistory(me, peer)

    # sort by ts if present
    try:
        arr.sort(key=lambda r: float(r.get("ts", 0)))
    except Exception:
        dummy = 0
    
    start = 0
    if len(arr) > 100:
        start = len(arr) - 100
    
    i = start
    while i < len(arr):
        r = arr[i]
        try:
            frm = str(r.get("from", ""))
            body = str(r.get("body", ""))
            estado = str(r.get("estado", ""))
            if frm != "" and body != "":
                print(f"@{frm}: {body}")
        except Exception:
            dummy2 = 0
        i = i + 1

def enqueue999(line):
    Acquired = False
    while not Acquired:
        if outgoing999Lock.acquire(timeout=5):
            Acquired = True
            try:
                outgoing999.append(line)
            finally:
                outgoing999Lock.release()
        else:
            time.sleep(0.1)

def computeReadUpToTs(me, peer):
    arr = loadPairHistory(me, peer)
    mx = 0.0
    i = 0
    while i < len(arr):
        it = arr[i]
        try:
            if it.get("from", None) == peer and it.get("to", None) == me:
                ts = float(it.get("ts", 0.0))
                if ts > mx:
                    mx = ts
        except Exception:
            dummy = 0
        i = i + 1
    return mx

def applyLeidoToOutgoing(me, peer, readUpToTs):
    # Update messages that I sent to peer: estado -> LEIDO for ts <= readUpToTs
    lock = getHistoryLock(me, peer)
    Acquired = False
    while not Acquired:
        if lock.acquire(timeout=5):
            Acquired = True    
            arr = loadPairHistory(me, peer)
            changed = False
            i = 0
            while i < len(arr):
                it = arr[i]
                try:
                    if it.get("from", None) == me and it.get("to", None) == peer:
                        ts = float(it.get("ts", -1))
                        if ts <= float(readUpToTs):
                            if it.get("estado", None) != "LEIDO":
                                it["estado"] = "LEIDO"
                                it["tsEstado"] = time.time()
                                changed = True
                except Exception:
                    dummy = 0
                i = i + 1
            if changed:
                path = histFileForPair(me, peer)
                protocol.atomicWriteJson(path, arr)

            lock.release()
        else:
            time.sleep(0.1)

def applyEntregadoToOutgoing(me, peer, deliveredUpToTs):
    # Update messages that I sent to peer: estado -> ENTREGADO for ts <= deliveredUpToTs
    lock = getHistoryLock(me, peer)
    Acquired = False
    while not Acquired:
        if lock.acquire(timeout=5):
            Acquired = True
            arr = loadPairHistory(me, peer)
            changed = False
            i = 0
            while i < len(arr):
                it = arr[i]
                try:
                    if it.get("from", None) == me and it.get("to", None) == peer:
                        ts = float(it.get("ts", -1))
                        if ts <= float(deliveredUpToTs):
                            # Don't downgrade LEIDO
                            estado = it.get("estado", "")
                            if estado != "LEIDO" and estado != "ENTREGADO":
                                it["estado"] = "ENTREGADO"
                                it["tsEstado"] = time.time()
                                changed = True
                except Exception:
                    dummy = 0
                i = i + 1

            if changed:
                path = histFileForPair(me, peer)
                protocol.atomicWriteJson(path, arr)

            lock.release()
        else:
            time.sleep(0.1)

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
    global server, inbox, user, password, logoutRequested, POLL_INTERVAL_SECONDS, serverList, pendingCounts

    running = True
    retrySeconds = 1

    while running:
        conectado = False
        scliente = None
        if logoutRequested:
            running = False

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

            try:
                req = protocol.makeList999(user)
                scliente.send(req.encode())
            except Exception as E:
                print(f"[999] Error enviando LIST: {E}")
                conectado = False
            
            pollInterval = POLL_INTERVAL_SECONDS
            lastPoll = time.time()

            scliente.settimeout(0.2)
            buffer = b""
            lastTsSeen = loadLastTsSeen(user)

            while conectado:
                now = time.time()
                toSend = []
                Acquired = False
                while not Acquired:
                    if outgoing999Lock.acquire(timeout=5):
                        Acquired = True
                        try:
                            if len(outgoing999) > 0:
                                toSend = outgoing999[:]
                                outgoing999.clear()
                        finally:
                            outgoing999Lock.release()
                    else:
                        time.sleep(0.1)

                i = 0
                while i < len(toSend) and conectado:
                    try:
                        scliente.send(toSend[i].encode())
                        _ = scliente.recv(1024)   # read OK to keep stream in sync
                    except Exception:
                        conectado = False
                    i = i + 1

                if now - lastPoll >= pollInterval:
                    try:
                        req = protocol.makeUpdate999(user, "@", lastTsSeen)
                        scliente.send((req + "\n").encode())
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
                                ok, origen, destino, ts, estado, tsEstado, mensaje = protocol.parseDeliver999(line)
                                if ok:
                                    origen = str(origen).strip()
                                    destino = str(destino).strip()
                                    estado = str(estado).strip().upper()
                                    mensaje = str(mensaje)

                                    if origen == "server" and estado == "LIST":
                                        try:
                                            n = int(mensaje.strip())
                                            print(f"[999] LIST: {n} chats con mensajes pendientes")
                                        except Exception:
                                            print(f"[999] LIST header recibido (no parseable): {mensaje}")
                                    elif estado == "LIST":
                                        # store count
                                        Acquired = False
                                        while not Acquired:
                                            if serverListLock.acquire(timeout=5):
                                                Acquired = True
                                                try:
                                                    serverList[origen] = int(mensaje)
                                                finally:
                                                    serverListLock.release()
                                            else:
                                                time.sleep(0.1)

                                    #  Not necessary anymore
                                    elif origen == "server" and estado == "UPDATE":
                                        try:
                                            n_upd = int(mensaje.strip())
                                            # if n_upd > 0:
                                            #     print(f"[999] UPDATE: {n_upd} actualizaciones (mensajes nuevos + mensajes leídos/entregados)")
                                        except Exception:
                                            dummy = 0

                                    else:
                                        if estado == "LEIDO":
                                            applyLeidoToOutgoing(user, origen, tsEstado)
                                            if ts > lastTsSeen:
                                                lastTsSeen = ts
                                                saveLastTsSeen(user, lastTsSeen)
                                        elif estado == "ENTREGADO" and mensaje == "":
                                            applyEntregadoToOutgoing(user, origen, tsEstado)
                                            if ts > lastTsSeen:
                                                lastTsSeen = ts    
                                                saveLastTsSeen(user, lastTsSeen)                                   
                                        elif estado == "ENTREGADO" and mensaje.strip() != "":
                                            record = {
                                                "from": origen,
                                                "to": user,
                                                "body": mensaje,
                                                "ts": ts,
                                                "estado": estado,
                                                "tsEstado": tsEstado
                                            }
                                            upsertPairHistory(user, origen, record)

                                            # Update pending count unless this chat is currently active
                                            Acquired = False
                                            while not Acquired:
                                                if pendingCountsLock.acquire(timeout=5):
                                                    Acquired = True
                                                    try:
                                                        if activeChat != origen:
                                                            if origen not in pendingCounts:
                                                                pendingCounts[origen] = 0
                                                            pendingCounts[origen] += 1
                                                    finally:
                                                        pendingCountsLock.release()
                                                else:
                                                    time.sleep(0.1)

                                            # Update serverList pending count
                                            Acquired = False
                                            while not Acquired:
                                                if serverListLock.acquire(timeout=1):
                                                    Acquired = True
                                                    try:
                                                        # We just downloaded one message from 'origen', so server-side pending
                                                        # count is at least one lower; we clamp to >=0
                                                        old = int(serverList.get(origen, 0))
                                                        newv = old - 1
                                                        if newv < 0:
                                                            newv = 0
                                                        serverList[origen] = newv
                                                    except Exception:
                                                        dummy = 0
                                                    serverListLock.release()
                                                else:
                                                    time.sleep(0.05)


                                            # Update last seen timestamp
                                            if ts > lastTsSeen:
                                                lastTsSeen = ts
                                                saveLastTsSeen(user, lastTsSeen)
                                        else:
                                            if ts > lastTsSeen:
                                                lastTsSeen = ts
                                                saveLastTsSeen(user, lastTsSeen)
                                else:
                                    print(line)

                                try:
                                    scliente.send("OK".encode())
                                except Exception:
                                    conectado = False

                if logoutRequested:
                    conectado = False
            
            # Closing connection before retrying                    
            try:
                scliente.close()
            except Exception:
                dummy = 0

        if logoutRequested:
            running = False

        time.sleep(retrySeconds)


def client666():
    global server, outbox, user, password, activeChat, logoutRequested

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

            # Resend tmp queue for this user (best-effort)
            tmpPath = tmpFileForUser(user)
            if os.path.exists(tmpPath):
                f = None
                data = None
                try:
                    f = open(tmpPath, "r", encoding="utf-8")
                    data = f.read()
                except Exception:
                    data = None
                if f is not None:
                    try:
                        f.close()
                    except Exception:
                        dummy = 0

                if data is not None:
                    lines = data.split("\n")
                    remaining = []
                    for line in lines:
                        l = line.strip()
                        if l != "":
                            try:
                                scliente.send(l.encode())
                                r = scliente.recv(1024)
                                if not r or r.decode().strip() != "OK":
                                    remaining.append(l)
                            except Exception:
                                remaining.append(l)

                    # rewrite tmp with remaining (or empty)
                    f2 = None
                    try:
                        f2 = open(tmpPath, "w", encoding="utf-8")
                        for l in remaining:
                            f2.write(l + "\n")
                    except Exception:
                        dummy2 = 0
                    if f2 is not None:
                        try:
                            f2.close()
                        except Exception:
                            dummy3 = 0

            usersSet = loadUsersSet()

            while conectado:
                if activeChat is None:
                    line = input(f"{user}: ")
                else:
                    line = input(f"@{activeChat}: ")

                # Allow blank line as refresh
                if line is None:
                    line = ""
                line = line.rstrip("\n")

                if line.strip() == "":
                    if activeChat is not None:
                        printChatHistory(user, activeChat)
                        readUpTo = computeReadUpToTs(user, activeChat)
                        req = protocol.makeRead999(user, activeChat, readUpTo)
                        enqueue999(req)
                        pendingCountsLock.acquire()
                        try:
                            if activeChat in pendingCounts:
                                pendingCounts[activeChat] = 0
                        finally:
                            pendingCountsLock.release()
                else:
                    if line.startswith("@"):
                        cmd = line[1:].strip()

                        if cmd.lower().strip() == "lista":
                            # Snapshot serverList
                            serverSnap = {}
                            Acquired = False
                            while not Acquired:
                                if serverListLock.acquire(timeout=5):
                                    Acquired = True
                                    try:
                                        for k in serverList:
                                            serverSnap[k] = serverList[k]
                                    finally:
                                        serverListLock.release()
                                else:
                                    time.sleep(0.1)

                            # Snapshot local pendingCounts
                            localSnap = {}
                            Acquired = False
                            while not Acquired:
                                if pendingCountsLock.acquire(timeout=5):
                                    Acquired = True
                                    try:
                                        for k in pendingCounts:
                                            localSnap[k] = pendingCounts[k]
                                    finally:
                                        pendingCountsLock.release()
                                else:
                                    time.sleep(0.1)

                            chats = getMyChats(user)

                            print("Chats:")
                            i = 0
                            while i < len(chats):
                                u = chats[i]
                                sp = 0
                                lp = 0
                                try:
                                    sp = int(serverSnap.get(u, 0))
                                except Exception:
                                    sp = 0
                                try:
                                    lp = int(localSnap.get(u, 0))
                                except Exception:
                                    lp = 0

                                if sp + lp > 0:
                                    print(f"@{u} (server: {sp} mensajes pendientes, local: {lp} mensajes pendientes)")
                                else:
                                    print(f"@{u}")
                                i = i + 1


                        elif cmd.lower().strip() == "salir":
                            conectado = False
                            running = False
                            # IMPORTANT: also signal the recv thread
                            try:
                                global logoutRequested
                                logoutRequested = True
                            except Exception:
                                dummy = 0
                        else:

                            peer = cmd
                            if peer == "":
                                print("Nombre vacío")
                            elif peer == user:
                                print("No puede chatear consigo mismo")
                            elif peer not in usersSet:
                                print(f"Usuario '{peer}' no existe")
                            else:
                                activeChat = peer
                                printChatHistory(user, activeChat)
                                readUpTo = computeReadUpToTs(user, activeChat)
                                req = protocol.makeRead999(user, activeChat, readUpTo)
                                enqueue999(req)

                    else:
                        if activeChat is None:
                            print("No hay conversación activa. Use @usuario: para abrir una.")
                        else:
                            # send to activeChat without retyping name
                            destino = activeChat
                            msg = line
                            ts = time.time()
                            payload = protocol.makeMsgSend666(user, destino, ts, msg)
                            try:
                                scliente.send(payload.encode())
                                resp = scliente.recv(1024)
                                respTxt = resp.decode(errors="ignore").strip()

                                if respTxt != "OK":
                                    print(f"Respuesta: {respTxt}")
                                    appendToTmpQueue(user, payload)
                                else:
                                    # Store in history as sent
                                    record = {
                                        "from": user,
                                        "to": destino,
                                        "body": msg,
                                        "ts": ts,
                                        "estado": "ENVIADO",
                                        "tsEstado": ts
                                    }
                                    upsertPairHistory(user, destino, record)
                                    
                                    printChatHistory(user, destino)
                                    Acquired = False
                                    while not Acquired:
                                        if pendingCountsLock.acquire(timeout=5):
                                            Acquired = True
                                            try:
                                                if destino in pendingCounts:
                                                    pendingCounts[destino] = 0
                                            finally:
                                                pendingCountsLock.release()
                                        else:
                                            time.sleep(0.1)                

                            except Exception as E:
                                appendToTmpQueue(user, payload)
                                print(f"[666] No se pudo enviar (servidor caído): {E}")
                                conectado = False

            try:
                scliente.close()
            except Exception:
                dummy = 0

        time.sleep(retrySeconds)

def menu():
    print("Comandos disponibles:"
    "\n\t@usuario - Cambiar chat activo a 'usuario'"
    "\n\t@lista - Listar chats abiertos"
    "\n\t@salir - Cerrar sesión")

print("Cliente de chat básico\n\tIntroduce tus credenciales para iniciar sesión.")

logoutRequested = False

runningApp = True
while runningApp:
    # Ask credentials
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
                menu()
                valid = True
            else:
                print("Credenciales incorrectas, pruebe de nuevo")
                time.sleep(0.5)

    logoutRequested = False
    recvThread = threading.Thread(target=client999)
    sendThread = threading.Thread(target=client666)
    recvThread.start()
    sendThread.start()

    # Wait for send thread to end (logout triggers this)
    sendThread.join()

    # Tell recv thread to exit too
    logoutRequested = True
    try:
        # client999 should check logoutRequested in its loop and exit
        dummy = 0
    except Exception:
        dummy = 0

    recvThread.join()

    # force re-login
    user = ""
    password = ""
    print("Sesión cerrada. Vuelve a iniciar sesión.")