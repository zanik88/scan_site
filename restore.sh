#!/bin/bash
# ============================================
# Восстановление БД из бэкапа
# ============================================

set -e

PROJECT_DIR="$HOME/Рабочий стол/deep"
BACKUP_DIR="${PROJECT_DIR}/backups"
DB_FILE="${PROJECT_DIR}/data/saas_audit.db"

if [ -z "$1" ]; then
    echo "Использование: $0 <путь_к_бэкапу>"
    echo ""
    echo "Доступные бэкапы:"
    ls -lht "${BACKUP_DIR}"/saas_audit_*.db 2>/dev/null | head -10
    exit 1
fi

BACKUP_FILE="$1"

if [ ! -f "${BACKUP_FILE}" ]; then
    echo "❌ Файл ${BACKUP_FILE} не найден"
    exit 1
fi

echo "⚠️  Это перезапишет текущую БД ${DB_FILE}"
read -p "Продолжить? (yes/no): " confirm
if [ "${confirm}" != "yes" ]; then
    echo "Отменено"
    exit 0
fi

cd "${PROJECT_DIR}"

echo "🛑 Останавливаем контейнеры..."
docker compose down

if [ -f "${DB_FILE}" ]; then
    mv "${DB_FILE}" "${DB_FILE}.before_restore_$(date +%Y%m%d_%H%M%S)"
    echo "💾 Текущая БД сохранена"
fi

cp "${BACKUP_FILE}" "${DB_FILE}"
echo "✅ БД восстановлена"

echo "🚀 Запускаем контейнеры..."
docker compose up -d

echo "🎉 Готово!"
