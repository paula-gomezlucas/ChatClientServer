# protocol.py

def makeSend666(sender, receiver, msg):
    # sender:receiver:msg
    sender = str(sender).strip()
    receiver = str(receiver).strip()
    msg = str(msg)
    return sender + ":" + receiver + ":" + msg


def makeDeliver999(sender, msg):
    # sender:msg\n   (newline is IMPORTANT for framing)
    sender = str(sender).strip()
    msg = str(msg)
    return sender + ":" + msg + "\n"


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
