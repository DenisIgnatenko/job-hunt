#!/bin/bash
# EC2 Ubuntu 22.04 — первоначальная настройка.
# Запускать один раз после подключения по SSH.
# Использование: bash setup.sh <github-repo-url>
#
# Пример:
#   bash setup.sh https://github.com/yourusername/job-hunt.git

set -e  # выход при любой ошибке

REPO_URL="${1}"
APP_DIR="$HOME/job-hunt"
SERVICE_NAME="job-hunt"

if [ -z "$REPO_URL" ]; then
    echo "Использование: bash setup.sh <github-repo-url>"
    exit 1
fi

echo "=== [1/6] Обновление системы ==="
sudo apt update && sudo apt upgrade -y

echo "=== [2/6] Установка Python 3.11 и зависимостей ==="
sudo apt install -y python3 python3-pip python3-venv git

echo "=== [3/6] Клонирование репозитория ==="
if [ -d "$APP_DIR" ]; then
    echo "Директория уже существует, пропускаем клонирование"
else
    git clone "$REPO_URL" "$APP_DIR"
fi

echo "=== [4/6] Создание venv и установка зависимостей ==="
cd "$APP_DIR"
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

echo "=== [5/6] Настройка .env ==="
if [ ! -f "$APP_DIR/.env" ]; then
    cp "$APP_DIR/.env.example" "$APP_DIR/.env"
    echo ""
    echo "ВАЖНО: заполни переменные в $APP_DIR/.env"
    echo "  nano $APP_DIR/.env"
    echo ""
fi

echo "=== [6/6] Установка systemd сервиса ==="
# Подставляем реальный путь пользователя в service файл
sed "s|__APP_DIR__|$APP_DIR|g; s|__USER__|$USER|g" \
    "$APP_DIR/deploy/job-hunt.service" \
    | sudo tee /etc/systemd/system/${SERVICE_NAME}.service > /dev/null

sudo systemctl daemon-reload
sudo systemctl enable ${SERVICE_NAME}

echo ""
echo "=== Установка завершена ==="
echo ""
echo "Следующие шаги:"
echo "  1. Заполни .env:         nano $APP_DIR/.env"
echo "  2. Запусти бот:          sudo systemctl start ${SERVICE_NAME}"
echo "  3. Статус:               sudo systemctl status ${SERVICE_NAME}"
echo "  4. Логи в реальном времени: sudo journalctl -u ${SERVICE_NAME} -f"
