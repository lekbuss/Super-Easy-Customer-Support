#!/bin/bash
set -e

PROJECT_DIR="/home/azureuser/Super-Easy-Customer-Support"

echo "=== Starting deployment ==="

cd $PROJECT_DIR

echo ">>> Pulling latest code..."
git pull origin main

echo ">>> Installing dependencies..."
source .venv/bin/activate
pip install -r requirements.txt -q

echo ">>> Restarting services..."
sudo -n /usr/bin/systemctl restart fastapi
sudo -n /usr/bin/systemctl restart streamlit

echo ">>> Status check..."
sudo -n /usr/bin/systemctl is-active fastapi && echo "FastAPI: OK" || echo "FastAPI: FAILED"
sudo -n /usr/bin/systemctl is-active streamlit && echo "Streamlit: OK" || echo "Streamlit: FAILED"

echo "=== Deployment complete ==="
