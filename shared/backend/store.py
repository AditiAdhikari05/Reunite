"""
store.py - tiny helpers to save JSON files safely, optionally encrypted with AES-256-GCM.
Set the STATE_KEY environment variable (a passphrase) to turn encryption on. Needs: pip install cryptography
"""
import hashlib
import json
import os

MAGIC = b"RAI1"          # first bytes of an encrypted file


def state_key():
    """AES-256 key made from the STATE_KEY passphrase, or None when encryption is off."""
    k = os.environ.get("STATE_KEY", "")
    if not k:
        return None
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: F401
    except ImportError:
        raise RuntimeError("STATE_KEY is set but the 'cryptography' package is missing. Run: pip install cryptography")
    return hashlib.pbkdf2_hmac("sha256", k.encode(), b"reunite-ai-state-v1", 200_000, dklen=32)


def read_json(path, key=None):
    raw = open(path, "rb").read()
    if raw.startswith(MAGIC):
        if not key:
            raise RuntimeError(f"{os.path.basename(path)} is encrypted. Start with the same STATE_KEY that was used to save it.")
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        raw = AESGCM(key).decrypt(raw[4:16], raw[16:], MAGIC)
    return json.loads(raw)


def write_json(path, obj, key=None):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    data = json.dumps(obj).encode()
    if key:                                       # OpenSSL uses the CPU's crypto instructions on s390x
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        nonce = os.urandom(12)
        data = MAGIC + nonce + AESGCM(key).encrypt(nonce, data, MAGIC)
    tmp = path + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(data)
    os.replace(tmp, path)
