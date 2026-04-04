#!/bin/bash
set -e

PROJECT_DIR="/home/azureuser/Super-Easy-Customer-Support"
VENV="$PROJECT_DIR/.venv/bin"
LOG_DIR="$PROJECT_DIR/logs"

mkdir -p $LOG_DIR

echo "=== Starting deployment ==="

cd $PROJECT_DIR

echo ">>> Pulling latest code..."
git pull origin main

echo ">>> Installing dependencies..."
source $VENV/activate
pip install -r requirements.txt -q

echo ">>> Stopping old processes..."
pkill -f "uvicorn app.main:app" || true
pkill -f "streamlit run dashboard/main.py" || true
sleep 3

echo ">>> Starting services..."
nohup $VENV/uvicorn app.main:app --host 0.0.0.0 --port 8000 > $LOG_DIR/fastapi.log 2>&1 &
sleep 3
nohup $VENV/streamlit run dashboard/main.py --server.port 8501 --server.address 0.0.0.0 > $LOG_DIR/streamlit.log 2>&1 &
sleep 3

echo ">>> Status check..."
pgrep -f "uvicorn app.main:app" && echo "FastAPI: OK" || echo "FastAPI: FAILED"
pgrep -f "streamlit run dashboard/main.py" && echo "Streamlit: OK" || echo "Streamlit: FAILED"

echo "=== Deployment complete ==="
