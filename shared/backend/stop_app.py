"""stop_app.py - stops any running app.py (the container has no pkill). Run: python3 stop_app.py"""
import os
import signal

n = 0
for pid in filter(str.isdigit, os.listdir("/proc")):
    try:
        cmd = open(f"/proc/{pid}/cmdline", "rb").read()
        if b"app.py" in cmd and b"stop_app" not in cmd and int(pid) != os.getpid():
            os.kill(int(pid), signal.SIGTERM)
            print("stopped", pid)
            n += 1
    except Exception:
        pass
print("nothing was running" if n == 0 else "done")
