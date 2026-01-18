import socket, threading
import protocol
import json, base64, os, time, hashlib

SERVER_HOST = "127.0.0.1"
PORT_INBOUND = 666
PORT_OUTBOUND = 999
DATA_DIR = "data"
USERS_FILE = os.path.join(DATA_DIR, "users.json")
HIST_DIR = os.path.join(DATA_DIR, "server_history")
PENDING_FILE = os.path.join(DATA_DIR, "pending.json")

threads = []
userSockets = {}
pendingMessages = {}
pendingEvents = {} # { userToNotify: [ {"tsEvent": float, "sender": str, "peer": str, "tsMsg": float, "tsRead": float, "body": str } ] }
usersDb = None
pairHistoryLocks = {}  # key: "a|b"  value: threading.Lock()

userSocketsSemaphore = threading.Semaphore(1)
pendingMessagesSemaphore = threading.Semaphore(1)
usersDbSemaphore = threading.Semaphore(1)
pendingEventsSemaphore = threading.Semaphore(1)
pairHistoryLocksSemaphore = threading.Semaphore(1)

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

def ensureDataDir():
    ok = False
    try:
        if not os.path.exists(DATA_DIR):
            os.mkdir(DATA_DIR)
        ok = True
    except Exception:
        ok = False
    return ok

def ensureHistDir():
    ok = False
    ensureDataDir()
    try:
        if not os.path.exists(HIST_DIR):
            os.makedirs(HIST_DIR)
        ok = True
    except Exception:
        ok = False
    return ok

def histFileForPair(a, b):
    ensureHistDir()
    f1 = os.path.join(HIST_DIR, a + "_" + b + ".json")
    f2 = os.path.join(HIST_DIR, b + "_" + a + ".json")

    # if one exists, use it
    if os.path.exists(f1):
        return f1
    if os.path.exists(f2):
        return f2

    # else: create with the order of first sender (a is sender at first message)
    return f1

def pairKey(a, b):
    # Canonical key so paula/lucia and lucia/paula share the same lock
    # Use string compare for stable ordering
    if a <= b:
        return a + "_" + b
    else:
        return b + "_" + a

def getPairHistoryLock(a, b):
    global pairHistoryLocks
    key = pairKey(a, b)

    lock = None
    Acquired = False
    while not Acquired:
        if pairHistoryLocksSemaphore.acquire(timeout=1):
            Acquired = True
            try:
                if key in pairHistoryLocks:
                    lock = pairHistoryLocks[key]
                else:
                    lock = threading.Semaphore(1)
                    pairHistoryLocks[key] = lock
            except Exception:
                lock = threading.Semaphore(1)  # fallback, should never happen
            pairHistoryLocksSemaphore.release()
        else:
            time.sleep(0.05)

    return lock

def loadPairHistory(a, b):
    path = histFileForPair(a, b)
    data = None
    f = None
    try:
        if os.path.exists(path):
            f = open(path, "r", encoding="utf-8")
            data = f.read()
    except Exception:
        data = None
    if f is not None:
        try:
            f.close()
        except Exception:
            dummy = 0

    if data is None or data.strip() == "":
        return []
    try:
        obj = json.loads(data)
        if obj is None:
            return []
        if isinstance(obj, list):
            return obj
        return []
    except Exception:
        return []

def savePairHistory(a, b, arr):
    path = histFileForPair(a, b)
    try:
        protocol.atomicWriteJson(path, arr)
        return True
    except Exception:
        return False

def markDeliveredForPair(sender, receiver, ts):
    # update sender
    arr = loadPairHistory(sender, receiver)
    i = 0
    while i < len(arr):
        r = arr[i]
        try:
            if r.get("from") == sender and r.get("to") == receiver and float(r.get("ts")) == float(ts):
                r["estado"] = "ENTREGADO"
                r["tsEstado"] = time.time()
        except Exception:
            dummy = 0
        i = i + 1
    savePairHistory(sender, receiver, arr)

def markReadForPair(sender, receiver, readUpToTs):
    arr = loadPairHistory(sender, receiver)
    changed = False

    i = 0
    while i < len(arr):
        item = arr[i]
        try:
            ts_msg = float(item.get("ts", -1))
            frm = item.get("from", None)
            to = item.get("to", None)
            estado = item.get("estado", None)

            if frm == sender and to == receiver:
                if ts_msg <= float(readUpToTs):
                    if estado != "LEIDO":
                        item["estado"] = "LEIDO"
                        item["tsEstado"] = time.time()
                        changed = True
        except Exception:
            dummy = 0
        i = i + 1

    if changed:
        savePairHistory(sender, receiver, arr)

