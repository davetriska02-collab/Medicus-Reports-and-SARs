"""Build the fully offline Windows bundle.

Produces a single zip containing the application, the embeddable Python
runtime and all dependencies pre-installed — for NHS practices whose proxy
blocks PowerShell downloads / PyPI. The recipient extracts the zip and runs
start_server.bat; nothing is downloaded at any point.

Run on any machine WITH internet access (Linux/Mac/Windows, Python 3.9+):

    python tools/build_offline_bundle.py [--tls] [--out dist/]

--tls additionally bundles cheroot + cryptography for HTTPS server mode.
"""
import argparse
import io
import os
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PY_VERSION = "3.12.9"
PY_EMBED_URL = (f"https://www.python.org/ftp/python/{PY_VERSION}/"
                f"python-{PY_VERSION}-embed-amd64.zip")

# Files/dirs shipped to practices (no tests, no repo docs, no data)
APP_ITEMS = [
    "app.py", "serve.py", "requirements.txt",
    "start_server.bat", "start_server.sh", "server_loop.bat",
    "install_as_server.bat", "update.bat", "SAR-Redact.html",
    "README.md", "INSTALL.md", "EASY_INSTALL_GUIDE.md",
    "SECURITY.md", "CHANGELOG.md",
    "sar", "static", "templates", "tools",
]
EMPTY_DIRS = ["data", "uploads", "output"]


def app_version() -> str:
    m = re.search(r'APP_VERSION\s*=\s*"([^"]+)"', (REPO / "app.py").read_text())
    return m.group(1) if m else "0.0.0"


def fetch_embed_python(staging: Path):
    print(f"[1/4] Downloading Python {PY_VERSION} embeddable runtime...")
    with urllib.request.urlopen(PY_EMBED_URL, timeout=60) as resp:
        data = resp.read()
    runtime = staging / "python-runtime"
    runtime.mkdir(parents=True)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        zf.extractall(runtime)
    # Enable site processing so Lib/site-packages is importable
    pth = next(runtime.glob("python3*._pth"))
    pth.write_text(pth.read_text().replace("#import site", "import site"))
    print(f"      {len(data)//1024//1024} MB extracted, {pth.name} patched")


# Pure-Python dependencies that ship only an sdist on PyPI (no wheel), which
# --only-binary rejects. They are built into universal py3-none-any wheels
# locally (--use-pep517 sidesteps a Debian setuptools bug) and offered to the
# Windows resolve via --find-links. extract-msg -> red-black-tree-mod.
SDIST_ONLY_PURE = ("red-black-tree-mod",)


def install_wheels(staging: Path, with_tls: bool):
    print("[2/4] Installing Windows wheels into the runtime...")
    target = staging / "python-runtime" / "Lib" / "site-packages"
    wheels = staging / "wheels"
    subprocess.run(
        [sys.executable, "-m", "pip", "wheel", "--quiet", "--use-pep517",
         "--no-deps", "-w", str(wheels), *SDIST_ONLY_PURE], check=True)
    for w in wheels.iterdir():
        if not w.name.endswith("-py3-none-any.whl") and \
           not w.name.endswith("-py2.py3-none-any.whl"):
            raise SystemExit(f"{w.name} is not a universal wheel — it cannot "
                             "be shipped in the Windows bundle")
    cmd = [
        sys.executable, "-m", "pip", "install",
        "--quiet", "--no-compile", "--target", str(target),
        "--platform", "win_amd64", "--implementation", "cp",
        "--python-version", "312", "--only-binary=:all:",
        "--find-links", str(wheels),
        "-r", str(REPO / "requirements.txt"),
    ]
    if with_tls:
        cmd += ["cheroot", "cryptography"]
    subprocess.run(cmd, check=True)
    shutil.rmtree(wheels)
    n = sum(1 for _ in target.iterdir())
    print(f"      {n} top-level packages installed")


def copy_app(staging: Path):
    print("[3/4] Copying application files...")
    for item in APP_ITEMS:
        src = REPO / item
        if not src.exists():
            print(f"      WARNING: {item} missing, skipped")
            continue
        if src.is_dir():
            shutil.copytree(src, staging / item,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            shutil.copy2(src, staging / item)
    for d in EMPTY_DIRS:
        (staging / d).mkdir(exist_ok=True)
        (staging / d / ".gitkeep").touch()


def make_zip(staging: Path, out_dir: Path, version: str, tls: bool = False) -> Path:
    print("[4/4] Writing bundle zip...")
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = "-tls" if tls else ""
    zip_path = out_dir / f"sar-redact-offline{suffix}-v{version}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(staging):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for f in files:
                if f.endswith(".pyc"):
                    continue
                full = Path(root) / f
                zf.write(full, Path("sar-redact") / full.relative_to(staging))
    size_mb = zip_path.stat().st_size / 1e6
    print(f"      {zip_path}  ({size_mb:.0f} MB)")
    return zip_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tls", action="store_true",
                    help="bundle cheroot + cryptography for HTTPS")
    ap.add_argument("--out", default=str(REPO / "dist"))
    args = ap.parse_args()

    version = app_version()
    print(f"Building offline bundle for SAR Redact v{version}"
          + (" (with TLS extras)" if args.tls else ""))
    staging = REPO / "dist" / ".staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    try:
        fetch_embed_python(staging)
        install_wheels(staging, args.tls)
        copy_app(staging)
        make_zip(staging, Path(args.out), version, tls=args.tls)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    print("\nDone. Recipient: extract the zip to C:\\SAR Redact\\ and run "
          "start_server.bat — no internet needed.")


if __name__ == "__main__":
    main()
