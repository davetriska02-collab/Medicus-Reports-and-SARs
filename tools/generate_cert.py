"""Generate a self-signed TLS certificate for SAR Redact server mode.

Usage:  python tools/generate_cert.py [extra-hostname-or-ip ...]

Writes data/tls/cert.pem and data/tls/key.pem (10-year validity) with SANs
for this machine's hostname, its LAN IP and localhost, plus any extras given
on the command line. Requires the 'cryptography' package:

    pip install cryptography

No admin rights needed — this is just two files in the data folder. Browsers
will show a one-time "not trusted" warning for self-signed certs; staff can
accept it, or IT can add the cert to the trusted store via group policy.
"""
import os
import socket
import sys
import pathlib
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

TLS_DIR = pathlib.Path(__file__).resolve().parent.parent / "data" / "tls"


def main():
    try:
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
    except ImportError:
        print("ERROR: the 'cryptography' package is required.")
        print("Install it with:  pip install cryptography")
        sys.exit(1)

    hostname = socket.gethostname()
    try:
        lan_ip = socket.gethostbyname(hostname)
    except OSError:
        lan_ip = ""

    san_names = [x509.DNSName(hostname), x509.DNSName("localhost")]
    import ipaddress
    for extra in ([lan_ip, "127.0.0.1"] + sys.argv[1:]):
        if not extra:
            continue
        try:
            san_names.append(x509.IPAddress(ipaddress.ip_address(extra)))
        except ValueError:
            san_names.append(x509.DNSName(extra))

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, hostname),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "SAR Redact"),
    ])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=3650))
            .add_extension(x509.SubjectAlternativeName(san_names), critical=False)
            .sign(key, hashes.SHA256()))

    os.makedirs(TLS_DIR, exist_ok=True)
    cert_path = TLS_DIR / "cert.pem"
    key_path = TLS_DIR / "key.pem"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption()))
    try:
        os.chmod(key_path, 0o600)
    except OSError:
        pass  # Windows

    print(f"Written: {cert_path}")
    print(f"Written: {key_path}")
    print(f"SANs: {hostname}, localhost, {lan_ip or '(no LAN IP found)'}"
          + (", " + ", ".join(sys.argv[1:]) if sys.argv[1:] else ""))
    print("\nRestart the server — it will switch to HTTPS automatically")
    print("(install cheroot first:  pip install cheroot)")


if __name__ == "__main__":
    main()
