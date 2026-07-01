#!/bin/bash
set -e

PROJECT="/home/alzemora/ALzemora-Grad-Ras-pi-5"

IP=$(hostname -I | awk '{print $1}')
echo "Pi IP: $IP  (also reachable as alzemora.local)"

cd "$PROJECT/Backend"
source venv/bin/activate
export LD_LIBRARY_PATH=/home/alzemora/.pyenv/versions/3.10.0/lib:${LD_LIBRARY_PATH}
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
