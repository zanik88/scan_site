#!/bin/bash
# ============================================
# Резервное копирование БД "Компонент-Эксперт"
# Работает напрямую с файлом на хосте
# ============================================

set -e

PROJECT_DIR="$HOME/Рабочий стол/deep"
BACKUP_DIR="${PROJECT_DIR}/backups"
DB_FILE="${PROJECT_DIR}/data/saas_audit.db"
REPORTS_DIR="${PROJECT_DIR}/generated_reports"
DATE=$(date +"%Y-%m-%d_%H-%M-%S")
KEEP_DAYS=7

mkdir -p "${BACKUP_DIR}"

# --- Проверяем, что БД существует ---
if [ ! -f "${DB_FILE}" ]; then
    echo "[$(date)] ❌ БД не найдена: ${DB_FILE}"
    exit 1
fi

# --- Бэкап через sqlite3 (.backup — безопасно для работающей БД) ---
BACKUP_FILE="${BACKUP_DIR}/saas_audit_${DATE}.db"

if command -v sqlite3 >/dev/null 2>&1; then
    sqlite3 "${DB_FILE}" ".backup '${BACKUP_FILE}'"
else
    # Если sqlite3 нет — простое копирование
    cp "${DB_FILE}" "${BACKUP_FILE}"
fi

if [ -f "${BACKUP_FILE}" ]; then
    SIZE=$(du -h "${BACKUP_FILE}" | cut -f1)
    echo "[$(date)] ✅ Бэкап создан: ${BACKUP_FILE} (${SIZE})"
else
    echo "[$(date)] ❌ Бэкап не создан"
    exit 1
fi

# --- Архив Excel-отчётов ---
if [ -d "${REPORTS_DIR}" ] && [ "$(ls -A ${REPORTS_DIR} 2>/dev/null)" ]; then
    REPORTS_ARCHIVE="${BACKUP_DIR}/reports_${DATE}.tar.gz"
    tar -czf "${REPORTS_ARCHIVE}" -C "${PROJECT_DIR}" generated_reports 2>/dev/null
    echo "[$(date)] ✅ Архив отчётов: ${REPORTS_ARCHIVE}"
fi

# --- Ротация ---
find "${BACKUP_DIR}" -name "saas_audit_*.db" -type f -mtime +${KEEP_DAYS} -delete
find "${BACKUP_DIR}" -name "reports_*.tar.gz" -type f -mtime +${KEEP_DAYS} -delete
echo "[$(date)] 🧹 Ротация завершена (храним ${KEEP_DAYS} дней)"
echo "[$(date)] 📊 Всего: $(ls -1 ${BACKUP_DIR}/saas_audit_*.db 2>/dev/null | wc -l) БД"
echo "----------------------------------------"
