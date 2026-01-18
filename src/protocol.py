# protocol.py
import time
import json
import os
import threading

readWriteLock = threading.Lock()

def makeMsgSend666(origen, destino, timestamp, mensaje):
    origen = str(origen).strip()
    destino = str(destino).strip()
    ts = str(timestamp)
    msg = str(mensaje).replace('"', "'")
    return "MSG;" + origen + ";" + destino + ";" + ts + ";\"" + msg + "\""


def parseMsgSend666(line):
    # Expect: MSG;origen;destino;timestamp;"mensaje"
    ok = False
    origen = None
    destino = None
    ts = None
    mensaje = None

    try:
        parts = line.split(";", 4)
        if len(parts) == 5 and parts[0] == "MSG":
            origen = parts[1].strip()
            destino = parts[2].strip()
            ts = float(parts[3].strip())

            mensajeRaw = parts[4].strip()
            if len(mensajeRaw) >= 2 and mensajeRaw[0] == "\"" and mensajeRaw[-1] == "\"":
                mensaje = mensajeRaw[1:-1]
                ok = True
    except Exception:
        ok = False

    return ok, origen, destino, ts, mensaje

def makeMsgDeliver999(origen, destino, timestamp, estado, tsEstado, mensaje):
    origen = str(origen).strip()
    destino = str(destino).strip()
    ts = str(timestamp)
    estado = str(estado).strip()
    tsE = str(tsEstado)
    msg = str(mensaje).replace('"', "'")
    return "MSG;" + origen + ";" + destino + ";" + ts + ";" + estado + ";" + tsE + ";\"" + msg + "\"\n"

def parseDeliver999(line):
    # MSG;origen;destino;timestamp;estado;tiempoEstado;"mensaje"
    ok = False
    origen = destino = estado = mensaje = None
    ts = tsEstado = None

    try:
        parts = line.split(";", 6)
        if len(parts) == 7 and parts[0] == "MSG":
            origen = parts[1].strip()
            destino = parts[2].strip()
            ts = float(parts[3].strip())
            estado = parts[4].strip()
            tsEstado = float(parts[5].strip())
            mraw = parts[6].strip()
            if len(mraw) >= 2 and mraw[0] == "\"" and mraw[-1] == "\"":
                mensaje = mraw[1:-1]
                ok = True
    except Exception:
        ok = False

    return ok, origen, destino, ts, estado, tsEstado, mensaje


def splitLines(buffer_bytes):
    # Input: bytes buffer (may contain partial messages)
    # Output: (lines_list_as_str, remaining_buffer_bytes)

    if buffer_bytes is None:
        return [], b""

    try:
        text = buffer_bytes.decode()
    except Exception:
        # If decoding fails, drop bad bytes to avoid blocking the whole thread
        return [], b""

    parts = text.split("\n")

    # if no newline yet, keep everything in remaining buffer
    if len(parts) == 1:
        return [], buffer_bytes

    # all except last are complete lines
    complete_lines = parts[:-1]
    remaining = parts[-1].encode()

    # strip empty ones
    cleaned = []
    for line in complete_lines:
        if line.strip() != "":
            cleaned.append(line.strip())

    return cleaned, remaining

def makeUpdate999(origen, destino, lastTs):
    ts = str(time.time())
    msg = ""
    return "MSG;" + origen + ";" + destino + ";" + ts + ";UPDATE;" + str(lastTs) + ";\"\""


def isUpdateRequest(line):
    ok, origen, destino, ts, estado, tsEstado, mensaje = parseDeliver999(line)
    if ok and estado == "UPDATE":
        return True, origen, destino, tsEstado
    return False, None, None, None

def makeList999(user):
    # LIST request always uses dest "@", ts=0
    return "LST;" + str(user) + ";@;0\n"

def isListRequest(line):
    # Returns (isList, user)
    ok = False
    u = None
    try:
        parts = line.strip().split(";", 3)
        if len(parts) >= 3:
            if parts[0] == "LST":
                u = parts[1].strip()
                ok = True
    except Exception:
        ok = False
        u = None
    return ok, u

def makeRead999(user, peer, readUpToTs):
    # READ request: MSG;user;peer;0;READ;readUpToTs;""
    return "MSG;" + str(user) + ";" + str(peer) + ";0;READ;" + str(readUpToTs) + ";\"\"\n"

def isReadRequest(line):
    ok, origen, destino, ts, estado, tsEstado, mensaje = parseDeliver999(line)
    if ok and estado == "READ":
        # origen = reader, destino = peer, tsEstado = readUpToTs
        return True, origen, destino, tsEstado
    return False, None, None, None


def atomicWriteJson(path, obj):
    tmp = path + ".tmp"
    f = None
    Acquired = False
    while not Acquired:
        if readWriteLock.acquire(timeout=5):
            Acquired = True
            try:
                f = open(tmp, "w", encoding="utf-8")
                f.write(json.dumps(obj, ensure_ascii=False, indent=2))
                f.close()
                f = None
                os.replace(tmp, path)   # atómico en Windows y Linux
                readWriteLock.release()
                return True
            except Exception:
                try:
                    if f is not None:
                        f.close()
                except Exception:
                    dummy = 0
                try:
                    if os.path.exists(tmp):
                        os.remove(tmp)
                except Exception:
                    dummy2 = 0
                readWriteLock.release()
                return False
        else:
            time.sleep(0.5)