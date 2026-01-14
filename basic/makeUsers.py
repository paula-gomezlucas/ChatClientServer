# make_users.py
import os
import json
import base64
import hashlib
import getpass

ITERATIONS = 200000 # Number of iterations for PBKDF2 -> the more the better, but slower

def hash_password(password, salt_bytes, iterations):
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt_bytes, iterations)
    return dk

users = {}

more = True
while more:
    username = input("Username: ").strip()
    if username == "":
        more = False
    else:
        pw = getpass.getpass("Password: ")
        salt = os.urandom(16)
        dk = hash_password(pw, salt, ITERATIONS)

        users[username] = {
            "salt": base64.b64encode(salt).decode(),
            "hash": base64.b64encode(dk).decode(),
            "iterations": ITERATIONS
        }

        again = input("Add another user? (y/n): ").strip().lower()
        if again != "y":
            more = False

payload = {"users": users}

f = None
try:
    f = open("users.json", "w", encoding="utf-8")
    f.write(json.dumps(payload, indent=2, ensure_ascii=False))
finally:
    if f is not None:
        f.close()

print("Created users.json")
