#!/bin/bash
# Обновление бота на EC2 после git push.
# Запускать на сервере: bash ~/job-hunt/deploy/update.sh

set -e

APP_DIR="$HOME/job-hunt"
SERVICE_NAME="job-hunt"

echo "=== Обновление $SERVICE_NAME ==="

cd "$APP_DIR"

echo "[1/4] Pull последних изменений..."
git pull origin main

echo "[2/4] Обновление зависимостей..."
.venv/bin/pip install -r requirements.txt --quiet

echo "[3/4] Перезапуск сервиса..."
sudo systemctl restart $SERVICE_NAME

echo "[4/4] Статус:"
sudo systemctl status $SERVICE_NAME --no-pager -l

echo ""
echo "Готово. Логи: sudo journalctl -u $SERVICE_NAME -f"
