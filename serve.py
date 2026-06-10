"""
SAR Redact v2 — Production launcher.
Runs on Waitress (multi-threaded WSGI). Safe for LAN deployment.

Usage (Windows):  venv/Scripts/python serve.py   or   python-runtime/python serve.py
Usage (Mac/Linux): venv/bin/python serve.py
"""
import os
import socket
from waitress import serve
from app import app, APP_VERSION
from sar.practice_config import get_config

HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", 5000))

if __name__ == "__main__":
    cfg = get_config()
    practice = cfg.get("practice_name", "SAR Redact")

    try:
        lan_ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        lan_ip = "this machine's IP"

    bar = "=" * max(58, len(practice) + 10)
    print()
    print(bar)
    print(f"  SAR Redact v{APP_VERSION} — {practice}")
    print(bar)
    print(f"  Local:    http://localhost:{PORT}")
    print(f"  Network:  http://{lan_ip}:{PORT}")
    print(bar)
    print("  Keep this window open while using SAR Redact.")
    print("  Press Ctrl+C to stop.\n")

    try:
        serve(app, host=HOST, port=PORT, threads=8)
    except OSError as e:
        if "address already in use" in str(e).lower() or "10048" in str(e) or "98" in str(e):
            print()
            print(f"  ERROR: Port {PORT} is already in use.")
            print(f"  Another program (or a previous SAR Redact instance) is using port {PORT}.")
            print()
            print("  Options:")
            print(f"    1. Close the other program and try again.")
            print(f"    2. Set a different port: set PORT=5001 && python serve.py")
            print()
        else:
            raise
