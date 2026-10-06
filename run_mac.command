#!/bin/bash
cd "$(dirname "$0")"
if command -v python3 >/dev/null 2>&1; then
  python3 pet_app.py
else
  echo "Ping & Purr needs Python 3.10 or newer."
  echo "Install it from https://www.python.org/downloads/ then run this again."
  read -r -p "Press Enter to close... "
fi