#!/bin/bash
# Double-click this in Finder to start the HVAC Toolkit dev server.
# (Or run from Terminal: ./run.command)

cd "$(dirname "$0")" || exit 1

if [ ! -f ".venv/bin/activate" ]; then
  echo "Could not find .venv in this folder."
  echo "Run: python3 -m venv .venv  then  pip install -r requirements.txt"
  echo
  read -r -p "Press Enter to close…"
  exit 1
fi

# shellcheck source=/dev/null
source .venv/bin/activate
python -m flask --app wsgi run --debug

echo
echo "Server stopped."
read -r -p "Press Enter to close…"
