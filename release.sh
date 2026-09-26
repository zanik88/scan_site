#!/bin/bash
# ============================================
# Автоматический релиз проекта «Компонент-Эксперт»
# ============================================
# Использование:
#   ./release.sh 9.1.0
# ============================================

set -e

# --- Проверки ---
if [ -z "$1" ]; then
    echo "❌ Использование: $0 <версия>"
    echo "   Пример: $0 9.1.0"
    exit 1
fi

VERSION="$1"
TAG="v${VERSION}"
TODAY=$(date +"%Y-%m-%d")

# Проверить, что мы в git-репозитории
if [ ! -d ".git" ]; then
    echo "❌ Не git-репозиторий. Запустите из папки проекта."
    exit 1
fi

# Проверить, что рабочая копия чистая
if [ -n "$(git status --porcelain)" ]; then
    echo "⚠️  Есть незакоммиченные изменения:"
    git status --short
    echo ""
    read -p "Продолжить? Коммит будет включать все изменения (y/n): " confirm
    if [ "$confirm" != "y" ]; then
        echo "Отменено."
        exit 0
    fi
fi

# Проверить, что тег не существует
if git rev-parse "$TAG" >/dev/null 2>&1; then
    echo "❌ Тег $TAG уже существует!"
    exit 1
fi

echo "=================================================="
echo "📦 Релиз $TAG от $TODAY"
echo "=================================================="

# --- Спросить список изменений ---
echo ""
echo "Введите список изменений (по одному на строку)."
echo "Пустая строка — закончить ввод."
echo ""

CHANGES=""
while true; do
    read -p "  • " item
    if [ -z "$item" ]; then
        break
    fi
    # Экранирование кавычек
    item="${item//\"/\\\"}"
    CHANGES="${CHANGES}            \"${item}\",\n"
done

if [ -z "$CHANGES" ]; then
    echo "⚠️  Не введено ни одного изменения. Релиз отменён."
    exit 1
fi

# --- Обновить version.py ---
echo ""
echo "📝 Обновляю version.py..."

# Резервная копия
cp version.py version.py.bak

# Найти строку с "CHANGELOG = [" и вставить новую запись после неё
python3 - "$VERSION" "$TODAY" "$CHANGES" <<'PYEOF'
import sys
import re

version = sys.argv[1]
date = sys.argv[2]
changes_raw = sys.argv[3]

# Формируем строки изменений
changes_lines = [line.strip() for line in changes_raw.split("\\n") if line.strip()]
changes_block = "\n".join("            " + line.rstrip(",") + "," for line in changes_lines)

new_entry = f'''    {{
        "version": "{version}",
        "date": "{date}",
        "changes": [
{changes_block}
        ]
    }},
'''

with open("version.py", "r", encoding="utf-8") as f:
    content = f.read()

# Ищем CHANGELOG = [ и вставляем после [
marker = "CHANGELOG = [\n"
if marker not in content:
    print("❌ Не найден CHANGELOG в version.py")
    sys.exit(1)

content = content.replace(marker, marker + new_entry, 1)

# Обновляем VERSION_FALLBACK на новый номер
content = re.sub(
    r'VERSION_FALLBACK\s*=\s*"[^"]+"',
    f'VERSION_FALLBACK = "{version}"',
    content,
    count=1,
)

with open("version.py", "w", encoding="utf-8") as f:
    f.write(content)

print(f"✅ version.py обновлён до {version}")
PYEOF

# Проверка синтаксиса
if ! python3 -m py_compile version.py; then
    echo "❌ Ошибка синтаксиса! Восстанавливаю version.py..."
    mv version.py.bak version.py
    exit 1
fi

rm -f version.py.bak

# --- Git: add / commit / tag / push ---
echo ""
echo "📦 Коммит..."
git add -A

COMMIT_MSG="Release ${TAG}: $(echo "$CHANGES" | head -1 | sed 's/.*"\(.*\)".*/\1/' | cut -c1-50)"
git commit -m "$COMMIT_MSG" || {
    echo "⚠️  Нет изменений для коммита. Возможно, всё уже закоммичено."
}

echo ""
echo "🏷️  Ставлю тег ${TAG}..."
git tag -a "$TAG" -m "Release ${TAG}"

echo ""
echo "🚀 Пуш в GitHub..."
git push origin main
git push origin "$TAG"

echo ""
echo "=================================================="
echo "✅ Релиз ${TAG} успешно выпущен!"
echo "=================================================="
echo ""
echo "📌 Дальше на сервере выполните:"
echo ""
echo "   cd /opt/scan_site"
echo "   git pull origin main"
echo "   git fetch --tags"
echo "   docker compose down && docker compose up -d --build"
echo ""
