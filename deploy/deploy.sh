#!/bin/bash
set -e

PROJECT_DIR="/home/azureuser/Super-Easy-Customer-Support/project"

echo "=== Starting deployment ==="

cd $PROJECT_DIR

echo ">>> Pulling latest code..."
git pull origin main

echo ">>> Installing dependencies..."
source .venv/bin/activate
pip install -r requirements.txt -q

echo ">>> Restarting services..."
sudo systemctl restart fastapi
sudo systemctl restart streamlit

echo ">>> Status check..."
sudo systemctl is-active fastapi && echo "FastAPI: OK" || echo "FastAPI: FAILED"
sudo systemctl is-active streamlit && echo "Streamlit: OK" || echo "Streamlit: FAILED"

echo "=== Deployment complete ==="
