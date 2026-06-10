#!/bin/bash
# SAR Redact v2 — Mac / Linux launcher
cd "$(dirname "$0")"

if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    venv/bin/pip install -r requirements.txt
fi

venv/bin/python serve.py