def enqueueEvent(userToNotify, kind, peer, upToTs):
    # userToNotify = who will receive the event on UPDATE
    # kind = "LEIDO" or "ENTREGADO"
    # peer = the other user in the conversation (reader/delivered-to)
    # upToTs = threshold timestamp
    Acquired = False
    while not Acquired:
        if pendingEventsSemaphore.acquire(timeout=1):
            Acquired = True
            ev = {"ts": time.time(), "kind": kind, "from": peer, "upTo": float(upToTs)}
            if userToNotify in pendingEvents:
                pendingEvents[userToNotify].append(ev)
            else:
                pendingEvents[userToNotify] = [ev]
            pendingEventsSemaphore.release()
        else:
            time.sleep(0.1)


def savePendingToDisk():
    global pendingMessages
    ensureDataDir()

    Acquired = False
    while not Acquired:
        if pendingMessagesSemaphore.acquire(timeout=1):
            Acquired = True
            try:
                protocol.atomicWriteJson(PENDING_FILE, pendingMessages)
            except Exception:
                dummy = 0
            pendingMessagesSemaphore.release()
        else:
            time.sleep(0.1)


def loadPendingFromDisk():
    global pendingMessages
    ensureDataDir()

    data = None
    f = None
    try:
        if os.path.exists(PENDING_FILE):
            f = open(PENDING_FILE, "r", encoding="utf-8")
            data = f.read()
    except Exception:
        data = None
    if f is not None:
        try:
            f.close()
        except Exception:
            dummy = 0

    if data is not None:
        try:
            obj = json.loads(data)
            if obj is not None:
                pendingMessages = obj
        except Exception:
            dummy2 = 0

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
                ok, sender, receiver, ts, msg = protocol.parseMsgSend666(message)
                if not ok:
                    activo = sendReplyAndMaybeClose(connection, "KO")
                else:
                    if authUser is None or sender != authUser:
                        activo = sendReplyAndMaybeClose(connection, "KO")
                    else:
                        record = {
                            "ts": float(ts),
                            "from": sender,
                            "to": receiver,
                            "body": msg,
                            "estado": "RECIBIDO",
                            "tsEstado": time.time()
                        }

                        lock = getPairHistoryLock(sender, receiver)
                        AcquiredLock = False
                        while not AcquiredLock:
                            if lock.acquire(timeout=5):
                                AcquiredLock = True
                                h = loadPairHistory(sender, receiver)
                                h.append(record)
                                savePairHistory(sender, receiver, h)
                                lock.release()
                            else:
                                time.sleep(0.1)

                        Acquired = False
                        while not Acquired:
                            if userSocketsSemaphore.acquire(timeout=1):
                                Acquired = True
                                if receiver in userSockets:
                                    sreceiver = userSockets[receiver]
                                    fullMessage = protocol.makeMsgDeliver999(sender, receiver, ts, "ENTREGADO", time.time(), msg)
                                    userSocketsSemaphore.release()

                                    sentOk = sendReply(sreceiver, fullMessage)

                                    if not sentOk:
                                        # Treat like offline: store into pendingMessages and persist
                                        record = {"ts": ts, "body": msg, "estado": "RECIBIDO", "tsEstado": time.time()}

                                        AcquiredMessages = False
                                        while not AcquiredMessages:
                                            if pendingMessagesSemaphore.acquire(timeout=1):
                                                AcquiredMessages = True

                                                if receiver in pendingMessages and sender in pendingMessages[receiver]:
                                                    pendingMessages[receiver][sender].append(record)
                                                elif receiver in pendingMessages:
                                                    pendingMessages[receiver].update({sender: [record]})
                                                else:
                                                    pendingMessages.update({receiver: {sender: [record]}})

                                                pendingMessagesSemaphore.release()
                                            else:
                                                time.sleep(0.1)

                                        savePendingToDisk()
                                    else:
                                        # Message sent OK
                                        markDeliveredForPair(sender, receiver, ts)
                                        enqueueEvent(sender, "ENTREGADO", receiver, ts)
                                else:
                                    userSocketsSemaphore.release()
                                    print(f"El usuario {receiver} no está conectado, guardando mensaje")

                                    record = {"ts": ts, "body": msg, "estado": "RECIBIDO", "tsEstado": time.time()}

                                    AcquiredMessages = False
                                    while not AcquiredMessages:
                                        if pendingMessagesSemaphore.acquire(timeout=1):
                                            AcquiredMessages = True

                                            if receiver in pendingMessages and sender in pendingMessages[receiver]:
                                                pendingMessages[receiver][sender].append(record)
                                            elif receiver in pendingMessages:
                                                pendingMessages[receiver].update({sender: [record]})
                                            else:
                                                pendingMessages.update({receiver: {sender: [record]}})

                                            pendingMessagesSemaphore.release()
                                        else:
                                            time.sleep(0.1)

                                    savePendingToDisk()
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

    # --- LOGIN HANDSHAKE (first recv must be LOGIN:...) ---
    datos = None
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
            text = ""
            try:
                text = datos.decode().strip()
            except Exception:
                text = ""

            isLogin, u, p = parseLogin(text)

            if isLogin and u is not None and p is not None:
                if authenticate(u, p):
                    receiver = u
                else:
                    activo = False
            else:
                activo = False

            if activo:
                # Save the socket
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
            else:
                # login KO
                activo = sendReplyAndMaybeClose(connection, "KO")

    # --- UPDATE LOOP ---
    if activo:
        connection.settimeout(1)

        buffer = b""

        while activo:
            chunk = None
            gotChunk = False

            try:
                chunk = connection.recv(1024)
                gotChunk = True
            except socket.timeout:
                gotChunk = False
            except ConnectionResetError:
                activo = False
            except Exception:
                activo = False

            if activo and gotChunk:
                if not chunk:
                    activo = False
                else:
                    buffer += chunk
                    lines, buffer = protocol.splitLines(buffer)

                    # We may receive multiple UPDATE lines; process each
                    idx = 0
                    while idx < len(lines) and activo:
                        reqText = lines[idx].strip()

                        # Parse UPDATE request
                        isUpd = False
                        u_origen = None
                        u_destino = None
                        lastTs = None

                        isList, uList = protocol.isListRequest(reqText)
                        isRead, readUser, readPeer, readUpToTs = protocol.isReadRequest(reqText)

                        if isList and receiver is not None and uList == receiver:
                            # Build conversations list from pendingMessages for this receiver
                            conv = []   # list of tuples (sender, count)

                            Acquired = False
                            while not Acquired:
                                if pendingMessagesSemaphore.acquire(timeout=1):
                                    Acquired = True

                                    mensaje = pendingMessages.get(receiver, None)
                                    if mensaje:
                                        for sender in mensaje:
                                            msg_list = mensaje[sender]
                                            try:
                                                conv.append((sender, len(msg_list)))
                                            except Exception:
                                                conv.append((sender, 0))

                                    pendingMessagesSemaphore.release()
                                else:
                                    time.sleep(0.1)

                            # Header: N
                            header = protocol.makeMsgDeliver999("server", receiver, time.time(), "LIST", 0, str(len(conv)))
                            sentOk = sendReply(connection, header)

                            # ACK header
                            if sentOk:
                                ack = None
                                try:
                                    ack = connection.recv(1024)
                                except Exception:
                                    ack = None
                                if not ack or ack.decode().strip() != "OK":
                                    sentOk = False

                            # Send N lines, each needs OK
                            if sentOk:
                                i = 0
                                while i < len(conv) and sentOk:
                                    s = conv[i][0]
                                    c = conv[i][1]

                                    # For each conversation line:
                                    # origen = sender, destino = receiver, ts=0, estado=LIST, texto = count
                                    line = protocol.makeMsgDeliver999(s, receiver, 0, "LIST", 0, str(c))
                                    sentOk = sendReply(connection, line)

                                    if sentOk:
                                        ack2 = None
                                        try:
                                            ack2 = connection.recv(1024)
                                        except Exception:
                                            ack2 = None
                                        if not ack2 or ack2.decode().strip() != "OK":
                                            sentOk = False

                                    i = i + 1

                            if not sentOk:
                                activo = False
                        
                        elif isRead and receiver is not None and readUser == receiver:
                            # receiver is authenticated user on this socket
                            # mark server history: messages from readPeer -> receiver become LEIDO up to readUpToTs
                            markReadForPair(readPeer, receiver, readUpToTs)

                            # enqueue a LEIDO event for the other side (readPeer), so they update their local outgoing statuses
                            enqueueEvent(readPeer, "LEIDO", receiver, readUpToTs)
                            
                            # ACK the READ request
                            okSent = sendReply(connection, "OK")
                            if not okSent:
                                activo = False
                        else:
                            if reqText != "":
                                isUpd, u_origen, u_destino, lastTs = protocol.isUpdateRequest(reqText)

                            # Only accept UPDATE from the authenticated user
                            if isUpd and receiver is not None and u_origen == receiver:
                                # Gather messages >= lastTs (minimal: from pendingMessages only)
                                toSend = []

                                Acquired = False
                                while not Acquired:
                                    if pendingMessagesSemaphore.acquire(timeout=1):
                                        Acquired = True

                                        mensaje = pendingMessages.get(receiver, None)
                                        if mensaje:
                                            for sender in mensaje:
                                                msg_list = mensaje[sender]
                                                j = 0
                                                while j < len(msg_list):
                                                    item = msg_list[j]

                                                    ts_msg = None
                                                    body = None

                                                    # Support dict record
                                                    if isinstance(item, dict):
                                                        ts_msg = item.get("ts", None)
                                                        body = item.get("body", None)

                                                    # Support tuple/list legacy just in case
                                                    elif isinstance(item, tuple) or isinstance(item, list):
                                                        if len(item) >= 2:
                                                            ts_msg = item[0]
                                                            body = item[1]

                                                    if ts_msg is not None and body is not None:
                                                        try:
                                                            toSend.append((sender, float(ts_msg), str(body)))
                                                        except Exception:
                                                            dummy = 0

                                                    j = j + 1

                                        pendingMessagesSemaphore.release()
                                    else:
                                        time.sleep(0.1)

                                eventsToSend = []

                                AcquiredE = False
                                while not AcquiredE:
                                    if pendingEventsSemaphore.acquire(timeout=1):
                                        AcquiredE = True
                                        try:
                                            evs = pendingEvents.get(receiver, None)
                                            if evs:
                                                j = 0
                                                while j < len(evs):
                                                    ev = evs[j]
                                                    try:
                                                        if float(ev["ts"]) > float(lastTs):
                                                            eventsToSend.append(ev)
                                                    except Exception:
                                                        dummy = 0
                                                    j = j + 1
                                        finally:
                                            pendingEventsSemaphore.release()
                                    else:
                                        time.sleep(0.1)


                                # Order by timestamp
                                try:
                                    toSend.sort(key=lambda x: x[1])
                                except Exception:
                                    dummy = 0

                                # 1) Send header with N and wait OK
                                header = protocol.makeMsgDeliver999(
                                    "server", receiver, time.time(), "UPDATE", 0, str(len(toSend) + len(eventsToSend))
                                )

                                sentOk = sendReply(connection, header)

                                if sentOk:
                                    ack = None
                                    try:
                                        ack = connection.recv(1024)
                                    except Exception:
                                        ack = None
                                    if not ack or ack.decode().strip() != "OK":
                                        sentOk = False

                                # 2) Send N messages; each requires OK
                                if sentOk:
                                    i = 0
                                    while i < len(toSend) and sentOk:
                                        sender = toSend[i][0]
                                        ts_msg = toSend[i][1]
                                        body = toSend[i][2]

                                        line = protocol.makeMsgDeliver999(
                                            sender, receiver, ts_msg, "ENTREGADO", time.time(), body
                                        )

                                        sentOk = sendReply(connection, line)

                                        if sentOk:
                                            ack2 = None
                                            try:
                                                ack2 = connection.recv(1024)
                                            except Exception:
                                                ack2 = None
                                            if not ack2 or ack2.decode().strip() != "OK":
                                                sentOk = False
                                            else:
                                                # Message ACKed: mark delivered + remove only that message from pendingMessages[receiver][sender]
                                                markDeliveredForPair(sender, receiver, ts_msg)
                                                enqueueEvent(sender, "ENTREGADO", receiver, ts_msg)

                                                AcquiredRM = False
                                                while not AcquiredRM:
                                                    if pendingMessagesSemaphore.acquire(timeout=1):
                                                        AcquiredRM = True
                                                        try:
                                                            if receiver in pendingMessages and sender in pendingMessages[receiver]:
                                                                lst = pendingMessages[receiver][sender]
                                                                EPS = 0.0001
                                                                newlst = []
                                                                m = 0
                                                                while m < len(lst):
                                                                    it = lst[m]
                                                                    ts_it = None
                                                                    try:
                                                                        if isinstance(it, dict):
                                                                            ts_it = float(it.get("ts", -1))
                                                                        elif isinstance(it, tuple) or isinstance(it, list):
                                                                            ts_it = float(it[0])
                                                                    except Exception:
                                                                        ts_it = None
                                                                    
                                                                    keep = True
                                                                    if ts_it is not None:
                                                                        try:
                                                                            if abs(float(ts_it) - float(ts_msg)) < EPS:
                                                                                keep = False
                                                                        except Exception:
                                                                            keep = True
                                                                    if keep:
                                                                        newlst.append(it)
                                                                    m = m + 1

                                                                pendingMessages[receiver][sender] = newlst

                                                                if len(pendingMessages[receiver][sender]) == 0:
                                                                    del pendingMessages[receiver][sender]
                                                                if len(pendingMessages[receiver]) == 0:
                                                                    del pendingMessages[receiver]
                                                        finally:
                                                            pendingMessagesSemaphore.release()
                                                    else:
                                                        time.sleep(0.1)


                                        i = i + 1

                                # 3) Send LEIDO/ENTREGADO events; each requires OK
                                if sentOk:
                                    k = 0
                                    while k < len(eventsToSend) and sentOk:
                                        ev = eventsToSend[k]
                                        evTs = float(ev.get("ts", time.time()))
                                        kind = ev.get("kind", "")
                                        peer = ev.get("from", "")
                                        upTo = float(ev.get("upTo", 0.0))

                                        # origen = reader, destino = receiver (the one receiving this event)
                                        line = protocol.makeMsgDeliver999(peer, receiver, evTs, kind, upTo, "")
                                        sentOk = sendReply(connection, line)

                                        if sentOk:
                                            ack3 = None
                                            try:
                                                ack3 = connection.recv(1024)
                                            except Exception:
                                                ack3 = None
                                            if not ack3 or ack3.decode().strip() != "OK":
                                                sentOk = False

                                        k = k + 1
                                
                                if sentOk:
                                    savePendingToDisk()

                                    # remove events that were sent
                                    AcquiredE2 = False
                                    while not AcquiredE2:
                                        if pendingEventsSemaphore.acquire(timeout=1):
                                            AcquiredE2 = True
                                            try:
                                                if receiver in pendingEvents:
                                                    # keep only events with ts <= lastTs? easiest is remove those we sent
                                                    remaining = []
                                                    x = 0
                                                    while x < len(pendingEvents[receiver]):
                                                        ev = pendingEvents[receiver][x]
                                                        keep = True
                                                        y = 0
                                                        while y < len(eventsToSend) and keep:
                                                            try:
                                                                if float(ev["ts"]) == float(eventsToSend[y]["ts"]):
                                                                    keep = False
                                                            except Exception:
                                                                dummy = 0
                                                            y = y + 1
                                                        if keep:
                                                            remaining.append(ev)
                                                        x = x + 1
                                                    if len(remaining) == 0:
                                                        del pendingEvents[receiver]
                                                    else:
                                                        pendingEvents[receiver] = remaining
                                            finally:
                                                pendingEventsSemaphore.release()
                                        else:
                                            time.sleep(0.1)

                                # If sending failed mid-way, keep pending as-is (so it retries next UPDATE)
                                if not sentOk:
                                    activo = False

                            else:
                                # Not an UPDATE request: ignore (keep alive)
                                dummy = 0

                        idx = idx + 1

            elif activo and not gotChunk:
                dummy = 0

    print("El cliente ha cerrado su conexion 999")

    Acquired = False
    while not Acquired:
        if userSocketsSemaphore.acquire(timeout=1):
            Acquired = True
            if receiver is not None:
                userSockets.pop(receiver, None)
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

loadPendingFromDisk()

inboxListener = threading.Thread(target=listenInbound)
outboxListener = threading.Thread(target=listenOutbound)
# hiloEscuchar = threading.Thread(target=menu)

inboxListener.start()
outboxListener.start()
# hiloEscuchar.start()

inboxListener.join()
outboxListener.join()
# hiloEscuchar.join()