#!/usr/bin/env bash
# Use Python 3 (system "python" may be Python 2.7 on Ubuntu).
cd "$(dirname "$0")"
exec python3 main.py "$@"
