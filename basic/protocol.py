# protocol.py
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
