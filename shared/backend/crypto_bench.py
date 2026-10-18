"""
crypto_bench.py - measures encryption/hashing speed on this machine (LinuxONE has built-in crypto instructions).
Run:  python crypto_bench.py        Needs: pip install cryptography
Writes models/crypto_benchmark.json. It reports what it measures; it does not compare against other machines.
"""
import hashlib
import json
import os
import time

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

HERE = os.path.dirname(os.path.abspath(__file__))
MB = 1024 * 1024


def rate(fn, mb, reps=5):
    best = 1e9
    for _ in range(reps):
        t = time.time(); fn(); best = min(best, time.time() - t)
    return round(mb / best / 1024, 2)               # GB/s (best of reps)


buf = os.urandom(64 * MB)
key, nonce = os.urandom(32), os.urandom(12)
aes = AESGCM(key)
ct = aes.encrypt(nonce, buf, None)
feats = ""
for line in open("/proc/cpuinfo"):
    if line.startswith("features"):
        feats = line.split(":", 1)[1].split(); break
out = {"buffer_mb": 64,
       "aes256_gcm_encrypt_gb_per_s": rate(lambda: aes.encrypt(nonce, buf, None), 64),
       "aes256_gcm_decrypt_gb_per_s": rate(lambda: aes.decrypt(nonce, ct, None), 64),
       "sha256_gb_per_s": rate(lambda: hashlib.sha256(buf).digest(), 64),
       "cpu_has_message_security_assist_flag": "msa" in feats,
       "note": "Python's cryptography library uses OpenSSL, which uses the processor's crypto instructions on s390x."}
os.makedirs(os.path.join(HERE, "models"), exist_ok=True)
json.dump(out, open(os.path.join(HERE, "models", "crypto_benchmark.json"), "w"), indent=1)
print(json.dumps(out, indent=1))
