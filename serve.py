"""
SAR Redact — Production launcher.

HTTP mode (default): Waitress, multi-threaded WSGI.
HTTPS mode: drop cert.pem + key.pem into data/tls/ (see tools/generate_cert.py)
and install cheroot (pip install cheroot). The launcher detects the cert and
serves TLS automatically — no admin rights involved.

Usage (Windows):  venv/Scripts/python serve.py   or   python-runtime/python serve.py
Usage (Mac/Linux): venv/bin/python serve.py
"""
import os
import pathlib
import socket

from app import app, APP_VERSION
from sar.practice_config import get_config

HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", 5000))

BASE_DIR = pathlib.Path(__file__).resolve().parent
TLS_CERT = BASE_DIR / "data" / "tls" / "cert.pem"
TLS_KEY = BASE_DIR / "data" / "tls" / "key.pem"


def _lan_ip() -> str:
    try:
        return socket.gethostbyname(socket.gethostname())
    except Exception:
        return "this machine's IP"


def _write_connect_file(scheme: str):
    """Write CONNECT.txt so staff onboarding is 'open this file, click the link'."""
    hostname = socket.gethostname()
    lines = [
        f"SAR Redact v{APP_VERSION} — connection details",
        "=" * 46,
        "",
        "Open one of these addresses in your browser:",
        "",
        f"  {scheme}://{hostname}:{PORT}",
        f"  {scheme}://{_lan_ip()}:{PORT}",
        "",
        "On the server machine itself:",
        f"  {scheme}://localhost:{PORT}",
        "",
        "Bookmark it. No software install is needed on your machine.",
    ]
    try:
        (BASE_DIR / "CONNECT.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError:
        pass


def _banner(scheme: str, practice: str, extra: str = ""):
    bar = "=" * max(58, len(practice) + 10)
    print()
    print(bar)
    print(f"  SAR Redact v{APP_VERSION} — {practice}")
    print(bar)
    print(f"  Local:    {scheme}://localhost:{PORT}")
    print(f"  Network:  {scheme}://{_lan_ip()}:{PORT}")
    print(f"  Hostname: {scheme}://{socket.gethostname()}:{PORT}")
    if extra:
        print(f"  {extra}")
    print(bar)
    print("  Keep this window open while using SAR Redact.")
    print("  Press Ctrl+C to stop.\n")


def _serve_https(practice: str) -> bool:
    """Serve TLS via cheroot if cert + package are available. Returns False
    to fall back to HTTP."""
    if not (TLS_CERT.exists() and TLS_KEY.exists()):
        return False
    try:
        from cheroot.wsgi import Server
        from cheroot.ssl.builtin import BuiltinSSLAdapter
    except ImportError:
        print("  NOTE: data/tls/ certificate found but cheroot is not installed.")
        print("        Run: pip install cheroot   — falling back to HTTP.\n")
        return False
    app.config["SESSION_COOKIE_SECURE"] = True
    server = Server((HOST, PORT), app)
    server.ssl_adapter = BuiltinSSLAdapter(str(TLS_CERT), str(TLS_KEY))
    _write_connect_file("https")
    _banner("https", practice,
            "TLS: self-signed — browsers show a one-time warning. See INSTALL.md.")
    try:
        server.start()
    except KeyboardInterrupt:
        server.stop()
    return True


if __name__ == "__main__":
    practice = get_config().get("practice_name", "SAR Redact")
    try:
        if not _serve_https(practice):
            from waitress import serve
            _write_connect_file("http")
            _banner("http", practice)
            serve(app, host=HOST, port=PORT, threads=8)
    except OSError as e:
        if "address already in use" in str(e).lower() or "10048" in str(e) or "98" in str(e):
            print()
            print(f"  ERROR: Port {PORT} is already in use.")
            print(f"  Another program (or a previous SAR Redact instance) is using port {PORT}.")
            print()
            print("  Options:")
            print("    1. Close the other program and try again.")
            print(f"    2. Set a different port: set PORT=5001 && python serve.py")
            print()
        else:
            raise
