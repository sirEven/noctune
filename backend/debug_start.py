#!/bin/bin/env python3
"""Start uvicorn with stderr logging to a file for debugging background crashes."""
import os, sys, subprocess

log_path = os.path.join(os.path.dirname(__file__), "server.log")

env = os.environ.copy()
env["PORT"] = "8001"
env["PYTHONPATH"] = os.path.join(os.path.dirname(__file__), "src")

with open(log_path, "w") as log:
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "noctune.main:create_app",
         "--host", "0.0.0.0", "--port", "8001", "--factory"],
        cwd=os.path.dirname(__file__),
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )

print(f"PID: {proc.pid}")
print(f"Log: {log_path}")

# Wait a bit and check
import time
time.sleep(3)

# Check if still running
poll = proc.poll()
if poll is not None:
    print(f"Process exited with code: {poll}")
    with open(log_path) as f:
        print("LOG OUTPUT:")
        print(f.read())
else:
    print("Process is running!")
    # Quick health check
    import urllib.request
    try:
        resp = urllib.request.urlopen("http://localhost:8001/api/status")
        print(f"Health check: {resp.status} {resp.read().decode()[:100]}")
    except Exception as e:
        print(f"Health check failed: {e}")