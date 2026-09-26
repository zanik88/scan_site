#!/usr/bin/env python3
"""Уменьшает TTL неудачных ИИ-ответов с 7 дней до 1 часа."""
import shutil, os, sys

MAIN = "main.py"
BAK = "main.py.bak_ttl_1h"

shutil.copy2(MAIN, BAK)
print(f"✅ Backup: {BAK}")

with open(MAIN, "r", encoding="utf-8") as f:
    content = f.read()

patched = []

# ============================================================
# 1. Заменить логику TTL в _get_ai_cache
# ============================================================
old1 = '''            ttl_days = 7 if cache.is_failure else 90
            age_days = (now - cache.created_at).days if cache.created_at else 0
            if age_days > ttl_days:'''

new1 = '''            # TTL: 1 час для неудачных, 90 дней для успешных
            ttl_seconds = 3600 if cache.is_failure else 90 * 86400
            age_seconds = (now - cache.created_at).total_seconds() if cache.created_at else 0
            if age_seconds > ttl_seconds:'''

if old1 in content:
    content = content.replace(old1, new1, 1)
    patched.append("TTL в _get_ai_cache: 7 дней → 1 час для неудачных")
else:
    print("⚠️ Якорь в _get_ai_cache не найден")

# ============================================================
# 2. Заменить логику TTL в cleanup_ai_cache
# ============================================================
old2 = '''        old_success = db.query(AILicenseCache).filter(
            AILicenseCache.is_failure == False,
            AILicenseCache.created_at < now - timedelta(days=90)
        ).delete()
        old_failure = db.query(AILicenseCache).filter(
            AILicenseCache.is_failure == True,
            AILicenseCache.created_at < now - timedelta(days=7)
        ).delete()'''

new2 = '''        old_success = db.query(AILicenseCache).filter(
            AILicenseCache.is_failure == False,
            AILicenseCache.created_at < now - timedelta(days=90)
        ).delete()
        old_failure = db.query(AILicenseCache).filter(
            AILicenseCache.is_failure == True,
            AILicenseCache.created_at < now - timedelta(hours=1)
        ).delete()'''

if old2 in content:
    content = content.replace(old2, new2, 1)
    patched.append("TTL в cleanup_ai_cache: 7 дней → 1 час")
else:
    print("⚠️ Якорь в cleanup_ai_cache не найден")

# ============================================================
# 3. Обновить текст в статистике админки (если есть)
# ============================================================
old3 = "Кэш хранит ответы GigaChat на 90 дней (или 7 дней для неудачных запросов)."
new3 = "Кэш хранит ответы GigaChat на 90 дней (или 1 час для неудачных запросов)."

if old3 in content:
    content = content.replace(old3, new3, 1)
    patched.append("Текст в админке обновлён")

# Записать
with open(MAIN, "w", encoding="utf-8") as f:
    f.write(content)

print(f"\n✅ Патчей применено: {len(patched)}")
for p in patched:
    print(f"   • {p}")

# Проверка синтаксиса
print("\n🔍 Проверка синтаксиса...")
if os.system("python3 -m py_compile main.py") == 0:
    print("✅ Синтаксис корректен")
    print("\n🎉 Готово! Дальше:")
    print("   ./release.sh 9.1.2")
else:
    print("❌ Ошибка! Восстанавливаем...")
    shutil.copy2(BAK, MAIN)
    sys.exit(1)
