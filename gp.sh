#!/bin/bash
#set -euo pipefail

echo "==> Git pull..."
git pull

echo ""
echo "==> Установка зависимостей..."
.venv/bin/pip install -r requirements.txt -q

echo ""
echo "==> Перезапуск PM2 с обновлением env..."
pm2 reload ecosystem.config.js --update-env

echo ""
echo "==> Сохранение списка процессов PM2 (для автозапуска после ребута)..."
pm2 save

echo ""
echo "==> Статус процессов:"
pm2 status

echo ""
echo "Деплой завершён успешно."
